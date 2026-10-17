#!/usr/bin/env python3
"""Update only super in an offline local VM, retaining its ART cache and keys."""
import argparse
import datetime
import fcntl
import hashlib
import json
import pathlib
import re
import os
import struct
import subprocess
import uuid
import zlib
from android_lp_state import stage_preserving_state
from debug_android_boot_vm import BASE, QEMU


def region_hash(path, start, length):
    h = hashlib.sha256()
    with path.open('rb') as inp:
        inp.seek(start)
        while length:
            data = inp.read(min(length, 4*1024*1024))
            assert data
            h.update(data)
            length -= len(data)
    return h.hexdigest()


def partitions(backing):
    with backing.open('rb') as inp:
        inp.seek(512)
        header = bytearray(inp.read(92))
        assert header[:8] == b'EFI PART'
        crc = struct.unpack_from('<I', header, 16)[0]
        struct.pack_into('<I', header, 16, 0)
        assert zlib.crc32(header) == crc
        entry_lba, count, stride, table_crc = struct.unpack_from('<QIII', header, 72)
        assert count == 128 and stride == 128
        inp.seek(entry_lba*512)
        table = inp.read(count*stride)
        assert zlib.crc32(table) == table_crc
    result = {}
    for i in range(count):
        entry = table[i*stride:(i+1)*stride]
        if entry[:16] == bytes(16):
            continue
        identity = str(uuid.UUID(bytes_le=entry[16:32]))
        first, last = struct.unpack_from('<QQ', entry, 32)
        name = entry[56:128].decode('utf-16le').rstrip('\0')
        result[name] = (first*512, (last-first+1)*512, identity)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name')
    parser.add_argument('--super-image', type=pathlib.Path, default=BASE/'dist/super_vm_debug.img')
    parser.add_argument('--manifest', type=pathlib.Path,
                        help='Explicit matching image manifest, e.g. native .work/fixed-super-manifest.json')
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9_-]{1,48}', args.name)
    work = BASE/'.work/android-boot-vm'
    lock = (work/'.disk.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    overlay = work/'overlays'/(args.name+'.qcow2')
    backing = work/'overlays'/(args.name+'-base.raw')
    assert overlay.is_file() and backing.is_file()
    assert not overlay.is_symlink() and not backing.is_symlink()
    manifest = json.loads((args.manifest or args.super_image.with_suffix('.manifest.json')).read_text())
    # qemu-img takes the same exclusive image lock as QEMU; an active guest
    # cannot be updated even if it was started outside our wrapper.
    subprocess.run([str(BASE/'.work/qemu-tools/qemu-img-launcher'),
                    str(QEMU.parent.parent/'UTM.app/Contents/Frameworks/qemu-img.framework/Versions/A/qemu-img'),
                    'commit', '-f', 'qcow2', str(overlay)], check=True)
    parts = partitions(backing)
    start, size, identity = parts['super']
    assert identity == '00000000-0000-4000-8000-000000000001'
    assert size == args.super_image.stat().st_size
    untouched = {name: region_hash(backing, at, length)
                 for name, (at, length, _) in parts.items() if name != 'super'}
    head_hash = region_hash(backing, 0, 1024*1024)
    tail_hash = region_hash(backing, backing.stat().st_size-1024*1024, 1024*1024)
    staged, installed, preserved = stage_preserving_state(
        args.super_image, backing, manifest, BASE/'.work', size, current_offset=start)
    changed = 0
    with staged.open('rb') as inp, backing.open('r+b', buffering=0) as out:
        offset = 0
        while chunk := inp.read(4*1024*1024):
            out.seek(start+offset)
            current = out.read(len(chunk))
            if chunk != current:
                out.seek(start+offset)
                assert out.write(chunk) == len(chunk)
                changed += len(chunk)
            offset += len(chunk)
        assert offset == size
        os.fsync(out.fileno())
    assert region_hash(backing, start, size) == region_hash(staged, 0, size)
    assert region_hash(backing, 0, 1024*1024) == head_hash
    assert region_hash(backing, backing.stat().st_size-1024*1024, 1024*1024) == tail_hash
    for name, digest in untouched.items():
        at, length, _ = parts[name]
        assert region_hash(backing, at, length) == digest, 'Changed unrelated VM partition: '+name
    staged.unlink()
    sidecar = overlay.with_suffix('.json')
    record = json.loads(sidecar.read_text())
    record.update(updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  super_source=str(args.super_image), super_partitions=installed,
                  untouched_partitions_sha256=untouched, preserved_raw_state=preserved)
    sidecar.write_text(json.dumps(record, indent=2)+'\n')
    print('VM_SUPER_UPDATE_PASS:', changed, 'bytes changed; GPT, userdata, metadata and raw state preserved')


if __name__ == '__main__':
    main()

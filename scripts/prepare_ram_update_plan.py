#!/usr/bin/env python3
"""Prepare a bounded LP update in currently unused super space, off-device."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
from android_lp_state import read_layout

SIZE = 8899264512
UUID = '00000000-0000-4000-8000-000000000001'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def prepare(prefix_path, images, output, protected_prefixes=(), archived_extents=()):
    output.mkdir(parents=True, exist_ok=True)
    prefix = prefix_path.read_bytes()
    assert len(prefix) == 1024*1024
    old = read_layout(prefix_path, SIZE)
    raw = bytearray(prefix[12288:12288+65536])
    hs = struct.unpack_from('<I', raw, 8)[0]
    po, pn, ps = struct.unpack_from('<III', raw, 80)
    eo, en, es = struct.unpack_from('<III', raw, 92)
    assert ps == 52 and es == 24
    active = [(a, a+n) for part in old.values() for a,n in part['extents']]
    occupied = list(active)
    history = []
    protected = []
    for index, source_prefix in enumerate(protected_prefixes):
        snapshot = read_layout(source_prefix, SIZE)
        for name, part in snapshot.items():
            history += [(name, a, a+n) for a, n in part['extents']]
        destination = output/('protected-prefix-'+str(index)+'.bin')
        shutil.copyfile(source_prefix, destination)
        protected.append({'file': destination.name, 'sha256': digest(destination)})
    archives = []
    released = set()
    for index, record in enumerate(archived_extents):
        name, start, size = record['partition'], record['offset'], record['bytes']
        assert name in ('vendor_a', 'system_ext_a')
        assert size > 0 and size % 4096 == 0 and start >= 1024*1024 and start % 4096 == 0
        assert start+size <= SIZE and (name, start, start+size) in history
        assert all(start >= end or start+size <= begin for begin, end in active), 'Cannot archive an active extent'
        assert all(start >= end or start+size <= begin for _,begin,end in released), 'Duplicate/overlapping archive'
        source = Path(record['source'])
        assert source.is_file() and not source.is_symlink() and source.stat().st_size == size
        assert digest(source) == record['sha256'], 'Host rollback archive differs'
        destination = output/('archived-'+str(index)+'-'+name+'.erofs')
        shutil.copyfile(source, destination); destination.chmod(0o600)
        assert digest(destination) == record['sha256']
        archives.append({'partition': name, 'offset': start, 'bytes': size,
                         'file': destination.name, 'sha256': record['sha256']})
        released.add((name, start, start+size))
    # Historical extents can be reused only when a complete byte-for-byte
    # rollback archive exists. Current active partitions always remain pinned.
    occupied += [(begin, end) for name, begin, end in history if (name,begin,end) not in released]
    occupied.sort()
    results = []
    for name, source in images.items():
        assert name in ('vendor_a', 'system_ext_a') and len(old[name]['extents']) == 1
        size = source.stat().st_size
        assert size > 0 and size % 4096 == 0
        cursor = 1024*1024
        for begin, end in occupied + [(SIZE, SIZE)]:
            cursor = (cursor+1048575)//1048576*1048576
            if cursor+size <= begin:
                break
            cursor = max(cursor, end)
        assert cursor+size <= SIZE
        occupied.append((cursor, cursor+size)); occupied.sort()
        entries = [hs+po+i*ps for i in range(pn) if bytes(raw[hs+po+i*ps:hs+po+i*ps+36]).split(b'\0')[0].decode() == name]
        assert len(entries) == 1
        first, count = struct.unpack_from('<II', raw, entries[0]+40)
        assert count == 1
        e = hs+eo+first*es
        struct.pack_into('<QIQI', raw, e, size//512, 0, cursor//512, 0)
        dst = output/(name+'.erofs')
        if source.resolve() != dst.resolve():
            shutil.copyfile(source, dst)
        dst.chmod(0o600)
        results.append({'partition': name, 'file': dst.name, 'offset': cursor, 'bytes': size, 'sha256': digest(dst)})
    ts = struct.unpack_from('<I', raw, 44)[0]
    raw[48:80] = hashlib.sha256(raw[hs:hs+ts]).digest()
    raw[12:44] = bytes(32)
    raw[12:44] = hashlib.sha256(raw[:hs]).digest()
    new_metadata = bytes(raw)*4
    (output/'metadata-new.bin').write_bytes(new_metadata)
    (output/'metadata-old-prefix.bin').write_bytes(prefix)
    plan = {'target_uuid': UUID, 'target_bytes': SIZE, 'images': results,
            'metadata_file': 'metadata-new.bin', 'metadata_sha256': hashlib.sha256(new_metadata).hexdigest(),
            'old_prefix_file': 'metadata-old-prefix.bin', 'old_prefix_sha256': hashlib.sha256(prefix).hexdigest(),
            'write_scope': ('unused or verified archived inactive extents plus four LP metadata copies inside super' if archives else 'unused extents plus four LP metadata copies inside super'),
            'old_payloads_preserved': not bool(archives), 'active_payloads_preserved': True,
            'archived_extents': archives, 'hardware_tested': False}
    plan['protected_prefixes'] = protected
    (output/'update-plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    return plan

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('prefix', type=Path)
    p.add_argument('vendor', type=Path)
    p.add_argument('system_ext', type=Path, nargs='?', help='Omit to update vendor only')
    p.add_argument('output', type=Path)
    p.add_argument('--protect', type=Path, action='append', default=[])
    p.add_argument('--archive-manifest', type=Path, help='Explicit inactive extent archives; each source must hash exactly before preparing a plan')
    a = p.parse_args()
    selected = {'vendor_a': a.vendor}
    if a.system_ext is not None:
        selected['system_ext_a'] = a.system_ext
    print(json.dumps(prepare(a.prefix, selected, a.output, a.protect, json.loads(a.archive_manifest.read_text()) if a.archive_manifest else ()), indent=2))

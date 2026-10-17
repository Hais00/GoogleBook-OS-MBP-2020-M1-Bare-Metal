#!/usr/bin/env python3
"""Install verified images into unused super extents, commit LP metadata last.

Runs in the RAM bootstrap, before Android mounts any logical partition. It
never opens a GPT or macOS partition for writing. The original image extents
remain intact so restoring the saved metadata rolls back this update. Historical
inactive extents may be reused only after validating an exact rollback archive
against both host bytes and the on-device extent before any write.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from android_lp_state import read_layout

SUPER_UUID = '00000000-0000-4000-8000-000000000001'
SUPER_BYTES = 8899264512

def hash_region(stream, offset, size):
    stream.seek(offset)
    result = hashlib.sha256()
    while size:
        data = stream.read(min(size, 1024*1024))
        if not data:
            raise ValueError('Short read')
        result.update(data)
        size -= len(data)
    return result.hexdigest()

def target_device():
    data = json.loads(subprocess.check_output(['lsblk', '-J', '-b', '-p', '-o', 'PATH,SIZE,PARTUUID,TYPE']))
    found = []
    def scan(items):
        for entry in items:
            if (entry.get('partuuid') or '').lower() == SUPER_UUID:
                assert entry['type'] == 'part' and int(entry['size']) == SUPER_BYTES
                found.append(Path(entry['path']))
            scan(entry.get('children', []))
    scan(data['blockdevices'])
    assert len(found) == 1, 'Target super UUID must identify exactly one partition'
    assert stat.S_ISBLK(found[0].stat().st_mode)
    model = Path('/proc/device-tree/model').read_bytes().rstrip(b'\0').decode()
    assert 'Apple' in model and ('MacBook Pro' in model or 'J293' in model), model
    return found[0]

def validate(plan, root, device):
    assert plan['target_uuid'] == SUPER_UUID and plan['target_bytes'] == SUPER_BYTES
    names = [item['partition'] for item in plan['images']]
    assert names and len(set(names)) == len(names)
    assert set(names) <= {'vendor_a', 'system_ext_a'}, 'Unapproved partition role'
    old = read_layout(device, SUPER_BYTES)
    active = [(a, a+n) for part in old.values() for a, n in part['extents']]
    occupied = list(active)
    history = []
    for record in plan.get('protected_prefixes', []):
        snapshot_path = root/record['file']
        assert snapshot_path.parent == root and not snapshot_path.is_symlink()
        assert hashlib.sha256(snapshot_path.read_bytes()).hexdigest() == record['sha256']
        snapshot = read_layout(snapshot_path, SUPER_BYTES)
        history += [(name, a, a+n) for name, part in snapshot.items() for a,n in part['extents']]
    released = set()
    archives = plan.get('archived_extents', [])
    if archives:
        assert plan.get('old_payloads_preserved') is False, 'Archived history must be disclosed'
        assert plan.get('active_payloads_preserved') is True
    for record in archives:
        name, start, size = record['partition'], record['offset'], record['bytes']
        assert name in ('vendor_a', 'system_ext_a')
        assert size > 0 and size % 4096 == 0 and start % 4096 == 0 and start >= 1024*1024
        assert start+size <= SUPER_BYTES and (name, start, start+size) in history, 'Archive is not an exact protected historical extent'
        assert all(start >= end or start+size <= begin for begin,end in active), 'Archive overlaps current active data'
        assert all(start >= end or start+size <= begin for _,begin,end in released), 'Overlapping archives'
        backup = root/record['file']
        assert backup.parent == root and backup.is_file() and not backup.is_symlink()
        assert backup.stat().st_size == size
        print('M1_ARCHIVE_VERIFY_BEGIN', name, start, size, flush=True)
        with backup.open('rb') as source:
            assert hash_region(source, 0, size) == record['sha256'], 'Rollback archive digest differs'
        with device.open('rb', buffering=0) as disk:
            assert hash_region(disk, start, size) == record['sha256'], 'Inactive on-device extent differs from its archive'
        print('M1_ARCHIVE_VERIFY_PASS', name, record['sha256'], flush=True)
        released.add((name,start,start+size))
    occupied += [(begin,end) for name,begin,end in history if (name,begin,end) not in released]
    new_ranges = []
    for item in plan['images']:
        source = root/item['file']
        assert source.parent == root and source.is_file() and not source.is_symlink()
        start, size = item['offset'], item['bytes']
        assert source.stat().st_size == size and size > 0 and size % 4096 == 0
        assert start % (1024*1024) == 0 and start >= 1024*1024 and start+size <= SUPER_BYTES
        assert all(start >= end or start+size <= begin for begin, end in occupied), 'Write overlaps an existing partition'
        assert all(start >= end or start+size <= begin for begin, end in new_ranges)
        new_ranges.append((start, start+size))
        print('M1_IMAGE_VALIDATE_BEGIN', item['partition'], size, flush=True)
        with source.open('rb') as stream:
            assert hash_region(stream, 0, size) == item['sha256'], 'Image digest differs'
        print('M1_IMAGE_VALIDATE_PASS', item['partition'], item['sha256'], flush=True)
    metadata = root/plan['metadata_file']
    assert metadata.parent == root and metadata.stat().st_size == 4*65536
    assert hashlib.sha256(metadata.read_bytes()).hexdigest() == plan['metadata_sha256']
    with device.open('rb', buffering=0) as stream:
        assert hash_region(stream, 0, 1024*1024) == plan['old_prefix_sha256'], 'On-disk metadata differs from backup'
    # Validate the complete proposed layout independently of its writer.
    prefix = bytearray((root/plan['old_prefix_file']).read_bytes())
    assert len(prefix) == 1024*1024 and hashlib.sha256(prefix).hexdigest() == plan['old_prefix_sha256']
    prefix[12288:12288+4*65536] = metadata.read_bytes()
    temporary = Path('/tmp/m1-new-super-prefix.bin')
    temporary.write_bytes(prefix)
    new = read_layout(temporary, SUPER_BYTES)
    for name, part in old.items():
        image = next((i for i in plan['images'] if i['partition'] == name), None)
        if image:
            assert new[name]['extents'] == [(image['offset'], image['bytes'])]
            assert new[name]['attributes'] == part['attributes']
        else:
            assert new[name] == part, 'Unexpected change to '+name
    assert set(new) == set(old)
    return metadata

def apply(plan, root, device, metadata):
    with device.open('r+b', buffering=0) as disk:
        for item in plan['images']:
            print('M1_IMAGE_WRITE_BEGIN', item['partition'], item['bytes'], flush=True)
            disk.seek(item['offset'])
            written = 0
            report_at = 64*1024*1024
            with (root/item['file']).open('rb') as source:
                while data := source.read(1024*1024):
                    assert disk.write(data) == len(data), 'Short write'
                    written += len(data)
                    if written >= report_at:
                        print('M1_IMAGE_WRITE_PROGRESS', item['partition'], written, item['bytes'], flush=True)
                        report_at += 64*1024*1024
            os.fsync(disk.fileno())
            assert hash_region(disk, item['offset'], item['bytes']) == item['sha256'], 'Readback differs'
            print('M1_IMAGE_READBACK_PASS', item['partition'], item['sha256'], flush=True)
        # Commit the first primary slot last; current active payloads are kept.
        # Any overwritten historical extent has already been verified against
        # its complete rollback archive before this writable descriptor opens.
        blob = metadata.read_bytes()
        for index in (2, 3, 1, 0):
            block = blob[index*65536:(index+1)*65536]
            disk.seek(12288+index*65536)
            assert disk.write(block) == len(block)
            os.fsync(disk.fileno())
            disk.seek(12288+index*65536)
            assert disk.read(len(block)) == block
        print('M1_LP_COMMIT_PASS', flush=True)
    layout = read_layout(device, SUPER_BYTES)
    for item in plan['images']:
        assert layout[item['partition']]['extents'] == [(item['offset'], item['bytes'])]
    print('M1_RAM_UPDATE_PASS', flush=True)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('plan', type=Path)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    plan = json.loads(args.plan.read_text())
    root = args.plan.parent.resolve()
    device = target_device()
    metadata = validate(plan, root, device)
    print('M1_RAM_UPDATE_PREFLIGHT_PASS', device, flush=True)
    if args.apply:
        apply(plan, root, device, metadata)

if __name__ == '__main__':
    main()

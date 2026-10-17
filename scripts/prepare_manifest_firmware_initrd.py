#!/usr/bin/env python3
"""Restore the exact original firmware bundle in isolated future artifacts."""
import gzip
import hashlib
import json
from pathlib import Path
import stat
from project_paths import BASE, WORK, LARGE_WORK
from prepare_m1_install import entries
from firmware_manifest import repair_firmware_entries
from build_ram_bootstrap import pack
from archive_android_stage import label


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unpack(data):
    rows = list(entries(gzip.decompress(data)))
    result = {n: (n, v, d) for n, v, d in rows}
    assert len(result) == len(rows)
    return result


def main():
    original_path = BASE/'artifacts/GoogleBook-USB-Debug/initrd.img'
    base_path = LARGE_WORK/'ram-bootstrap/android-initrd.img'
    original_data, base_data = original_path.read_bytes(), base_path.read_bytes()
    original, base = unpack(original_data), unpack(base_data)
    repaired, report = repair_firmware_entries(original)
    assert repaired['lib/firmware/.vendorfw.manifest'][2] == base['lib/firmware/.vendorfw.manifest'][2]
    # Keep all already-qualified initrd entries, signed regdb and overlays.
    # Restore only names lost from that initrd; reverify the whole manifest.
    combined = dict(repaired)
    combined.update(base)
    combined, _ = repair_firmware_entries(combined)
    raw = pack(list(combined.values()))
    data = gzip.compress(raw, compresslevel=6, mtime=0)
    actual = unpack(data)
    assert set(actual) == set(combined) and set(base) <= set(actual)
    for name, (_, values, payload) in base.items():
        if not name.startswith('lib/firmware/'):
            assert actual[name][1][1:5] == values[1:5] and actual[name][2] == payload, name
    assert actual['init'][2] == base['init'][2]
    repair_firmware_entries(actual)
    out = LARGE_WORK/'android-initrd-firmware-restored'
    out.mkdir(exist_ok=False)
    (out/'initrd.img').write_bytes(data)
    note = {'source_original_initrd': str(original_path), 'source_original_initrd_sha256': sha(original_data),
        'source_base_initrd': str(base_path), 'source_base_initrd_sha256': sha(base_data),
        'initrd_sha256': sha(data), 'compressed_bytes': len(data), 'uncompressed_bytes': len(raw),
        'entries': len(actual), 'newly_present_paths': sorted(set(actual)-set(base)),
        'firmware_repair': report, 'original_manifest_unchanged': True,
        'original_firmware_versions_preserved': True, 'nonfirmware_entries_unchanged': True,
        'frozen_kernel19_initrd_unchanged': sha(base_path.read_bytes()) == sha(base_data),
        'physical_installation_performed': False, 'hardware_compatibility_verified': False}
    (out/'manifest.json').write_text(json.dumps(note, indent=2)+'\n')
    # The future vendor clone must offer the same complete original dataset to
    # later firmware reloads. Preflight every path and label before writing.
    stage = WORK/'vendor-linux-cleanup-stage'
    records = []
    for name, (_, _, payload) in sorted(repaired.items()):
        if not name.startswith('lib/firmware/') or name == 'lib/firmware/.vendorfw.manifest':
            continue
        if stat.S_IFMT(repaired[name][1][1]) != stat.S_IFREG:
            continue
        target = stage/'firmware'/name.removeprefix('lib/firmware/')
        assert target.is_file() and not target.is_symlink() and target.stat().st_nlink == 1, target
        context = label(target)
        assert context.rstrip(b'\0') == b'u:object_r:vendor_firmware_file:s0', target
        before = target.stat()
        records.append((target, payload, context, (before.st_uid, before.st_gid, before.st_mode)))
    changed = []
    for target, payload, context, metadata in records:
        old_sha, new_sha = sha(target.read_bytes()), sha(payload)
        if old_sha != new_sha:
            target.write_bytes(payload)
            changed.append({'path': str(target.relative_to(stage)), 'before_sha256': old_sha,
                            'after_sha256': new_sha})
        current = target.stat()
        assert sha(target.read_bytes()) == new_sha and label(target) == context
        assert metadata == (current.st_uid, current.st_gid, current.st_mode)
    (WORK/'firmware-manifest-vendor-stage.json').write_text(json.dumps({
        'stage': str(stage), 'verified_members': len(records), 'changed': changed,
        'source_manifest': str(out/'manifest.json'), 'original_payloads_hash_verified': True,
        'ownership_modes_labels_preserved': True, 'physical_installation_performed': False}, indent=2)+'\n')
    for path in [WORK/'wifi-firmware-candidate/provenance.json',
                 LARGE_WORK/'android-initrd-wifi-candidate/manifest.json']:
        if path.exists():
            old = json.loads(path.read_text())
            old['superseded_by'] = str(out/'manifest.json')
            old['reason'] = 'Original FILE/LINK manifest fully recovers provided firmware without a version update.'
            path.write_text(json.dumps(old, indent=2)+'\n')
    print('ORIGINAL_FIRMWARE_MANIFEST_RESTORE_PASS',
          'recovered='+str(len(report['repaired_members'])), 'vendor_verified='+str(len(records)),
          'vendor_changed='+str(len(changed)), 'initrd_bytes='+str(len(data)))


if __name__ == '__main__':
    main()

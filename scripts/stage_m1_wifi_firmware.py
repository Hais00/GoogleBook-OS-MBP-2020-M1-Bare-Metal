#!/usr/bin/env python3
"""Stage the verified Asahi-named Wi-Fi bundle in the future vendor clone."""
import hashlib
import json
from project_paths import WORK
from archive_android_stage import label


def main():
    candidate = WORK/'wifi-firmware-candidate'
    note = json.loads((candidate/'provenance.json').read_text())
    assert not note.get('superseded_by'), 'Use the complete original manifest restoration instead'
    assert note['board_type'] == 'apple,honshu' and not note['generic_aliases_added']
    stage = WORK/'vendor-linux-cleanup-stage'
    changed = []
    for item in note['firmware']:
        name = item['name']
        assert name.startswith('brcm/brcmfmac4378b1-pcie.apple,honshu') and '/' not in name[5:]
        data = (candidate/'lib/firmware'/name).read_bytes()
        assert len(data) > 0 and hashlib.sha256(data).hexdigest() == item['sha256']
        dest = stage/'firmware'/name
        assert dest.is_file() and not dest.is_symlink() and dest.stat().st_nlink == 1
        before = dest.stat()
        context = label(dest)
        assert context.rstrip(b'\0') == b'u:object_r:vendor_firmware_file:s0'
        old_sha = hashlib.sha256(dest.read_bytes()).hexdigest()
        # Retain the existing inode, security xattrs, owner and mode.
        dest.write_bytes(data)
        after = dest.stat()
        assert (before.st_uid, before.st_gid, before.st_mode) == (
            after.st_uid, after.st_gid, after.st_mode)
        assert label(dest) == context
        assert hashlib.sha256(dest.read_bytes()).hexdigest() == item['sha256']
        changed.append({'path': str(dest.relative_to(stage)), 'before_sha256': old_sha,
                        'after_sha256': item['sha256'], 'security_label_preserved': True})
    (WORK/'wifi-firmware-vendor-stage.json').write_text(json.dumps({
        'stage': str(stage), 'files': changed, 'source': str(candidate/'provenance.json'),
        'physical_installation_performed': False, 'hardware_compatibility_verified': False,
        'frozen_vendor_generation7_changed': False}, indent=2)+'\n')
    print('M1_WIFI_FIRMWARE_STAGED_FUTURE_VENDOR_ONLY', len(changed))


if __name__ == '__main__':
    main()

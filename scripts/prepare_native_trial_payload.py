#!/usr/bin/env python3
"""Assemble the exact native-graphics trial payload, without contacting hardware."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import argparse
from project_paths import BASE, WORK, LARGE_WORK
from boot_config import BOOT_ARGS

MAINT = Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance')

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap-directory', type=Path, default=LARGE_WORK/'ram-bootstrap')
    parser.add_argument('--kernel-version', type=int, default=14)
    parser.add_argument('--direct-android', action='store_true',
                        help='Boot the validated Android initrd without the RAM image installer')
    parser.add_argument('--android-initrd', type=Path,
                        help='Direct boot of a manifest-verified original-firmware restoration')
    parser.add_argument('--owner-inventory-initrd', type=Path,
                        help='Verified read-only Linux census followed by that unchanged Android initrd')
    parser.add_argument('--run-directory', type=Path)
    options = parser.parse_args()
    assert not options.android_initrd or options.direct_android
    assert not options.owner_inventory_initrd or (options.direct_android and options.android_initrd)
    boot_mode = 'direct-android' if options.direct_android else 'ram-installer'
    version = options.kernel_version
    kernel = LARGE_WORK/('kernel'+str(version))
    run = options.run_directory or LARGE_WORK/('trial-native-egl-kernel'+str(version))
    assert not (run/'guest.bin').exists(), 'Refusing to replace an existing trial payload'
    receipt_root = kernel if (kernel/'clean-kernel-build.json').exists() else WORK
    build = json.loads((receipt_root/'clean-kernel-build.json').read_text())
    for name, record in build['files'].items():
        assert digest(kernel/name) == record['sha256']
    profile = json.loads((receipt_root/'clean-kernel-profile.json').read_text())
    assert profile['qualcomm_enabled'] == []
    assert digest(kernel/'config') == profile['config_sha256']
    dt = (kernel/'t8103-j293.dtb').read_bytes()
    for compat in (b'apple,agx-t8103\0', b'apple,display-subsystem\0', b'apple,dcp\0'):
        assert compat in dt
    assert struct.unpack_from('>I', dt)[0] == 0xd00dfeed
    image = (kernel/'Image').read_bytes()
    assert image[56:60] == b'ARM\x64'
    initrd = options.bootstrap_directory/'initrd.img'
    ram_manifest = json.loads((initrd.parent/'manifest.json').read_text())
    assert digest(initrd) == ram_manifest['initrd_sha256']
    if options.direct_android:
        initrd = initrd.parent/'android-initrd.img'
        assert digest(initrd) == ram_manifest['android_initrd_sha256']
        from prepare_m1_install import entries
        unpacked = gzip.decompress(initrd.read_bytes())
        members = {name: (values, content) for name, values, content in entries(unpacked)}
        assert 'init' in members and members['init'][1]
        if options.android_initrd:
            from firmware_manifest import repair_firmware_entries
            selected = options.android_initrd
            selected_manifest = json.loads((selected.parent/'manifest.json').read_text())
            assert digest(selected) == selected_manifest['initrd_sha256']
            unpacked = gzip.decompress(selected.read_bytes())
            selected_members = {n: (v, d) for n, v, d in entries(unpacked)}
            manifest_name = 'lib/firmware/.vendorfw.manifest'
            assert selected_members[manifest_name][1] == members[manifest_name][1]
            allowed = {'lib/firmware/'+line.split()[1]
                       for line in members[manifest_name][1].decode().splitlines()}
            # Every modification must name an original manifest member. Keep
            # Android code, permissions and signed regdb byte-for-byte intact.
            for name in set(members) | set(selected_members):
                old = members.get(name)
                new = selected_members.get(name)
                if name not in allowed:
                    assert old and new and old[0][1:5] == new[0][1:5] and old[1] == new[1], name
            repaired, report = repair_firmware_entries(
                {n: (n, v, d) for n, (v, d) in selected_members.items()})
            assert not report['repaired_members'], 'Candidate must already contain all verified firmware bytes'
            initrd, members = selected, selected_members
            ram_manifest = dict(selected_manifest, source_ram_bootstrap_manifest=ram_manifest)
        ram_manifest = dict(ram_manifest, initrd_sha256=digest(initrd),
                            compressed_bytes=initrd.stat().st_size,
                            uncompressed_bytes=len(unpacked), entries=len(members),
                            boot_mode='direct-android', ram_installer_included=False)
    if options.owner_inventory_initrd:
        selected = options.owner_inventory_initrd
        owner = json.loads((selected.parent/'manifest.json').read_text())
        assert owner['schema'] in ('googlebook-preboot-owner.v1', 'googlebook-preboot-owner.v2-minimal')
        assert not owner['ram_installer_included'] and not owner['wrapper_block_device_open_or_mount']
        assert digest(selected) == owner['initrd_sha256']
        assert digest(initrd) == owner['android_initrd_sha256']
        om = {n: (v, d) for n, v, d in entries(gzip.decompress(selected.read_bytes()))}
        if owner['schema'] == 'googlebook-preboot-owner.v2-minimal':
            assert owner['restored_members'] == {
                'init': 'gos-owner/original-init',
                'dev/console': 'gos-owner/original-dev-console',
                'dev/null': 'gos-owner/original-dev-null'}
            for name, (values, content) in members.items():
                actual = owner['restored_members'].get(name, name)
                assert om[actual][0][1:5] == values[1:5] and om[actual][1] == content, name
        else:
            assert hashlib.sha256(om['android-initrd.img'][1]).hexdigest() == digest(initrd)
        assert hashlib.sha256(om['init'][1]).hexdigest() == owner['init_sha256']
        assert hashlib.sha256(om[owner.get('probe_member', 'alsa-owner-inventory')][1]).hexdigest() == owner['owner_probe_sha256']
        assert 'm1_ram_image_update.py' not in om and 'android_lp_state.py' not in om
        for name, (_, content) in members.items():
            if name.startswith('lib/firmware/'):
                assert om[name][1] == content, name
        initrd = selected
        boot_mode = 'preboot-owner-inventory-then-android'
        ram_manifest = dict(owner, android_manifest=ram_manifest, boot_mode=boot_mode)
    boot = MAINT/'artifacts/m1n1.bin'
    assert digest(boot) == '2946af402a4766167ea16f266860ce648d0751feacd9bb401dd1ea2889a4da69'
    data = bytearray(boot.read_bytes())
    data += ('chosen.bootargs='+BOOT_ARGS+'\n').encode()
    data += b'chosen.asahi,efi-system-partition=00000000-0000-4000-8000-000000000003\n'
    data += dt
    data += gzip.compress(image, compresslevel=6, mtime=0)
    data += b'm1n1_initramfs'+initrd.stat().st_size.to_bytes(4,'little')+initrd.read_bytes()
    transport_size = len(gzip.compress(data, compresslevel=1))
    assert transport_size <= 120*1024*1024, 'Payload exceeds the pinned proxy client 128MiB heap (8MiB reserved)'
    run.mkdir(exist_ok=True)
    (run/'guest.bin').write_bytes(data)
    (run/'bootargs.txt').write_text(BOOT_ARGS+'\n')
    (run/'payload.json').write_text(json.dumps({'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
        'transport_compressed_bytes': transport_size, 'transport_heap_margin_bytes': 8*1024*1024,
        'kernel': build, 'initrd': ram_manifest, 'hardware_verified':False, 'bootargs':BOOT_ARGS,
        'boot_mode': boot_mode},indent=2)+'\n')
    print(run/'guest.bin', len(data))

if __name__ == '__main__':
    main()

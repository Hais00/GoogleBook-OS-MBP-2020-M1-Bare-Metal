#!/usr/bin/env python3
"""Install the validated payload on the two explicitly identified Android partitions."""
import datetime
import argparse
import gzip
import hashlib
import json
import os
import pathlib
import plistlib
import shutil
import struct
import subprocess
import tempfile
from boot_config import BOOT_ARGS
from android_lp_state import stage_preserving_state

BASE = pathlib.Path(__file__).resolve().parents[1]
EXPECTED = {"disk0s7": "00000000-0000-4000-8000-000000000002",
            "disk0s8": "00000000-0000-4000-8000-000000000001"}

def info(dev):
    result = plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", dev]))
    assert result["DiskUUID"] == EXPECTED[dev], (dev, "partition identity changed")
    return result

def digest(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for b in iter(lambda: f.read(4*1024*1024), b""):
            h.update(b)
    return h.hexdigest()


def backup_super(device, size, directory, seed=None):
    """Read-only, sparse full backup of the previous physical Android super."""
    path = directory/'super-before.img'
    source_hash = hashlib.sha256()
    if seed is not None:
        assert seed.is_file() and seed.stat().st_size == size
        subprocess.run(['/bin/cp', '-c', str(seed), str(path)], check=True)
    with open(device, 'rb', buffering=0) as inp, path.open('r+b' if seed else 'xb') as out:
        path.chmod(0o600)
        remaining = size
        while remaining:
            data = inp.read(min(4*1024*1024, remaining))
            assert data and len(data) % 4096 == 0
            source_hash.update(data)
            if seed is not None:
                at = out.tell()
                if out.read(len(data)) != data:
                    out.seek(at)
                    assert out.write(data) == len(data)
            elif any(data):
                assert out.write(data) == len(data)
            else:
                out.seek(len(data), os.SEEK_CUR)
            remaining -= len(data)
        out.truncate(size)
        out.flush()
        os.fsync(out.fileno())
    assert digest(path) == source_hash.hexdigest(), 'Backup failed readback verification'
    return {'path': str(path), 'bytes': size, 'sha256': source_hash.hexdigest()}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--boot-only', action='store_true', help='Update EFI boot files without rewriting Android super')
    parser.add_argument('--hardware-bringup', action='store_true',
                        help='Explicit diagnostic hardware install before a completed QEMU desktop boot; retain all other checks')
    parser.add_argument('--backup-seed', type=pathlib.Path,
                        help='Clone a previous super template to save backup space; every physical byte is still compared and backup readback verified')
    args = parser.parse_args()
    assert os.geteuid() == 0, "Run with sudo"
    super_image = BASE / "dist/super_m1_fixed.img"
    manifest = json.loads((BASE / ".work/fixed-super-manifest.json").read_text())
    assert {p["partition"] for p in manifest} == {"system_a", "vendor_a", "system_ext_a", "misc", "desktop_security_storage", "desktop_security_persist"}
    repair = json.loads((BASE/'.work/system-m1-repair-policy.json').read_text())
    assert {m['method'] for m in repair['disabled_lifecycle_methods']} == {'onStart', 'onBootPhase'}
    assert repair['erofs_full_integrity_check_passed']
    assert repair['image_sha256'] == next(p['sha256'] for p in manifest if p['partition'] == 'system_a')
    labels = json.loads((BASE / '.work/vendor-vintf-label-validation.json').read_text())
    assert labels['board_profile'] == 'm1', 'Refusing a VM graphics profile on physical hardware'
    assert not labels['drm_trace_enabled'], 'Use the normal HWC imports for physical installation'
    assert labels['vendor_image_sha256'] == next(p for p in manifest if p['partition'] == 'vendor_a')['sha256']
    assert labels['disabled_init_files_outside_parsed_directory']
    assert labels['disabled_vintf_fragments_outside_manifest_directory']
    assert labels['all_drm_card_and_render_nodes_gpu_device']
    graphics = json.loads((BASE/'.work/graphics-selinux-validation.json').read_text())
    assert graphics['android_selinux_enforcing']
    assert graphics['actual_android_label_matcher_passed'] and graphics['actual_loaded_policy_access_checks_passed']
    for name in ['vendor_a', 'system_ext_a']:
        assert graphics['partitions_sha256'][name] == next(p['sha256'] for p in manifest if p['partition'] == name)
    android_boot = None
    if args.hardware_bringup:
        print('Diagnostic hardware bring-up requested: full QEMU Android boot is NOT validated.', flush=True)
    else:
        android_boot = json.loads((BASE/'.work/full-android-boot-validation.json').read_text())
        assert android_boot['sys_boot_completed'] == '1'
        assert android_boot['system_server_stable'] and android_boot['surfaceflinger_stable']
        assert android_boot['display_frame_verified']
        for name in ['system_a', 'system_ext_a']:
            assert android_boot['partitions_sha256'][name] == next(
                p['sha256'] for p in manifest if p['partition'] == name), 'Untested userspace image: '+name
    target = info("disk0s8")
    esp = info("disk0s7")
    assert target["Size"] == super_image.stat().st_size
    assert not target.get("MountPoint")
    assert target["Content"] == "Microsoft Basic Data"
    assert esp["Content"] == "EFI" and esp.get("MountPoint")
    mount = pathlib.Path(esp["MountPoint"])
    with open("/dev/rdisk0s7", "rb", buffering=0) as f:
        b = f.read(4096)
    assert struct.unpack_from("<I", b, 67)[0] == 0x0d870d88
    disk_size = plistlib.loads(subprocess.check_output(['diskutil','info','-plist','disk0']))['Size']
    with open("/dev/rdisk0", "rb", buffering=0) as f:
        before_gpt = f.read(24576)
        f.seek(disk_size-24576)
        before_gpt_backup = f.read(24576)
    assert before_gpt == (BASE / ".work/backup-before-repair/gpt-primary.bin").read_bytes()
    # All source files are validated before the first physical disk write.
    boot = BASE / "apple_silicon_boot"
    relative = ["Image", "initrd.img", "t8103-j293.dtb", "EFI/BOOT/BOOTAA64.EFI",
                "EFI/BOOT/grub.cfg", "EFI/debian/grub.cfg", "boot/grub/grub.cfg", "extlinux/extlinux.conf",
                "BOOT_INSTRUCTIONS.md", "CONFIGURAZIONE_E_MODIFICHE_M1.md"]
    expected_files = {rel: digest(boot / rel) for rel in relative}
    assert graphics['kernel_sha256'] == expected_files['Image']
    if android_boot is not None:
        assert android_boot['kernel_sha256'] == expected_files['Image'], 'Full Android boot used a different kernel'
    image = (boot / 'Image').read_bytes()
    start = image.index(b'IKCFG_ST')
    end = image.index(b'IKCFG_ED', start)
    config = gzip.decompress(image[start+8:end]).decode()
    for required in ['SECURITY', 'SECURITYFS', 'SECURITY_NETWORK', 'SECURITY_SELINUX',
                     'AUDIT', 'ANDROID_BINDER_IPC', 'ANDROID_BINDERFS', 'DRM_APPLE', 'DRM_ASAHI',
                     'ARM64_16K_PAGES', 'EROFS_FS', 'EROFS_FS_SECURITY', 'EXT4_FS_SECURITY', 'TMPFS_XATTR',
                     'PRINTK', 'SERIAL_SAMSUNG', 'SERIAL_SAMSUNG_CONSOLE', 'SERIAL_EARLYCON',
                     'CPUSETS', 'CPUSETS_V1', 'QUOTA', 'QFMT_V2',
                     'FS_ENCRYPTION', 'FS_VERITY', 'UNICODE', 'KVM',
                     'VSOCKETS', 'VIRTIO_VSOCKETS', 'VHOST_VSOCK']:
        assert 'CONFIG_' + required + '=y\n' in config, 'Missing Android kernel requirement: ' + required
    for rel in ['EFI/BOOT/grub.cfg', 'boot/grub/grub.cfg', 'extlinux/extlinux.conf']:
        assert BOOT_ARGS in (boot / rel).read_text(), 'Boot arguments differ: ' + rel
    lsm = next(l for l in config.splitlines() if l.startswith('CONFIG_LSM='))
    assert 'selinux' in lsm.split('=',1)[1].strip('"').split(','), 'SELinux is compiled but not activated'
    smoke = json.loads((BASE / '.work/selinux-smoke-results.json').read_text())
    assert smoke['kernel_sha256'] == expected_files['Image']
    assert smoke['enforcing_mount_test_passed'] and smoke['original_android_policy_load_passed']
    assert smoke['cpuset_v1_mount_and_task_test_passed'] and smoke['userspace_kmsg_burst_test_passed']
    assert smoke['ext4_quota_mount_and_android_features_test_passed']
    assert (BASE / ".work/backup-before-repair/efi-gos.img").stat().st_size == esp["Size"]
    # Keep a complete rollback of current super and the actual installed EFI
    # files before opening either physical partition for writing.
    backup = pathlib.Path(tempfile.mkdtemp(prefix='backup-before-hardware-', dir=BASE/'.work'))
    backup.chmod(0o700)
    (backup/'gpt-primary.bin').write_bytes(before_gpt)
    (backup/'gpt-backup.bin').write_bytes(before_gpt_backup)
    shutil.copy2(BASE/'.work/installed-manifest.json', backup/'installed-manifest.json')
    for rel in relative:
        current = mount/rel
        if current.is_file():
            saved = backup/'efi-files'/rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current, saved)
            assert digest(saved) == digest(current)
    saved_super = None
    if not args.boot_only:
        assert shutil.disk_usage(BASE).free > target['Size']+1024*1024*1024, 'Insufficient room for rollback backup'
        print('Backing up existing physical super before installation...', flush=True)
        saved_super = backup_super('/dev/rdisk0s8', target['Size'], backup, args.backup_seed)
    backup_info = {'super': saved_super, 'efi_files_sha256': {
        rel: digest(backup/'efi-files'/rel) for rel in relative if (backup/'efi-files'/rel).is_file()},
        'gpt_primary_sha256': hashlib.sha256(before_gpt).hexdigest(),
        'gpt_backup_sha256': hashlib.sha256(before_gpt_backup).hexdigest()}
    (backup/'backup-manifest.json').write_text(json.dumps(backup_info, indent=2)+'\n')
    print('Rollback backup verified:', backup, flush=True)
    if args.boot_only:
        previous = json.loads((BASE / '.work/installed-manifest.json').read_text())
        assert previous['targets'] == EXPECTED
        expected_super = previous['super_sha256']
        installed_parts = previous.get('super_partitions', [])
        preserved = ['all existing super contents (boot-only update)']
        print('Boot-only update: Android super is preserved.', flush=True)
    else:
        staged, installed_parts, preserved = stage_preserving_state(
            super_image, '/dev/rdisk0s8', manifest, BASE/'.work', target['Size'])
        expected_super = digest(staged)
        print("Writing validated Android super image to disk0s8...", flush=True)
        with staged.open("rb") as inp, open("/dev/rdisk0s8", "r+b", buffering=0) as out:
            written = 0
            for chunk in iter(lambda: inp.read(4*1024*1024), b""):
                assert len(chunk) % 4096 == 0
                assert out.write(chunk) == len(chunk)
                written += len(chunk)
            assert written == target["Size"]
            os.fsync(out.fileno())
        info("disk0s8")
        assert digest("/dev/rdisk0s8") == expected_super
        staged.unlink()
        print("Android super image read back: SHA-256 matches.", flush=True)
    info("disk0s7")
    for rel in relative:
        dest = mount / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(dest.name + ".new")
        shutil.copyfile(boot / rel, temporary)
        with temporary.open("rb") as f:
            os.fsync(f.fileno())
        assert digest(temporary) == expected_files[rel]
        os.replace(temporary, dest)
    for rel, expected in expected_files.items():
        assert digest(mount / rel) == expected, rel
    with open("/dev/rdisk0", "rb", buffering=0) as f:
        assert f.read(24576) == before_gpt, "Partition table unexpectedly changed"
        f.seek(disk_size-24576)
        assert f.read(24576) == before_gpt_backup, 'Backup GPT unexpectedly changed'
    result = {"installed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "targets": EXPECTED, "super_sha256": expected_super,
              "super_partitions": installed_parts,
              "preserved_runtime_state": preserved,
              "super_hash_scope": "installation readback; writable logical state can change after boot",
              "boot_files_sha256": expected_files, "gpt_unchanged": True,
              "boot_only_update": args.boot_only, "super_written_this_run": not args.boot_only,
              "installation_mode": 'diagnostic-hardware-bringup' if args.hardware_bringup else 'validated-qemu-userspace',
              "full_qemu_android_boot_validated": android_boot is not None,
              "rollback_backup": str(backup),
              "selinux_mount_and_policy_smoke_tests": smoke,
              "graphics_selinux_validation": graphics,
              "userdata_reformatted": False, "runtime_boot_test": "pending user reboot"}
    (BASE / ".work/installed-manifest.json").write_text(json.dumps(result, indent=2)+"\n")
    print("EFI files verified; GPT and userdata preserved. Installation complete.", flush=True)

if __name__ == "__main__":
    main()

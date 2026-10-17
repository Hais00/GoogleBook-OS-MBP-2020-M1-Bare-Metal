#!/usr/bin/env python3
"""Prepare Android/M1 boot files without writing any physical disk."""
import gzip
import ctypes
import hashlib
import pathlib
import shutil
import stat
import struct
import argparse
import json
from boot_config import BOOT_ARGS
from apple_graphics_policy import DRM_FILE_CONTEXTS

BASE = pathlib.Path(__file__).resolve().parents[1]
BOOT = BASE / "apple_silicon_boot"
VENDOR = BASE / "vendor_work"
BACKUP = BASE / ".work/backup-before-repair"
GRAPHICS = pathlib.Path("/opt/googlebook/build/graphics-out")

FSTAB = """# Apple M1: dynamic Android slot A, on the internal NVMe boot device.
system_a /system erofs ro wait,logical,first_stage_mount
vendor_a /vendor erofs ro wait,logical,first_stage_mount
product_a /product erofs ro wait,logical,first_stage_mount
system_ext_a /system_ext erofs ro wait,logical,first_stage_mount
/dev/block/by-name/metadata /metadata ext4 noatime,nosuid,nodev wait,first_stage_mount,formattable
/dev/block/by-name/userdata /data ext4 noatime,nosuid,nodev wait,check,formattable,quota,latemount
/dev/block/mapper/misc /misc emmc defaults defaults
"""

def entries(data):
    pos = 0
    while pos + 110 <= len(data):
        assert data[pos:pos+6] in [b"070701", b"070702"]
        vals = [int(data[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
        name = data[pos+110:pos+110+vals[11]-1].decode()
        start = (pos + 110 + vals[11] + 3) & ~3
        payload = data[start:start+vals[6]]
        pos = (start + vals[6] + 3) & ~3
        if name == "TRAILER!!!":
            return
        yield name.removeprefix("./"), vals, payload

def pack(items):
    out = bytearray()
    for ino, (name, values, payload) in enumerate(items + [("TRAILER!!!", [0]*13, b"")], 1):
        vals = values.copy()
        vals[0], vals[2], vals[3], vals[5] = ino, 0, 0, 0
        vals[6], vals[11], vals[12] = len(payload), len(name.encode()) + 1, 0
        out += b"070701" + "".join(f"{v:08x}" for v in vals).encode() + name.encode() + b"\0"
        out += b"\0" * (-len(out) % 4)
        out += payload
        out += b"\0" * (-len(out) % 4)
    out += b"\0" * (-len(out) % 512)
    return bytes(out)

def regular(name, payload, mode=stat.S_IFREG | 0o644):
    v = [0] * 13
    v[1], v[4] = mode, 1
    return name, v, payload

def backup_vendor(rel):
    src, dst = VENDOR / rel, BACKUP / "vendor-files" / rel
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def prepare(profile='m1', trace_drm=False):
    assert profile in ['m1', 'virt']
    # A modified platform CIL must be compiled, not silently shadowed by the
    # stock precompiled policy. Normal images keep the original cached policy.
    cil = pathlib.Path('/opt/googlebook/build/system-ext-work/etc/selinux/system_ext_sepolicy.cil')
    original_cil = pathlib.Path('/opt/googlebook/build/system-ext-original/etc/selinux/system_ext_sepolicy.cil')
    cached = VENDOR/'etc/selinux/precompiled_sepolicy'
    if cil.exists() and cil.read_bytes() != original_cil.read_bytes():
        if cached.exists():
            target = VENDOR/'etc/googlebook-disabled/precompiled_sepolicy'
            target.parent.mkdir(exist_ok=True)
            cached.replace(target)
    elif not cached.exists():
        shutil.copy2('/opt/googlebook/build/vendor-original/etc/selinux/precompiled_sepolicy', cached)
    for rel in ["etc/fstab.android-desktop", "build.prop", "etc/ueventd.rc", "lib64/libgbm.so", "etc/init/hwc3-drm.rc"]:
        backup_vendor(rel)
    for filename, rel in {
        "libgbm.so": "lib64/libgbm.so",
        "libminigbm_gralloc.so": "lib64/libminigbm_gralloc.so",
        "libm1gate.so": "lib64/libm1gate.so",
        "mapper.minigbm.so": "lib64/hw/mapper.minigbm.so",
        "gralloc.cros.so": "lib64/hw/gralloc.cros.so",
        "android.hardware.graphics.allocator-service.minigbm": "bin/hw/android.hardware.graphics.allocator-service.minigbm",
        "android.hardware.boot-service.googlebook": "bin/hw/android.hardware.boot-service.android-desktop",
        "vulkan.pastel.so": "lib64/hw/vulkan.pastel.so",
    }.items():
        src, dst = GRAPHICS / filename, VENDOR / rel
        assert src.is_file()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        dst.chmod(0o755 if rel.startswith("bin/") else 0o644)
    minigbm = BASE / "minigbm/cros_gralloc"
    hwc_rc = VENDOR / "etc/init/hwc3-drm.rc"
    hwc_lines = [l for l in hwc_rc.read_text().splitlines() if "setenv LD_PRELOAD /vendor/lib64/libgooglebook_drm_backend.so" not in l]
    assert hwc_lines[0].startswith("service vendor.hwcomposer-3 ")
    hwc_rc.write_text("\n".join(hwc_lines) + "\n")
    use_generic_hwc_backend(trace_drm)
    prepare_empty_audio()
    # Keep the compatibility names without storing the same Vulkan driver thrice.
    asahi = VENDOR / "lib64/hw/vulkan.asahi.so"
    for alias in ["vulkan.default.so", "vulkan.adreno.so"]:
        p = asahi.with_name(alias)
        if p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).digest() == hashlib.sha256(asahi.read_bytes()).digest():
            backup_vendor("lib64/hw/" + alias)
            p.unlink()
            p.symlink_to("vulkan.asahi.so")
    for n, values, payload in entries((BASE / ".work/firmware.cpio").read_bytes()):
        rel = n.removeprefix("vendorfw").lstrip("/")
        dest = VENDOR / "firmware" / rel
        kind = stat.S_IFMT(values[1])
        if kind == stat.S_IFDIR:
            dest.mkdir(parents=True, exist_ok=True)
        elif kind == stat.S_IFREG:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(payload)
            dest.chmod(values[1] & 0o777)
        elif kind == stat.S_IFLNK:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.is_symlink():
                dest.symlink_to(payload.decode())
    shutil.copy2(minigbm / "aidl/allocator.rc", VENDOR / "etc/init/allocator-minigbm.rc")
    shutil.copy2(minigbm / "aidl/allocator.xml", VENDOR / "etc/vintf/manifest/allocator-minigbm.xml")
    shutil.copy2(minigbm / "mapper_stablec/mapper.minigbm.xml", VENDOR / "etc/vintf/manifest/mapper.minigbm.xml")
    for rel in ["etc/vintf/manifest/vendor.qti.hardware.display.allocator-service.xml", "etc/vintf/manifest/mapper.qti.xml"]:
        src = VENDOR / rel
        backup_vendor(rel)
        if src.exists():
            src.rename(src.with_suffix(src.suffix + ".disabled"))
    # Init parses every regular file in its configuration directories, even
    # names ending in .disabled. Keep disabled definitions outside those trees.
    # A Google firmware roll-forward write is not a valid action on this board.
    rollforward = VENDOR / 'etc/init/desktop_kernel_max_rollforward_boot.rc'
    if rollforward.exists():
        rollforward.rename(rollforward.with_suffix('.rc.disabled'))
    for directory, destination in [("etc/init", "etc/init-disabled"),
                                    ("etc/vintf/manifest", "etc/vintf-disabled/manifest")]:
        for src in (VENDOR / directory).glob("*.disabled"):
            dst = VENDOR / destination / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)
    # This M1 board has no Google GSC/Titan StrongBox device. Keep the original
    # package for recovery, outside the APEX scan path, rather than advertise it.
    strongbox = VENDOR / 'apex/com.android.hardware.keymint.strongbox.desktop.apex'
    if strongbox.exists():
        dst = VENDOR / 'apex-disabled' / strongbox.name
        dst.parent.mkdir(exist_ok=True)
        strongbox.replace(dst)
    # Secretkeeper requires protected persistent storage. Advertising this
    # TIPC client before its VM exists creates a circular early-VM dependency.
    for rel in ['etc/vintf/manifest/android.hardware.security.secretkeeper.trusty.xml',
                'etc/init/android.hardware.security.secretkeeper.trusty.desktop.rc']:
        src = VENDOR / rel
        if src.exists():
            dst = VENDOR / 'etc/googlebook-disabled' / src.name
            dst.parent.mkdir(exist_ok=True)
            src.replace(dst)
    props = {
        "ro.hardware.gralloc": "cros", "ro.hardware.vulkan": 'asahi' if profile == 'm1' else 'pastel', "ro.hardware.egl": "angle",
        "vendor.hwc.backend_override": "generic", "ro.vendor.hwc.use_overlay_planes": "0",
        "vendor.minigbm.debug": "nocompression", "vendor.gralloc.disable_ubwc": "1",
        # The 2D virtio scanout accepts ARGB/XRGB, not Android's default
        # RGBA (ABGR in DRM). BGRA8888 maps to its supported ARGB8888 format.
        # Restore the native RGBA preference when switching back to Apple DRM.
        "ro.surface_flinger.default_composition_pixel_format": "1" if profile == 'm1' else "5",
        "ro.surface_flinger.wcg_composition_pixel_format": "1" if profile == 'm1' else "5",
        # This board boots one Android slot from EFI-GOS; it has no A/B bootloader.
        "ro.build.ab_update": "false", "ro.virtual_ab.enabled": "false",
        "ro.virtual_ab.compression.enabled": "false",
        "ro.virtual_ab.userspace.snapshots.enabled": "false",
        "ro.virtual_ab.batch_writes": "false", "ro.virtual_ab.io_uring.enabled": "false",
        "ro.virtual_ab.compression.xor.enabled": "false", "ro.virtual_ab.ublk.enabled": "false",
        # Asahi KVM does not provide the protected-VM mode expected by this image.
        # Select the image's existing non-protected Trusty path instead.
        "ro.boot.hypervisor.protected_vm.supported": "0",
        # ARPAL depends on Qualcomm DSP hardware. Select the image's provided
        # empty audio module during board bring-up; do not drive Apple speakers.
        "vendor.audio.dras.default_nothing": "true",
    }
    propfile = VENDOR / "build.prop"
    lines = [l for l in propfile.read_text().splitlines() if l.split("=", 1)[0] not in props]
    propfile.write_text("\n".join(lines) + "\n\n# Apple M1 DRM/AGX graphics\n" +
                        "".join(f"{k}={v}\n" for k, v in props.items()))
    (VENDOR/'etc/googlebook-profile.json').write_text(json.dumps({'profile':profile, 'drm_trace':trace_drm})+'\n')
    (VENDOR / "etc/fstab.android-desktop").write_text(FSTAB)
    # Preserve the original ueventd rules; add the standard DRM device permissions.
    uevent = VENDOR / "etc/ueventd.rc"
    marker = "# GoogleBook M1 graphics devices"
    content = uevent.read_text().split(marker)[0]
    uevent.write_text(content + marker + "\n/dev/dri/card* 0660 system graphics\n/dev/dri/renderD* 0666 root graphics\n"
                     "/dev/block/mapper/desktop_security_storage 0660 system system\n"
                     "/dev/block/mapper/desktop_security_persist 0660 system system\n")
    contexts = VENDOR / 'etc/selinux/vendor_file_contexts'
    marker = '# GoogleBook Apple DRM device labels'
    content = contexts.read_text().split(marker)[0].rstrip()
    contexts.write_text(content+'\n\n'+marker+'\n'+''.join(
        pattern+' '+label+'\n' for pattern, label in DRM_FILE_CONTEXTS.items()))
    misc_context = '/dev/block/mapper/misc u:object_r:misc_block_device:s0'
    if misc_context not in contexts.read_text():
        with contexts.open('a') as out:
            out.write('\n# M1 boot-control storage, contained in Android super\n' + misc_context + '\n')
    for name in ['desktop_security_storage','desktop_security_persist']:
        rule='/dev/block/mapper/'+name+' u:object_r:secure_storage_block_device:s0'
        if rule not in contexts.read_text():
            with contexts.open('a') as out:out.write(rule+'\n')
    boot_rc = VENDOR / 'etc/init/android.hardware.boot-service.android-desktop.rc'
    boot_rc.write_text('''service vendor.boot-default /vendor/bin/hw/android.hardware.boot-service.android-desktop
    interface aidl android.hardware.boot.IBootControl/default
    class early_hal
    user root
    group root system
''')
    (VENDOR / 'etc/init/googlebook-debug-console.rc').write_text('''# Opt-in local serial shell for development captures.
service vendor.googlebook.console /system/bin/sh -c "echo GOS_CONSOLE_READY; exec /system/bin/sh -i"
    class core
    console
    user shell
    group shell log readproc inet
    seclabel u:r:shell:s0
    disabled
    oneshot

# Native coldboot may still be creating /dev/console during early-init.
# Match Android's own console trigger, after wait_for_coldboot_done.
on init && property:ro.boot.googlebook.debug=1
    start vendor.googlebook.console
''')
    old_override = VENDOR / 'etc/init/googlebook-trusty.rc'
    if old_override.exists():
        old_override.unlink()  # Platform service adaptations live in system_ext.
    # Retire the old shell logger: executing a shell in init's SELinux domain
    # fails on this user build. Kernel UART and the gated UID2000 serial console
    # provide the tested capture path without an invalid privileged service.
    for rel in ['bin/googlebook-bootlog.sh', 'etc/init/googlebook-bootlog.rc']:
        (VENDOR/rel).unlink(missing_ok=True)
    # Rebuild the original first-stage archive, preserving special nodes and links.
    original = BACKUP / "apple_silicon_boot/initrd.img"
    items = list(entries(gzip.decompress(original.read_bytes())))
    items = [(n, v, FSTAB.encode() if "fstab" in n else p) for n, v, p in items]
    for n, _, _ in items:
        if "fstab" in n:
            target = BASE / "ramdisk_work" / n
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(FSTAB)
    names = {n for n, _, _ in items}
    for n in ["lib", "lib/firmware"]:
        if n not in names:
            items.append(regular(n, b"", stat.S_IFDIR | 0o755)); names.add(n)
    for n, v, payload in entries((BASE / ".work/firmware.cpio").read_bytes()):
        n = "lib/firmware" + n.removeprefix("vendorfw")
        if n not in names:
            items.append((n, v, payload)); names.add(n)
    raw = pack(items)
    check = list(entries(raw))
    assert len(check) == len(items)
    assert next(p for n, _, p in check if n == "init").startswith(b"\x7fELF")
    (BOOT / "initrd.img").write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    # A stable FAT UUID makes GRUB independent of NVMe enumeration order.
    args = BOOT_ARGS
    cfg = f'''set default=0
set timeout=10
search --no-floppy --fs-uuid --set=root 0D87-0D88

menuentry "GoogleBook OS - Apple M1 / Asahi GPU" --id=googlebook-m1 {{
    search --no-floppy --fs-uuid --set=root 0D87-0D88
    linux /Image {args}
    initrd /initrd.img
}}
menuentry "Riavvia il Mac" {{ reboot; }}
'''
    for rel in ["EFI/BOOT/grub.cfg", "boot/grub/grub.cfg"]:
        (BOOT / rel).write_text(cfg)
    bridge = BOOT / "EFI/debian/grub.cfg"
    bridge.parent.mkdir(exist_ok=True)
    bridge.write_text("search --no-floppy --fs-uuid --set=root 0D87-0D88\nset prefix=($root)/boot/grub\nconfigfile $prefix/grub.cfg\n")
    (BOOT / "extlinux/extlinux.conf").write_text(f"default GoogleBookOS\nprompt 1\ntimeout 100\nlabel GoogleBookOS\n    menu label GoogleBook OS - Apple M1 / Asahi GPU\n    linux /Image\n    initrd /initrd.img\n    append {args}\n")
    restore_vendor_labels()
    print("Prepared first-stage ramdisk, GRUB/extlinux configuration and minigbm Android graphics.")

def restore_vendor_labels():
    """Preserve original Android SELinux labels via Darwin's xattr API."""
    original = pathlib.Path("/opt/googlebook/build/vendor-original")
    assert original.is_dir(), "Extract the original vendor image with fsck.erofs --xattrs first"
    libc = ctypes.CDLL("libSystem.B.dylib", use_errno=True)
    libc.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    libc.getxattr.restype = ctypes.c_ssize_t
    libc.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    libc.setxattr.restype = ctypes.c_int
    def get(path, attr):
        size = libc.getxattr(str(path).encode(), attr.encode(), None, 0, 0, 1)
        if size < 0:
            return None
        buf = ctypes.create_string_buffer(size)
        assert libc.getxattr(str(path).encode(), attr.encode(), buf, size, 0, 1) == size
        return buf.raw
    def set_attr(path, attr, data):
        rc = libc.setxattr(str(path).encode(), attr.encode(), data, len(data), 0, 1)
        if rc and ctypes.get_errno() == 13 and not path.is_symlink():
            mode = stat.S_IMODE(path.stat().st_mode)
            try:
                path.chmod(mode | stat.S_IWUSR)
                rc = libc.setxattr(str(path).encode(), attr.encode(), data, len(data), 0, 1)
            finally:
                path.chmod(mode)
        if rc:
            raise OSError(ctypes.get_errno(), str(path))
    overrides = {
        "bin/hw/android.hardware.graphics.allocator-service.minigbm": "hal_graphics_allocator_default_exec",
        "lib64/libgbm.so": "same_process_hal_file",
        "lib64/libminigbm_gralloc.so": "same_process_hal_file",
        "lib64/libm1gate.so": "same_process_hal_file",
        "lib64/hw/mapper.minigbm.so": "same_process_hal_file",
        "lib64/hw/gralloc.cros.so": "same_process_hal_file",
        "lib64/hw/vulkan.asahi.so": "same_process_hal_file",
        "lib64/hw/vulkan.default.so": "same_process_hal_file",
        "lib64/hw/vulkan.pastel.so": "same_process_hal_file",
        "bin/hw/googlebook-audio-hal": "hal_audio_default_exec",
    }
    count = 0
    for p in [VENDOR] + list(VENDOR.rglob("*")):
        rel = p.relative_to(VENDOR).as_posix()
        # New configuration files must receive Android's existing /vendor/etc
        # type too. vendor_file is not readable by servicemanager for VINTF.
        fallback = b"u:object_r:vendor_configs_file:s0\0" if rel == "etc" or rel.startswith("etc/") else b"u:object_r:vendor_file:s0\0"
        label = get(original / rel, "security.selinux") or fallback
        if rel in overrides:
            label = f"u:object_r:{overrides[rel]}:s0\0".encode()
        elif rel.startswith("firmware/") or rel == "firmware":
            label = b"u:object_r:vendor_firmware_file:s0\0"
        set_attr(p, "security.selinux", label)
        caps = get(original / rel, "security.capability")
        if caps:
            set_attr(p, "security.capability", caps)
        count += 1
    print("Preserved Android security labels:", count)

def prepare_empty_audio():
    """Reuse the provided empty audio HAL, without a slow Qualcomm DSP probe."""
    original = BASE/'.work/audio-apex/root'
    assert (original/'bin/hw/dras.core.audio').is_file()
    # The original vendor already contains this HAL's Rust/NDK dependencies.
    # A privileged service ignores LD_LIBRARY_PATH: use the normal vendor
    # library namespace for our uniquely named, board-specific adapter too.
    previous_bundle = VENDOR/'lib64/googlebook-audio'
    if previous_bundle.exists():
        expected = {p.name for p in (original/'lib64').iterdir()} | {'libgosagmservice.so'}
        assert {p.name for p in previous_bundle.iterdir()} <= expected
        shutil.rmtree(previous_bundle)
    shutil.copy2(GRAPHICS/'libgosagmservice.so', VENDOR/'lib64/libgosagmservice.so')
    data = (original/'bin/hw/dras.core.audio').read_bytes()
    previous, replacement = b'libagmipcservice.so', b'libgosagmservice.so'
    assert len(previous) == len(replacement) and data.count(previous) == 1
    target = VENDOR/'bin/hw/googlebook-audio-hal'
    target.write_bytes(data.replace(previous, replacement))
    target.chmod(0o755)
    rc = (original/'etc/dras.core-arpal.audio.rc').read_text()
    rc = rc.replace('/apex/com.android.hardware.audio.desktop/bin/hw/dras.core.audio',
                    '/vendor/bin/hw/googlebook-audio-hal', 1)
    first, rest = rc.split('\n', 1)
    rc = first+'\n    override\n'+rest
    (VENDOR/'etc/init/googlebook-audio.rc').write_text(rc)


def use_generic_hwc_backend(trace_drm=False):
    """Use a normal ELF dependency, retaining every original address/relocation."""
    rel = "bin/hw/android.hardware.composer.hwc3-service.drm"
    backup_vendor(rel)
    original = pathlib.Path("/opt/googlebook/build/vendor-original") / rel
    data = bytearray(original.read_bytes())
    assert data[:5] == b"\x7fELF\x02"
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, count = struct.unpack_from("<HH", data, 54)
    loads, dynamic = [], None
    for i in range(count):
        p = struct.unpack_from("<IIQQQQQQ", data, phoff+i*phsize)
        if p[0] == 1:
            loads.append(p)
        if p[0] == 2:
            dynamic = p
    assert dynamic
    tags = []
    for off in range(dynamic[2], dynamic[2]+dynamic[5], 16):
        tag, val = struct.unpack_from("<QQ", data, off)
        if tag == 0:
            break
        tags.append((tag, val))
    va = next(v for t, v in tags if t == 5)
    segment = next(p for p in loads if p[3] <= va < p[3]+p[5])
    strings = segment[2] + va - segment[3]
    matches = []
    for tag, val in tags:
        if tag == 1:
            off = strings + val
            name = bytes(data[off:]).split(b"\0", 1)[0]
            if name == b"libsdmcore.so":
                matches.append((off, name))
    assert len(matches) == 1
    off, previous = matches[0]
    replacement = b"libm1gate.so"
    assert len(replacement) <= len(previous)
    data[off:off+len(previous)+1] = replacement + b"\0"*(len(previous)+1-len(replacement))
    if trace_drm:
        # These are undefined, unversioned imports. Renaming them preserves
        # all ELF addresses; the wrapper delegates every original DRM call.
        for name in [b'drmModeAddFB2', b'drmModeAddFB2WithModifiers']:
            assert data.count(name+b'\0') == 1
            data = data.replace(name+b'\0', b'gos'+name[3:]+b'\0')
    assert len(data) == original.stat().st_size
    target = VENDOR / rel
    target.write_bytes(data)
    target.chmod(0o755)
    print("HWC uses libm1gate.so; original ELF addresses and relocations preserved.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=['m1','virt'], default='m1')
    parser.add_argument('--trace-drm', action='store_true')
    args = parser.parse_args()
    prepare(args.profile, args.trace_drm)

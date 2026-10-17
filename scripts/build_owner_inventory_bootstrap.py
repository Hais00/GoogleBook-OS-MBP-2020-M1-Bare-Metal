#!/usr/bin/env python3
"""Build a read-only Linux owner census, then switch to the unchanged Android initrd."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import stat
import tarfile
from build_ram_bootstrap import pack
from prepare_m1_install import entries, regular
from project_paths import BASE, WORK

INIT = b'''#!/bin/busybox sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
rescue() {
    echo GOS_OWNER_BOOTSTRAP_ERROR_NO_AUTOMATIC_RESET
    exec /bin/busybox sh -i
}
trap rescue EXIT
mkdir -p /proc /sys /dev /android
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
echo GOS_PREBOOT_OWNER_BEGIN
id
uname -a
i=0
while [ ! -e /sys/bus/platform/drivers/snd-soc-macaudio/sound ] && [ "$i" -lt 50 ]; do
    sleep 0.1
    i=$((i+1))
done
for f in /proc/asound/cards /proc/asound/pcm /proc/asound/version /sys/module/snd_soc_macaudio/parameters/please_blow_up_my_speakers; do
    echo GOS_PREBOOT_FILE_BEGIN="$f"
    if cat "$f"; then echo GOS_PREBOOT_FILE_RC=0; else echo GOS_PREBOOT_FILE_RC=$?; fi
    echo GOS_PREBOOT_FILE_END="$f"
done
if timeout 20 /alsa-owner-inventory; then echo GOS_PREBOOT_ALSA_RC=0; else echo GOS_PREBOOT_ALSA_RC=$?; fi
echo GOS_PREBOOT_OWNER_END
mount -t tmpfs -o mode=0755 tmpfs /android
gzip -dc /android-initrd.img | (cd /android && cpio -idmu)
test -x /android/init
umount /proc
umount /sys
umount /dev
echo GOS_PREBOOT_ANDROID_HANDOFF
exec /bin/busybox switch_root /android /init
'''

MINIMAL_INIT = b'''#!/gos-owner/busybox sh
set -eu
export PATH=/gos-owner/tools
rescue() {
    echo GOS_OWNER_BOOTSTRAP_ERROR_NO_AUTOMATIC_RESET
    exec /gos-owner/busybox sh -i
}
trap rescue EXIT
mkdir -p /proc /sys /dev /gos-owner/devsnd
mount -t proc proc /proc
mount -t sysfs sysfs /sys
echo GOS_PREBOOT_OWNER_BEGIN
id
uname -a
i=0
while [ ! -e /sys/bus/platform/drivers/snd-soc-macaudio/sound ] && [ "$i" -lt 50 ]; do
    sleep 0.1
    i=$((i+1))
done
for f in /proc/asound/cards /proc/asound/pcm /proc/asound/version /sys/module/snd_soc_macaudio/parameters/please_blow_up_my_speakers; do
    echo GOS_PREBOOT_FILE_BEGIN="$f"
    if cat "$f"; then echo GOS_PREBOOT_FILE_RC=0; else echo GOS_PREBOOT_FILE_RC=$?; fi
    echo GOS_PREBOOT_FILE_END="$f"
done
for ctl in /sys/class/sound/controlC*; do
    [ -f "$ctl/dev" ] || continue
    read -r devt < "$ctl/dev"
    case "$devt" in ''|*[!0-9:]*|:*|*:) echo GOS_INVALID_CONTROL_DEVT="$devt"; exit 1;; esac
    mknod "/gos-owner/devsnd/${ctl##*/}" c "${devt%:*}" "${devt#*:}"
done
if timeout 20 /gos-owner/alsa-owner-inventory --preboot-nodes; then echo GOS_PREBOOT_ALSA_RC=0; else echo GOS_PREBOOT_ALSA_RC=$?; fi
echo GOS_PREBOOT_OWNER_END
umount /proc
umount /sys
mv /gos-owner/original-init /init
mv /gos-owner/original-dev-console /dev/console
mv /gos-owner/original-dev-null /dev/null
echo GOS_PREBOOT_ANDROID_HANDOFF
exec /init
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--android-initrd', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--minimal', action='store_true',
                   help='Use the original Android root with only BusyBox and its actual musl dependency')
    a = p.parse_args()
    assert not a.output.exists(), 'Refusing to overwrite a prepared bootstrap'
    android = a.android_initrd.read_bytes()
    android_manifest = json.loads((a.android_initrd.parent/'manifest.json').read_text())
    assert sha(android) == android_manifest['initrd_sha256']
    am = {n: (n, v, d) for n, v, d in entries(gzip.decompress(android))}
    assert am['init'][2]
    rootfs = Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance/build/rootfs-base.tar.gz')
    members = {}
    with tarfile.open(rootfs) as tar:
        for ent in tar.getmembers():
            name = ent.name.removeprefix('./').rstrip('/')
            if not name or name == '.':
                continue
            assert not name.startswith('/') and '..' not in Path(name).parts
            vals = [0]*13
            vals[2], vals[3], vals[4] = ent.uid, ent.gid, 1
            data = b''
            if ent.isdir():
                vals[1] = stat.S_IFDIR | ent.mode
            elif ent.issym():
                vals[1] = stat.S_IFLNK | 0o777
                data = ent.linkname.encode()
            elif ent.isreg() or ent.islnk():
                vals[1] = stat.S_IFREG | ent.mode
                data = tar.extractfile(ent).read()
            elif ent.ischr() or ent.isblk():
                vals[1] = (stat.S_IFCHR if ent.ischr() else stat.S_IFBLK) | ent.mode
                vals[9], vals[10] = ent.devmajor, ent.devminor
            else:
                continue
            members[name] = (name, vals, data)
    for name, value in am.items():
        if name == 'lib/firmware' or name.startswith('lib/firmware/'):
            members[name] = value
    if a.minimal:
        root = members
        members = dict(am)
        for name in ['gos-owner', 'gos-owner/tools']:
            members[name] = regular(name, b'', stat.S_IFDIR | 0o755)
        for old, new in [('bin/busybox', 'gos-owner/busybox'),
                         ('lib/ld-musl-aarch64.so.1', 'lib/ld-musl-aarch64.so.1'),
                         ('lib/libc.musl-aarch64.so.1', 'lib/libc.musl-aarch64.so.1')]:
            assert new not in members
            _, v, d = root[old]
            members[new] = (new, list(v), d)
        _, v, d = am['init']
        members['gos-owner/original-init'] = ('gos-owner/original-init', list(v), d)
        for name, backup in [('dev/console', 'gos-owner/original-dev-console'),
                             ('dev/null', 'gos-owner/original-dev-null')]:
            _, v, d = am[name]
            members[backup] = (backup, list(v), d)
        for applet in ['mkdir', 'mount', 'umount', 'cat', 'id', 'uname', 'sleep', 'timeout', 'mv', 'mknod']:
            name = 'gos-owner/tools/'+applet
            members[name] = regular(name, b'../busybox', stat.S_IFLNK | 0o777)
    probe = (WORK/'alsa-owner-probe/alsa-owner-inventory').read_bytes()
    build = json.loads((WORK/'alsa-owner-probe/build.json').read_text())
    assert sha(probe) == build['binary_sha256']
    script = MINIMAL_INIT if a.minimal else INIT
    probe_member = 'gos-owner/alsa-owner-inventory' if a.minimal else 'alsa-owner-inventory'
    additions = [('init', script, 0o755), (probe_member, probe, 0o755)]
    if not a.minimal:
        additions.append(('android-initrd.img', android, 0o600))
    for name, data, mode in additions:
        members[name] = regular(name, data, stat.S_IFREG | mode)
    assert 'm1_ram_image_update.py' not in members and 'android_lp_state.py' not in members
    for name, major, minor in [('dev/console', 5, 1), ('dev/null', 1, 3)]:
        vals = [0]*13
        vals[1], vals[4], vals[9], vals[10] = stat.S_IFCHR | 0o600, 1, major, minor
        members[name] = (name, vals, b'')
    raw = pack(list(members.values()))
    check = {n: (v, d) for n, v, d in entries(raw)}
    assert check['init'][1] == script
    if a.minimal:
        restored = {'init': 'gos-owner/original-init',
                    'dev/console': 'gos-owner/original-dev-console',
                    'dev/null': 'gos-owner/original-dev-null'}
        for name, (_, v, d) in am.items():
            actual = restored.get(name, name)
            assert check[actual][0][1:5] == v[1:5] and check[actual][1] == d, name
    else:
        assert check['android-initrd.img'][1] == android
    payload = gzip.compress(raw, compresslevel=6, mtime=0)
    a.output.mkdir()
    (a.output/'initrd.img').write_bytes(payload)
    (a.output/'manifest.json').write_text(json.dumps({
        'schema': 'googlebook-preboot-owner.v2-minimal' if a.minimal else 'googlebook-preboot-owner.v1',
        'initrd_sha256': sha(payload), 'minimal': a.minimal, 'probe_member': probe_member,
        'restored_members': restored if a.minimal else {},
        'android_initrd_sha256': sha(android), 'android_initrd_source': str(a.android_initrd),
        'source_rootfs_sha256': sha(rootfs.read_bytes()), 'init_sha256': sha(script),
        'owner_probe_sha256': sha(probe), 'owner_probe_build': build,
        'entries': len(members), 'ram_installer_included': False,
        'wrapper_block_device_open_or_mount': False, 'pcm_data_open_or_write': False,
        'handoff': 'Original Android /init, unchanged original restored-firmware initrd',
        'hardware_verified': False}, indent=2)+'\n')
    print('OWNER_BOOTSTRAP_BUILD_PASS', a.output, len(payload))


if __name__ == '__main__':
    main()

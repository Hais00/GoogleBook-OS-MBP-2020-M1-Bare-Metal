#!/usr/bin/env python3
"""Build a RAM installer that hands off to the original Android init in-place."""
import gzip
import argparse
import hashlib
import json
from pathlib import Path
import stat
import tarfile
from project_paths import BASE, WORK, LARGE_WORK
from prepare_m1_install import entries, regular
from firmware_manifest import repair_firmware_entries

MAINT = Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance')

INIT = b'''#!/bin/busybox sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root
rescue() {
    echo "M1_RAM_BOOTSTRAP_STOPPED: inspect the error; no automatic reset."
    exec /bin/busybox sh -i
}
trap rescue EXIT
mkdir -p /proc /sys /dev /run /tmp /mnt/inbox /mnt/outbox /android
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
echo M1_RAM_BOOTSTRAP_BEGIN
mdev -s
# Each exported generation is immutable during a trial. Cache its verified
# bytes in RAM so validation and installation do not transfer every image twice.
timeout 30 mount -t 9p -o trans=virtio,version=9p2000,ro,cache=loose m1inbox /mnt/inbox
timeout 30 mount -t 9p -o trans=virtio,version=9p2000,cache=none m1outbox /mnt/outbox
echo M1_RAM_BOOTSTRAP_SHARES_READY
python3 /m1_ram_image_update.py /mnt/inbox/update-plan.json --apply > /mnt/outbox/install.log 2>&1 || {
    cat /mnt/outbox/install.log
    exit 1
}
cat /mnt/outbox/install.log
sync
exec /android-handoff.sh
'''

HANDOFF = b'''#!/bin/busybox sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
echo M1_ANDROID_HANDOFF_PREPARE
mount -t tmpfs -o mode=0755 tmpfs /android
gzip -dc /android-initrd.img | (cd /android && cpio -idmu)
test -x /android/init
umount /mnt/inbox
umount /mnt/outbox
sync
umount /proc
umount /sys
umount /dev
echo M1_ANDROID_HANDOFF_EXEC
exec /bin/busybox switch_root /android /init
'''

def pack(items):
    out = bytearray()
    for ino, (name, values, payload) in enumerate(items + [('TRAILER!!!', [0]*13, b'')], 1):
        vals = list(values)
        vals[0], vals[5], vals[6], vals[11], vals[12] = ino, 0, len(payload), len(name.encode())+1, 0
        out += b'070701'+''.join(f'{x:08x}' for x in vals).encode()+name.encode()+b'\0'
        out += bytes(-len(out)%4);out += payload;out += bytes(-len(out)%4)
    out += bytes(-len(out)%512)
    return bytes(out)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verified-android-initrd',type=Path)
    parser.add_argument('--deduplicate-firmware',action='store_true',help='Transport firmware once and copy the exact tree during Android handoff')
    parser.add_argument('--output-directory',type=Path,default=LARGE_WORK/'ram-bootstrap')
    args=parser.parse_args()
    members = {}
    with tarfile.open(MAINT/'build/rootfs-base.tar.gz') as root:
        for entry in root.getmembers():
            name = entry.name.removeprefix('./').rstrip('/')
            if not name or name == '.':
                continue
            vals = [0]*13
            vals[2], vals[3], vals[4] = entry.uid, entry.gid, 1
            payload = b''
            if entry.isdir():
                vals[1] = stat.S_IFDIR | entry.mode
            elif entry.issym():
                vals[1] = stat.S_IFLNK | 0o777; payload = entry.linkname.encode()
            elif entry.isreg() or entry.islnk():
                vals[1] = stat.S_IFREG | entry.mode; payload = root.extractfile(entry).read()
            elif entry.ischr() or entry.isblk():
                vals[1] = (stat.S_IFCHR if entry.ischr() else stat.S_IFBLK) | entry.mode
                vals[9], vals[10] = entry.devmajor, entry.devminor
            else:
                continue
            members[name] = (name, vals, payload)
    original = BASE/'artifacts/GoogleBook-USB-Debug/initrd.img'
    if args.verified_android_initrd:
        selected=args.verified_android_initrd
        proof=json.loads((selected.parent/'manifest.json').read_text())
        android_initrd=selected.read_bytes()
        assert hashlib.sha256(android_initrd).hexdigest()==proof['initrd_sha256']
        assert hashlib.sha256(original.read_bytes()).hexdigest()==proof['source_original_initrd_sha256']
        android_entries={name:(name,vals,data) for name,vals,data in entries(gzip.decompress(android_initrd))}
        repaired,firmware_repair=repair_firmware_entries(android_entries)
        assert not firmware_repair['repaired_members'], 'Firmware must already be restored and qualified'
        original_members={n:(v,d) for n,v,d in entries(gzip.decompress(original.read_bytes()))}
        for n,(v,d) in original_members.items():
            if not n.startswith('lib/firmware/'):
                assert android_entries[n][1][1:5]==v[1:5] and android_entries[n][2]==d,n
    else:
        android_entries = {name:(name,vals,data) for name,vals,data in entries(gzip.decompress(original.read_bytes()))}
        android_entries, firmware_repair = repair_firmware_entries(android_entries)
        for name in ('regulatory.db', 'regulatory.db.p7s'):
            path = 'lib/firmware/'+name
            android_entries[path] = regular(path, (WORK/'wireless-regdb'/name).read_bytes())
        overrides = WORK/'firmware-overrides'
        if overrides.exists():
            for source in sorted(overrides.rglob('*')):
                if source.is_file():
                    name = str(source.relative_to(overrides))
                    assert name.startswith('lib/firmware/') and source.stat().st_size > 0
                    android_entries[name] = regular(name, source.read_bytes())
        # Every firmware alias now has verified bytes. New inode identities in the
        # output archive must not turn hardlinks back into empty placeholders.
        for name, (_, vals, data) in list(android_entries.items()):
            if name.startswith('lib/firmware/') and stat.S_IFMT(vals[1]) == stat.S_IFREG:
                assert data, 'Empty firmware payload: '+name
                vals = list(vals);vals[4] = 1
                android_entries[name] = (name, vals, data)
        android_initrd = gzip.compress(pack(list(android_entries.values())), compresslevel=6, mtime=0)
    full_android_initrd_sha256=hashlib.sha256(android_initrd).hexdigest()
    handoff=HANDOFF
    if args.deduplicate_firmware:
        assert args.verified_android_initrd, 'Deduplication requires the fully verified Android tree'
        thin=[v for n,v in android_entries.items() if not n.startswith('lib/firmware/')]
        android_initrd=gzip.compress(pack(thin),compresslevel=6,mtime=0)
        handoff=HANDOFF.replace(b'test -x /android/init',b'cp -a /lib/firmware /android/lib/\ntest -x /android/init')
    for name, vals, data in android_entries.values():
        if name == 'lib/firmware' or name.startswith('lib/firmware/'):
            members[name] = (name, vals, data)
    additions = {'init': (INIT, 0o755), 'android-handoff.sh': (handoff, 0o755),
                 'android-initrd.img': (android_initrd, 0o600)}
    for name in ('m1_ram_image_update.py', 'android_lp_state.py'):
        additions[name] = ((BASE/'scripts'/name).read_bytes(), 0o644)
    for name, (data, mode) in additions.items():
        members[name] = regular(name, data, stat.S_IFREG | mode)
    for name, major, minor in [('dev/console', 5, 1), ('dev/null', 1, 3)]:
        vals = [0]*13;vals[1] = stat.S_IFCHR|0o600;vals[4] = 1;vals[9], vals[10] = major, minor
        members[name] = (name, vals, b'')
    output = args.output_directory
    output.mkdir(exist_ok=True)
    data = pack(list(members.values()))
    # Round-trip the archive, including its original Android initrd digest.
    check = {name: (vals, payload) for name, vals, payload in entries(data)}
    assert check['android-initrd.img'][1] == android_initrd
    assert check['init'][1] == INIT
    payload = gzip.compress(data, compresslevel=6, mtime=0)
    (output/'initrd.img').write_bytes(payload)
    (output/'android-initrd.img').write_bytes(android_initrd)
    (output/'manifest.json').write_text(json.dumps({'initrd_sha256': hashlib.sha256(payload).hexdigest(),
        'uncompressed_bytes': len(data), 'compressed_bytes': len(payload), 'entries': len(members),
        'source_android_initrd_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
        'android_initrd_sha256': hashlib.sha256(android_initrd).hexdigest(),
        'full_android_initrd_sha256':full_android_initrd_sha256,
        'firmware_transported_once':args.deduplicate_firmware,
        'handoff_sha256':hashlib.sha256(handoff).hexdigest(),
        'android_initrd_changes': (['exact verified original-firmware-restored Android initrd; no further modifications'] if args.verified_android_initrd else ['signed regulatory database', 'authenticated nonempty firmware overlays', 'restore firmware aliases from original FILE/LINK manifest']),
        'firmware_repair': firmware_repair,
        'reboot_required_for_handoff': False, 'hardware_verified': False}, indent=2)+'\n')
    print(output, len(payload))

if __name__ == '__main__':
    main()

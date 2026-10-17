#!/bin/sh
# Only in the isolated build VM, after mounting its disposable Linux scratch disk.
set -eu
stem=${1:-vendor-generation11-btaudio-r2}
case "$stem" in ''|*[!a-zA-Z0-9_-]*) exit 2;; esac
mountpoint -q /mnt/scratch
[ "$(cat /sys/class/block/vda/serial)" = GOS_AUDIO_SCRATCH ]
work=/mnt/scratch/$stem
mkdir -p /tmp/maintroot "$work/image" "$work/readback"
tar -xzf /mnt/build/rootfs-base.tar.gz -C /tmp/maintroot
cp /mnt/build/$stem.tar "$work/source.tar"
mkdir -p /tmp/maintroot/mnt/build /tmp/maintroot/scratch
mount --bind /mnt/build /tmp/maintroot/mnt/build
mount --bind /mnt/scratch /tmp/maintroot/scratch
chroot /tmp/maintroot mkfs.erofs -b4096 -zlz4hc,12 -C65536 --tar=f --sort=none /scratch/$stem/image/vendor.erofs /scratch/$stem/source.tar
chroot /tmp/maintroot fsck.erofs /scratch/$stem/image/vendor.erofs
cp "$work/image/vendor.erofs" /mnt/build/$stem.erofs
mount -t erofs -o loop,ro "$work/image/vendor.erofs" "$work/readback"
mkdir -p /tmp/maintroot/vendor-readback
# Bind the child mount explicitly: a bind of /mnt/scratch is not recursive.
mount --bind "$work/readback" /tmp/maintroot/vendor-readback
chroot /tmp/maintroot python3 /mnt/build/scan-tree.py /vendor-readback /mnt/build/$stem-readback-full.json
chroot /tmp/maintroot python3 -c 'import json,sys; assert len(json.load(open(sys.argv[1]))) > 3000' /mnt/build/$stem-readback-full.json
umount /tmp/maintroot/vendor-readback
umount "$work/readback"
sha256sum /mnt/build/$stem.erofs
echo EROFS_BUILD_AND_SCAN_PASS "$stem"

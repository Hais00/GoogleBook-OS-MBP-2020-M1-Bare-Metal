#!/usr/bin/env python3
"""Exercise the installed Android userspace in QEMU, using local image files.

This diagnoses hardware-independent init/APEX failures; it does not test M1 GPU
or other Apple hardware. A sparse virtual disk is copied from local images and
QEMU uses a temporary snapshot or a named persistent overlay with its own frozen
backing copy. No physical disk is exposed to the VM.
"""
import argparse
import datetime
import fcntl
import json
import os
import pathlib
import re
import socket
import struct
import subprocess
import time
import threading
import uuid
import zlib

from boot_config import BOOT_ARGS

BASE = pathlib.Path(__file__).resolve().parents[1]
QEMU = pathlib.Path('/opt/googlebook/host/Documents/M1 Reverse/.local/qemu/bin/qemu-system-aarch64')
SECTOR = 512


def persistent_disk(work, disk, name, resume):
    assert re.fullmatch(r'[a-z0-9_-]{1,48}', name), 'Invalid local overlay name'
    directory = work/'overlays'
    directory.mkdir(exist_ok=True, mode=0o700)
    overlay = directory/(name+'.qcow2')
    backing = directory/(name+'-base.raw')
    if overlay.exists():
        assert resume and backing.is_file(), 'Use --reuse-disk to resume this VM overlay'
        return overlay
    assert not backing.exists(), 'An incomplete backing copy already exists'
    # Freeze a private backing copy; later diagnostic disk rebuilds cannot
    # invalidate an existing overlay's data, keys or compiled ART cache.
    subprocess.run(['/bin/cp', '-c', str(disk), str(backing)], check=True)
    backing.chmod(0o600)
    frameworks = QEMU.parent.parent/'UTM.app/Contents/Frameworks'
    launcher = BASE/'.work/qemu-tools/qemu-img-launcher'
    launcher.parent.mkdir(exist_ok=True)
    source = BASE/'scripts/qemu_img_framework_main.c'
    subprocess.run(['cc', '-O2', str(source), '-Wl,-rpath,'+str(frameworks),
                    '-o', str(launcher)], check=True)
    subprocess.run([str(launcher), str(frameworks/'qemu-img.framework/Versions/A/qemu-img'),
                    'create', '-f', 'qcow2', '-F', 'raw', '-b', str(backing), str(overlay)], check=True)
    overlay.chmod(0o600)
    (directory/(name+'.json')).write_text(json.dumps({
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'backing': str(backing), 'overlay': str(overlay),
        'physical_disks_exposed': False}, indent=2)+'\n')
    return overlay


def make_disk(directory, super_image=None):
    directory.mkdir(exist_ok=True)
    sources = [
        super_image or BASE / 'dist/super_m1_fixed.img',
        BASE / '.work/metadata-before-earlylog.img',
        BASE / 'dist/userdata.img',
    ]
    for p in sources:
        assert p.is_file() and not str(p).startswith('/dev/')
        assert p.stat().st_size % SECTOR == 0
        assert '"' not in str(p) and '\n' not in str(p)
    head_sectors, esp_sectors, tail_sectors = 2048, 32768, 2048
    sizes = [esp_sectors] + [p.stat().st_size // SECTOR for p in sources]
    start = head_sectors
    partitions = []
    for index, size, name, partuuid in zip(
            [6, 7, 8, 9], sizes, ['EFI-GOS', 'super', 'metadata', 'userdata'],
            ['00000000-0000-4000-8000-000000000002',
             '00000000-0000-4000-8000-000000000001',
             '00000000-0000-4000-8000-000000000004',
             '00000000-0000-4000-8000-000000000005']):
        partitions.append((index, start, start + size - 1, name, partuuid))
        start += size
    total = start + tail_sectors
    table = bytearray(128 * 128)
    for index, first, last, name, partuuid in partitions:
        typeuuid = ('c12a7328-f81f-11d2-ba4b-00a0c93ec93b' if index == 6 else
                    'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7')
        table[index*128:(index+1)*128] = struct.pack(
            '<16s16sQQQ72s', uuid.UUID(typeuuid).bytes_le,
            uuid.UUID(partuuid).bytes_le, first, last, 0, name.encode('utf-16le'))
    diskid = uuid.uuid5(uuid.NAMESPACE_URL, 'googlebook-disposable-android-debug-vm').bytes_le

    def header(current, backup, entries_lba):
        data = bytearray(struct.pack('<8sIIIIQQQQ16sQIII', b'EFI PART', 0x10000,
                                    92, 0, 0, current, backup, 34, total-34,
                                    diskid, entries_lba, 128, 128, zlib.crc32(table)))
        struct.pack_into('<I', data, 16, zlib.crc32(data))
        return data

    head = bytearray(head_sectors * SECTOR)
    head[446:462] = struct.pack('<B3sB3sII', 0, b'\0'*3, 0xee, b'\xff'*3, 1, total-1)
    head[510:512] = b'\x55\xaa'
    head[512:604] = header(1, total-1, 2)
    head[1024:1024+len(table)] = table
    tail = bytearray(tail_sectors * SECTOR)
    tail[-33*SECTOR:-SECTOR] = table
    tail[-SECTOR:-SECTOR+92] = header(total-1, 1, total-33)
    (directory/'gpt-head.bin').write_bytes(head)
    (directory/'gpt-tail.bin').write_bytes(tail)
    image = directory/'android-disposable.raw'
    print('Preparing sparse virtual disk from local image files...', flush=True)
    zero = bytes(4*1024*1024)
    with image.open('wb') as disk:
        disk.write(head)
        disk.seek(esp_sectors * SECTOR, 1)
        for source in sources:
            with source.open('rb') as inp:
                while chunk := inp.read(len(zero)):
                    if chunk == zero[:len(chunk)]:
                        disk.seek(len(chunk), 1)
                    else:
                        disk.write(chunk)
        disk.write(tail)
        assert disk.tell() == total * SECTOR
    return image


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel', type=pathlib.Path, default=BASE/'apple_silicon_boot/Image')
    p.add_argument('--initrd', type=pathlib.Path, default=BASE/'apple_silicon_boot/initrd.img')
    p.add_argument('--super-image', type=pathlib.Path, help='Choose a VM-specific super image without changing the hardware image')
    p.add_argument('--timeout', type=int, default=90)
    p.add_argument('--cpu', default='max', help='QEMU ARM64 CPU model; neoverse-n1 is close to M1 instruction features')
    p.add_argument('--cpus', type=int, choices=range(1, 9), default=2)
    p.add_argument('--graphics', action='store_true', help='Expose an actual virtio KMS display for the VM graphics profile')
    p.add_argument('--audio', action='store_true',
                   help='Expose a virtio ALSA card with a silent host backend for audio HAL bring-up')
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--reuse-disk', action='store_true',
                   help='Reuse the existing local disk copy or resume the named overlay')
    p.add_argument('--persistent-overlay', metavar='NAME',
                   help='Keep VM writes in a named local qcow2 overlay with a frozen private backing copy')
    p.add_argument('--commands-file', type=pathlib.Path,
                   help='Run these shell commands when the opt-in diagnostic serial shell is ready')
    args = p.parse_args()
    work = BASE/'.work/android-boot-vm'
    work.mkdir(exist_ok=True)
    lock = (work/'.disk.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        p.error('Another diagnostic VM or disk preparation is using this virtual disk')
    disk = work/'android-disposable.raw'
    if args.reuse_disk:
        assert disk.is_file(), 'Prepare the local disk copy first'
    else:
        disk = make_disk(work, args.super_image)
    if args.persistent_overlay:
        disk = persistent_disk(work, disk, args.persistent_overlay, args.reuse_disk)
    if args.prepare_only:
        print('Prepared local image-only virtual disk:', disk)
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    log = work/('android-console-'+stamp+'.log')
    cmdline = BOOT_ARGS.replace('console=tty0 console=ttySAC0,115200n8', 'console=ttyAMA0')
    # AOSP's strict boot_part_uuid matcher supports MMC/NVMe/SCSI, not virtio.
    # The VM therefore uses the older platform boot-device selector.
    cmdline = cmdline.replace(
        'androidboot.boot_part_uuid=00000000-0000-4000-8000-000000000002',
        'androidboot.boot_devices=a003e00.virtio_mmio')
    if args.commands_file and 'androidboot.googlebook.debug=1' not in cmdline:
        cmdline += ' androidboot.googlebook.debug=1'
    cmd = [str(QEMU), '-machine', 'virt,gic-version=3,virtualization=on', '-cpu', args.cpu,
           '-accel', 'tcg,thread=multi', '-smp', str(args.cpus), '-m', '4096',
           '-nographic', '-monitor', 'none', '-no-reboot',
           '-drive', (f'file={disk},format=qcow2,if=none,id=android' if args.persistent_overlay else
                      f'file={disk},format=raw,if=none,id=android,snapshot=on'),
           '-device', 'virtio-blk-device,drive=android',
           '-kernel', str(args.kernel), '-initrd', str(args.initrd), '-append', cmdline]
    if args.graphics:
        cmd += ['-device', 'virtio-gpu-pci,xres=1280,yres=800',
                '-device', 'qemu-xhci', '-device', 'usb-kbd', '-device', 'usb-tablet']
        qmp = pathlib.Path('/tmp')/f'googlebook-qmp-{os.getuid()}-{os.getpid()}.sock'
        cmd += ['-qmp', f'unix:{qmp},server=on,wait=off']
    if args.audio:
        cmd += ['-audiodev', 'none,id=audio0', '-device', 'virtio-sound-pci,audiodev=audio0']
    print('Android VM log:', log, flush=True)
    print('Persistent local VM overlay; no physical disks exposed.' if args.persistent_overlay else
          'Disposable QEMU snapshot; backing images and physical disks are preserved.', flush=True)
    with log.open('xb', buffering=0) as out:
        control = log.with_suffix('.stdin') if args.commands_file else None
        control_fd = None
        if control:
            os.mkfifo(control, 0o600)
            control_fd = os.open(control, os.O_RDONLY | os.O_NONBLOCK)
            print('Diagnostic input FIFO:', control, flush=True)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, bufsize=0)
        def capture():
            while data := proc.stdout.read(8192):
                out.write(data)
        reader = threading.Thread(target=capture, daemon=True)
        reader.start()
        sent = False
        try:
            deadline = time.monotonic() + args.timeout
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
                output = log.read_text(errors='replace')
                if control_fd is not None:
                    try:
                        data = os.read(control_fd, 8192)
                    except BlockingIOError:
                        data = b''
                    if data:
                        proc.stdin.write(data)
                        proc.stdin.flush()
                if args.commands_file and not sent and 'GOS_CONSOLE_READY' in output:
                    proc.stdin.write(args.commands_file.read_bytes()+b'\n')
                    proc.stdin.flush()
                    sent = True
                    print('Diagnostic shell commands sent.', flush=True)
                if '---[ end Kernel panic' in output or 'reboot: Restarting system' in output:
                    time.sleep(0.5)
                    break
                if (re.search(r'^GOS_STABLE_BOOT_COMPLETED=1\r?$', output, re.M) and
                        re.search(r'^GOS_WATCH_END\r?$', output, re.M)):
                    print('Android reports a stable completed boot; capturing display.', flush=True)
                    break
        finally:
            if args.graphics and proc.poll() is None and qmp.exists():
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                        sock.settimeout(4)
                        sock.connect(str(qmp))
                        stream = sock.makefile('rwb', buffering=0)
                        assert 'QMP' in json.loads(stream.readline())
                        for request in [
                            {'execute': 'qmp_capabilities'},
                            {'execute': 'screendump', 'arguments': {
                                'filename': str(log.with_suffix('.ppm'))}}]:
                            stream.write(json.dumps(request).encode()+b'\n')
                            while True:
                                response = json.loads(stream.readline())
                                if 'event' not in response:
                                    assert 'return' in response, response
                                    break
                    print('VM display captured:', log.with_suffix('.ppm'), flush=True)
                except (OSError, ValueError, AssertionError) as error:
                    print('VM display capture failed:', error, flush=True)
            if proc.poll() is None:
                proc.terminate()
            try:
                status = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                status = proc.wait()
            reader.join(timeout=5)
            if args.graphics:
                qmp.unlink(missing_ok=True)
            if control_fd is not None:
                os.close(control_fd)
                control.unlink(missing_ok=True)
    lines = log.read_text(errors='replace').splitlines()
    for line in lines:
        if any(s in line for s in ['init second stage', 'apexd-bootstrap: Activated',
                                   "Service 'apexd-bootstrap'", 'Could not start',
                                   'Unknown subsys', 'FATAL', 'CANNOT LINK',
                                   'Kernel panic', 'Restarting system', 'qemu-system-aarch64:']):
            print(line)
    print('QEMU exit status:', status, '\nFull log:', log, flush=True)


if __name__ == '__main__':
    main()

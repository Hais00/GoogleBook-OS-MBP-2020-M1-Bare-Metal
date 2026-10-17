#!/usr/bin/env python3
"""Run the real software audio providers; no disks, radio, or sound hardware."""
import hashlib
import argparse
import json
from pathlib import Path
import socket
import re
import subprocess
import time
from project_paths import LARGE_WORK

ROOT = LARGE_WORK/'native-primary-audio-local-runtime-r9'

def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='')
    parser.add_argument('--negative-control', action='store_true')
    args = parser.parse_args()
    assert not args.label or re.fullmatch('[a-z0-9-]+', args.label)
    suffix = '-'+args.label if args.label else ''
    if suffix: ROOT = ROOT.with_name(ROOT.name+suffix)
    control = Path.home()/('.local/gos-native-primary-audio'+suffix)
    control.mkdir(exist_ok=True)
    serial, qmp = control/'serial.sock', control/'qmp.sock'
    assert not serial.exists() and not qmp.exists(), 'Inspect previous VM before reuse'
    kernel = LARGE_WORK/'kernel23/Image'
    (ROOT/'guest-logs').mkdir(exist_ok=True)
    command = ['/opt/homebrew/bin/qemu-system-aarch64', '-name', 'gos-audio-software-test',
        '-machine', 'virt,accel=hvf,gic-version=3', '-cpu', 'host', '-smp', '2', '-m', '2048',
        '-display', 'none', '-monitor', 'none', '-no-reboot', '-nic', 'none',
        '-kernel', str(kernel), '-initrd', str(LARGE_WORK/'ram-bootstrap/initrd.img'),
        '-append', 'console=ttyAMA0 loglevel=4 panic=0 rdinit=/bin/sh selinux=1 enforcing=0',
        '-chardev', f'socket,id=console,path={serial},server=on,wait=off,logfile={ROOT}/kernel-uart.log',
        '-serial', 'chardev:console', '-qmp', f'unix:{qmp},server=on,wait=off',
        '-fsdev', f'local,id=fixture,path={ROOT},security_model=none,readonly=on',
        '-device', 'virtio-9p-pci,fsdev=fixture,mount_tag=fixture',
        '-fsdev', f'local,id=results,path={ROOT}/guest-logs,security_model=none',
        '-device', 'virtio-9p-pci,fsdev=results,mount_tag=results']
    result = {'command': command, 'physical_disks_attached': False, 'network_attached': False,
              'hardware_verified': False, 'real_ALSA_loopback': True, 'production_speaker_protection_qualified': False, 'kernel_sha256': hashlib.sha256(kernel.read_bytes()).hexdigest(),
              'negative_control': args.negative_control,
              'SELinux_runtime_qualified': False, 'actual_Bionic_Binder_used': True,
              'local_test_policy': 'Unchanged compiled Android policy, permissive in this diskless CPU VM only; physical device unchanged'}
    with (ROOT/'qemu-host.log').open('wb') as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    result['pid'] = process.pid
    (ROOT/'state.json').write_text(json.dumps(result, indent=2)+'\n')
    try:
        deadline = time.monotonic()+20
        while not serial.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(.1)
        with socket.socket(socket.AF_UNIX) as connection:
            connection.connect(str(serial)); connection.settimeout(.2)
            text = b''
            deadline = time.monotonic()+180
            while time.monotonic() < deadline:
                try: text += connection.recv(65536)
                except TimeoutError: pass
                if b'/ # ' in text or b'~ # ' in text: break
            assert b'/ # ' in text or b'~ # ' in text, 'Guest shell did not become ready; no test command sent'
            commands = (
                'mount -t devtmpfs devtmpfs /dev; mount -t proc proc /proc; mount -t sysfs sysfs /sys; '
                'mkdir -p /host /audio-root; mount -t 9p -o trans=virtio,version=9p2000.L,cache=loose,ro fixture /host; '
                'mount --bind /host/root /audio-root; '
                'mkdir -p /sys/fs/selinux; mount -t selinuxfs selinuxfs /sys/fs/selinux; '
                'mount --bind /sys /audio-root/sys; '
                'mount --bind /sys/fs/selinux /audio-root/sys/fs/selinux; '
                'chroot /audio-root /system/bin/audio-local-policy; '
                'mount -t tmpfs tmpfs /audio-root/data; mount -t tmpfs tmpfs /audio-root/tmp; '
                'mount -t tmpfs tmpfs /audio-root/dev; '
                'for n in null zero random urandom kmsg; do cp -a /dev/$n /audio-root/dev/; done; '
                
                'mkdir -p /audio-root/dev/binderfs; mount -t binder binder /audio-root/dev/binderfs; '
                'chroot /audio-root /system/bin/audio-local-binderfs; '
                
                'mount --bind /proc /audio-root/proc; mkdir -p /results; '
                'mount -t 9p -o trans=virtio,version=9p2000.L results /results; '
                '/bin/sh /audio-root/test.sh '+('false' if args.negative_control else 'true')+
                '; echo LOCAL_AUDIO_TEST_DONE_RC=$?\n')
            connection.sendall(commands.encode())
            deadline = time.monotonic()+65
            while time.monotonic() < deadline and process.poll() is None:
                try: text += connection.recv(65536)
                except TimeoutError: pass
                if re.search(rb'\nLOCAL_AUDIO_TEST_DONE_RC=\d+\r?\n', text): break
            (ROOT/'runtime-output.log').write_bytes(text)
            expected = b'NATIVE_AUDIO_BINDER_FMQ_ALSA_PASS'
            result['pass'] = all(marker in text for marker in [
                expected, b'LOCAL_AUDIO_SOFTWARE_RUNTIME_RC=0',
                b'\nLOCAL_AUDIO_TEST_DONE_RC=0'])
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=10)
        result['qemu_stopped'] = process.poll() is not None
        (ROOT/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('LOCAL_AUDIO_SOFTWARE_RUNTIME_PASS' if result.get('pass') else 'LOCAL_AUDIO_SOFTWARE_RUNTIME_FAIL')
    print((ROOT/'runtime-output.log').read_text(errors='replace')[-10000:])
    if not result.get('pass'): raise SystemExit(1)

if __name__ == '__main__': main()

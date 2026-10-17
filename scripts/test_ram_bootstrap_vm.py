#!/usr/bin/env python3
"""Boot the exact new kernel/initrd in a diskless local VM for runtime checks."""
import json
from pathlib import Path
import subprocess
import argparse
import re
from project_paths import LARGE_WORK
from boot_config import BOOT_ARGS

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-version', type=int, default=14)
    parser.add_argument('--label',default='',help='Keep independent test logs and sockets separate')
    options=parser.parse_args();version=options.kernel_version
    assert not options.label or re.fullmatch(r'[a-z0-9-]+',options.label)
    suffix=('-'+options.label) if options.label else ''
    root = LARGE_WORK/'ram-bootstrap'
    control = Path.home()/('.local/googlebook-bootstrap-test-k'+str(version)+suffix)
    control.mkdir(exist_ok=True)
    for name in ('serial.sock', 'qmp.sock'):
        assert not (control/name).exists(), 'Inspect the previous test before starting another one'
    maint = Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance')
    kernel = LARGE_WORK/('kernel'+str(version))/'Image'
    assert kernel.is_file()
    args = ['/opt/homebrew/bin/qemu-system-aarch64', '-name', 'googlebook-ram-bootstrap-test',
            '-machine', 'virt,accel=hvf,gic-version=3', '-cpu', 'host', '-smp', '1', '-m', '2048',
            '-display', 'none', '-monitor', 'none', '-no-reboot', '-nic', 'none',
            '-kernel', str(kernel), '-initrd', str(root/'initrd.img'),
            '-append', BOOT_ARGS.replace('console=tty0 console=ttySAC0,115200n8', 'console=ttyAMA0')+' rdinit=/bin/sh',
            '-chardev', f'socket,id=console,path={control}/serial.sock,server=on,wait=off,logfile={root}/qemu-kernel{version}{suffix}-runtime.log',
            '-serial', 'chardev:console', '-qmp', f'unix:{control}/qmp.sock,server=on,wait=off']
    for tag, dirname in [('m1inbox','inbox'), ('m1outbox','outbox')]:
        args += ['-fsdev', f'local,id={tag},path={maint}/shared/{dirname},security_model=none'+(',readonly=on' if dirname=='inbox' else ''),
                 '-device', f'virtio-9p-pci,fsdev={tag},mount_tag={tag}']
    with (root/('qemu-kernel'+str(version)+suffix+'-host.log')).open('wb') as output:
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    (root/('qemu-kernel'+str(version)+suffix+'-state.json')).write_text(json.dumps({'pid':proc.pid, 'serial':str(control/'serial.sock'), 'qmp':str(control/'qmp.sock'), 'command':args, 'physical_disks_attached':False},indent=2)+'\n')
    print(proc.pid)

if __name__ == '__main__':
    main()

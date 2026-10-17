#!/usr/bin/env python3
"""Boot the bundled Android kernel under m1n1 on a USB-connected target Mac."""
import argparse
import gzip
import hashlib
import json
import os
import pathlib
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('m1n1', type=pathlib.Path,
                        help='Matching, already built m1n1 development directory on the receiving Mac')
    parser.add_argument('--device', help='PRIMARY proxy port, usually /dev/cu.usbmodemP_01')
    parser.add_argument('--prepare-only', action='store_true',
                        help='Assemble the guest without connecting to hardware')
    args = parser.parse_args()
    bundle = pathlib.Path(__file__).resolve().parent
    tree = args.m1n1.expanduser().resolve()
    binary = tree / 'build/m1n1.bin'
    chainload = tree / 'proxyclient/tools/chainload.py'
    run_guest = tree / 'proxyclient/tools/run_guest.py'
    for p in [binary, chainload, run_guest]:
        if not p.is_file():
            parser.error('Missing m1n1 component: ' + str(p))
    manifest = json.loads((bundle / 'manifest.json').read_text())
    for rel, expected in manifest['files_sha256'].items():
        actual = hashlib.sha256((bundle / rel).read_bytes()).hexdigest()
        if actual != expected:
            parser.error('Bundle checksum mismatch: ' + rel)
    image = gzip.decompress((bundle / 'Image.gz').read_bytes())
    if hashlib.sha256(image).hexdigest() != manifest['installed_kernel_sha256']:
        parser.error('Kernel differs from the installed, tested Image')
    bootargs = (bundle / 'bootargs.txt').read_text().strip()
    dtb = (bundle / 't8103-j293.dtb').read_bytes()
    for compatible in [b'apple,agx-t8103\0', b'apple,display-subsystem\0', b'apple,dcp\0']:
        if compatible not in dtb:
            parser.error('DTB is missing an Asahi driver compatible: ' + compatible.decode().rstrip('\0'))
    print('Matched Asahi DTB SHA-256:', hashlib.sha256(dtb).hexdigest(), flush=True)
    # This is the payload format used by the upstream run_guest_kernel helper.
    payload = bytearray(binary.read_bytes())
    payload += ('chosen.bootargs=' + bootargs + '\n').encode()
    payload += b'chosen.asahi,efi-system-partition=00000000-0000-4000-8000-000000000003\n'
    payload += dtb
    payload += (bundle / 'Image.gz').read_bytes()
    initrd = (bundle / 'initrd.img').read_bytes()
    payload += b'm1n1_initramfs' + len(initrd).to_bytes(4, 'little') + initrd
    guest = bundle / 'm1n1-googlebook-guest.bin'
    guest.write_bytes(payload)
    print('Guest prepared:', guest, '\nKernel SHA-256:', manifest['installed_kernel_sha256'], flush=True)
    if args.prepare_only:
        return
    env = os.environ.copy()
    if args.device:
        env['M1N1DEVICE'] = args.device
    print('Keep capture_uart.py running in a second terminal on the secondary UART.', flush=True)
    print('Chainloading matching m1n1 into target RAM...', flush=True)
    subprocess.run([sys.executable, str(chainload), '-r', str(binary)], env=env, check=True)
    print('Starting Linux under the hypervisor...', flush=True)
    subprocess.run([sys.executable, str(run_guest), '-r', str(guest)], env=env, check=True)


if __name__ == '__main__':
    main()

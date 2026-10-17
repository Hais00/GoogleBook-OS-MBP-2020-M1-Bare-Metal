#!/usr/bin/env python3
"""Boot the actual ARM64 kernel in QEMU and exercise Android early-init mounts."""
import argparse
import pathlib
import subprocess

BASE = pathlib.Path(__file__).resolve().parents[1]
QEMU = pathlib.Path('/opt/googlebook/host/Documents/M1 Reverse/.local/qemu/bin/qemu-system-aarch64')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('kernel', type=pathlib.Path)
    p.add_argument('--expect-fail', action='store_true')
    p.add_argument('--expect-cpuset-fail', action='store_true')
    p.add_argument('--expect-quota-fail', action='store_true')
    p.add_argument('--policy', action='store_true')
    p.add_argument('--name', default='early-android')
    a = p.parse_args()
    args = 'console=ttyAMA0 rdinit=/init loglevel=5 printk.devkmsg=on panic=0 enforcing=' + ('0' if a.policy else '1')
    if a.policy:
        args += ' -- --policy'
    cmd = [str(QEMU), '-machine', 'virt,gic-version=3', '-cpu', 'max',
           '-accel', 'tcg,thread=multi', '-smp', '2', '-m', '1024', '-nographic',
           '-monitor', 'none', '-no-reboot', '-kernel', str(a.kernel),
           '-initrd', str(BASE/'.work/selinux-smoke.cpio.gz'), '-append', args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        data, _ = proc.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        proc.kill()
        data, _ = proc.communicate()
    out = BASE/'.work'/('qemu-'+a.name+'.log')
    out.write_bytes(data)
    text = data.decode(errors='replace')
    for line in text.splitlines():
        if any(s in line for s in ['SELINUX_SMOKE_', 'CPUSET_V1_SMOKE_', 'DEVKMSG_SMOKE_', 'EXT4_QUOTA_SMOKE_', 'Active LSMs:', 'Enforcing state:', 'Kernel panic', 'qemu-system-aarch64:']):
            print(line)
    print('Log:', out)
    if a.expect_quota_fail:
        assert 'SELINUX_SMOKE_FAIL: mount ext4 with quota feature' in text, text[-3000:]
        print('Confirmed original failure mounting an ext4 filesystem with quota.')
    elif a.expect_cpuset_fail:
        assert 'SELINUX_SMOKE_FAIL: mount legacy cpuset v1' in text, text[-3000:]
        print('Confirmed original failure at legacy cpuset v1 mount.')
    elif a.expect_fail:
        assert 'SELINUX_SMOKE_FAIL: /sys/fs/selinux' in text, text[-3000:]
        print('Confirmed original failure at SELinux filesystem mount.')
    else:
        assert 'CPUSET_V1_SMOKE_PASS:' in text and 'DEVKMSG_SMOKE_PASS:' in text
        assert 'EXT4_QUOTA_SMOKE_PASS:' in text
        assert 'SELINUX_SMOKE_PASS:' in text, text[-3000:]
        if a.policy:
            assert 'original Android policy loaded' in text
        else:
            assert 'with enforcing=1' in text

if __name__ == '__main__':
    main()

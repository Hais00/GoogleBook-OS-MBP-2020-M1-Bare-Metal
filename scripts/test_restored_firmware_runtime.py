#!/usr/bin/env python3
"""Have Linux unpack the actual candidate CPIO and hash all firmware files.

Append offline Alpine tools after the candidate's *unaltered* CPIO archive.
The second archive adds a checker init and does not contain firmware paths.
QEMU has no physical disks or USB devices; its only export is a result folder.
"""
import gzip
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from project_paths import BASE, LARGE_WORK
from prepare_m1_install import entries, regular
from build_ram_bootstrap import pack
from firmware_manifest import repair_firmware_entries

INIT = b'''#!/bin/busybox sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mkdir -p /proc /sys /dev /mnt/result
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
timeout 15 mount -t 9p -o trans=virtio,version=9p2000.L result /mnt/result
python3 /firmware-runtime-check.py
echo GOS_FIRMWARE_MANIFEST_RUNTIME_PASS
exec /sbin/poweroff -f
'''

CHECKER = b'''import hashlib,json,stat
from pathlib import Path
expected=json.loads(Path('/firmware-runtime-expected.json').read_text())
for name,record in expected.items():
 p=Path('/')/name;s=p.lstat()
 assert stat.S_ISREG(s.st_mode) and s.st_nlink==1,name
 assert [s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode)]==record['metadata'],name
 with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
 assert actual==record['sha256'],name
Path('/mnt/result/result.json').write_text(json.dumps({'pass':True,'files':len(expected),'actual_linux_unpacked_hashes_and_metadata_match':True,'physical_hardware_qualified':False},indent=2)+'\\n')
print('FIRMWARE_CONTENTS_VERIFIED',len(expected),flush=True)
'''


def main():
    root = LARGE_WORK/'firmware-manifest-runtime'
    root.mkdir(exist_ok=False)
    candidate = LARGE_WORK/'android-initrd-firmware-restored/initrd.img'
    manifest = json.loads((candidate.parent/'manifest.json').read_text())
    compressed = candidate.read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == manifest['initrd_sha256']
    raw = gzip.decompress(compressed)
    original = BASE/'artifacts/GoogleBook-USB-Debug/initrd.img'
    source = {n: (n, v, d) for n, v, d in entries(gzip.decompress(original.read_bytes()))}
    repaired, _ = repair_firmware_entries(source)
    expected = {}
    for line in source['lib/firmware/.vendorfw.manifest'][2].decode().splitlines():
        name = 'lib/firmware/'+line.split()[1]
        _, values, data = repaired[name]
        expected[name] = {'sha256': hashlib.sha256(data).hexdigest(),
                          'metadata': [values[2], values[3], values[1] & 0o7777]}
    tools = []
    excluded = {'init', 'android-initrd.img', 'android-handoff.sh',
                'm1_ram_image_update.py', 'android_lp_state.py'}
    for name, values, data in entries(gzip.decompress((LARGE_WORK/'ram-bootstrap/initrd.img').read_bytes())):
        if name not in excluded and not name.startswith('lib/firmware'):
            tools.append((name, values, data))
    tools += [regular('init', INIT, 0o100755), regular('firmware-runtime-check.py', CHECKER),
              regular('firmware-runtime-expected.json', json.dumps(expected).encode())]
    fixture_raw = raw+pack(tools)
    assert fixture_raw[:len(raw)] == raw
    fixture = root/'test-initrd.img'
    fixture.write_bytes(gzip.compress(fixture_raw, compresslevel=1, mtime=0))
    control = Path(tempfile.mkdtemp(prefix='gos-firmware-test-', dir=Path.home()/'.local'))
    qmp = control/'qmp.sock'
    log = root/'kernel-uart.log'
    command = ['/opt/homebrew/bin/qemu-system-aarch64', '-name', 'firmware-manifest-runtime',
        '-machine', 'virt,accel=hvf,gic-version=3', '-cpu', 'host', '-smp', '2', '-m', '2048',
        '-display', 'none', '-monitor', 'none', '-no-reboot', '-nic', 'none',
        '-kernel', str(LARGE_WORK/'kernel19/Image'), '-initrd', str(fixture),
        '-append', 'console=ttyAMA0 loglevel=5 panic=0 rdinit=/init', '-serial', 'file:'+str(log),
        '-qmp', 'unix:'+str(qmp)+',server=on,wait=off',
        '-fsdev', 'local,id=result,path='+str(root)+',security_model=none',
        '-device', 'virtio-9p-pci,fsdev=result,mount_tag=result']
    with (root/'qemu-host.log').open('wb') as out:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=out)
    state = {'pid': process.pid, 'command': command, 'physical_disks_attached': False,
        'candidate_cpio_prefix_preserved_byte_for_byte': True,
        'candidate_initrd_sha256': manifest['initrd_sha256'], 'expected_firmware_files': len(expected),
        'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest()}
    (root/'state.json').write_text(json.dumps(state, indent=2)+'\n')
    try:
        deadline = time.monotonic()+45
        while time.monotonic()<deadline and process.poll() is None:
            text = log.read_text(errors='replace') if log.exists() else ''
            if 'GOS_FIRMWARE_MANIFEST_RUNTIME_PASS' in text:
                break
            time.sleep(.2)
        assert (root/'result.json').is_file(), log
        result = json.loads((root/'result.json').read_text())
        assert result['pass'] and result['files'] == len(expected)
        state['pass'] = True
    finally:
        if process.poll() is None:
            try:
                with socket.socket(socket.AF_UNIX) as s:
                    s.settimeout(3)
                    s.connect(str(qmp))
                    f=s.makefile('rwb',buffering=0)
                    f.readline()
                    f.write(b'{"execute":"qmp_capabilities"}\n')
                    while b'"return"' not in f.readline():
                        pass
                    f.write(b'{"execute":"quit"}\n')
                process.wait(timeout=10)
            except Exception:
                process.terminate()
                process.wait(timeout=10)
        state['qemu_stopped'] = process.poll() is not None
        (root/'state.json').write_text(json.dumps(state, indent=2)+'\n')
    print('ACTUAL_LINUX_FIRMWARE_UNPACK_HASH_VALIDATION_PASS', len(expected), flush=True)


if __name__ == '__main__':
    main()

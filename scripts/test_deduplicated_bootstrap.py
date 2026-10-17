#!/usr/bin/env python3
"""Run the production thin-Android handoff and verify every reconstructed member."""
import gzip
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import time
from project_paths import LARGE_WORK
from build_ram_bootstrap import pack
from prepare_m1_install import entries, regular

CHECKER=b'''import hashlib,json,os,stat
from pathlib import Path
expected=json.loads(Path('/reconstruction-expected.json').read_text())
for name,e in expected.items():
 p=Path('/android')/name;s=p.lstat()
 assert [s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),stat.S_IFMT(s.st_mode)]==e['metadata'],(name,'metadata')
 if stat.S_ISREG(s.st_mode):assert hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256'],(name,'content')
 elif stat.S_ISLNK(s.st_mode):assert os.readlink(p)==e['link'],(name,'link')
Path('/mnt/outbox/reconstructed-tree-result.json').write_text(json.dumps({'pass':True,'members':len(expected),'original_Android_and_all_firmware_bytes_and_metadata_match':True,'physical_device_written':False},indent=2)+'\\n')
print('GOS_ANDROID_FULL_TREE_RECONSTRUCTION_PASS',len(expected),flush=True)
'''
INIT=b'''#!/bin/busybox sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mkdir -p /proc /sys /dev /mnt/inbox /mnt/outbox /android
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t 9p -o trans=virtio,version=9p2000.L,ro,cache=loose m1inbox /mnt/inbox
mount -t 9p -o trans=virtio,version=9p2000.L,cache=none m1outbox /mnt/outbox
exec /android-handoff.sh
'''
root=LARGE_WORK/'deduplicated-input22-bootstrap-test-v3';root.mkdir(exist_ok=False);(root/'inbox').mkdir()
bootstrap=LARGE_WORK/'ram-bootstrap-input22-deduplicated';manifest=json.loads((bootstrap/'manifest.json').read_text())
assert manifest['firmware_transported_once']
compressed=(bootstrap/'initrd.img').read_bytes();assert hashlib.sha256(compressed).hexdigest()==manifest['initrd_sha256']
members={n:(n,v,d) for n,v,d in entries(gzip.decompress(compressed))}
original=LARGE_WORK/'android-initrd-firmware-restored/initrd.img';raw=original.read_bytes();assert hashlib.sha256(raw).hexdigest()==manifest['full_android_initrd_sha256']
expected={}
for n,v,d in entries(gzip.decompress(raw)):
 r={'metadata':[v[2],v[3],stat.S_IMODE(v[1]),stat.S_IFMT(v[1])]}
 if stat.S_ISREG(v[1]):r['sha256']=hashlib.sha256(d).hexdigest()
 elif stat.S_ISLNK(v[1]):
  # Linux init/initramfs.c do_symlink uses symlink+chown; symlink mode is always0777.
  r['metadata'][2]=0o777;r['link']=d.decode()
 expected[n]=r
_,v,handoff=members['android-handoff.sh'];assert hashlib.sha256(handoff).hexdigest()==manifest['handoff_sha256']
assert b'cp -a /lib/firmware /android/lib/' in handoff
# Fixture observes immediately after production reconstruction; the original Android /init remains unchanged.
handoff=handoff.replace(b'test -x /android/init',b'python3 /reconstruction-check.py\ntest -x /android/init')
members['android-handoff.sh']=regular('android-handoff.sh',handoff,stat.S_IFREG|0o755)
members['init']=regular('init',INIT,stat.S_IFREG|0o755)
members['reconstruction-check.py']=regular('reconstruction-check.py',CHECKER)
members['reconstruction-expected.json']=regular('reconstruction-expected.json',json.dumps(expected).encode())
fixture=root/'initrd.img';fixture.write_bytes(gzip.compress(pack(list(members.values())),compresslevel=1,mtime=0))
command=['/opt/homebrew/bin/qemu-system-aarch64','-name','gos-input22-handoff-proof','-machine','virt,accel=hvf,gic-version=3','-cpu','host','-smp','2','-m','2048','-display','none','-monitor','none','-no-reboot','-nic','none','-kernel',str(LARGE_WORK/'kernel22/Image'),'-initrd',str(fixture),'-append','console=ttyAMA0 loglevel=5 panic=0 rdinit=/init androidboot.hardware=android-desktop androidboot.slot_suffix=_a','-serial','file:'+str(root/'kernel-uart.log'),'-fsdev','local,id=inbox,path='+str(root/'inbox')+',security_model=none','-device','virtio-9p-pci,fsdev=inbox,mount_tag=m1inbox','-fsdev','local,id=outbox,path='+str(root)+',security_model=none','-device','virtio-9p-pci,fsdev=outbox,mount_tag=m1outbox']
record={'command':command,'physical_disks_attached':False,'hardware_verified':False,'production_handoff_sha256':manifest['handoff_sha256']}
with (root/'host.log').open('wb') as stream:process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream)
try:
 deadline=time.monotonic()+60
 while time.monotonic()<deadline and process.poll() is None:
  text=(root/'kernel-uart.log').read_text(errors='replace') if (root/'kernel-uart.log').exists() else ''
  if ('init first stage started' in text or 'init: Failed to read vbmeta partitions.' in text) and 'GOS_ANDROID_FULL_TREE_RECONSTRUCTION_PASS' in text:break
  time.sleep(.2)
 text=(root/'kernel-uart.log').read_text(errors='replace');result=json.loads((root/'reconstructed-tree-result.json').read_text())
 assert result['pass'] and result['members']==len(expected)
 assert 'M1_ANDROID_HANDOFF_EXEC' in text and ('init first stage started' in text or 'init: Failed to read vbmeta partitions.' in text)
 assert 'BUG:' not in text and 'Internal error:' not in text
 record.update(pass_=True,android_first_stage_reached=True,members=len(expected),firmware_and_android_original_tree_verified=True)
finally:
 if process.poll() is None:process.terminate();process.wait(timeout=10)
 record['qemu_stopped']=process.poll() is not None;(root/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('DEDUPLICATED_FIRMWARE_ANDROID_HANDOFF_RUNTIME_PASS',len(expected))

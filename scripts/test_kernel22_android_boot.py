#!/usr/bin/env python3
"""Diskless boot of the exact kernel22 and original-firmware Android initrd."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import time
from project_paths import LARGE_WORK
from boot_config import BOOT_ARGS

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--kernel-version',type=int,default=22)
version=parser.parse_args().kernel_version
root=LARGE_WORK/('kernel'+str(version)+'-diskless-android-boot')
root.mkdir(exist_ok=False)
kernel=LARGE_WORK/('kernel'+str(version))/'Image';initrd=LARGE_WORK/'android-initrd-firmware-restored/initrd.img'
build=json.loads((kernel.parent/'clean-kernel-build.json').read_text());manifest=json.loads((initrd.parent/'manifest.json').read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(kernel)==build['files']['Image']['sha256'] and digest(initrd)==manifest['initrd_sha256']
command=['/opt/homebrew/bin/qemu-system-aarch64','-name','gos-kernel'+str(version)+'-offline','-machine','virt,accel=hvf,gic-version=3','-cpu','host','-smp','2','-m','2048','-display','none','-monitor','none','-no-reboot','-nic','none','-kernel',str(kernel),'-initrd',str(initrd),'-append',BOOT_ARGS+' console=ttyAMA0','-serial','file:'+str(root/'kernel-uart.log')]
record={'command':command,'kernel_sha256':digest(kernel),'initrd_sha256':digest(initrd),'physical_disks_attached':False,'hardware_verified':False}
with (root/'host.log').open('wb') as stream:process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream)
record['pid']=process.pid
try:
 deadline=time.monotonic()+45
 while time.monotonic()<deadline and process.poll() is None:
  text=(root/'kernel-uart.log').read_text(errors='replace') if (root/'kernel-uart.log').exists() else ''
  if 'First stage init' in text or 'init first stage' in text or 'init first stage started' in text:break
  time.sleep(.2)
 text=(root/'kernel-uart.log').read_text(errors='replace')
 assert 'init first stage started' in text or 'init first stage' in text or 'First stage init' in text,text[-4000:]
 assert 'BUG:' not in text and 'Internal error:' not in text
 record['android_first_stage_init_reached']=True
 record['scope']='Exact kernel and initrd boot reach real Android first-stage init. No physical M1 input/display drivers are qualified by QEMU.'
finally:
 if process.poll() is None:process.terminate();process.wait(timeout=10)
 record['qemu_stopped']=process.poll() is not None
 (root/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print('KERNEL'+str(version)+'_REAL_ANDROID_FIRST_STAGE_DISKLESS_BOOT_PASS')

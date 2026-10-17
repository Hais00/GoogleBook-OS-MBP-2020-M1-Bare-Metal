#!/usr/bin/env python3
"""Verify exact early firmware bytes using the production kernel in a diskless CPU VM."""
import argparse,gzip,json,hashlib,re,subprocess,time
from pathlib import Path
from project_paths import WORK,LARGE_WORK
from build_ram_bootstrap import pack
from prepare_m1_install import regular
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bootstrap-directory',type=Path,required=True);p.add_argument('--output-directory',type=Path,required=True);p.add_argument('--kernel-version',type=int,default=24);a=p.parse_args();out=a.output_directory;out.mkdir();manifest=json.loads((a.bootstrap_directory/'manifest.json').read_text());data=(a.bootstrap_directory/'initrd.img').read_bytes();assert hashlib.sha256(data).hexdigest()==manifest['initrd_sha256'];fw=json.loads((WORK/'avd-fw-build.json').read_text());assert re.fullmatch('[0-9a-f]{64}',fw['sha256']) and fw['vectors_address']==0
script=('''#!/bin/busybox sh
set -eu
export PATH=/usr/bin:/usr/sbin:/bin:/sbin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
test "$(sha256sum /lib/firmware/apple/avd-fw-v2-t0.bin | cut -d ' ' -f 1)" = '''+fw['sha256']+'''
echo ACTUAL_KERNEL_EARLY_AVD_FIRMWARE_SHA_PASS
exec /sbin/poweroff -f
''').encode();fixture=data+gzip.compress(pack([regular('init',script,0o100755)]),compresslevel=1,mtime=0);(out/'initrd.img').write_bytes(fixture);kernel=LARGE_WORK/('kernel'+str(a.kernel_version))/'Image'
cmd=['/opt/homebrew/bin/qemu-system-aarch64','-machine','virt,accel=hvf,gic-version=3','-cpu','host','-smp','2','-m','1024','-display','none','-monitor','none','-no-reboot','-nic','none','-kernel',str(kernel),'-initrd',str(out/'initrd.img'),'-append','console=ttyAMA0 loglevel=4 panic=0 rdinit=/init','-serial','file:'+str(out/'kernel-uart.log')]
with (out/'host.log').open('wb') as log:process=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
r={'command':cmd,'pid':process.pid,'physical_disks_attached':False,'AVD_hardware_tested':False,'bootstrap_manifest':str(a.bootstrap_directory/'manifest.json'),'actual_firmware_sha256':fw['sha256'],'kernel_sha256':hashlib.sha256(kernel.read_bytes()).hexdigest()}
try:
 end=time.monotonic()+120
 while process.poll() is None and time.monotonic()<end:
  text=(out/'kernel-uart.log').read_text(errors='replace') if (out/'kernel-uart.log').exists() else ''
  if 'ACTUAL_KERNEL_EARLY_AVD_FIRMWARE_SHA_PASS' in text:break
  time.sleep(.2)
 r['pass']='ACTUAL_KERNEL_EARLY_AVD_FIRMWARE_SHA_PASS' in (out/'kernel-uart.log').read_text(errors='replace');assert r['pass']
finally:
 if process.poll() is None:process.terminate();process.wait(timeout=10)
 r['qemu_stopped']=process.poll() is not None;(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print('KERNEL_ACTUAL_EARLY_FIRMWARE_BYTES_PASS')

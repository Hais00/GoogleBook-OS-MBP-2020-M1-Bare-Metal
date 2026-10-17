#!/usr/bin/env python3
"""Have the exact production Kernel22 read every file of the compressed vendor candidate.

Only saved regular files are attached to QEMU, read-only. This verifies the
kernel filesystem reader; Android SELinux/HAL and optical tests are separate.
"""
import gzip
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import time
from project_paths import LARGE_WORK
from build_ram_bootstrap import pack
from prepare_m1_install import regular

MAINT=Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance')
ROOT=LARGE_WORK/'vendor9-erofs-kernel22-runtime'
IMAGE=MAINT/'build/vendor-generation9-input.erofs'
CHECKER=b'''import hashlib,json,os,stat
from pathlib import Path
root=Path('/mnt/vendor');expected=json.loads(Path('/vendor-expected.json').read_text())
assert len(expected)>3000
seen={str(p.relative_to(root)) for p in [root]+sorted(root.rglob('*'))}
assert seen==set(expected),('inode inventory differs',len(seen),len(expected))
regular=0
for name,e in expected.items():
 p=root/name;s=p.lstat()
 assert [s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),stat.S_IFMT(s.st_mode)]==[e['uid'],e['gid'],e['mode'],e['kind']],(name,'metadata')
 if stat.S_ISREG(s.st_mode):
  with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
  assert actual==e['sha256'],(name,'content hash');regular+=1
 elif stat.S_ISLNK(s.st_mode):assert os.readlink(p)==e['link'],(name,'symlink target')
assert regular>2600
Path('/mnt/result/result.json').write_text(json.dumps({'pass':True,'same_production_kernel_compressed_payloads_verified':True,'inodes':len(seen),'regular_files_hashed':regular,'owners_modes_types_and_symlinks_match':True,'security_xattrs_scope':'Verified separately by full EROFS readback in the build VM; this fixture does not load Android SELinux policy','physical_device_written':False},indent=2)+'\\n')
print('GOS_KERNEL22_EROFS_ALL_VENDOR_PAYLOADS_PASS',len(seen),regular,flush=True)
'''
INIT=b'''#!/bin/busybox sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mkdir -p /proc /sys /dev /mnt/vendor /mnt/result
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
[ "$(cat /sys/class/block/vda/ro)" = 1 ]
mount -t erofs -o ro /dev/vda /mnt/vendor
mount -t 9p -o trans=virtio,version=9p2000.L,cache=none result /mnt/result
python3 /vendor-check.py
echo GOS_KERNEL22_EROFS_RUNTIME_FINISHED
exec /sbin/poweroff -f
'''

def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
 global ROOT,IMAGE
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--kernel-version',type=int,default=22)
 parser.add_argument('--image',type=Path,required=True)
 parser.add_argument('--validation',type=Path,required=True)
 parser.add_argument('--readback',type=Path,required=True)
 parser.add_argument('--compression-label',required=True)
 parser.add_argument('--output-directory',type=Path,default=ROOT)
 options=parser.parse_args();ROOT=options.output_directory;IMAGE=options.image
 assert IMAGE.is_file() and stat.S_ISREG(IMAGE.stat().st_mode)
 ROOT.mkdir(exist_ok=False)
 validation=json.loads(options.validation.read_text())
 assert validation['pass'] and digest(IMAGE)==validation['sha256']
 kernel=LARGE_WORK/('kernel'+str(options.kernel_version))/'Image';build=json.loads((kernel.parent/'clean-kernel-build.json').read_text())
 assert digest(kernel)==build['files']['Image']['sha256']
 expected=json.loads(options.readback.read_text())
 assert len(expected)==validation['entries']
 original=LARGE_WORK/'ram-bootstrap-input22-deduplicated/initrd.img';proof=json.loads((original.parent/'manifest.json').read_text());assert digest(original)==proof['initrd_sha256']
 marker=('GOS_KERNEL'+str(options.kernel_version)+'_EROFS_RUNTIME_FINISHED')
 init=INIT.replace(b'KERNEL22',('KERNEL'+str(options.kernel_version)).encode())
 checker=CHECKER.replace(b'KERNEL22',('KERNEL'+str(options.kernel_version)).encode())
 additions=[regular('init',init,stat.S_IFREG|0o755),regular('vendor-check.py',checker),regular('vendor-expected.json',json.dumps(expected).encode())]
 fixture=ROOT/'initrd.img'
 # Linux supports concatenated initramfs gzip members. Original tools are kept
 # byte-for-byte; the second member changes only the fixture init/checker.
 fixture.write_bytes(original.read_bytes()+gzip.compress(pack(additions),compresslevel=1,mtime=0))
 command=['/opt/homebrew/bin/qemu-system-aarch64','-name','kernel'+str(options.kernel_version)+'-erofs-vendor-proof','-machine','virt,accel=hvf,gic-version=3','-cpu','host','-smp','2','-m','2048','-display','none','-monitor','none','-no-reboot','-nic','none','-kernel',str(kernel),'-initrd',str(fixture),'-append','console=ttyAMA0 loglevel=5 panic=0 rdinit=/init','-serial','file:'+str(ROOT/'kernel-uart.log'),'-drive','file='+str(IMAGE)+',if=none,id=vendor,format=raw,readonly=on','-device','virtio-blk-pci,drive=vendor','-fsdev','local,id=result,path='+str(ROOT)+',security_model=none','-device','virtio-9p-pci,fsdev=result,mount_tag=result']
 state={'command':command,'compression_recipe_label':options.compression_label,'kernel_sha256':digest(kernel),'image_sha256':validation['sha256'],'physical_disks_attached':False,'physical_device_written':False,'hardware_verified':False}
 with (ROOT/'host.log').open('wb') as out:process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=out)
 state['pid']=process.pid;(ROOT/'state.json').write_text(json.dumps(state,indent=2)+'\n')
 try:
  deadline=time.monotonic()+90
  while time.monotonic()<deadline and process.poll() is None:
   text=(ROOT/'kernel-uart.log').read_text(errors='replace') if (ROOT/'kernel-uart.log').exists() else ''
   if marker in text:break
   time.sleep(.2)
  result=json.loads((ROOT/'result.json').read_text());assert result['pass'] and result['inodes']==validation['entries']
  state['pass']=True
 finally:
  if process.poll() is None:process.terminate();process.wait(timeout=10)
  state['qemu_stopped']=process.poll() is not None;(ROOT/'state.json').write_text(json.dumps(state,indent=2)+'\n')
 print('PRODUCTION_KERNEL'+str(options.kernel_version)+'_ACTUAL_EROFS_VENDOR_ALL_FILES_PASS')


if __name__=='__main__':main()

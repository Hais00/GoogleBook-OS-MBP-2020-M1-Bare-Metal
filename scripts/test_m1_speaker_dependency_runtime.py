#!/usr/bin/env python3
"""Diskless Bionic smoke test of separate ALSA/speakersafetyd dependency.
Never attaches physical sound, radio, or block devices; this is not an acoustic
or thermal-model hardware qualification.
"""
import hashlib,json,re,shutil,socket,subprocess,time
from pathlib import Path
from project_paths import WORK,LARGE_WORK
ROOT=LARGE_WORK/'speaker-dependency-local-runtime'
CONTROL=Path.home()/'.local/gos-speaker-dependency-test'
def main():
 ROOT.mkdir(exist_ok=True);CONTROL.mkdir(exist_ok=True)
 fixture=LARGE_WORK/'audio-software-local-runtime-r11/root'
 assert (fixture/'system/bin/linker64').exists()
 receipt=json.loads((WORK/'speakersafetyd-android-build.json').read_text())
 binary=Path(receipt['binary']);alsa=Path('/opt/googlebook/kernel-build/alsa-android-a47c8bc3fef1/stage/vendor/lib64/libasound.so')
 for p in [binary,alsa]:shutil.copyfile(p,ROOT/p.name)
 serial=CONTROL/'serial.sock';qmp=CONTROL/'qmp.sock'
 assert not serial.exists() and not qmp.exists(),'Inspect prior VM before reuse'
 kernel=LARGE_WORK/'kernel23/Image'
 cmd=['/opt/homebrew/bin/qemu-system-aarch64','-name','gos-speaker-dependency-cpu-test','-machine','virt,accel=hvf,gic-version=3','-cpu','host','-smp','2','-m','1024','-display','none','-monitor','none','-no-reboot','-nic','none','-kernel',str(kernel),'-initrd',str(LARGE_WORK/'ram-bootstrap/initrd.img'),'-append','console=ttyAMA0 loglevel=4 panic=0 rdinit=/bin/sh selinux=1 enforcing=0','-chardev',f'socket,id=console,path={serial},server=on,wait=off,logfile={ROOT}/kernel-uart.log','-serial','chardev:console','-qmp',f'unix:{qmp},server=on,wait=off','-fsdev',f'local,id=fixture,path={fixture},security_model=none,readonly=on','-device','virtio-9p-pci,fsdev=fixture,mount_tag=fixture','-fsdev',f'local,id=artifacts,path={ROOT},security_model=none,readonly=on','-device','virtio-9p-pci,fsdev=artifacts,mount_tag=artifacts']
 result={'command':cmd,'physical_disks_attached':False,'sound_devices_attached':False,'hardware_qualified':False,'kernel_sha256':hashlib.sha256(kernel.read_bytes()).hexdigest(),'binary_sha256':receipt['sha256'],'alsa_sha256':hashlib.sha256(alsa.read_bytes()).hexdigest()}
 with (ROOT/'qemu-host.log').open('wb') as log:p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
 result['pid']=p.pid;(ROOT/'state.json').write_text(json.dumps(result,indent=2)+'\n')
 try:
  deadline=time.monotonic()+20
  while not serial.exists() and time.monotonic()<deadline:assert p.poll() is None;time.sleep(.1)
  with socket.socket(socket.AF_UNIX) as s:
   s.connect(str(serial));s.settimeout(.2);data=b''
   deadline=time.monotonic()+20
   while time.monotonic()<deadline:
    try:data+=s.recv(65536)
    except TimeoutError:pass
    if b'/ # ' in data or b"can't access tty" in data:break
   command='mount -t devtmpfs devtmpfs /dev; mount -t proc proc /proc; mkdir -p /root /artifacts; mount -t 9p -o trans=virtio,version=9p2000.L,cache=loose,ro fixture /root; mount -t 9p -o trans=virtio,version=9p2000.L,cache=loose,ro artifacts /artifacts; mount -t tmpfs tmpfs /root/tmp; mount -t tmpfs tmpfs /root/dev; cp -a /dev/null /root/dev/null; mount --bind /proc /root/proc; mkdir /root/tmp/speaker-test; cp /artifacts/speakersafetyd /artifacts/libasound.so /root/tmp/speaker-test/; chmod 755 /root/tmp/speaker-test/speakersafetyd; test ! -e /root/dev/snd || exit 90; LD_LIBRARY_PATH=/tmp/speaker-test chroot /root /tmp/speaker-test/speakersafetyd --version; echo SPEAKER_VERSION_RC=$?; LD_LIBRARY_PATH=/tmp/speaker-test chroot /root /tmp/speaker-test/speakersafetyd --help; echo SPEAKER_HELP_RC=$?; LD_LIBRARY_PATH=/tmp/speaker-test chroot /root /tmp/speaker-test/speakersafetyd --config-path /tmp/no-config; echo SPEAKER_NO_HARDWARE_RC=$?; echo SPEAKER_DEPENDENCY_TEST_END\n'
   s.sendall(command.encode());deadline=time.monotonic()+25
   while time.monotonic()<deadline:
    try:data+=s.recv(65536)
    except TimeoutError:pass
    if re.search(rb'[\r\n]SPEAKER_DEPENDENCY_TEST_END\r?\n',data):break
   (ROOT/'guest-console.log').write_bytes(data)
   assert re.search(rb'[\r\n]SPEAKER_VERSION_RC=0\r?\n',data),data[-3500:]
   assert re.search(rb'[\r\n]SPEAKER_HELP_RC=0\r?\n',data),data[-3500:]
   error=re.search(rb'[\r\n]SPEAKER_NO_HARDWARE_RC=(\d+)\r?\n',data);assert error and int(error[1])!=0
   assert b'Could not read device tree compatible' in data,data[-3500:]
   result.update(passed=True,version_help_executed_in_Bionic=True,missing_hardware_fails_before_control_access=True,physical_playback_tested=False)
 finally:
  try:
   with socket.socket(socket.AF_UNIX) as s:
    s.connect(str(qmp));s.recv(4096);s.sendall(b'{"execute":"qmp_capabilities"}\n');s.recv(4096);s.sendall(b'{"execute":"quit"}\n')
  except OSError:pass
  p.wait(timeout=10);result['vm_stopped']=True
  (ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print('SPEAKER_DEPENDENCY_BIONIC_RUNTIME_PASS')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Stage the separate native ALSA primary and Asahi protector.
Image preparation only. Hardware qualification is recorded separately.
"""
import hashlib,json,shutil,stat,subprocess
from pathlib import Path
from project_paths import WORK,BASE,LARGE_WORK
from stage_native_egl import clone_tree,copy_labeled,getlabel
from stage_m1_input import label
from build_m1_native_audio_abi import GROUPS
STAGE=WORK/'vendor-native-audio13-r2-stage'
PARENT=WORK/'vendor-btaudio12-stage'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not STAGE.exists(),'Refusing to overwrite another stage'
 test=json.loads((LARGE_WORK/'native-primary-audio-local-runtime-r8/result.json').read_text());assert test['pass'] and test['qemu_stopped']
 build=WORK/'native-primary-audio-build';nr=json.loads((build/'native-build.json').read_text());pr=json.loads((WORK/'speakersafetyd-android-build.json').read_text())
 assert digest(Path(nr['binary']))==nr['sha256'];assert digest(Path(pr['binary']))==pr['sha256']
 clone_tree(PARENT,STAGE)
 def write(name,text,kind='u:object_r:vendor_configs_file:s0'):
  p=STAGE/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);p.chmod(0o644);label(p,kind)
 def cp(source,name,kind,mode=0o644):
  p=STAGE/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,p);p.chmod(mode);label(p,kind)
 executable='u:object_r:hal_audio_default_exec:s0';library='u:object_r:vendor_file:s0';config='u:object_r:vendor_configs_file:s0'
 cp(Path(nr['binary']),'bin/hw/android.hardware.audio.service.m1',executable,0o755)
 cp(Path(pr['binary']),'bin/hw/speakersafetyd-m1',executable,0o755)
 for _,_,n in GROUPS:cp(build/n,'lib64/'+n,library)
 alsa=Path('/opt/googlebook/kernel-build/alsa-android-a47c8bc3fef1/stage/vendor')
 cp(alsa/'lib64/libasound.so','lib64/libasound.so',library)
 for s in (alsa/'etc/alsa-m1').rglob('*'):
  name=Path('etc/alsa-m1')/s.relative_to(alsa/'etc/alsa-m1')
  if s.is_dir():(STAGE/name).mkdir(parents=True,exist_ok=True);label(STAGE/name,config)
  elif s.is_file():cp(s,str(name),config)
 cp(Path(pr['config']),'etc/m1-audio/speakersafetyd/apple/j293.conf',config)
 asahi=WORK/'references/xerj-code/corpora/android-asahi-audio/asahi-audio'
 for n in ['front-48.wav','rear-48.wav']:cp(asahi/'firs/j293'/n,'etc/m1-audio/j293/'+n,config)
 # Preserve the dependency notices and a reproducible source/patch inventory.
 cp(asahi/'LICENSE','etc/m1-audio/licenses/asahi-audio-LICENSE',config)
 protector=Path(pr['source']);license=next(p for p in [protector/'LICENSE',protector/'COPYING'] if p.exists())
 cp(license,'etc/m1-audio/licenses/speakersafetyd-LICENSE',config)
 alsasource=WORK/'references/xerj-code/corpora/alsa-native-userspace/alsa-lib'
 cp(alsasource/'COPYING','etc/m1-audio/licenses/alsa-lib-COPYING',config)
 write('etc/m1-audio/integration.json',json.dumps({'native_core_version':3,'native_core_hash':nr['abi_core_hash'],'native_binary_sha256':nr['sha256'],'protector':pr,'physical_playback_qualified':False,'output_peak_ceiling':0.125,'sample_rate':48000,'application_channels':2,'physical_channels':4,'scope':'J293 protected speakers; supplied Google Rust/C++ Bluetooth providers retained unchanged; no physical mic advertised'},indent=2)+'\n')
 write('etc/vintf/manifest/m1-native-audio.xml','''<manifest version="9.0" type="device">
 <hal format="aidl"><name>android.hardware.audio.core</name><version>3</version><fqname>IModule/m1</fqname></hal>
</manifest>
''')
 write('etc/init/m1-native-audio.rc','''on post-fs-data
    mkdir /dev/speakersafetyd 0700 audioserver audio
    restorecon_recursive /dev/speakersafetyd

service vendor.audio-m1-safety /vendor/bin/hw/speakersafetyd-m1 --config-path /vendor/etc/m1-audio/speakersafetyd
    class hal
    user audioserver
    group audio
    capabilities SYS_NICE
    rlimit rtprio 10 10
    stdio_to_kmsg
    onrestart restart vendor.audio-m1

service vendor.audio-m1 /vendor/bin/hw/android.hardware.audio.service.m1
    class hal
    user audioserver
    group audio
    capabilities SYS_NICE
    interface aidl android.hardware.audio.core.IModule/m1
    rlimit rtprio 10 10
    onrestart restart audioserver
''')
 cil=STAGE/'etc/selinux/vendor_sepolicy.cil'
 cil.write_text(cil.read_text()+'''
; Native M1 audio: narrowly label the actual board identity and tmpfs boot flag.
(type vendor_m1_audio_model_file)
(roletype object_r vendor_m1_audio_model_file)
(typeattributeset fs_type (vendor_m1_audio_model_file))
(typeattributeset sysfs_type (vendor_m1_audio_model_file))
(genfscon sysfs "/firmware/devicetree/base/compatible" (u object_r vendor_m1_audio_model_file ((s0) (s0))))
(allow hal_audio_default sysfs_202604 (dir (search read open getattr)))
(allow hal_audio_default vendor_m1_audio_model_file (file (read open getattr)))
(type vendor_m1_audio_runtime_file)
(roletype object_r vendor_m1_audio_runtime_file)
(typeattributeset file_type (vendor_m1_audio_runtime_file))
(typeattributeset dev_type (vendor_m1_audio_runtime_file))
(allow hal_audio_default vendor_m1_audio_runtime_file (dir (search read open getattr write add_name remove_name)))
(allow hal_audio_default vendor_m1_audio_runtime_file (file (create read open getattr write unlink)))
(typetransition hal_audio_default vendor_m1_audio_runtime_file file vendor_m1_audio_runtime_file)
''')
 fc=STAGE/'etc/selinux/vendor_file_contexts';fc.write_text(fc.read_text()+r'''
/vendor/bin/hw/android\.hardware\.audio\.service\.m1 u:object_r:hal_audio_default_exec:s0
/vendor/bin/hw/speakersafetyd-m1 u:object_r:hal_audio_default_exec:s0
/dev/speakersafetyd(/.*)? u:object_r:vendor_m1_audio_runtime_file:s0
''')
 sc=STAGE/'etc/selinux/vendor_service_contexts';sc.write_text(sc.read_text()+'\nandroid.hardware.audio.core.IModule/m1 u:object_r:hal_audio_service:s0\n')
 # Assign every new directory the normal vendor config/bin/lib context too.
 for p in STAGE.rglob('*'):
  if p.is_dir():
   try:getlabel(p)
   except OSError:label(p,config if str(p.relative_to(STAGE)).startswith('etc') else library)
 changed=[];added=[]
 for p in STAGE.rglob('*'):
  if p.is_file() and not p.is_symlink():
   old=PARENT/p.relative_to(STAGE)
   if not old.exists():added.append(str(p.relative_to(STAGE)))
   elif digest(p)!=digest(old):changed.append(str(p.relative_to(STAGE)))
 assert set(changed)=={'etc/selinux/vendor_file_contexts','etc/selinux/vendor_service_contexts','etc/selinux/vendor_sepolicy.cil'},changed
 assert digest(STAGE/'bin/hw/googlebook-audio-hal')==digest(PARENT/'bin/hw/googlebook-audio-hal')
 result={'stage':str(STAGE),'parent':str(PARENT),'added':sorted(added),'changed':sorted(changed),'native':nr,'protector':pr,'real_Binder_FMQ_ALSA_loopback_pass':True,'policy_compile_pass':False,'physical_device_written':False,'hardware_verified':False}
 (WORK/'native-audio13-stage.json').write_text(json.dumps(result,indent=2)+'\n');print('M1_NATIVE_AUDIO13_STAGE_PASS',len(added))
if __name__=='__main__':main()

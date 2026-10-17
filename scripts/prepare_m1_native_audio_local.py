#!/usr/bin/env python3
import hashlib,json,shutil,subprocess
from pathlib import Path
from project_paths import BASE,WORK,LARGE_WORK,SYSTEM_ORIGINAL,NDK
from build_m1_native_audio_abi import GROUPS
ROOT=LARGE_WORK/'native-primary-audio-local-runtime-r9'
def main():
 assert not ROOT.exists();ROOT.mkdir()
 original=LARGE_WORK/'audio-software-local-runtime-r11/root';root=ROOT/'root'
 subprocess.run(['/bin/cp','-cR',str(original),str(root)],check=True)
 build=WORK/'native-primary-audio-build'
 files=[(build/n,'vendor/lib64/'+n) for _,_,n in GROUPS]+[(build/n,'vendor/bin/hw/'+n) for n in ['audio-service-local-loopback-test','audio-local-pcm-probe']]
 files += [(Path('/opt/googlebook/kernel-build/alsa-android-a47c8bc3fef1/stage/vendor/lib64/libasound.so'),'vendor/lib64/libasound.so')]
 receipt=[]
 for src,name in files:
  dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);dest.chmod(0o755 if '/bin/' in name else 0o644);receipt.append({'source':str(src),'target':name,'sha256':hashlib.sha256(src.read_bytes()).hexdigest()})
 shutil.copytree('/opt/googlebook/kernel-build/alsa-android-a47c8bc3fef1/stage/vendor/etc/alsa-m1',root/'vendor/etc/alsa-m1')
 # Resolve real ELF dependencies which were not used by the prior fixture.
 queue=[root/name for _,name in files];seen=set()
 while queue:
  p=queue.pop();output=subprocess.check_output([NDK/'bin/llvm-readelf','-d',p],text=True)
  import re
  for name in re.findall(r'\(NEEDED\).*?\[(.*?)\]',output):
   if name in seen:continue
   seen.add(name)
   if (root/'vendor/lib64'/name).exists() or (root/'system/lib64'/name).exists():continue
   source=next((p for p in [WORK/'vendor-btaudio12-stage/lib64'/name,SYSTEM_ORIGINAL/'lib64'/name] if p.is_file()),None);assert source,name
   target=root/('vendor/lib64/' if 'vendor-btaudio12-stage' in str(source) else 'system/lib64/')/name
   shutil.copyfile(source,target);queue.append(target)
 (root/'vendor/etc/vintf/manifest/m1-local-test.xml').write_text('<manifest version="1.0" type="device"><hal format="aidl"><name>android.hardware.audio.core</name><version>3</version><interface><name>IModule</name><instance>m1_test</instance></interface></hal></manifest>\n')
 shutil.copyfile(BASE/'scripts/native_audio_local_runtime.sh',root/'test.sh')
 module=Path('/opt/googlebook/kernel-build/linux-asahi/sound/drivers/snd-aloop.ko');shutil.copyfile(module,ROOT/module.name)
 (ROOT/'preparation.json').write_text(json.dumps({'files':receipt,'test_only':True,'physical_disks':False,'physical_audio':False,'module_sha256':hashlib.sha256(module.read_bytes()).hexdigest()},indent=2)+'\n')
 print('NATIVE_PRIMARY_LOCAL_FIXTURE_READY')
if __name__=='__main__':main()

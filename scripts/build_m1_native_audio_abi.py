#!/usr/bin/env python3
"""Build genuine frozen AOSP audio ABI for an isolated native primary process.
No service is registered by this build. These libraries never replace the
provided Google service libraries, which use a newer private implementation.
"""
import concurrent.futures,hashlib,json,subprocess
from project_paths import BASE,WORK,NDK,VNDK,SYSTEM_ORIGINAL
REF=WORK/'references/native-audio-aosp16'
ROOT=WORK/'native-primary-audio-build'
GROUPS=[('media-audio-aidl/aidl_api/android.media.audio.common.types/4',4,'libm1audio_types_v4.so'),
('common-aidl/aidl_api/android.hardware.common/2',2,'libm1audio_common_v2.so'),
('fmq-aidl/aidl_api/android.hardware.common.fmq/1',1,'libm1audio_fmq_v1.so'),
('audio-aidl/aidl_api/android.hardware.audio.common/4',4,'libm1audio_metadata_v4.so'),
('audio-aidl/aidl_api/android.hardware.audio.core.sounddose/3',3,'libm1audio_sounddose_v3.so'),
('media-audio-aidl/aidl_api/android.media.audio.eraser.types/1',1,'libm1audio_eraser_v1.so'),
('audio-aidl/aidl_api/android.hardware.audio.effect/3',3,'libm1audio_effect_v3.so'),
('audio-aidl/aidl_api/android.hardware.audio.core/3',3,'libm1audio_core_v3.so')]
def run(cmd,log):
 r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);log.parent.mkdir(parents=True,exist_ok=True);log.write_text(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError(str(log)+'\n'+r.stderr[-4000:])
def main():
 ROOT.mkdir(exist_ok=True);gen=ROOT/'generated';inc=gen/'include'
 aidlroots=[REF/p for p,_,_ in GROUPS]+[WORK/'references/wifi-aosp-5688f7eb1e11/binder-aidl']
 for path,ver,name in GROUPS:
  frozen=REF/path; files=sorted(frozen.rglob('*.aidl'));assert files
  api_hash=(frozen/'.hash').read_text().splitlines()[-1]
  run([BASE/'build/aosp/aidl','--lang=ndk','--structured','--stability=vintf','--min_sdk_version=34','--version='+str(ver),'--hash='+api_hash]+['-I'+str(p) for p in aidlroots]+['-o',gen/name/'src','-h',inc]+files,ROOT/(name+'.aidl.log'))
 compiler=NDK/'bin/aarch64-linux-android35-clang++'
 include=[inc]+[WORK/'aosp-binder-ndk'/p for p in ['include_cpp','include_ndk','include_platform']]
 cxx=[compiler,'-std=c++17','-O2','-fPIC','-fno-rtti','-ffunction-sections','-fdata-sections','-nostdinc++','-isystem',VNDK/'external/libcxx/include']+['-I'+str(p) for p in include]
 links=['-nostdlib++','-Wl,--no-undefined','-Wl,-z,max-page-size=16384','-Wl,--gc-sections']
 for d in [ROOT,WORK/'vendor-btaudio12-stage/lib64',SYSTEM_ORIGINAL/'lib64']:links+=['-L'+str(d),'-Wl,-rpath-link,'+str(d)]
 outputs=[]
 for path,ver,name in GROUPS:
  def one(s):
   obj=ROOT/'objects'/name/(s.stem+'.o');obj.parent.mkdir(parents=True,exist_ok=True);run(cxx+['-c',s,'-o',obj],obj.with_suffix('.log'));return obj
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:objs=list(pool.map(one,sorted((gen/name/'src').rglob('*.cpp'))))
  out=ROOT/name
  run([compiler,'-shared']+links+objs+outputs+['-lbinder_ndk','-l:libc++.so','-Wl,-soname,'+name,'-o',out],ROOT/(name+'.link.log'))
  outputs.append(out);print('NATIVE_AUDIO_FROZEN_ABI_PASS',name,flush=True)
 receipt={'service_implemented':False,'deployed':False,'metadata':'Actual frozen versions and hashes; no version/hash overrides','files':{str(p):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in outputs}}
 (ROOT/'abi-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()

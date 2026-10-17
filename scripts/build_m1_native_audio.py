#!/usr/bin/env python3
"""Build isolated AOSP V3 native primary using a real M1 ALSA driver."""
import concurrent.futures,hashlib,json,re,subprocess,shutil,argparse
from pathlib import Path
from project_paths import BASE,WORK,NDK,VNDK,SYSTEM_ORIGINAL
from build_m1_native_audio_abi import ROOT,REF,GROUPS,run
UP=REF/'audio-aidl/default'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--local-alsa-test',action='store_true');options=parser.parse_args()
 source=ROOT/'source';source.mkdir(exist_ok=True)
 shutil.copytree(UP/'include',source/'include',dirs_exist_ok=True)
 # Keep public reference byte-for-byte. Remove unused example factories and
 # optional sound-dose processor in our separate derivative; no dummy primary.
 s=(UP/'Module.cpp').read_text().replace('#include <algorithm>', '#include <algorithm>\n#include <cmath>')
 for name in ['ModuleBluetooth','ModulePrimary','ModuleRemoteSubmix','ModuleStub','ModuleUsb']:
  s=s.replace('#include "core-impl/'+name+'.h"\n','')
 a=s.index('std::shared_ptr<Module> Module::createInstance(');b=s.index('// static\nstd::optional<Module::Type>',a)
 s=s[:a]+s[b:]
 a=s.index('    if (!mSoundDose) {',s.index('ndk::ScopedAStatus Module::getSoundDose('));b=s.index('\n}\n',a)
 s=s[:a]+'    (void)_aidl_return;\n    return ndk::ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);'+s[b:]
 # Sound-dose is optional and the Android framework owns its fallback. Do not
 # require an optional implementation before opening an ordinary PCM stream.
 a=s.index('    std::shared_ptr<ISoundDose> soundDose;');b=s.index('    StreamContext temp;',a)
 s=s[:a]+s[b:]
 s=s.replace('mSoundDose.getInstance()', 'std::shared_ptr<sounddose::StreamDataProcessorInterface>{}')
 (source/'Module.cpp').write_text(s)
 headers=source/'include/core-impl';headers.mkdir(parents=True,exist_ok=True)
 h=(UP/'include/core-impl/Module.h').read_text().replace('    ChildInterface<sounddose::SoundDose> mSoundDose;\n','')
 (headers/'Module.h').write_text(h)
 h=(UP/'include/core-impl/SoundDose.h').read_text()
 h=h[:h.index('class SoundDose final')]+'} // namespace aidl::android::hardware::audio::core::sounddose\n'
 h=h.replace('#include <audio_utils/MelProcessor.h>\n','').replace('#include <audio_utils/mutex.h>\n','')
 (headers/'SoundDose.h').write_text(h)
 includes=[source/'include',REF/'libfmq/include',REF/'libfmq/base',ROOT/'generated/include',REF/'audio-aidl/common/include',UP/'include',REF/'liberror-include',REF/'media-audio-include',REF/'audio-utils-include',BASE/'scripts',Path('/opt/googlebook/kernel-build/alsa-android-a47c8bc3fef1/stage/vendor/include')]
 includes += [WORK/'aosp-binder-ndk'/p for p in ['include_cpp','include_ndk','include_platform']]
 for p in json.loads((BASE/'build/aosp/include-dirs.json').read_text()):
  if '/aosp-vndk' in p:includes.append(Path(str(VNDK)+p.split('/aosp-vndk',1)[1]))
 common=[NDK/'bin/aarch64-linux-android35-clang++','-std=c++20','-O2','-fPIC','-fno-rtti','-D_GNU_SOURCE','-DANDROID','-DBACKEND_NDK','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Wno-unused-parameter','-Wno-deprecated-declarations','-nostdinc++','-isystem',VNDK/'external/libcxx/include']+['-I'+str(p) for p in includes]
 if options.local_alsa_test:common+=['-DM1_AUDIO_LOCAL_ALSA_TEST']
 sources=[source/'Module.cpp',UP/'Stream.cpp',BASE/'scripts/m1_native_audio_configuration.cpp',REF/'audio-aidl/common/StreamWorker.cpp']
 sources += [BASE/'scripts/m1_native_audio.cpp',BASE/'scripts/m1_native_audio_pcm.cpp'] if (BASE/'scripts/m1_native_audio.cpp').exists() else []
 def one(p):
  obj=ROOT/('local-objects' if options.local_alsa_test else 'native-objects')/(p.stem+'.o');obj.parent.mkdir(exist_ok=True);run(common+['-c',p,'-o',obj],obj.with_suffix('.log'));return obj
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(one,sources))
 if not (BASE/'scripts/m1_native_audio.cpp').exists():print('NATIVE_AUDIO_AOSP_BASE_COMPILED');return
 links=['-nostdlib++','-Wl,--no-undefined','-Wl,-z,max-page-size=16384','-Wl,--gc-sections']
 for d in [ROOT,WORK/'vendor-btaudio12-stage/lib64',SYSTEM_ORIGINAL/'lib64',Path('/opt/googlebook/kernel-build/alsa-android-a47c8bc3fef1/stage/vendor/lib64')]:links+=['-L'+str(d),'-Wl,-rpath-link,'+str(d)]
 binary=ROOT/('audio-service-local-loopback-test' if options.local_alsa_test else 'android.hardware.audio.service.m1')
 libs=['libc++','libbinder_ndk','libbase','libcutils','liblog','libutils','libfmq','libhardware','libasound']
 run([common[0]]+links+objects+[ROOT/name for _,_,name in GROUPS]+['-l:'+n+'.so' for n in libs+['libm']]+['-o',binary],ROOT/('local-native-link.log' if options.local_alsa_test else 'native-link.log'))
 if options.local_alsa_test:
  obj=ROOT/'local-objects/m1_native_audio_local_probe.o'
  run(common+['-c',BASE/'scripts/m1_native_audio_local_probe.cpp','-o',obj],obj.with_suffix('.log'))
  run([common[0]]+links+[obj]+[ROOT/name for _,_,name in GROUPS]+['-l:'+n+'.so' for n in libs+['libm']]+['-o',ROOT/'audio-local-pcm-probe'],ROOT/'local-probe-link.log')
 receipt={'binary':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'deployed':False,'hardware_verified':False,'abi_core_version':3,'abi_core_hash':(REF/'audio-aidl/aidl_api/android.hardware.audio.core/3/.hash').read_text().strip().splitlines()[-1],'reference_commit':'5688f7eb1e117ed26e642a695de300b7683acb87'}
 (ROOT/('local-native-build.json' if options.local_alsa_test else 'native-build.json')).write_text(json.dumps(receipt,indent=2)+'\n');print('M1_NATIVE_PRIMARY_AUDIO_BUILD_PASS')
if __name__=='__main__':main()

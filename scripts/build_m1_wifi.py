#!/usr/bin/env python3
"""Build a matched public frozen Wi-Fi V3 service and native Linux backend."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL

REF=WORK/'references/wifi-aosp-5688f7eb1e11'
ROOT=WORK/'native-radio-build/wifi'
SUPPORT=WORK/'references/aosp-wifi-hal-e7e8646a896f/libwifi_hal/include'
VENDOR=WORK/'vendor-input-stage/lib64'

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args, log):
    r=subprocess.run(list(map(str,args)),capture_output=True,text=True)
    log.parent.mkdir(parents=True,exist_ok=True);log.write_text(r.stdout+r.stderr)
    if r.returncode: raise RuntimeError(str(log)+'\n'+r.stderr[-5000:])

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    pin=json.loads((REF/'provenance.json').read_text());assert pin['commit']=='5688f7eb1e117ed26e642a695de300b7683acb87'
    groups=[('wifi/common/aidl/aidl_api/android.hardware.wifi.common/2',2,'android.hardware.wifi.common-V2-m1.so'),
            ('wifi/aidl/aidl_api/android.hardware.wifi/3',3,'android.hardware.wifi-V3-ndk.so')]
    generated=ROOT/'generated';generated.mkdir(exist_ok=True)
    for path,version,name in groups:
        frozen=REF/path;files=sorted(frozen.rglob('*.aidl'))
        run([BASE/'build/aosp/aidl','--lang=ndk','--structured','--stability=vintf','--min_sdk_version=34',
             '--version='+str(version),'--hash='+(frozen/'.hash').read_text().splitlines()[-1],
             '-I',REF/'binder-aidl','-I',REF/groups[0][0],'-I',REF/groups[1][0],'-o',generated/name/'src','-h',generated/'include']+files,ROOT/('aidl-'+str(version)+'.log'))
    includes=[BASE/'scripts',REF/'wifi/legacy_headers/include',SUPPORT,REF/'wifi/aidl/default',generated/'include',
              WORK/'aosp-binder-ndk/include_cpp',WORK/'aosp-binder-ndk/include_ndk',WORK/'aosp-binder-ndk/include_platform',
              VNDK/'external/libnl/include',VNDK/'external/libxml2/include']
    # Match the existing Android C++ runtime; do not package a second libc++.
    common=[NDK/'bin/aarch64-linux-android35-clang++','-std=c++17','-O2','-fPIC','-fno-rtti',
            '-D_GNU_SOURCE','-DANDROID','-DWIFI_HAL_INTERFACE_COMBINATIONS={{{STA}, 1}}','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
            '-Wno-unused-parameter','-Wno-error=implicit-fallthrough','-nostdinc++','-isystem',VNDK/'external/libcxx/include']+['-I'+str(p) for p in includes]
    legacy_roots=json.loads((BASE/'build/aosp/include-dirs.json').read_text())
    for p in legacy_roots:
        if '/aosp-vndk' in p:common+=['-I'+str(VNDK)+p.split('/aosp-vndk',1)[1]]
    links=['-nostdlib++','-Wl,--no-undefined','-Wl,-z,max-page-size=16384']
    for directory in [ROOT,VENDOR,SYSTEM_ORIGINAL/'lib64']:
        links+=['-L'+str(directory),'-Wl,-rpath-link,'+str(directory)]
    def objects(sources,label):
        folder=ROOT/'objects'/label;folder.mkdir(parents=True,exist_ok=True)
        def one(source):
            obj=folder/(source.stem+'.o');run(common+['-c',source,'-o',obj],obj.with_suffix('.log'));return obj
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:return list(pool.map(one,sources))
    for path,version,name in groups:
        objs=objects(sorted((generated/name/'src').rglob('*.cpp')),name)
        extra=[] if version==2 else ['-l:'+groups[0][2]]
        run([common[0],'-shared']+links+objs+extra+['-lbinder_ndk','-l:libc++.so','-Wl,-soname,'+name,'-o',ROOT/name],ROOT/('link-'+name+'.log'))
        print('WIFI_FROZEN_INTERFACE_BUILD_PASS',name,flush=True)
    backend=[BASE/'scripts/m1_wifi_linux.cpp',BASE/'scripts/m1_wifi_hal.cpp']
    objs=objects(backend,'native-backend')
    run([common[0],'-shared']+links+objs+['-l:libnl.so','-l:libc++.so','-llog','-Wl,-soname,libwifi-hal.so','-o',ROOT/'libwifi-hal.so'],ROOT/'link-native-backend.log')
    names=['aidl_struct_util','aidl_sync_util','ringbuffer','wifi','wifi_ap_iface','wifi_chip',
           'wifi_feature_flags','wifi_iface_util','wifi_legacy_hal','wifi_legacy_hal_factory',
           'wifi_legacy_hal_stubs','wifi_mode_controller','wifi_nan_iface','wifi_p2p_iface',
           'wifi_rtt_controller','wifi_sta_iface','wifi_status_util','service']
    sources=[REF/'wifi/aidl/default'/(n+'.cpp') for n in names]
    objs=objects(sources,'service')
    libs=['android.hardware.wifi-V3-ndk', 'libbase','libbinder_ndk','libcutils','liblog','libnl','libutils','libwifi-hal','libwifi-system-iface','libxml2','libc++']
    binary=ROOT/'android.hardware.wifi-service.m1'
    run([common[0]]+links+objs+['-l:'+p+'.so' for p in libs]+['-l:'+groups[0][2],'-o',binary],ROOT/'link-service.log')
    files=[binary,ROOT/'libwifi-hal.so']+[ROOT/n for _,_,n in groups]
    receipt={'source_commit':pin['commit'],'interface_version':3,'interface_hash':(REF/groups[1][0]/'.hash').read_text().splitlines()[-1],
       'library_backend_same_legacy_header':True,'chip_mode_bootstrap':'AOSP V3 mode, one observed STA initially; nl80211 dynamic combinations replace limits while retaining the same V3 ID','unsupported_operations':'AOSP service error-returning stubs; no success ACKs invented',
       'dependencies':'Existing libnl/libwifi-system-iface; separate frozen common-V2 library keeps provided libraries unchanged',
       'files':{str(p):{'bytes':p.stat().st_size,'sha256':digest(p)} for p in files},
       'sources':{str(p):digest(p) for p in backend+[BASE/'scripts/m1_wifi_linux.h']},
       'physical_device_written':False,'hardware_verified':False,'namespace_runtime_verified':False,'tests_pass':False}
    (ROOT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('M1_NATIVE_WIFI_SERVICE_BUILD_PASS',binary,flush=True)
if __name__=='__main__':main()

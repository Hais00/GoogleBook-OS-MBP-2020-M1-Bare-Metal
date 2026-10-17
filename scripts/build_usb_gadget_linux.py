#!/usr/bin/env python3
"""Build the actual configfs/FunctionFS gadget owner against frozen AIDL V1."""
import hashlib
import json
from pathlib import Path
import subprocess
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL


def main():
    frozen=WORK/'usb-linux-source/aidl-gadget1';output=WORK/'usb-gadget-linux-build';output.mkdir(exist_ok=True)
    generated=output/'generated';sha=(frozen/'.hash').read_text().splitlines()[-1]
    library=WORK/'vendor-egl-stage/lib64/android.hardware.usb.gadget-V1-ndk.so'
    assert sha.encode() in library.read_bytes()
    command=[BASE/'build/aosp/aidl','--lang=ndk','--structured','--stability=vintf','--min_sdk_version=34',
             '--version=1','--hash='+sha,'-I',frozen,'-o',generated/'src','-h',generated/'include']
    subprocess.run(list(map(str,command+sorted(frozen.rglob('*.aidl')))),check=True)
    roots=json.loads((BASE/'build/aosp/include-dirs.json').read_text())
    roots=[str(VNDK)+p.split('/aosp-vndk',1)[1] for p in roots]
    includes=[generated/'include',BASE/'scripts',WORK/'aosp-binder-ndk/include_cpp',WORK/'aosp-binder-ndk/include_ndk',WORK/'aosp-binder-ndk/include_platform']+roots
    flags=['--target=aarch64-linux-android36','-std=c++17','-O2','-fPIC','-Wall','-Wextra','-Werror',
           '-fno-exceptions','-fno-rtti','-nostdinc++','-isystem',str(VNDK/'external/libcxx/include'),'-D_GNU_SOURCE','-DANDROID']
    flags+=['-I'+str(p) for p in includes]
    sources=[BASE/'scripts'/name for name in ['usb_linux_gadget_binding.cpp','usb_linux_gadget.cpp','usb_linux_gadget_service.cpp','usb_linux_gadget_service_test.cpp']]
    objects=[]
    for source in sources:
        obj=output/(source.stem+'.o');result=subprocess.run([str(NDK/'bin/clang++')]+flags+['-c',str(source),'-o',str(obj)],capture_output=True,text=True)
        obj.with_suffix('.log').write_text(result.stdout+result.stderr)
        if result.returncode:raise RuntimeError(source.name+':\n'+result.stderr[-6000:])
        objects.append(obj)
    binary=output/'android.hardware.usb.gadget-service.linux'
    link=[NDK/'bin/aarch64-linux-android35-clang++','-nostdlib++','-Wl,--no-undefined','-Wl,-z,max-page-size=16384','-o',binary]+[o for o in objects if o.stem!='usb_linux_gadget_service_test']
    for folder in [WORK/'vendor-egl-stage/lib64',SYSTEM_ORIGINAL/'lib64']:link+=['-L'+str(folder),'-Wl,-rpath-link,'+str(folder)]
    link+=['-l:'+name+'.so' for name in ['android.hardware.usb.gadget-V1-ndk','libbinder_ndk','liblog','libc++']]
    result=subprocess.run(list(map(str,link)),capture_output=True,text=True);(output/'link.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(result.stderr)
    test=output/'usb-gadget-service-test'
    command=[str(test) if x==binary else str(x) for x in link if x!=output/'usb_linux_gadget_service.o']+[str(output/'usb_linux_gadget_service_test.o')]
    result=subprocess.run(command,capture_output=True,text=True);(output/'test-link.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(result.stderr)
    receipt={'binary':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'frozen_interface':1,'frozen_hash':sha,
             'sources':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
             'controller':'observed real dwc3 UDC; dummy/ambiguous selection rejected','functionfs':'kernel ready bit plus endpoint readiness',
             'functions':'ADB/MTP/PTP/RNDIS/NCM and their ADB combinations; remaining functions unsupported by current kernel profile',
             'hardware_verified':False,'staged':False,'physical_device_written':False,'android_callback_test_pass':False}
    receipt['headers']={n:hashlib.sha256((BASE/'scripts'/n).read_bytes()).hexdigest() for n in ['usb_linux_gadget_binding.h','usb_linux_gadget.h']}
    receipt.update(test_binary=str(test),test_sha256=hashlib.sha256(test.read_bytes()).hexdigest())
    (WORK/'usb-gadget-linux-build.json').write_text(json.dumps(receipt,indent=2)+'\n');print('USB_GADGET_LINUX_BUILD_PASS',binary)


if __name__=='__main__':main()

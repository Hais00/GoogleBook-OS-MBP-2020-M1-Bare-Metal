#!/usr/bin/env python3
"""Build the native Linux Type-C HAL against frozen public USB V3."""
import hashlib
import json
import subprocess
from pathlib import Path
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL


def main():
    source = WORK/'usb-linux-source'
    pin = json.loads((source/'provenance.json').read_text())
    frozen = source/'aidl-usb3'
    output = WORK/'usb-linux-build'
    output.mkdir(exist_ok=True)
    generated = output/'generated'
    frozen_hash = (frozen/'.hash').read_text().splitlines()[-1]
    library = WORK/'vendor-egl-stage/lib64/android.hardware.usb-V3-ndk.so'
    assert frozen_hash.encode() in library.read_bytes(), 'Frozen USB ABI differs from provided library'
    command = [BASE/'build/aosp/aidl', '--lang=ndk', '--structured', '--stability=vintf',
               '--min_sdk_version=34', '--version=3', '--hash='+frozen_hash,
               '-I', frozen, '-o', generated/'src', '-h', generated/'include']
    subprocess.run(list(map(str, command+sorted(frozen.rglob('*.aidl')))), check=True)
    roots = json.loads((BASE/'build/aosp/include-dirs.json').read_text())
    roots = [str(VNDK)+p.split('/aosp-vndk', 1)[1] for p in roots]
    includes = [generated/'include', BASE/'scripts', WORK/'aosp-binder-ndk/include_cpp',
                WORK/'aosp-binder-ndk/include_ndk', WORK/'aosp-binder-ndk/include_platform']+roots
    flags = ['--target=aarch64-linux-android36', '-std=c++17', '-O2', '-fPIC',
             '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-fno-rtti', '-nostdinc++',
             '-isystem', str(VNDK/'external/libcxx/include'), '-D_GNU_SOURCE', '-DANDROID']
    flags += ['-I'+str(p) for p in includes]
    sources = [BASE/'scripts/usb_linux_typec.cpp', BASE/'scripts/usb_linux_service.cpp',
               BASE/'scripts/usb_linux_service_test.cpp']
    objects = []
    for path in sources:
        obj = output/(path.stem+'.o')
        result = subprocess.run([str(NDK/'bin/clang++')]+flags+['-c',str(path),'-o',str(obj)],
                                capture_output=True,text=True)
        obj.with_suffix('.log').write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(path.name+':\n'+result.stderr[-6000:])
        objects.append(obj)
    binary = output/'android.hardware.usb-service.linux'
    link = [NDK/'bin/aarch64-linux-android35-clang++', '-nostdlib++', '-Wl,--no-undefined',
            '-Wl,-z,max-page-size=16384', '-o', binary]+[
                p for p in objects if p.stem != 'usb_linux_service_test']
    for folder in [WORK/'vendor-egl-stage/lib64', SYSTEM_ORIGINAL/'lib64']:
        link += ['-L'+str(folder), '-Wl,-rpath-link,'+str(folder)]
    link += ['-l:'+name+'.so' for name in ['android.hardware.usb-V3-ndk', 'libbinder_ndk',
              'libcutils', 'liblog', 'libc++']]
    result = subprocess.run(list(map(str,link)),capture_output=True,text=True)
    (output/'link.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr)
    test=output/'usb-linux-service-test'
    test_link=[str(test) if p==binary else str(p) for p in link
               if p!=output/'usb_linux_service.o']+[str(output/'usb_linux_service_test.o')]
    result=subprocess.run(test_link,capture_output=True,text=True)
    (output/'test-link.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(result.stderr)
    receipt = {'frozen_interface':3, 'frozen_hash':frozen_hash, 'reference_commit':pin['commit'],
               'binary':str(binary), 'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
               'sources':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
               'role_completion':'matching readback from the requested kernel port; store alone is insufficient',
               'sysfs_discovery':'strict registered port names with actual kernel role capabilities',
               'unqualified_controls':'data gating, port reset, power transfer limit, contaminant detection report NOT_SUPPORTED',
               'hardware_verified':False,'physical_device_written':False,'staged':False}
    receipt['header_sha256']=hashlib.sha256((BASE/'scripts/usb_linux_typec.h').read_bytes()).hexdigest()
    receipt.update(test_binary=str(test),test_binary_sha256=hashlib.sha256(test.read_bytes()).hexdigest(),
                   android_callback_tests_pass=False)
    (WORK/'usb-linux-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('USB_LINUX_PORT_BUILD_PASS',binary)


if __name__=='__main__':
    main()

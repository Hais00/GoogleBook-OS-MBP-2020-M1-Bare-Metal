#!/usr/bin/env python3
"""Build frozen public ILights V2, the M1 sysfs provider and CPU callback fixtures."""
import hashlib
import json
from pathlib import Path
import subprocess
from project_paths import BASE, WORK, VNDK, NDK, SYSTEM_ORIGINAL


def main():
    reference = WORK/'references/android-light2'
    provenance = json.loads((reference/'provenance.json').read_text())
    assert provenance['frozen'] and provenance['version'] == 2
    root = WORK/'m1-lights-build'
    root.mkdir(exist_ok=True)
    generated = root/'generated'
    aidl = reference/'aidl'
    sources = sorted(aidl.rglob('*.aidl'))
    command = [BASE/'build/aosp/aidl', '--lang=ndk', '--structured', '--stability=vintf',
               '--min_sdk_version=34', '--version=2', '--hash='+provenance['hash'],
               '-I', aidl, '-o', generated/'src', '-h', generated/'include']+sources
    subprocess.run(list(map(str, command)), check=True)
    flags = ['--target=aarch64-linux-android35', '-std=c++17', '-O2', '-fPIC',
             '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-fno-rtti', '-nostdinc++',
             '-isystem', str(VNDK/'external/libcxx/include'), '-D_GNU_SOURCE', '-DANDROID']
    includes = [BASE/'scripts', generated/'include', WORK/'aosp-binder-ndk/include_cpp',
                WORK/'aosp-binder-ndk/include_ndk', WORK/'aosp-binder-ndk/include_platform']
    flags += ['-I'+str(path) for path in includes]
    def run(command, log):
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
        (root/log).write_text(result.stdout+result.stderr)
        if result.returncode: raise RuntimeError(result.stderr[-6000:])
    generated_objects = []
    for source in sorted((generated/'src').rglob('*.cpp')):
        obj = root/(source.stem+'.aidl.o')
        run([NDK/'bin/clang++']+flags+['-c', source, '-o', obj], obj.name+'.log')
        generated_objects.append(obj)
    for source in ['m1_lights.cpp', 'm1_lights_service.cpp', 'm1_lights_test.cpp']:
        variants = [''] if source != 'm1_lights_service.cpp' else ['', '-test']
        for suffix in variants:
            obj = root/(Path(source).stem+suffix+'.o')
            definitions = ['-DGOS_LIGHTS_TEST_LIBRARY'] if suffix else []
            run([NDK/'bin/clang++']+flags+definitions+['-c', BASE/'scripts'/source, '-o', obj], obj.name+'.log')
    link = [NDK/'bin/aarch64-linux-android35-clang++', '-nostdlib++', '-Wl,--no-undefined', '-Wl,-z,max-page-size=16384']
    for path in [WORK/'vendor-linux-cleanup-stage/lib64', SYSTEM_ORIGINAL/'lib64']:
        link += ['-L'+str(path), '-Wl,-rpath-link,'+str(path)]
    libraries = ['-l:libbinder_ndk.so', '-l:libc++.so']
    shared = root/'android.hardware.light-V2-ndk.so'
    run(link+['-shared', '-Wl,-soname,'+shared.name, '-o', shared]+generated_objects+libraries, 'aidl-link.log')
    binary = root/'android.hardware.lights-service.m1'
    run(link+['-o', binary, root/'m1_lights.o', root/'m1_lights_service.o', '-L'+str(root),
              '-Wl,-rpath-link,'+str(root), '-l:'+shared.name]+libraries, 'service-link.log')
    test = root/'m1-lights-test'
    run(link+['-o', test, root/'m1_lights.o', root/'m1_lights_service-test.o', root/'m1_lights_test.o']+
        generated_objects+libraries, 'test-link.log')
    files = [binary, shared, test]
    record = {'interface': 'canonical frozen android.hardware.light V2', 'interface_hash': provenance['hash'],
              'source_provenance': provenance, 'system_target_matrix': '202604 accepts versions2-3',
              'files': {str(p): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for p in files},
              'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (BASE/'scripts').glob('m1_lights*')},
              'fixture_pass': False, 'namespace_runtime_pass': False, 'hardware_verified': False,
              'physical_device_written': False,
              'semantics': 'Discover actual sysfs controllers; only their kernel interfaces accept commands. Per-controller errors do not block qualified main display, and remain in HAL dump. No flash/low-persistence simulation.'}
    (WORK/'m1-lights-build.json').write_text(json.dumps(record, indent=2)+'\n')
    print('M1_LIGHTS_AND_CALLBACK_FIXTURE_BUILD_PASS', binary)


if __name__ == '__main__':
    main()

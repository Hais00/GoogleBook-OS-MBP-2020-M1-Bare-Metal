#!/usr/bin/env python3
"""Build AOSP's explicitly nonsecure Gatekeeper/SharedSecret reference HAL."""
import hashlib
import json
from pathlib import Path
import subprocess
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL


def main():
    reference = WORK/'references/aosp-hals-16qpr2'
    source = reference/'gatekeeper/aidl/software'
    frozen = reference/'gatekeeper/aidl/frozen1'
    output = WORK/'gatekeeper-nonsecure-build'
    output.mkdir(exist_ok=True)
    generated = output/'generated'
    includes = [frozen] + list(Path('/opt/googlebook/build/aosp-port/security-aidl').iterdir())
    args = [BASE/'build/aosp/aidl', '--lang=ndk', '--structured', '--stability=vintf',
            '--min_sdk_version=34', '--version=1',
            '--hash='+(frozen/'.hash').read_text().splitlines()[-1],
            '-o', generated/'src', '-h', generated/'include']
    for p in includes:
        args += ['-I', p]
    subprocess.run(list(map(str, args+sorted(frozen.rglob('*.aidl')))), check=True)
    roots = json.loads((BASE/'build/aosp/include-dirs.json').read_text())
    roots = [str(VNDK)+p.split('/aosp-vndk', 1)[1] for p in roots]
    scrypt = WORK/'references/aosp-scrypt'
    includes = [generated/'include', source, scrypt, scrypt/'lib/crypto', scrypt/'lib/util',
                Path('/opt/googlebook/build/aosp-keymaster/include'),
                Path('/opt/googlebook/build/aosp-keymaster/ng/include'),
                VNDK/'system/gatekeeper/include', VNDK/'external/boringssl/src/include',
                Path('/opt/googlebook/build/aosp-port/security-generated/include'),
                Path('/opt/googlebook/build/aosp-port/security-native'),
                WORK/'aosp-binder-ndk/include_cpp', WORK/'aosp-binder-ndk/include_ndk',
                WORK/'aosp-binder-ndk/include_platform'] + roots
    flags = ['--target=aarch64-linux-android36', '-fPIC', '-O2', '-D_GNU_SOURCE',
             '-DANDROID', '-Wno-deprecated-declarations']+['-I'+str(p) for p in includes]
    objects = []
    sources = [source/n for n in ['GateKeeper.cpp', 'SharedSecret.cpp', 'service.cpp']]
    sources += [scrypt/'lib/crypto/crypto_scrypt-neon.c']
    sources += [BASE/'scripts/gatekeeper_nonsecure_test.cpp']
    for p in sources:
        cpp = p.suffix == '.cpp'
        extra = ['-std=c++17', '-fno-rtti', '-fno-exceptions', '-nostdinc++',
                 '-isystem', str(VNDK/'external/libcxx/include')] if cpp else [
                 '-std=c11', '-DHAVE_CONFIG_H', '-DUSE_OPENSSL_PBKDF2']
        obj = output/(p.stem+'.o')
        result = subprocess.run([str(NDK/('bin/clang++' if cpp else 'bin/clang'))]+flags+extra+
                                ['-c', str(p), '-o', str(obj)], capture_output=True, text=True)
        obj.with_suffix('.log').write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(p.name+':\n'+result.stderr[-6000:])
        objects.append(obj)
    binary = output/'android.hardware.gatekeeper-service.nonsecure'
    link = [NDK/'bin/aarch64-linux-android35-clang++', '-nostdlib++',
            '-Wl,--no-undefined', '-Wl,-z,max-page-size=16384', '-o', binary]+[
            p for p in objects if p.stem != 'gatekeeper_nonsecure_test']
    for directory in [BASE/'vendor_work/lib64', SYSTEM_ORIGINAL/'lib64']:
        link += ['-L'+str(directory), '-Wl,-rpath-link,'+str(directory)]
    link += ['-l:'+n+'.so' for n in ['android.hardware.gatekeeper-V1-ndk',
             'android.hardware.security.sharedsecret-V1-ndk', 'android.hardware.security.keymint-V5-ndk',
             'libbase', 'libbinder_ndk', 'libcrypto', 'libcutils', 'libgatekeeper',
             'libhardware', 'libkeymaster_portable', 'liblog', 'libutils', 'libc++']]
    result = subprocess.run(list(map(str, link)), capture_output=True, text=True)
    (output/'link.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr)
    test = output/'gatekeeper-nonsecure-test'
    test_link = [str(test) if item == binary else str(item) for item in link
                 if item != output/'service.o']
    test_link += [str(output/'gatekeeper_nonsecure_test.o'), '-lpuresoftkeymasterdevice']
    result = subprocess.run(test_link, capture_output=True, text=True)
    (output/'test-link.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr)
    receipt = {'source_commit': json.loads((reference/'provenance.json').read_text())['commit'],
               'binary': str(binary), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
               'scrypt_source': json.loads((scrypt/'provenance.json').read_text()),
               'hardware_backed': False, 'credential_tests_pass': False,
               'test_binary': str(test), 'test_sha256': hashlib.sha256(test.read_bytes()).hexdigest(),
               'staged': False, 'physical_device_written': False}
    (WORK/'gatekeeper-nonsecure-build.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('GATEKEEPER_NONSECURE_BUILD_PASS', binary)


if __name__ == '__main__':
    main()

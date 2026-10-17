#!/usr/bin/env python3
"""Build an ownership regression against actual HWC objects and its pre-fix source."""
import hashlib
import json
from pathlib import Path
import subprocess
import base64
import urllib.request
import build_hwc_drm as hwc
from project_paths import BASE, WORK, NDK, SYSTEM_ORIGINAL


def main():
    root = WORK/'hwc-owner-test'
    root.mkdir(exist_ok=True)
    receipt = json.loads((WORK/'hwc-drm-build.json').read_text())
    sources = [hwc.SRC/p for p in receipt['files']]+[Path('/opt/googlebook/build/aosp-aidlcommon/NativeHandle.cpp')]
    sources = [p for p in sources if not __import__('re').search(r'\bint\s+main\s*\(', p.read_text())]
    objects = [hwc.compile_one(p) for p in sources]
    test = root/'owner-test.o'
    def run(command, name):
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
        (root/name).write_text(result.stdout+result.stderr)
        if result.returncode: raise RuntimeError(result.stderr[-6500:])
    run([NDK/'bin/clang++', '--target=aarch64-linux-android36']+hwc.flags+
        ['-c', BASE/'scripts/m1_hwc_owner_test.cpp', '-o', test], 'test-compile.log')
    link = [NDK/'bin/aarch64-linux-android35-clang++', '-nostdlib++', '-Wl,--no-undefined', '-Wl,-z,max-page-size=16384']
    for path in [WORK/'mesa-stage/vendor/lib64', BASE/'vendor_work/lib64', SYSTEM_ORIGINAL/'lib64']:
        link += ['-L'+str(path), '-Wl,-rpath-link,'+str(path)]
    wrapped = ['open', 'drmSetClientCap', 'drmGetCap', 'drmSetMaster', 'drmIsMaster',
               'drmModeGetResources', 'drmModeGetConnector', 'drmModeObjectGetProperties', 'drmModeGetProperty']
    link += ['-Wl,--wrap='+symbol for symbol in wrapped]
    libs = ['-l:'+p+'.so' for p in ['android.hardware.graphics.composer3-V4-ndk',
            'android.hardware.graphics.common-V7-ndk', 'android.hardware.drm.common-V1-ndk',
            'libbase', 'libbinder_ndk', 'libcutils', 'libdrm', 'libhardware', 'libhidlbase',
            'liblog', 'libsync', 'libui', 'libutils', 'libc++']]
    binary = root/'hwc-owner-test'
    run(link+['-o', binary, test]+objects+libs, 'positive-link.log')
    original = root/'DrmDevice-original.cpp'
    pin = json.loads((WORK/'references/drm-hwcomposer-aosp-revision.json').read_text())['commit']
    source_url = f'https://android.googlesource.com/platform/external/drm_hwcomposer/+/{pin}/drm/DrmDevice.cpp?format=TEXT'
    if not original.is_file():
        original.write_bytes(base64.b64decode(urllib.request.urlopen(source_url, timeout=45).read(), validate=True))
    control = root/'DrmDevice-original.o'
    run([NDK/'bin/clang++', '--target=aarch64-linux-android36']+hwc.flags+
        ['-I'+str(hwc.SRC/'drm'), '-c', original, '-o', control], 'control-compile.log')
    fixed_obj = hwc.OUT/'drm_DrmDevice.cpp.o'
    assert fixed_obj in objects
    negative = root/'hwc-owner-control'
    run(link+['-o', negative, test]+[control if p == fixed_obj else p for p in objects]+libs,
        'negative-link.log')
    record = {'positive': str(binary), 'negative': str(negative),
              'files': {str(p): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in [binary, negative]},
              'actual_production_object': str(fixed_obj), 'control_source_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
              'scope': 'CPU callbacks + actual DrmDevice source and actual FD lifetime; no physical DRM or KMS master is granted',
              'control_source_url': source_url, 'control_source_commit': pin,
              'runtime_tested': False, 'hardware_qualified': False}
    (WORK/'hwc-owner-test.json').write_text(json.dumps(record, indent=2)+'\n')
    print('HWC_OWNER_REGRESSION_AND_PRE_FIX_CONTROL_BUILT', binary)


if __name__ == '__main__':
    main()

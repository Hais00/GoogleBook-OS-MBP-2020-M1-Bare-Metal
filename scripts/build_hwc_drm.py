#!/usr/bin/env python3
"""Build the public AOSP DRM composer without vendor-specific backends."""
import concurrent.futures
import hashlib
import json
import pathlib
import re
import subprocess
import shutil
import shlex
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL

SRC = WORK/'drm-hwcomposer-aosp'
OUT = WORK/'hwc-drm-build'
OUT.mkdir(exist_ok=True)
roots = json.loads((BASE/'build/aosp/include-dirs.json').read_text())
roots = [str(VNDK)+p.split('/aosp-vndk', 1)[1] for p in roots]
includes = [WORK/'hwc-generated/include', SRC, WORK/'aosp-binder-ndk/include_cpp',
            WORK/'aosp-binder-ndk/include_ndk', WORK/'aosp-binder-ndk/include_platform', '/opt/googlebook/build/aosp-aidlcommon/include',
            '/opt/googlebook/build/aosp-fmq',
            BASE/'mesa/subprojects/libdrm-2.4.123', BASE/'mesa/subprojects/libdrm-2.4.123/include/drm'] + roots
flags = ['-std=c++17', '-fPIC', '-O2', '-fno-rtti', '-fno-exceptions', '-nostdinc++',
         '-isystem', str(VNDK/'external/libcxx/include'), '-DUSE_IMAPPER4_METADATA_API',
         '-DHWC2_INCLUDE_STRINGIFICATION', '-DHWC2_USE_CPP11', '-DHAS_LIBDISPLAY_INFO=0', '-D_GNU_SOURCE', '-DANDROID']
flags += ['-I'+str(p) for p in includes]

def compile_one(path):
    obj = OUT/(str(path.relative_to(SRC)).replace('/', '_')+'.o') if path.is_relative_to(SRC) else OUT/(path.name+'.o')
    depfile = obj.with_suffix('.d')
    cmd = [str(NDK/'bin/clang++'), '--target=aarch64-linux-android36'] + flags + ['-MMD', '-MF', str(depfile), '-c', str(path), '-o', str(obj)]
    signature = json.dumps(cmd)
    stamp = obj.with_suffix('.cmd.json')
    if obj.exists() and stamp.exists() and depfile.exists() and stamp.read_text() == signature:
        dependencies = shlex.split(depfile.read_text().replace('\\\n', ' ').split(':', 1)[1])
        if dependencies and all(pathlib.Path(p).exists() and pathlib.Path(p).stat().st_mtime <= obj.stat().st_mtime for p in dependencies):
            return obj
    p = subprocess.run(cmd, capture_output=True, text=True)
    obj.with_suffix('.log').write_text(p.stdout+p.stderr)
    if p.returncode:
        raise RuntimeError(path.name+':\n'+(p.stdout+p.stderr)[-7500:])
    stamp.write_text(signature)
    return obj

def main():
    shutil.copy2(BASE/'drm-hwcomposer/utils/DrmDevicePaths.h', SRC/'utils/DrmDevicePaths.h')
    bp = (SRC/'Android.bp').read_text()
    files = []
    for group in ('drm_hwcomposer_common', 'drm_hwcomposer_hwc3', 'drm_hwcomposer_service'):
        block = re.search(r'name: "'+group+r'",\s*srcs: \[(.*?)\]', bp, re.S)[1]
        files += re.findall(r'"([^"]+\.cpp)"', block)
    # The installed mapper exposes standard metadata. A legacy drm_gralloc
    # handle parser is incompatible with minigbm and must not be selected.
    files += ['stats/CompositionStatsAtomReporter.cpp']
    sources = [SRC/f for f in files] + [pathlib.Path('/opt/googlebook/build/aosp-aidlcommon/NativeHandle.cpp')]
    assert not any('sdm' in str(p).lower() for p in sources)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        objects = list(pool.map(compile_one, sources))
    binary = OUT/'android.hardware.composer.hwc3-service.drm'
    link = [NDK/'bin/aarch64-linux-android35-clang++', '-nostdlib++', '-Wl,--no-undefined', '-Wl,-z,max-page-size=16384', '-o', binary] + objects
    for directory in (WORK/'mesa-stage/vendor/lib64', BASE/'vendor_work/lib64', SYSTEM_ORIGINAL/'lib64'):
        link += ['-L'+str(directory), '-Wl,-rpath-link,'+str(directory)]
    for lib in ['android.hardware.graphics.composer3-V4-ndk', 'android.hardware.graphics.common-V7-ndk', 'android.hardware.drm.common-V1-ndk', 'base', 'binder_ndk', 'cutils', 'drm', 'hardware', 'hidlbase', 'log', 'sync', 'ui', 'utils', 'c++']:
        link += ['-l:'+lib+'.so' if lib.startswith('android.') else '-l'+lib]
    p = subprocess.run(list(map(str, link)), capture_output=True, text=True)
    (OUT/'link.log').write_text(p.stdout+p.stderr)
    if p.returncode:
        raise RuntimeError(p.stderr)
    receipt = {'source': json.loads((WORK/'references/drm-hwcomposer-aosp-revision.json').read_text())['commit'],
               'local_changes': {str(p.relative_to(SRC)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [SRC/'drm/ResourceManager.cpp', SRC/'utils/DrmDevicePaths.h',
                                           SRC/'drm/DrmDevice.cpp', SRC/'drm/DrmDevice.h']},
               'files': files, 'binary': str(binary), 'sha256': hashlib.file_digest(binary.open('rb'), 'sha256').hexdigest(), 'hardware_verified': False}
    (WORK/'hwc-drm-build.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('Built public AOSP DRM HWC:', binary)

if __name__ == '__main__':
    main()

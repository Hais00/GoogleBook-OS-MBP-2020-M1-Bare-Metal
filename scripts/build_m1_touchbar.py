#!/usr/bin/env python3
"""Build the native event-driven ADP function row; no raw hardware register access."""
import hashlib
import json
import subprocess
from pathlib import Path
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL


def main():
    root = WORK/'m1-touchbar-build'
    root.mkdir(exist_ok=True)
    sources = [BASE/'scripts/m1_touchbar.cpp', BASE/'scripts/m1_touchbar_model.cpp', BASE/'scripts/m1_input_key_state.cpp']
    includes = [BASE/'scripts', WORK/'m1-lights-build/generated/include',
                WORK/'aosp-binder-ndk/include_cpp', WORK/'aosp-binder-ndk/include_ndk',
                WORK/'aosp-binder-ndk/include_platform', VNDK/'external/freetype/include',
                BASE/'mesa/subprojects/libdrm-2.4.123', BASE/'mesa/subprojects/libdrm-2.4.123/include/drm']
    flags = ['--target=aarch64-linux-android35', '-std=c++17', '-O2', '-fPIC', '-fno-rtti',
             '-Wall', '-Wextra', '-Werror', '-nostdinc++', '-isystem', str(VNDK/'external/libcxx/include'),
             '-D_GNU_SOURCE', '-DANDROID']+['-I'+str(p) for p in includes]
    def run(command, name):
        r = subprocess.run(list(map(str, command)), capture_output=True, text=True)
        (root/name).write_text(r.stdout+r.stderr)
        if r.returncode: raise RuntimeError(r.stderr[-8000:])
    objects = []
    for source in sources:
        obj = root/(source.stem+'.o'); objects.append(obj)
        run([NDK/'bin/clang++']+flags+['-c', source, '-o', obj], source.stem+'.log')
    binary = root/'m1-touchbar'
    command = [NDK/'bin/aarch64-linux-android35-clang++', '-nostdlib++', '-Wl,--no-undefined',
               '-Wl,-z,max-page-size=16384', '-o', binary]+objects
    for p in [WORK/'m1-lights-build', WORK/'vendor-linux-cleanup-stage/lib64', SYSTEM_ORIGINAL/'lib64']:
        command += ['-L'+str(p), '-Wl,-rpath-link,'+str(p)]
    command += ['-l:'+name+'.so' for name in ['android.hardware.light-V2-ndk', 'libdrm', 'libft2', 'libbinder_ndk', 'libc++', 'liblog']]
    run(command, 'link.log')
    record = {'binary': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'sources': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+[BASE/'scripts/m1_touchbar_model.h',BASE/'scripts/m1_input_key_state.h']},
              'dependencies': 'Frozen public ILights V2, libdrm, Android system FreeType/Roboto, Linux evdev/uinput',
              'physical_device_written': False, 'hardware_verified': False, 'namespace_runtime_pass': False,
              'scope': 'Actual adp + non-desktop output only, event-driven rendering, actual page-flip events, real touch axes, truthful virtual key events; sole ILights sysfs writer',
              'orientation': 'Clockwise logical horizontal to kernel portrait scanout; requires physical visual validation',
              'android_per_device_keyboard_backlight_slider_qualified': False}
    (WORK/'m1-touchbar-build.json').write_text(json.dumps(record, indent=2)+'\n')
    print('M1_NATIVE_TOUCHBAR_BUILD_PASS', binary)


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Build test-only Bionic property and Binder clients, never staged in vendor."""
import hashlib
import json
import subprocess
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL

def main():
    root = WORK/'native-audio-local-tests'
    root.mkdir(exist_ok=True)
    reference = WORK/'references/android-audio-bootstrap/property_service'
    includes = [reference/'libpropertyinfoserializer/include', reference/'libpropertyinfoparser/include',
                VNDK/'system/libbase/include']
    sources = [BASE/'scripts/audio_local_properties.cpp'] + [reference/'libpropertyinfoserializer'/name
        for name in ['property_info_serializer.cpp', 'trie_builder.cpp', 'trie_serializer.cpp']]
    sources.append(reference/'libpropertyinfoparser/property_info_parser.cpp')
    links = ['-nostdlib++', '-Wl,--no-undefined', '-Wl,-z,max-page-size=16384']
    for path in [WORK/'vendor-wifi-stage-r2/lib64', SYSTEM_ORIGINAL/'lib64']:
        links += ['-L'+str(path), '-Wl,-rpath-link,'+str(path)]
    commands = [[NDK/'bin/aarch64-linux-android35-clang++', '-std=c++17', '-O2', '-Wall', '-Wextra',
        '-Werror', '-nostdinc++', '-isystem', VNDK/'external/libcxx/include'] +
        ['-I'+str(p) for p in includes] + sources + [SYSTEM_ORIGINAL/'lib64/bootstrap/libc.so'] +
        links + ['-l:libbase.so', '-l:libc++.so', '-o', root/'audio-local-properties'],
        [NDK/'bin/aarch64-linux-android35-clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
         '-nostdinc++', '-isystem', VNDK/'external/libcxx/include'] +
        ['-I'+str(WORK/'aosp-binder-ndk'/p) for p in ['include_ndk', 'include_platform', 'include_cpp']] +
        [BASE/'scripts/audio_local_binder_probe.cpp'] + links + ['-lbinder_ndk', '-o', root/'audio-local-binder-probe'],
        [NDK/'bin/aarch64-linux-android35-clang', '-D_GNU_SOURCE', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
         BASE/'scripts/audio_local_binderfs.c', '-Wl,-z,max-page-size=16384', '-o', root/'audio-local-binderfs'],
        [NDK/'bin/aarch64-linux-android35-clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
         BASE/'scripts/audio_local_policy.c', '-Wl,-z,max-page-size=16384', '-o', root/'audio-local-policy'],
        [NDK/'bin/aarch64-linux-android35-clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
         BASE/'scripts/audio_local_log_capture.c', '-Wl,-z,max-page-size=16384', '-o', root/'audio-local-log-capture']]
    for i, command in enumerate(commands):
        r = subprocess.run(list(map(str, command)), capture_output=True, text=True)
        (root/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode: raise RuntimeError(r.stderr)
    result = {'test_only': True, 'installed_in_vendor': False, 'commands': [list(map(str, c)) for c in commands],
              'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                        [root/name for name in ['audio-local-properties', 'audio-local-binder-probe', 'audio-local-binderfs', 'audio-local-policy', 'audio-local-log-capture']]}}
    (root/'build.json').write_text(json.dumps(result, indent=2)+'\n')
    print('M1_AUDIO_LOCAL_TEST_CLIENTS_BUILD_PASS')

if __name__ == '__main__': main()

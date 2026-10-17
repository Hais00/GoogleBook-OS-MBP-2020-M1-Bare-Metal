#!/usr/bin/env python3
"""Build a reproducible NDK AVC decoder diagnostic and pixel reference."""
import hashlib
import json
from pathlib import Path
import subprocess
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL

out = WORK/'codec-probe'
out.mkdir(exist_ok=True)
commands = [
    ['/opt/homebrew/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
     '-i', 'testsrc2=size=64x48:rate=4', '-frames:v', '4', '-c:v', 'libx264',
     '-preset', 'ultrafast', '-tune', 'zerolatency', '-pix_fmt', 'yuv420p',
     '-movflags', '+faststart', '-y', str(out/'clip.mp4')],
    ['/opt/homebrew/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-i',
     str(out/'clip.mp4'), '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-y', str(out/'reference.yuv')]
]
for command in commands:
    subprocess.run(command, check=True)
raw = (out/'reference.yuv').read_bytes()
assert len(raw) == 4*4608
hashes = []
for i in range(4):
    value = 14695981039346656037
    for byte in raw[i*4608:(i+1)*4608]:
        value = ((value ^ byte)*1099511628211) & ((1 << 64)-1)
    hashes.append(value)
(out/'codec_reference.h').write_text('#pragma once\n#include <cstdint>\n'
    'static constexpr uint64_t kExpected[] = {'+
    ','.join('UINT64_C(0x%016x)' % h for h in hashes)+'};\n')
commands.append([str(NDK/'bin/clang++'), '--target=aarch64-linux-android35',
    '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-nostdlib++',
    '-I'+str(out), '-I'+str(VNDK/'frameworks/native/libs/binder/ndk/include_platform'),
    str(BASE/'scripts/codec_decode_probe.cpp'), '-lmediandk',
    '-L'+str(SYSTEM_ORIGINAL/'lib64'), '-l:libbinder_ndk.so',
    '-landroid', '-Wl,-z,max-page-size=16384', '-o', str(out/'codec-decode-probe')])
subprocess.run(commands[-1], check=True)
paths = [BASE/'scripts/codec_decode_probe.cpp', out/'codec_reference.h',
         out/'codec-decode-probe', out/'clip.mp4', out/'reference.yuv']
(out/'build.json').write_text(json.dumps({
    'commands': commands, 'files': {str(p): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
    'bytes': p.stat().st_size} for p in paths},
    'reference_frames_fnv64': ['%016x' % h for h in hashes],
    'runtime_tested': False}, indent=2)+'\n')
print('NDK_CODEC_PROBE_BUILD_PASS')

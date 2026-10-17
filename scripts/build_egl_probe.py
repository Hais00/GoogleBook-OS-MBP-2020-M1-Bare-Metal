#!/usr/bin/env python3
"""Build a diagnostic that uses Android's production EGL/GLES and AHB APIs."""
import hashlib
import json
import subprocess
from project_paths import BASE, WORK, NDK, GRAPHICS_OUT

GRAPHICS_OUT.mkdir(parents=True,exist_ok=True)
source=BASE/'scripts/egl_android_probe.c'
output=GRAPHICS_OUT/'googlebook-eglprobe'
command=[str(NDK/'bin/aarch64-linux-android34-clang'),'-O2','-Wall','-Wextra',
         '-Wl,-z,max-page-size=16384',str(source),'-lEGL','-lGLESv2','-landroid','-lmediandk','-llog','-o',str(output)]
result=subprocess.run(command,capture_output=True,text=True)
(WORK/'logs/egl-probe-build.log').write_text(result.stdout+result.stderr)
if result.returncode:
    print(result.stderr);raise SystemExit(result.returncode)
receipt={'command':command,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
         'binary_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'hardware_tested':False}
(WORK/'egl-probe-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(output)

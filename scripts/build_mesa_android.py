#!/usr/bin/env python3
"""Build upstream Mesa's native Android EGL/GLES Asahi backend, preserving Vulkan."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from project_paths import BASE, WORK, NDK, require_build_inputs

def run(command, logfile, env):
    print('RUN', command[0], 'log:', logfile, flush=True)
    with logfile.open('w') as log:
        result = subprocess.run([str(x) for x in command], stdout=log, stderr=subprocess.STDOUT, env=env)
    if result.returncode:
        print('\n'.join(logfile.read_text(errors='replace').splitlines()[-45:]))
        raise SystemExit(result.returncode)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure-only',action='store_true')
    args=parser.parse_args()
    require_build_inputs()
    src=BASE/'mesa';out=WORK/'mesa-android-native';logs=WORK/'logs';logs.mkdir(parents=True,exist_ok=True)
    hostbin=WORK/'host-bin';hostbin.mkdir(exist_ok=True)
    for rel in ('src/compiler/clc/mesa_clc','src/compiler/spirv/vtn_bindgen2','src/asahi/clc/asahi_clc'):
        p=src/'build-native'/rel
        if not p.is_file():raise RuntimeError(f'Missing native shader compiler: {p}')
        shutil.copy2(p,hostbin/p.name)
    cross=WORK/'mesa-android-native.ini'
    cross.write_text(f'''[constants]
ndk_path = {str(NDK.parents[3])!r}
[binaries]
ar = {str(NDK/'bin/llvm-ar')!r}
c = [{str(NDK/'bin/aarch64-linux-android34-clang')!r}]
cpp = [{str(NDK/'bin/aarch64-linux-android34-clang++')!r}, '-fno-exceptions', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-static-libstdc++']
c_ld = 'lld'
cpp_ld = 'lld'
strip = {str(NDK/'bin/llvm-strip')!r}
pkg-config = '/opt/homebrew/bin/pkg-config'
[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'armv8'
endian = 'little'
[properties]
needs_exe_wrapper = false
''')
    env=os.environ.copy()
    env['PATH']=os.pathsep.join([str(WORK/'venv/bin'),str(hostbin),str(NDK/'bin'),'/opt/homebrew/opt/bison/bin','/opt/homebrew/opt/flex/bin','/opt/homebrew/bin','/usr/bin','/bin'])
    # Do not resolve a macOS .pc library into the Android target build.
    empty_pc=WORK/'target-pkgconfig';empty_pc.mkdir(exist_ok=True)
    env['PKG_CONFIG_LIBDIR']=str(empty_pc);env['PKG_CONFIG_PATH']=''
    meson=[str(WORK/'venv/bin/python'),'-m','mesonbuild.mesonmain']
    flags=['--cross-file',str(cross),'--buildtype=release','--prefix=/vendor','--libdir=lib64',
           '--force-fallback-for=libdrm','-Ddri-drivers-path=/vendor/lib64/dri',
           '-Dallow-fallback-for=libdrm','-Dlibdrm:auto_features=disabled','-Dlibdrm:tests=false',
           '-Dplatforms=android','-Dplatform-sdk-version=34','-Dandroid-stub=true',
           '-Dandroid-libbacktrace=disabled','-Dgallium-drivers=asahi','-Dvulkan-drivers=asahi',
           '-Degl=enabled','-Dgles1=enabled','-Dgles2=enabled','-Dglx=disabled','-Dglvnd=disabled',
           '-Degl-lib-suffix=_mesa','-Dgles-lib-suffix=_mesa','-Dgbm=disabled',
           '-Dllvm=disabled','-Dmesa-clc=system','-Dprecomp-compiler=system',
           '-Dspirv-tools=disabled','-Dzstd=disabled','-Db_lundef=true','-Dxmlconfig=disabled']
    signature=WORK/'mesa-native-configure-signature.json'
    wanted=json.dumps(flags)
    if not (out/'build.ninja').is_file() or not signature.exists() or signature.read_text()!=wanted:
        setup=['setup']+(['--reconfigure'] if (out/'build.ninja').is_file() else [])
        run(meson+setup+[out,src]+flags,logs/'mesa-native-configure.log',env)
        signature.write_text(wanted)
    if args.configure_only:return
    run(['/opt/homebrew/bin/ninja','-C',out,'-j6'],logs/'mesa-native-build.log',env)
    stage=WORK/'mesa-stage'
    if stage.exists():shutil.rmtree(stage)
    run(meson+['install','-C',out,'--no-rebuild','--destdir',stage],logs/'mesa-native-install.log',env)
    libraries=[]
    for p in out.rglob('*.so*'):
        if p.is_file() and not p.is_symlink() and '/subprojects/' not in str(p) and '/android_stub/' not in str(p):
            libraries.append({'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    receipt={'mesa_commit':subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip(),
             'backend':'Mesa Android EGL/GLES + Asahi Gallium; Honeykrisp Vulkan retained',
             'configuration':flags,'libraries':libraries,'install_stage':str(stage),'hardware_tested':False}
    (WORK/'mesa-native-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Native Android EGL/GLES build complete; runtime not yet tested',flush=True)

if __name__=='__main__':main()

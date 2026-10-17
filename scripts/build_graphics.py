#!/usr/bin/env python3
"""Cross-build upstream minigbm allocator/mapper for Apple DCP on Android."""
import concurrent.futures
import json
import pathlib
import subprocess
import sys
from project_paths import WORK, NDK as NDK_ROOT, GRAPHICS_OUT, SYSTEM_ORIGINAL

BASE = pathlib.Path(__file__).resolve().parents[1]
SRC = BASE / "minigbm"
OUT = GRAPHICS_OUT
VNDK = pathlib.Path("/opt/googlebook/build/aosp-vndk")
NDK = NDK_ROOT / 'bin'
OUT.mkdir(exist_ok=True)
roots = json.loads((BASE / 'build/aosp/include-dirs.json').read_text())
roots = [str(VNDK)+p.split('/aosp-vndk', 1)[1] for p in roots]
includes = [str(SRC), "/opt/googlebook/build/aosp-mapper", "/opt/googlebook/build/aosp-fmq", "/opt/googlebook/build/aosp-aidlcommon/include",
            str(BASE / "mesa/subprojects/libdrm-2.4.123"),
            str(BASE / "mesa/subprojects/libdrm-2.4.123/include/drm")]
includes += roots
flags = ["-fPIC", "-O2", "-D_GNU_SOURCE", "-DANDROID_API_LEVEL=34", "-Wno-deprecated-declarations"]
flags += ["-I" + p for p in includes]
cppflags = ["-std=c++20", "-fno-rtti", "-fno-exceptions", "-nostdinc++", "-isystem", str(VNDK / "external/libcxx/include")]
libdirs = [OUT, BASE / "vendor_work/lib64", pathlib.Path("/opt/googlebook/build/system-original/system/lib64")]
ldflags = ["-Wl,--no-undefined", "-Wl,-z,max-page-size=16384"]
for p in libdirs:
    ldflags += ["-L" + str(p), "-Wl,-rpath-link," + str(p)]

def run(cmd, name):
    p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True)
    (OUT / (name + ".log")).write_text(p.stdout + p.stderr)
    if p.returncode:
        errors = [l for l in (p.stdout + p.stderr).splitlines() if "error:" in l]
        print(name + ":\n" + "\n".join(errors[:10]) + "\nLog: " + str(OUT / (name + ".log")), flush=True)
        raise SystemExit(1)

def compile_one(rel):
    src = SRC / rel
    obj = OUT / (rel.replace("/", "_") + ".o")
    cpp = src.suffix in [".cc", ".cpp"]
    cc = NDK / ("aarch64-linux-android34-clang++" if cpp else "aarch64-linux-android34-clang")
    extra = cppflags if cpp else ["-std=c11"]
    cmd = [cc] + flags + extra + ["-c", src, "-o", obj]
    signature = json.dumps([str(x) for x in cmd])
    stamp = obj.with_suffix(".cmd.json")
    if obj.exists() and obj.stat().st_mtime > src.stat().st_mtime and stamp.exists() and stamp.read_text() == signature:
        return obj
    run(cmd, obj.name)
    stamp.write_text(signature)
    return obj

def objects(files):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(compile_one, files))

def shared(name, objs, libs):
    run([NDK / "aarch64-linux-android34-clang++", "-shared", "-nostdlib++"] +
        [str(o) for o in objs] + ldflags + ["-Wl,-soname," + name, "-o", OUT / name] +
        ["-l" + x for x in libs], name)
    print("BUILT", OUT / name, flush=True)

if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    if phase == 'label-probe':
        run([NDK/'aarch64-linux-android34-clang', BASE/'scripts/selinux_graphics_probe.c',
             '-I'+str(VNDK/'external/selinux/libselinux/include'),
             '-Wl,-z,max-page-size=16384'] + ldflags +
            ['-lselinux', '-o', OUT/'googlebook-labelprobe'], 'label-probe')
        print('BUILT actual Android SELinux graphics label/access probe', flush=True)
    if phase == 'native-vkprobe':
        run([NDK/'aarch64-linux-android34-clang', BASE/'scripts/vulkan_hal_probe.c',
             '-I'+str(BASE/'mesa/include')] +
            flags + ['-I/opt/googlebook/build/swiftshader-android-headers',
            '-I'+str(VNDK/'external/vulkan-headers/include'),
            '-I'+str(VNDK/'system/core/libvndksupport/include')] + ldflags + ['-DGOS_LOGCAT', '-DGOS_REQUIRE_APPLE_GPU',
            '-lvndksupport', '-ldl', '-llog', '-lselinux', '-o', OUT/'googlebook-native-vkprobe'], 'native-vkprobe')
        print('BUILT Apple GPU-only HAL probe logging through logcat', flush=True)
    if phase == 'audio-no-agm':
        run([NDK/'aarch64-linux-android34-clang', '-shared', '-fPIC', '-O2',
             '-Wl,--no-undefined', '-Wl,-z,max-page-size=16384',
             '-Wl,-soname,libgosagmservice.so', BASE/'scripts/audio_no_agm.c',
             '-llog', '-o', OUT/'libgosagmservice.so'], 'audio-no-agm')
        print('BUILT unavailable-AGM adapter for the empty audio profile', flush=True)
    if phase == 'software-keymint':
        flags = ['-I/opt/googlebook/build/aosp-port/security-native'] + flags
        flags += ['-I/opt/googlebook/build/aosp-port/security-generated/include',
                  '-I/opt/googlebook/build/aosp-keymaster/ng/include',
                  '-I/opt/googlebook/build/aosp-keymaster/include',
                  '-I/opt/googlebook/build/aosp-cppbor/include/cppbor',
                  '-I/opt/googlebook/build/aosp-vndk/external/boringssl/src/include']
        objs = objects([str(BASE/'scripts/keymint_software.cpp')])
        run([NDK/'aarch64-linux-android34-clang++', '-nostdlib++'] + objs + ldflags +
            ['-o', OUT/'android.hardware.security.keymint-service.googlebook-software',
             '-lkeymint_fake_latest', '-lkeymaster_portable', '-lpuresoftkeymasterdevice',
             '-l:android.hardware.security.keymint-V5-ndk.so',
             '-l:android.hardware.security.rkp-V3-ndk.so',
             '-l:android.hardware.security.secureclock-V1-ndk.so',
             '-l:android.hardware.security.sharedsecret-V1-ndk.so',
             '-lbinder_ndk', '-llog', '-lc++'], 'software-keymint')
        print('BUILT AOSP software KeyMint service (SecurityLevel::SOFTWARE)', flush=True)
    if phase in ["all", "bootcontrol"]:
        generated = pathlib.Path('/opt/googlebook/build/aosp-port/boot-generated/include')
        assert (generated/'aidl/android/hardware/boot/BnBootControl.h').is_file()
        flags += ['-I' + str(generated)]
        objs = objects([str(BASE/'scripts/bootcontrol_m1.cpp')])
        run([NDK/'aarch64-linux-android34-clang++', '-nostdlib++'] + objs + ldflags +
            ['-o', OUT/'android.hardware.boot-service.googlebook',
             '-l:android.hardware.boot-V1-ndk.so', '-lbinder_ndk', '-llog', '-lc++', '-lz'],
            'bootcontrol-m1')
        print('BUILT single-slot BootControl HAL', flush=True)
    if phase in ["all", "backend_gate"]:
        objs = objects([str(BASE / "scripts/apple_drm_backend_gate.cpp")])
        run([NDK / "aarch64-linux-android34-clang++", "-shared", "-nostdlib++"] +
            [str(o) for o in objs] + ldflags + ["-Wl,-soname,libm1gate.so", "-Wl,--no-as-needed",
            "-lsdmcore", "-ldrm", "-llog", "-Wl,--as-needed", "-o", OUT / "libm1gate.so"], "libm1gate.so")
        print("BUILT", OUT / "libm1gate.so", flush=True)
    if phase in ["all", "core"]:
        files = ["drv.c", "drv_helpers.c", "drv_array_helpers.c", "dumb_driver.c", "asahi.c",
                 "gbm.c", "gbm_helpers.c", "minigbm_helpers.c", "backend_mock.c",
                 "virtgpu.c", "virtgpu_virgl.c", "virtgpu_cross_domain.c", "dma_heap.c", "dri.c"]
        shared("libgbm.so", objects(files), ["drm", "log", "cutils"])
    if phase in ["all", "common"]:
        files = ["cros_gralloc/cros_gralloc_buffer.cc", "cros_gralloc/cros_gralloc_driver.cc",
                 "cros_gralloc/cros_gralloc_helpers.cc", "cros_gralloc/gralloc4/CrosGralloc4Utils.cc"]
        shared("libminigbm_gralloc.so", objects(files),
               ["gbm", "drm", "log", "cutils", "sync", "base", "gralloctypes", "hidlbase", "c++"])
    if phase in ["all", "mapper"]:
        shared("mapper.minigbm.so", objects(["cros_gralloc/mapper_stablec/Mapper.cpp"]),
               ["minigbm_gralloc", "gbm", "drm", "log", "cutils", "base", "gralloctypes", "hidlbase", "c++"])
    if phase in ["all", "legacy"]:
        shared("gralloc.cros.so", objects(["cros_gralloc/gralloc0/gralloc0.cc"]),
               ["minigbm_gralloc", "gbm", "drm", "log", "cutils", "sync", "hardware", "hidlbase", "c++"])
    if phase in ["all", "allocator"]:
        objs = objects(["cros_gralloc/aidl/Allocator.cpp", "cros_gralloc/aidl/Main.cpp", "/opt/googlebook/build/aosp-aidlcommon/NativeHandle.cpp"])
        run([NDK / "aarch64-linux-android34-clang++", "-nostdlib++"] + [str(o) for o in objs] +
            ldflags + ["-o", OUT / "android.hardware.graphics.allocator-service.minigbm"] +
            [("-l:" + x + ".so") if x.startswith("android.") else "-l" + x for x in ["minigbm_gralloc", "android.hardware.graphics.allocator-V2-ndk",
              "android.hardware.common-V2-ndk", "binder_ndk", "log", "cutils", "base", "gralloctypes", "hidlbase", "c++"]], "allocator")
        print("BUILT allocator", flush=True)

#!/usr/bin/env python3
"""Rebuild the known working Asahi kernel with a recorded M1-only profile."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import argparse
from project_paths import BASE, WORK, NDK, LARGE_WORK

SRC = __import__('pathlib').Path('/opt/googlebook/kernel-build/linux-asahi')
PIN = '94fb23346d522edf53722357c426a3e58030beea'
LOG = WORK / 'logs/clean-kernel-build.log'
RUST = SRC.parent / 'rust-1.85.0'

def run(args, **kw):
    subprocess.run([str(x) for x in args], cwd=SRC, check=True, **kw)

def digest(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-number', type=int, default=17)
    parser.add_argument('--native-audio', action='store_true',
                        help='Build Apple/USB audio into Image (separate hardware qualification)')
    parser.add_argument('--native-input', action='store_true',
                        help='Build J293 Touch Bar panel, uinput and keyboard illumination dependencies')
    parser.add_argument('--native-video', action='store_true',
                        help='Build the actual Apple AVD stateless V4L2 decoder and dependencies into Image')
    parser.add_argument('--privileged-gpu-priority', action='store_true',
                        help='Enable capability-checked Asahi HIGH/REALTIME queues and caller-scoped discovery')
    options = parser.parse_args()
    output = LARGE_WORK/('kernel'+str(options.build_number))
    if output.exists():
        raise FileExistsError(f'Kernel artifacts already exist: {output}; select a new build number')
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SRC, text=True).strip() == PIN
    priority_patch = BASE/'scripts/kernel-asahi-privileged-priority.patch'
    if options.privileged_gpu_priority:
        if subprocess.run(['git', 'apply', '--check', str(priority_patch)], cwd=SRC,
                          capture_output=True).returncode == 0:
            run(['git', 'apply', priority_patch])
        else:
            run(['git', 'apply', '--reverse', '--check', priority_patch])
    elif priority_patch.exists() and subprocess.run(
            ['git', 'apply', '--reverse', '--check', str(priority_patch)], cwd=SRC,
            capture_output=True).returncode == 0:
        raise RuntimeError('Priority patch is present: explicitly select --privileged-gpu-priority')
    patch = WORK / 'baseline/active-kernel-local.patch'
    if subprocess.run(['git', 'apply', '--check', str(patch)], cwd=SRC, capture_output=True).returncode == 0:
        run(['git', 'apply', patch])
    else:
        run(['git', 'apply', '--reverse', '--check', patch])
    android_patch = BASE/'scripts/kernel-android-memfd.patch'
    if subprocess.run(['git','apply','--check',str(android_patch)],cwd=SRC,capture_output=True).returncode == 0:
        run(['git','apply',android_patch])
    else:
        run(['git','apply','--reverse','--check',android_patch])
    fence_provenance = json.loads((WORK/'references/drm-fence-fixes/provenance.json').read_text())
    for record in fence_provenance['patches']:
        source_patch = __import__('pathlib').Path(record['patch'])
        assert digest(source_patch) == record['sha256']
        if subprocess.run(['git', 'apply', '--check', str(source_patch)], cwd=SRC,
                          capture_output=True).returncode == 0:
            run(['git', 'apply', source_patch])
        else:
            run(['git', 'apply', '--reverse', '--check', source_patch])
    # The ADP allocation fix is versioned alongside this builder. Keep its
    # exact bytes in the build profile; physical validation is a separate gate.
    adp_patch = BASE/'scripts/kernel-adp-scanout-pitch.patch'
    if subprocess.run(['git', 'apply', '--check', str(adp_patch)], cwd=SRC,
                      capture_output=True).returncode == 0:
        run(['git', 'apply', adp_patch])
    else:
        run(['git', 'apply', '--reverse', '--check', adp_patch])
    (SRC/'scripts/include/bits').mkdir(exist_ok=True)
    shutil.copy2(NDK/'sysroot/usr/include/bits/elf_common.h', SRC/'scripts/include/bits/elf_common.h')
    for name in ('elf.h', 'endian.h', 'byteswap.h'):
        header = (BASE/'scripts/kernel-host-include'/name).read_text()
        header = header.replace('/opt/googlebook/host/android-ndk-r28/toolchains/llvm/prebuilt/darwin-x86_64/sysroot/usr/include/bits/elf_common.h', 'bits/elf_common.h')
        (SRC/'scripts/include'/name).write_text(header)
    config = (BASE/'artifacts/kernel12-checkpoint/config').read_text()
    # These are platform choices, not the ARCH_HAS_* capability symbols.
    platforms = set(re.findall(r'^config (ARCH_\w+)', (SRC/'arch/arm64/Kconfig.platforms').read_text(), re.M))
    disabled = set()
    lines = []
    # Several Qualcomm drivers use product/family names rather than QCOM.
    qcom = re.compile(r'QCOM|QCA|QUALCOMM|MSM|QRTR|QDSP6|(?:^|_)(?:WCD|WSA|LPASS)|'
                      r'^SND_SOC_PM4125|^ATH[0-9_]|^WLAN_VENDOR_ATH$|^NET_VENDOR_ATHEROS$')
    for line in config.splitlines():
        m = re.match(r'CONFIG_(\w+)=(.*)', line)
        if m and m[2] in ('y', 'm') and ((m[1] in platforms and m[1] != 'ARCH_APPLE') or qcom.search(m[1]) or m[1] in ('AT803X_PHY', 'USB_CHIPIDEA')):
            line = '# CONFIG_' + m[1] + ' is not set'
            disabled.add(m[1])
        lines.append(line)
    config = '\n'.join(lines) + '\n'
    forced = ['NET_9P', 'NET_9P_FD', 'NET_9P_VIRTIO', '9P_FS', 'VIRTIO_MMIO', 'CMA_SYSFS', 'FTRACE', 'FTRACE_SYSCALLS',
              'ZRAM', 'ZRAM_BACKEND_LZ4', 'ZRAM_BACKEND_LZO', 'ZRAM_BACKEND_ZSTD', 'HIDRAW', 'MEMFD_ASHMEM_SHIM']
    if options.native_audio:
        # J293's four amplifiers share the shutdown GPIO. The gpiolib core
        # creates auxiliary proxy devices; a module cannot bind without a
        # matching module installation in this direct RAM boot profile.
        forced += ['SND_SOC', 'SND_SOC_APPLE_MACAUDIO', 'SND_SOC_APPLE_AOP_AUDIO',
                   'SND_USB_AUDIO', 'GPIO_SHARED_PROXY']
    if options.native_input:
        forced += ['DRM_ADP', 'DRM_PANEL_SUMMIT', 'INPUT_UINPUT', 'INPUT_EVDEV',
                   'LEDS_PWM', 'PWM_APPLE', 'HID_APPLE', 'GPIO_SHARED_PROXY']
    if options.native_video:
        firmware = json.loads((WORK/'avd-fw-build.json').read_text())
        assert digest(__import__('pathlib').Path(firmware['file'])) == firmware['sha256']
        assert firmware.get('vectors_address') == 0 and firmware.get('reset_vector_in_executable_text'), 'AVD requires verified Cortex-M3 reset vector layout'
        forced += ['MEDIA_SUPPORT', 'VIDEO_DEV', 'MEDIA_CONTROLLER', 'MEDIA_PLATFORM_SUPPORT',
                   'MEDIA_PLATFORM_DRIVERS', 'V4L_PLATFORM_DRIVERS', 'VIDEO_APPLE_AVD']
    for symbol in forced:
        config, count = re.subn(r'^(?:# )?CONFIG_' + symbol + r'(?:=.*| is not set)$', 'CONFIG_' + symbol + '=y', config, flags=re.M)
        if not count:
            config += 'CONFIG_' + symbol + '=y\n'
    (SRC/'.config').write_text(config)
    rust_source = SRC.parent/'rust-src'
    if not rust_source.exists():
        rust_source.symlink_to(RUST/'lib/rustlib/src/rust/library', target_is_directory=True)
    hostbin = SRC.parent/'host-bin'
    hostbin.mkdir(exist_ok=True)
    if not (hostbin/'sed').exists():
        (hostbin/'sed').symlink_to('/opt/homebrew/bin/gsed')
    env = os.environ.copy()
    env.update(PATH=':'.join(map(str, [hostbin, RUST/'bin', WORK/'kernel-tools/bin', '/opt/homebrew/opt/make/libexec/gnubin', '/opt/homebrew/opt/llvm@19/bin', NDK/'bin', '/opt/homebrew/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin'])),
               LIBCLANG_PATH='/opt/homebrew/opt/llvm@19/lib', LC_ALL='C',
               RUST_LIB_SRC=str(rust_source),
               KBUILD_BUILD_USER='googlebook', KBUILD_BUILD_HOST='m1-clean-build', KBUILD_BUILD_VERSION=str(options.build_number))
    args = ['/opt/homebrew/bin/gmake', 'ARCH=arm64', 'LLVM=1', 'HOSTCC=/usr/bin/clang', 'HOSTCXX=/usr/bin/clang++', 'KRUSTFLAGS=-Aunknown_lints']
    with LOG.open('w') as log:
        run(args + ['olddefconfig'], env=env, stdout=log, stderr=subprocess.STDOUT)
        final = (SRC/'.config').read_text()
        enabled = re.findall(r'^CONFIG_(\w+)=[ym]$', final, re.M)
        residual = [s for s in enabled if qcom.search(s)]
        assert not residual, 'Qualcomm remains enabled: ' + repr(residual)
        required = ['ARM64_16K_PAGES', 'ARCH_APPLE', 'RUST', 'DRM_ASAHI', 'DRM_APPLE', 'NET_9P_VIRTIO', '9P_FS', 'CMA_SYSFS', 'FTRACE_SYSCALLS', 'TRACING', 'BPF_EVENTS', 'ZRAM', 'ZSMALLOC', 'MEMFD_ASHMEM_SHIM']
        if options.native_audio:
            required += ['SND_SOC', 'SND_SOC_APPLE_MCA', 'SND_SOC_APPLE_MACAUDIO', 'SND_SOC_APPLE_AOP_AUDIO',
                         'SND_SOC_TAS2770', 'SND_SOC_CS42L83', 'APPLE_ADMAC', 'APPLE_SIO',
                         'SND_USB_AUDIO', 'GPIO_SHARED_PROXY']
        if options.native_input:
            required += ['DRM_ADP', 'DRM_PANEL_SUMMIT', 'INPUT_UINPUT', 'INPUT_EVDEV',
                         'LEDS_PWM', 'PWM_APPLE', 'HID_APPLE', 'GPIO_SHARED_PROXY']
        if options.native_video:
            required += ['VIDEO_APPLE_AVD', 'VIDEO_DEV', 'MEDIA_CONTROLLER',
                         'V4L2_MEM2MEM_DEV', 'VIDEOBUF2_DMA_CONTIG']
        for symbol in required:
            assert 'CONFIG_' + symbol + '=y' in final, 'Missing required kernel feature: ' + symbol
        (WORK/'clean-kernel-profile.json').write_text(json.dumps({'commit': PIN, 'disabled': sorted(disabled),
            'qualcomm_enabled': residual, 'qualcomm_filter': qcom.pattern,
            'qualcomm_coverage': 'known named symbols; not a complete dependency/firmware audit',
            'native_audio_builtin': options.native_audio, 'drm_fence_patches': fence_provenance['patches'],
            'native_input_builtin': options.native_input,
            'native_AVD_decoder_builtin': options.native_video,
            'privileged_gpu_priority': options.privileged_gpu_priority,
            'gpu_priority_patch': ({'file': str(priority_patch), 'sha256': digest(priority_patch),
                'authorization': 'CAP_SYS_NICE in initial user namespace, rechecked for each elevated queue',
                'discovery': 'Caller-scoped availability snapshot in GET_PARAMS; no privilege grant',
                'hard_realtime_guarantee': False, 'hardware_verified': False}
                if options.privileged_gpu_priority else None),
            'AVD_firmware': firmware if options.native_video else None,
            'adp_pitch_patch': {'file': str(adp_patch), 'sha256': digest(adp_patch), 'hardware_verified': False},
            'config_sha256': digest(SRC/'.config'), 'hardware_verified': False}, indent=2)+'\n')
        run(args + ['-j6', 'Image', 'dtbs'], env=env, stdout=log, stderr=subprocess.STDOUT)
    output.mkdir(exist_ok=True)
    files = {}
    for source, name in ((SRC/'arch/arm64/boot/Image', 'Image'), (SRC/'arch/arm64/boot/dts/apple/t8103-j293.dtb', 't8103-j293.dtb'), (SRC/'.config', 'config')):
        shutil.copy2(source, output/name)
        files[name] = {'bytes': source.stat().st_size, 'sha256': digest(source)}
    (WORK/'clean-kernel-build.json').write_text(json.dumps({'output': str(output), 'files': files, 'hardware_verified': False}, indent=2)+'\n')
    for name in ('clean-kernel-profile.json', 'clean-kernel-build.json'):
        shutil.copy2(WORK/name, output/name)
    print('Kernel build complete:', output)

if __name__ == '__main__':
    main()

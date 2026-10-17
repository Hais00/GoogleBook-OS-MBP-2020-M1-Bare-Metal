#!/usr/bin/env python3
"""Reproduce the real DRM callback race in two offline ARM64 kernels.

An isolated APFS build clone contains the production objects. The negative
control uses the original CRTC implementation; the positive case uses the full
published two-patch fix. No production source, image, or physical device is
modified. The fixture controls the precise ops-read/signal/callback ordering.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from project_paths import BASE, WORK, LARGE_WORK, NDK
from boot_config import BOOT_ARGS

PRODUCTION = Path('/opt/googlebook/kernel-build/linux-asahi')
CLONE = PRODUCTION.parent/'googlebook-fence-regression-kernel'
OUT = LARGE_WORK/'drm-fence-callback-regression'
REL = Path('drivers/gpu/drm/drm_crtc.c')


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def save(path, record):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(record, indent=2)+'\n')
    temp.replace(path)


def runtime(variant, image, root):
    control = Path(tempfile.mkdtemp(prefix='googlebook-fence-'+variant+'-', dir=Path.home()/'.local'))
    qmp = control/'qmp.sock'
    log = root/'kernel-uart.log'
    command = ['/opt/homebrew/bin/qemu-system-aarch64', '-name', 'fence-regression-'+variant,
        '-machine', 'virt,accel=hvf,gic-version=3', '-cpu', 'host', '-smp', '2', '-m', '2048',
        '-display', 'none', '-monitor', 'none', '-no-reboot', '-nic', 'none',
        '-kernel', str(image), '-initrd', str(LARGE_WORK/'ram-bootstrap/android-initrd.img'),
        '-append', BOOT_ARGS.replace('console=tty0 console=ttySAC0,115200n8', 'console=ttyAMA0'),
        '-serial', 'file:'+str(log), '-qmp', 'unix:'+str(qmp)+',server=on,wait=off']
    with (root/'qemu-host.log').open('wb') as output:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output, stderr=output)
    note = {'pid': process.pid, 'command': command, 'physical_disks_attached': False}
    save(root/'qemu-state.json', note)
    try:
        text = ''
        deadline = time.monotonic()+40
        while time.monotonic() < deadline and process.poll() is None:
            text = log.read_text(errors='replace') if log.exists() else ''
            if ('end Kernel panic' in text or
                (variant == 'fixed' and 'GOS_DRM_FENCE_RACE_PASS' in text and
                 'init first stage started' in text.lower())):
                break
            time.sleep(.1)
        if variant == 'control':
            passed = ('GOS_DRM_FENCE_RACE_BEGIN' in text and
                      'kernel BUG at drivers/gpu/drm/drm_crtc.c' in text and
                      'drm_crtc_fence_get_driver_name' in text and
                      'Kernel panic - not syncing' in text and
                      'GOS_DRM_FENCE_RACE_PASS' not in text)
        else:
            passed = ('GOS_DRM_FENCE_RACE_PASS' in text and
                      'init first stage started' in text.lower() and
                      'Kernel panic' not in text and 'GOS_DRM_FENCE_RACE_FAIL' not in text)
        note.update(pass_expected_outcome=passed, uart_sha256=digest(log),
                    kernel_uart_log=str(log),
                    expected='specific original DRM BUG' if variant == 'control' else 'callbacks succeed')
    finally:
        if process.poll() is None:
            try:
                with socket.socket(socket.AF_UNIX) as s:
                    s.settimeout(3)
                    s.connect(str(qmp))
                    f = s.makefile('rwb', buffering=0)
                    f.readline()
                    f.write(b'{"execute":"qmp_capabilities"}\n')
                    while b'"return"' not in f.readline():
                        pass
                    f.write(b'{"execute":"quit"}\n')
                process.wait(timeout=10)
            except Exception:
                process.terminate()
                process.wait(timeout=10)
        note['qemu_stopped'] = process.poll() is not None
        save(root/'runtime-result.json', note)
    assert note['pass_expected_outcome'], root/'kernel-uart.log'
    return note


def main():
    assert CLONE.is_dir() and CLONE != PRODUCTION
    assert (CLONE/'.git').is_dir()
    OUT.mkdir(exist_ok=False)
    fixed = (PRODUCTION/REL).read_bytes()
    reference = WORK/'references/drm-fence-fixes'
    metadata = json.loads((reference/'57acb869490b504996ea46cbb80af49e35ec66e1.json').read_text())
    assert blob(fixed) == metadata['tree_diff'][0]['new_id']
    old_metadata = json.loads((reference/'bbea9e696f0cca2573b58f89bfbb19af03595c5a.json').read_text())
    old = subprocess.check_output(['git', 'show', 'HEAD:'+str(REL)], cwd=CLONE)
    assert blob(old) == old_metadata['tree_diff'][0]['old_id']
    config_sha = digest(LARGE_WORK/'kernel19/config')
    assert digest(CLONE/'.config') == config_sha
    fragment = (BASE/'scripts/tests/drm_fence_callback_regression.inc').read_bytes()
    before = {'source': digest(PRODUCTION/REL), 'config': digest(PRODUCTION/'.config'),
              'production_image': digest(LARGE_WORK/'kernel19/Image')}
    env = os.environ.copy()
    hostbin = PRODUCTION.parent/'host-bin'
    rust = PRODUCTION.parent/'rust-1.85.0'
    env.update(PATH=':'.join(map(str, [hostbin, rust/'bin', WORK/'kernel-tools/bin',
        '/opt/homebrew/opt/make/libexec/gnubin', '/opt/homebrew/opt/llvm@19/bin', NDK/'bin',
        '/opt/homebrew/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin'])),
        LIBCLANG_PATH='/opt/homebrew/opt/llvm@19/lib', LC_ALL='C',
        RUST_LIB_SRC=str(PRODUCTION.parent/'rust-src'), KBUILD_BUILD_USER='googlebook-regression',
        KBUILD_BUILD_HOST='offline-only', KBUILD_BUILD_VERSION='19',
        KBUILD_BUILD_TIMESTAMP='2026-10-17 00:00:00 +0000')
    command = ['/opt/homebrew/bin/gmake', 'ARCH=arm64', 'LLVM=1', 'HOSTCC=/usr/bin/clang',
               'HOSTCXX=/usr/bin/clang++', 'KRUSTFLAGS=-Aunknown_lints', '-j4', 'Image']
    results = {}
    state = {'host_pid': os.getpid(), 'clone': str(CLONE), 'physical_device_used': False,
             'fixture_sha256': hashlib.sha256(fragment).hexdigest(), 'config_sha256': config_sha,
             'hardware_qualified': False, 'production_before': before, 'results': results}
    save(OUT/'state.json', state)
    for variant, core in [('control', old), ('fixed', fixed)]:
        root = OUT/variant
        root.mkdir()
        (CLONE/REL).write_bytes(core+b'\n'+fragment)
        state.update(phase=variant+'-build', core_source_git_blob=blob(core))
        with (root/'build.log').open('wb') as output:
            process = subprocess.Popen(command, cwd=CLONE, env=env, stdout=output, stderr=output)
            state['build_pid'] = process.pid
            save(OUT/'state.json', state)
            assert process.wait() == 0, root/'build.log'
        assert digest(CLONE/'.config') == config_sha
        image = root/'Image'
        shutil.copy2(CLONE/'arch/arm64/boot/Image', image)
        save(root/'build.json', {'image_sha256': digest(image), 'core_source_git_blob': blob(core),
             'fixture_sha256': state['fixture_sha256'], 'command': command,
             'test_only': True, 'hardware_launch_allowed': False})
        state['phase'] = variant+'-runtime'
        save(OUT/'state.json', state)
        results[variant] = runtime(variant, image, root)
        save(OUT/'state.json', state)
        print('DRM_FENCE_RUNTIME_EXPECTED_OUTCOME_PASS', variant, flush=True)
    after = {'source': digest(PRODUCTION/REL), 'config': digest(PRODUCTION/'.config'),
             'production_image': digest(LARGE_WORK/'kernel19/Image')}
    assert before == after
    state.update(phase='complete', passed=True, production_unchanged=True, production_after=after,
                 scope='Actual DMA-fence/CRTC callbacks with deterministic RCU ops snapshot interleaving; '
                       'does not test CRTC teardown, physical display, or GPU/DMA hardware drain')
    save(OUT/'state.json', state)
    print('DRM_FENCE_CALLBACK_REGRESSION_PASS', flush=True)


if __name__ == '__main__':
    main()

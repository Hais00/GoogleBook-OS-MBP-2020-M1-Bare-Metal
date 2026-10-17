#!/usr/bin/env python3
"""Build the public AOSP Bluetooth V1 HAL with its Linux HCI transport."""
import hashlib
import json
from pathlib import Path
import subprocess
from project_paths import BASE, WORK, NDK, VNDK, SYSTEM_ORIGINAL

SOURCE = WORK/'references/aosp-bluetooth-15'
OUTPUT = WORK/'bluetooth-linux-build'


def main():
    pin = json.loads((SOURCE/'provenance.json').read_text())
    assert pin['commit'] == '488942f82bd1bc9ad1cb65a02c71421dc3a6a3d6'
    OUTPUT.mkdir(exist_ok=True)
    generated = OUTPUT/'generated'
    generated.mkdir(exist_ok=True)
    frozen = SOURCE/'aidl'
    files = sorted(frozen.rglob('*.aidl'))
    command = [BASE/'build/aosp/aidl', '--lang=ndk', '--structured',
               '--stability=vintf', '--min_sdk_version=34', '--version=1',
               '--hash='+(frozen/'.hash').read_text().splitlines()[-1],
               '-I', frozen, '-o', generated/'src', '-h', generated/'include'] + files
    subprocess.run(list(map(str, command)), check=True)
    roots = json.loads((BASE/'build/aosp/include-dirs.json').read_text())
    roots = [Path(str(VNDK)+p.split('/aosp-vndk', 1)[1]) for p in roots]
    includes = [generated/'include', SOURCE/'default', SOURCE/'hci', SOURCE/'async',
                Path('/opt/googlebook/build/aosp-fmq'), Path('/opt/googlebook/build/aosp-aidlcommon/include'),
                WORK/'aosp-binder-ndk/include_cpp', WORK/'aosp-binder-ndk/include_ndk',
                WORK/'aosp-binder-ndk/include_platform'] + roots
    flags = ['--target=aarch64-linux-android36', '-std=c++17', '-fPIC', '-O2',
             '-Wall', '-Wextra', '-fno-rtti', '-fno-exceptions', '-nostdinc++',
             '-isystem', str(VNDK/'external/libcxx/include'),
             '-D_GNU_SOURCE', '-DANDROID'] + ['-I'+str(p) for p in includes]
    sources = [SOURCE/p for p in ['default/service.cpp', 'default/BluetoothHci.cpp',
               'default/net_bluetooth_mgmt.cpp', 'hci/hci_packetizer.cc',
               'hci/h4_protocol.cc', 'async/async_fd_watcher.cc']]
    # Backport the upstream Linux rfkill correction without changing the
    # frozen V1 Binder interface or any other HCI implementation code.
    modern_root = WORK/'references/aosp-hals-16qpr2'
    modern_pin = json.loads((modern_root/'provenance.json').read_text())
    assert modern_pin['commit'] == 'aa229558cbf04bc997ed27465c5e7ad497123d1b'
    modern = modern_root/'bluetooth/aidl/default/net_bluetooth_mgmt.cpp'
    modern_hash = '1237e1858eb288f79d713f59cee1dcd53ecc7d24117f41c2889da765d2d96840'
    assert hashlib.sha256(modern.read_bytes()).hexdigest() == modern_hash
    legacy = (SOURCE/'default/net_bluetooth_mgmt.cpp').read_text()
    opening, closing = legacy.split('void NetBluetoothMgmt::closeHci()', 1)
    expected = opening.replace('  // Block Bluetooth.\n  rfkill(1);',
                               '  // Unblock Bluetooth.\n  rfkill(0);', 1)
    expected += 'void NetBluetoothMgmt::closeHci()' + closing.replace(
        '  // Unblock Bluetooth.\n  rfkill(0);', '  // Block Bluetooth.\n  rfkill(1);', 1)
    assert expected == modern.read_text(), 'Backport must contain only upstream rfkill polarity correction'
    overlay = OUTPUT/'source/net_bluetooth_mgmt.cpp'
    overlay.parent.mkdir(exist_ok=True)
    overlay.write_bytes(modern.read_bytes())
    logical_sources = [str(p.relative_to(SOURCE)) for p in sources]
    sources[2] = overlay  # Includes the unchanged V1 helper header via SOURCE/default.
    objects = []
    for source in sources:
        obj = OUTPUT/(source.stem+'.o')
        result = subprocess.run([str(NDK/'bin/clang++')] + flags +
                                ['-c', str(source), '-o', str(obj)], capture_output=True, text=True)
        obj.with_suffix('.log').write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(source.name+':\n'+result.stderr[-6000:])
        objects.append(obj)
    binary = OUTPUT/'android.hardware.bluetooth-service.default'
    link = [NDK/'bin/aarch64-linux-android35-clang++', '-nostdlib++',
            '-Wl,--no-undefined', '-Wl,-z,max-page-size=16384', '-o', binary] + objects
    for directory in [BASE/'vendor_work/lib64', SYSTEM_ORIGINAL/'lib64']:
        link += ['-L'+str(directory), '-Wl,-rpath-link,'+str(directory)]
    link += ['-l:'+name+'.so' for name in ['android.hardware.bluetooth-V1-ndk',
             'libbase', 'libbinder_ndk', 'libcutils', 'libhidlbase', 'libutils', 'liblog', 'libc++']]
    result = subprocess.run(list(map(str, link)), capture_output=True, text=True)
    (OUTPUT/'link.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr)
    receipt = {'source_commit': pin['commit'], 'interface_version': 1,
               'source_files': {name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for name,p in zip(logical_sources,sources)},
               'rfkill_backport': {'source_commit': modern_pin['commit'],
                    'source_sha256': modern_hash,
                    'scope': 'Unblock before HCI user-channel bind; block after closing it',
                    'frozen_V1_interface_unchanged': True, 'only_two_rfkill_calls_and_comments_changed': True},
               'binary': str(binary), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
               'transport': 'AOSP Linux HCI user channel; actual kernel controller required',
               'hardware_verified': False, 'staged': False}
    (WORK/'bluetooth-linux-build.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('BLUETOOTH_LINUX_BUILD_PASS', binary)


if __name__ == '__main__':
    main()

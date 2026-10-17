#!/usr/bin/env python3
"""Prepare a diskless Android linker test with the M1's actual namespace config."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from project_paths import BASE, WORK, NDK, SYSTEM_ORIGINAL, LARGE_WORK

BUILD = Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance/build')
ROOT = BUILD/'vendor-namespace-test'


def needed(path):
    result = subprocess.run([str(NDK/'bin/llvm-readelf'), '--dynamic', str(path)],
                            check=True, capture_output=True, text=True)
    return re.findall(r'\(NEEDED\).*?\[(.*?)\]', result.stdout)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o755 if '/bin/' in str(target) else 0o644)


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', type=Path,
                        default=WORK/'gatekeeper-nonsecure-build/android.hardware.gatekeeper-service.nonsecure')
    parser.add_argument('--fixture', default='vendor-namespace-test')
    parser.add_argument('--vendor-root', type=Path, default=WORK/'vendor-egl-stage')
    parser.add_argument('--library', type=Path, action='append', default=[])
    parser.add_argument('--copy-executable', action='store_true', help='Copy actual CPU fixture; never run a hardware provider in QEMU')
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9-]+', args.fixture)
    ROOT = BUILD/args.fixture
    vendor = args.vendor_root.resolve()
    assert vendor.is_dir() and vendor.is_relative_to(WORK.resolve())
    overrides = {path.name: path.resolve() for path in args.library}
    assert all(path.is_file() and path.is_relative_to(WORK.resolve()) for path in overrides.values())
    config = LARGE_WORK/'trial-native-egl-kernel17-b/linkerconfig-ld.config.txt'
    capture = json.loads(config.with_name('linkerconfig-capture.json').read_text())
    assert hashlib.sha256(config.read_bytes()).hexdigest() == capture['sha256']
    section = re.search(r'\[vendor\]\n(.*?)(?:\n\[|\Z)', config.read_text(), re.S)[1]
    allowed = set()
    for line in section.splitlines():
        if re.match(r'namespace.default.link.system.shared_libs\s*\+?=', line):
            allowed.update(line.split('=', 1)[1].strip().split(':'))
    assert 'libc.so' in allowed and 'libkeymaster_portable.so' not in allowed
    executable = args.executable.resolve()
    assert executable.is_relative_to(WORK.resolve())
    libraries = needed(executable)
    source = ROOT/'link-test.c'
    ROOT.mkdir(exist_ok=True)
    if (ROOT/'vendor/lib64').exists():
        shutil.rmtree(ROOT/'vendor/lib64')
    source.write_text('#include <stdio.h>\nint main(void) { puts("VENDOR_NAMESPACE_LINK_PASS"); return 0; }\n')
    test = ROOT/'vendor/bin/hw/gatekeeper-link-test'
    test.parent.mkdir(parents=True, exist_ok=True)
    command = [str(NDK/'bin/aarch64-linux-android35-clang'), '-Wl,-z,max-page-size=16384',
               '-Wl,--no-as-needed', str(source), '-L'+str(vendor/'lib64'),
               '-L'+str(SYSTEM_ORIGINAL/'lib64'), '-Wl,-rpath-link,'+str(vendor/'lib64'),
               '-Wl,-rpath-link,'+str(SYSTEM_ORIGINAL/'lib64'), '-o', str(test)]
    for path in args.library:
        command.insert(1, '-L'+str(path.resolve().parent))
        command.insert(1, '-Wl,-rpath-link,'+str(path.resolve().parent))
    command += ['-l:'+name for name in libraries]
    subprocess.run(command, check=True)
    copy(config, ROOT/'linkerconfig/ld.config.txt')
    copy(BUILD/'secilc-bionic/system/bin/bootstrap/linker64', ROOT/'system/bin/linker64')
    queue = [('vendor', name) for name in libraries]
    # Deliberately keep the inaccessible private libraries in /system, so
    # the baseline test detects namespace isolation rather than missing files.
    queue += [('system', name) for name in ['libkeymaster_portable.so', 'libcppbor.so', 'libcppcose_rkp.so']]
    seen, missing, sources = set(), set(), {}
    while queue:
        namespace, name = queue.pop()
        if (namespace, name) in seen:
            continue
        seen.add((namespace, name))
        if namespace == 'vendor':
            candidates = ([overrides[name]] if name in overrides else [])+[vendor/'lib64'/name, vendor/'lib64/hw'/name, vendor/'lib64/egl'/name]
            found = next((p for p in candidates if p.is_file()), None)
            if found is None:
                if name in allowed:
                    queue.append(('system', name))
                else:
                    missing.add(name)
                continue
            destination = ROOT/'vendor/lib64'/name
        else:
            candidates = [SYSTEM_ORIGINAL/'lib64'/name, SYSTEM_ORIGINAL/'lib64/bootstrap'/name]
            found = next((p for p in candidates if p.is_file()), None)
            assert found is not None, ('missing actual system library', name)
            destination = ROOT/'system/lib64'/name
        copy(found, destination)
        sources[str(destination.relative_to(ROOT))] = {'source': str(found),
            'sha256': hashlib.sha256(found.read_bytes()).hexdigest()}
        queue += [(namespace, dep) for dep in needed(found)]
    for name in ['libc.so', 'libm.so', 'libdl.so']:
        original = SYSTEM_ORIGINAL/'lib64/bootstrap'/name
        for folder in ['system/lib64/bootstrap', 'apex/com.android.runtime/lib64/bionic']:
            copy(original, ROOT/folder/name)
    if args.copy_executable:
        copy(executable, ROOT/'vendor/bin/hw'/executable.name)
    for directory in ['dev', 'proc', 'sys']:
        (ROOT/directory).mkdir(exist_ok=True)
    receipt = {'actual_linker_config_sha256': capture['sha256'],
               'vendor_missing_private_libraries': sorted(missing),
               'link_test_needed': needed(test), 'provider_needed': libraries,
               'provider': str(executable), 'vendor_root': str(vendor),
               'library_overrides': {name: str(path) for name, path in overrides.items()},
               'sources': sources, 'dynamic_test_pass': False,
               'physical_device_written': False}
    (BUILD/(args.fixture+'-preparation.json')).write_text(json.dumps(receipt, indent=2)+'\n')
    print('VENDOR_NAMESPACE_FIXTURE_READY; private libraries missing:', sorted(missing))


if __name__ == '__main__':
    main()

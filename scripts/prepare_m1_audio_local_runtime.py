#!/usr/bin/env python3
"""Prepare real Bionic/Binder software audio services in an isolated diskless VM."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from project_paths import BASE, WORK, NDK, SYSTEM_ORIGINAL, LARGE_WORK

ROOT = LARGE_WORK/'audio-software-local-runtime'
VENDOR = WORK/'vendor-audio-stage'
ORIGINAL = WORK/'references/audio-apex-elf-audit'

def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='')
    args = parser.parse_args()
    assert not args.label or re.fullmatch('[a-z0-9-]+', args.label)
    if args.label: ROOT = ROOT.with_name(ROOT.name+'-'+args.label)
    assert not ROOT.exists(), 'Use a new fixture name for revised inputs'
    ROOT.mkdir()
    root = ROOT/'root'
    root.mkdir()
    sources = {}
    def copy(source, relative):
        target = root/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o755 if '/bin/' in '/'+relative else 0o644)
        sources[relative] = {'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    def needed(path):
        result = subprocess.check_output([str(NDK/'bin/llvm-readelf'), '-d', str(path)], text=True)
        return re.findall(r'\(NEEDED\).*?\[(.*?)\]', result)
    programs = [
        ('vendor', VENDOR/'bin/hw/googlebook-audio-hal', 'vendor/bin/hw/googlebook-audio-hal'),
        ('vendor', ORIGINAL/'bin/hw/dras.core-cpp.audio', 'vendor/bin/hw/dras.core-cpp.audio'),
        ('vendor', WORK/'native-audio-local-tests/audio-local-binder-probe', 'vendor/bin/hw/audio-local-binder-probe'),
        ('system', WORK/'native-audio-local-tests/audio-local-properties', 'system/bin/audio-local-properties'),
        ('system', WORK/'native-audio-local-tests/audio-local-binderfs', 'system/bin/audio-local-binderfs'),
        ('system', WORK/'native-audio-local-tests/audio-local-policy', 'system/bin/audio-local-policy'),
        ('system', WORK/'native-audio-local-tests/audio-local-log-capture', 'system/bin/audio-local-log-capture'),
        ('system', SYSTEM_ORIGINAL/'bin/servicemanager', 'system/bin/servicemanager'),
        ('system', SYSTEM_ORIGINAL/'bin/logd', 'system/bin/logd'),
        ('system', SYSTEM_ORIGINAL/'bin/logcat', 'system/bin/logcat'),
    ]
    queue = []
    for ns, source, relative in programs:
        copy(source, relative)
        queue += [(ns, name) for name in needed(source)]
    # The provided arpal executable loads these by name, even for the existing
    # nothing-primary profile. Keep the actual installed libraries in this
    # fixture too; no substitute PAL implementation is supplied by the test.
    queue += [('vendor', name) for name in ['libar-pal.so', 'libpalclient.so', 'libgosagmservice.so']]
    config = LARGE_WORK/'trial-native-egl-kernel17-b/linkerconfig-ld.config.txt'
    copy(config, 'linkerconfig/ld.config.txt')
    section = re.search(r'\[vendor\]\n(.*?)(?:\n\[|\Z)', config.read_text(), re.S)[1]
    allowed = set()
    for line in section.splitlines():
        if re.match(r'namespace.default.link.system.shared_libs\s*\+?=', line):
            allowed.update(line.split('=', 1)[1].strip().split(':'))
    seen = set()
    while queue:
        ns, name = queue.pop()
        if (ns, name) in seen: continue
        seen.add((ns, name))
        if ns == 'vendor':
            choices = [VENDOR/'lib64'/name, ORIGINAL/'lib64'/name]
            found = next((p for p in choices if p.is_file()), None)
            if found is None:
                assert name in allowed, ('inaccessible vendor dependency', name)
                queue.append(('system', name)); continue
        else:
            choices = [SYSTEM_ORIGINAL/'lib64'/name, SYSTEM_ORIGINAL/'lib64/bootstrap'/name]
            found = next((p for p in choices if p.is_file()), None)
            assert found, ('missing actual system dependency', name)
        copy(found, ns+'/lib64/'+name)
        queue += [(ns, dep) for dep in needed(found)]
    for name in ['libc.so', 'libm.so', 'libdl.so']:
        for folder in ['system/lib64/bootstrap', 'apex/com.android.runtime/lib64/bionic']:
            copy(SYSTEM_ORIGINAL/'lib64/bootstrap'/name, folder+'/'+name)
    copy(SYSTEM_ORIGINAL/'bin/bootstrap/linker64', 'system/bin/linker64')
    copy(SYSTEM_ORIGINAL/'bin/bootstrap/linker64', 'system/bin/bootstrap/linker64')
    policy = Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance/build/policy-input22/policy-input22.bin')
    # The validated compiler input contains one additional blank line. Every
    # nonempty source line must match exactly; no permission change is waived.
    assert [s for s in (VENDOR/'etc/selinux/vendor_sepolicy.cil').read_text().splitlines() if s.strip()] == [
        s for s in (policy.parent/'vendor/vendor_sepolicy.cil').read_text().splitlines() if s.strip()]
    copy(policy, 'cpu-fixture-policy.bin')
    for relative in ['etc/selinux', 'etc/vintf']:
        shutil.copytree(SYSTEM_ORIGINAL/relative, root/'system'/relative, symlinks=True)
    shutil.copytree(VENDOR/'etc', root/'vendor/etc', symlinks=True)
    # The original APEX declarations participate in the real service registry.
    archive = Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance/build/audio-apex-original-files.tar')
    with tarfile.open(archive) as tar:
        for member in tar:
            name = member.name.removeprefix('./')
            if member.isfile() and name.startswith('etc/vintf/'):
                target = root/'vendor/etc/vintf/manifest'/Path(name).name
                target.write_bytes(tar.extractfile(member).read())
    for directory in ['dev', 'proc', 'sys', 'data/local/tmp', 'data/vendor/audio', 'tmp', 'mnt', 'odm/etc', 'product/etc']:
        (root/directory).mkdir(parents=True, exist_ok=True)
    (root/'GOS_LOCAL_AUDIO_TEST').write_text('Diskless CPU software-service fixture, not production\n')
    copy(BASE/'scripts/audio_local_runtime.sh', 'test.sh')
    record = {'root': str(root), 'sources': sources, 'actual_linkerconfig_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
              'software_providers_unchanged': True, 'fixture_paths_relocated_to_vendor': True,
              'hardware_devices_exposed': False, 'SELinux_runtime_qualified': False,
              'physical_device_written': False}
    (ROOT/'preparation.json').write_text(json.dumps(record, indent=2)+'\n')
    print('LOCAL_AUDIO_SOFTWARE_FIXTURE_READY', len(sources))

if __name__ == '__main__': main()

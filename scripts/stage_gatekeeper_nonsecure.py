#!/usr/bin/env python3
"""Select AOSP's declared nonsecure Gatekeeper for the M1 software profile."""
import ctypes
import hashlib
import json
import shutil
from project_paths import WORK, SYSTEM_ORIGINAL
from stage_native_egl import copy_labeled, lib, getlabel


def main():
    receipt = json.loads((WORK/'gatekeeper-nonsecure-build.json').read_text())
    assert receipt['credential_tests_pass']
    assert receipt['shared_secret_with_installed_puresoft_keymaster_pass']
    assert not receipt['hardware_backed']
    binary = WORK/'gatekeeper-nonsecure-build/android.hardware.gatekeeper-service.nonsecure'
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == receipt['binary_sha256']
    vendor = WORK/'vendor-egl-stage'
    reference = WORK/'references/aosp-hals-16qpr2/gatekeeper/aidl/software'
    target = vendor/'bin/hw'/binary.name
    shutil.copy2(binary, target)
    label = b'u:object_r:hal_gatekeeper_default_exec:s0\0'
    assert lib.setxattr(str(target).encode(), b'security.selinux', label, len(label), 0, 1) == 0
    assert getlabel(target) == label
    # These private implementation libraries are not LLNDK exports. Package
    # them with the vendor HAL instead of widening Android's namespace links.
    dependencies = {}
    for name in ['libkeymaster_portable.so', 'libcppbor.so', 'libcppcose_rkp.so']:
        source = SYSTEM_ORIGINAL/'lib64'/name
        copy_labeled(source, vendor/'lib64'/name, vendor/'lib64/libgatekeeper.so')
        dependencies[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    config = vendor/'etc/init/android.hardware.gatekeeper-service.nonsecure.rc'
    config_reference = vendor/'etc/init/allocator-minigbm.rc'
    copy_labeled(reference/config.name, config, config_reference)
    text = config.read_text().replace('/apex/com.android.hardware.gatekeeper/bin/hw/', '/vendor/bin/hw/')
    text += ('    interface aidl android.hardware.gatekeeper.IGatekeeper/default\n'
             '    interface aidl android.hardware.security.sharedsecret.ISharedSecret/gatekeeper\n')
    config.write_text(text)
    for name in ['android.hardware.gatekeeper-service.nonsecure.xml',
                 'android.hardware.security.sharedsecret-gatekeeper.xml']:
        copy_labeled(reference/name, vendor/'etc/vintf/manifest'/name, config_reference)
    contexts = vendor/'etc/selinux/vendor_file_contexts'
    rule = (r'/(vendor|system/vendor)/bin/hw/android\.hardware\.gatekeeper-service\.nonsecure'
            ' u:object_r:hal_gatekeeper_default_exec:s0')
    text = contexts.read_text()
    if rule not in text:
        contexts.write_text(text+'\n'+rule+'\n')
    service_contexts = (vendor/'etc/selinux/vendor_service_contexts').read_text()
    assert 'android.hardware.security.sharedsecret.ISharedSecret/gatekeeper' in service_contexts
    removed = []
    for name in ['bin/hw/android.hardware.gatekeeper-service.trusty',
                 'etc/init/android.hardware.gatekeeper-service.trusty.rc',
                 'etc/vintf/manifest/android.hardware.gatekeeper-service.trusty.xml']:
        p = vendor/name
        if p.exists():
            removed.append({'file': name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
            p.unlink()
    (WORK/'gatekeeper-nonsecure-stage.json').write_text(json.dumps({
        'provider': binary.name, 'hardware_backed': False,
        'credential_tests_pass': True, 'software_keymint_shared_secret_test_pass': True,
        'startup_class': 'early_hal', 'new_selinux_allow_rules': 0,
        'private_vendor_dependencies': dependencies,
        'actual_vendor_namespace_link_test_required': True,
        'removed': removed, 'hardware_verified': False,
        'physical_device_written': False,
    }, indent=2)+'\n')
    print('GATEKEEPER_NONSECURE_STAGE_PASS')


if __name__ == '__main__':
    main()

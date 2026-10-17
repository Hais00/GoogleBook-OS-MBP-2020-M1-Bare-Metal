#!/usr/bin/env python3
"""Stage real Linux graphics/Bluetooth providers in the private M1 images."""
import hashlib
import json
from project_paths import WORK
from stage_native_egl import copy_labeled


def main():
    vendor = WORK/'vendor-egl-stage'
    graphics = WORK/'graphics-out/libgbm.so'
    bluetooth = WORK/'bluetooth-linux-build/android.hardware.bluetooth-service.default'
    for binary, receipt, key in [(graphics, 'minigbm-render-build.json', 'sha256'),
                                 (bluetooth, 'bluetooth-linux-build.json', 'binary_sha256')]:
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == json.loads((WORK/receipt).read_text())[key]
    render_receipt = json.loads((WORK/'minigbm-render-build.json').read_text())
    assert render_receipt['sync_error_propagation_test_pass']
    common = WORK/'graphics-out/libminigbm_gralloc.so'
    assert hashlib.sha256(common.read_bytes()).hexdigest() == render_receipt['common_sha256']
    changes = []
    copy_labeled(graphics, vendor/'lib64/libgbm.so', vendor/'lib64/libgbm.so')
    copy_labeled(common, vendor/'lib64'/common.name, vendor/'lib64'/common.name)
    old_bluetooth = vendor/'bin/hw/android.hardware.bluetooth@aidl-service-qti'
    new_bluetooth = vendor/'bin/hw'/bluetooth.name
    copy_labeled(bluetooth, new_bluetooth,
                 old_bluetooth if old_bluetooth.exists() else new_bluetooth)
    reference = WORK/'references/aosp-bluetooth-15/default'
    for source, target, label in [
        ('bluetooth-service-default.rc', 'etc/init/bluetooth-service-default.rc',
         'etc/init/android.hardware.bluetooth@aidl-service-qti.rc'),
        ('bluetooth-service-default.xml', 'etc/vintf/manifest/bluetooth-service-default.xml',
         'etc/vintf/manifest/bluetooth_hci.xml')]:
        copy_labeled(reference/source, vendor/target,
                     vendor/label if (vendor/label).exists() else vendor/target)
    for name in ['bin/hw/android.hardware.bluetooth@aidl-service-qti',
                 'etc/init/android.hardware.bluetooth@aidl-service-qti.rc',
                 'etc/vintf/manifest/bluetooth_hci.xml',
                 'etc/vintf/manifest/bt_lmp_event-saidl.xml',
                 'etc/vintf/manifest/bttpi-saidl.xml',
                 'etc/vintf/manifest/vendor.qti.hardware.bluetooth.btavsprovider.xml']:
        p = vendor/name
        if p.exists():
            changes.append({'removed': name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
            p.unlink()
    properties = {
        'ro.board.platform': 't8103',
        'ro.product.board': 'j293',
        'ro.surface_flinger.has_wide_color_display': 'false',
        'ro.surface_flinger.has_HDR_display': 'false',
        'ro.surface_flinger.protected_contents': 'false',
        'ro.bluetooth.a2dp_offload.supported': 'false',
    }
    prop_file = vendor/'build.prop'
    rows = [line for line in prop_file.read_text().splitlines()
            if line.split('=', 1)[0].strip() not in set(properties) | {'ro.vendor.extension_library'}]
    rows += ['# Capabilities implemented by the native Linux M1 providers.']
    rows += [key+'='+value for key, value in properties.items()]
    prop_file.write_text('\n'.join(rows)+'\n')
    (WORK/'linux-device-hal-stage.json').write_text(json.dumps({
        'graphics': 'Asahi render-node mapper with DCP PRIME allocations',
        'bluetooth': 'public AOSP V1 Linux HCI user-channel HAL',
        'properties': properties, 'qualcomm_performance_extension': 'not loaded',
        'removed': changes, 'hardware_verified': False,
        'qualcomm_cleanup_complete': False, 'physical_device_written': False,
    }, indent=2)+'\n')
    print('LINUX_DEVICE_HAL_STAGE_PASS')


if __name__ == '__main__':
    main()

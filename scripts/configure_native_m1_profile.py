#!/usr/bin/env python3
"""Apply the M1 HAL configuration to a private image stage, never a disk."""
import hashlib
import json
from project_paths import WORK

VENDOR = WORK/'vendor-egl-stage'

def main():
    changes = []
    # Weaver is optional and requires a real secure hardware provider. A
    # declaration without that provider blocks SyntheticPasswordManager.
    removed = {
        'etc/vintf/manifest/android.hardware.weaver-service.android-desktop.xml': 'no Weaver hardware provider',
        'etc/init/android.hardware.weaver-service.android-desktop.rc': 'no Weaver hardware provider',
        'lib64/sensors.qsh.so': 'Qualcomm sensor DSP is not present',
        'etc/init/vendor.sensors.sscrpcd.rc': 'Qualcomm sensor DSP is not present',
        'etc/init/init.vendor.sensors.rc': 'Qualcomm sensor DSP is not present',
        'etc/vintf/manifest/soundtrigger.qti.xml': 'Qualcomm DSP sound-trigger provider is not implemented on M1',
        'etc/vintf/manifest/vendor.qti.hardware.sensorscalibrate.xml': 'Qualcomm calibration provider is not present',
        'etc/permissions/android.hardware.sensor.accelerometer.xml': 'no implemented internal accelerometer provider',
        'etc/permissions/android.hardware.sensor.gyroscope.xml': 'no implemented internal gyroscope provider',
        'etc/permissions/android.hardware.sensor.light.xml': 'no implemented internal light-sensor provider',
    }
    # Android Vulkan presentation is not yet implemented by this ICD. Do not
    # advertise graphics/API conformance based on a compute-only diagnostic.
    for p in (VENDOR/'etc/permissions').glob('*vulkan*.xml'):
        removed[str(p.relative_to(VENDOR))] = 'Android Vulkan presentation/conformance not qualified'
    for name, reason in removed.items():
        path = VENDOR/name
        if path.exists() or path.is_symlink():
            record = {'file':name, 'reason':reason}
            if path.is_file() and not path.is_symlink():
                record['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            changes.append(record)
            path.unlink()
    dynamic = VENDOR/'lib64/hw/sensors.dynamic_sensor_hal.so'
    assert dynamic.is_file()
    (VENDOR/'etc/sensors/hals.conf').write_text(
        '# Native M1 profile: real dynamic HID sensors, without the Qualcomm DSP.\n'
        'sensors.dynamic_sensor_hal.so\n')
    props = (VENDOR/'build.prop').read_text().splitlines()
    for line in props:
        if line.split('=',1)[0].strip() in ('vendor.dynamic_sensor.mock.file','vendor.dynamic_sensor.mock.socket'):
            assert not line.split('=',1)[-1].strip(), 'Mock sensor activation must stay disabled'
    cil = VENDOR/'etc/selinux/vendor_sepolicy.cil'
    text = cil.read_text()
    rules = '''
; minigbm reserved-region memfds are passed to app graphics clients.
; Only descriptor access/mapping; no execute permission or filesystem access.
(allow appdomain hal_graphics_allocator_default (memfd_file (read write getattr map)))
(allow shell hal_graphics_allocator_default (memfd_file (read write getattr map)))
'''
    if '(allow appdomain hal_graphics_allocator_default (memfd_file (read write getattr map)))' not in text:
        cil.write_text(text+rules)
    uevent = VENDOR/'etc/ueventd.rc'
    text = uevent.read_text()
    if '/dev/hidraw*' not in text:
        uevent.write_text(text+'\n# Dynamic HID sensor provider is a system/input-group client.\n/dev/hidraw* 0660 system input\n')
    (WORK/'native-m1-hal-profile.json').write_text(json.dumps({
        'stage':str(VENDOR), 'removed_this_run':changes,
        'sensors':'provided AOSP dynamic HID sub-HAL; no mock input configured',
        'weaver':'not advertised; no provider exists on this profile',
        'graphics_memfd':'scoped allocator-to-client sharing; full policy compilation required',
        'remaining_qualcomm_components_removed':False, 'physical_device_written':False,
    },indent=2)+'\n')
    print('M1 HAL stage configured:',len(changes),'unsupported entries removed')

if __name__ == '__main__':
    main()

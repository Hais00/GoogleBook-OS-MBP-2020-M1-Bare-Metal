#!/usr/bin/env python3
"""Prepare the original Google desktop Bluetooth software path, without ELF edits."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import xml.etree.ElementTree as ET
from project_paths import WORK
from stage_native_egl import getlabel
from stage_m1_input import label

BASE = WORK / 'vendor-wifi-stage-r2'
STAGE = WORK / 'vendor-audio-stage'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(relative, text):
    path = STAGE / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o644)
    label(path, 'u:object_r:vendor_configs_file:s0')


def main():
    assert not STAGE.exists(), 'Refusing to overwrite an existing audio stage'
    shutil.copytree(BASE, STAGE, symlinks=True)
    # macOS copy2 omits Android's non-native SELinux xattr.
    for source in [BASE] + sorted(BASE.rglob('*')):
        target = STAGE / source.relative_to(BASE)
        mode = stat.S_IMODE(target.lstat().st_mode)
        change = not target.is_symlink() and not mode & stat.S_IWUSR
        try:
            if change:
                target.chmod(mode | stat.S_IWUSR)
            label(target, getlabel(source).rstrip(b'\0').decode())
        finally:
            if change:
                target.chmod(mode)

    props = {
        'bluetooth.hfp.software_datapath.enabled': 'true',
        'ro.bluetooth.a2dp_offload.supported': 'false',
        'persist.bluetooth.a2dp_offload.disabled': 'true',
        'ro.bluetooth.leaudio_offload.supported': 'false',
        'persist.bluetooth.leaudio_offload.disabled': 'true',
        'persist.bluetooth.bluetooth_audio_hal.disabled': 'false',
    }
    path = STAGE / 'build.prop'
    lines = [line for line in path.read_text().splitlines()
             if line.split('=', 1)[0] not in props]
    path.write_text('\n'.join(lines) + '\n\n# Native Bluetooth software audio; no Qualcomm DSP offload.\n' +
                    ''.join(f'{key}={value}\n' for key, value in props.items()))
    for key in props:
        assert sum(line.startswith(key + '=') for line in path.read_text().splitlines()) == 1

    # The existing C++ binary selects r_submix and, with the real HFP software
    # switch, bluetooth. Its desktop ModuleBluetooth constructor registers the
    # provider factory and forwards software providers to IDesktopAudioFactory
    # in the unchanged Rust process over Binder.
    original_rc = (WORK / 'references/audio-apex-elf-audit/etc/dras.core-cpp.audio.no_bt.rc').read_text()
    first, rest = original_rc.split('\n', 1)
    write('etc/init/googlebook-bluetooth-audio.rc', first + '\n    override\n' +
          '    interface aidl android.hardware.bluetooth.audio.IBluetoothAudioProviderFactory/default\n' +
          '    interface aidl android.hardware.audio.core.IModule/bluetooth\n' + rest)
    write('etc/vintf/manifest/googlebook-bluetooth-software.xml', '''<manifest version="9.0" type="device">
    <hal format="aidl">
        <name>android.hardware.audio.core</name>
        <version>4</version>
        <fqname>IModule/bluetooth</fqname>
    </hal>
</manifest>
''')
    # HFP ports are external Bluetooth endpoints, never internal speakers.
    write('etc/m1_bluetooth_software_audio_policy_configuration.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<module name="bluetooth" halVersion="3.0">
    <mixPorts>
        <mixPort name="hfp output" role="source">
            <profile name="" format="AUDIO_FORMAT_PCM_16_BIT" samplingRates="8000 16000 32000" channelMasks="AUDIO_CHANNEL_OUT_MONO"/>
        </mixPort>
        <mixPort name="hfp input" role="sink">
            <profile name="" format="AUDIO_FORMAT_PCM_16_BIT" samplingRates="8000 16000 32000" channelMasks="AUDIO_CHANNEL_IN_MONO"/>
        </mixPort>
    </mixPorts>
    <devicePorts>
        <devicePort tagName="BT SCO Headset Out" type="AUDIO_DEVICE_OUT_BLUETOOTH_SCO_HEADSET" role="sink"/>
        <devicePort tagName="BT SCO Headset In" type="AUDIO_DEVICE_IN_BLUETOOTH_SCO_HEADSET" role="source"/>
    </devicePorts>
    <routes>
        <route type="mix" sink="BT SCO Headset Out" sources="hfp output"/>
        <route type="mix" sink="hfp input" sources="BT SCO Headset In"/>
    </routes>
</module>
''')
    policy = STAGE / 'etc/audio_policy_configuration.xml'
    text = policy.read_text()
    assert text.count('</modules>') == 1
    text = text.replace('</modules>', '''    <xi:include href="m1_bluetooth_software_audio_policy_configuration.xml"/>
        <xi:include href="a2dp_audio_policy_configuration.xml"/>
    </modules>''')
    write('etc/audio_policy_configuration.xml', text)
    # Use the schema's whitespace list syntax consistently.
    path = STAGE / 'etc/a2dp_audio_policy_configuration.xml'
    text = path.read_text().replace('44100,48000', '44100 48000').replace(
        'AUDIO_CHANNEL_IN_MONO,AUDIO_CHANNEL_IN_STEREO',
        'AUDIO_CHANNEL_IN_MONO AUDIO_CHANNEL_IN_STEREO')
    write('etc/a2dp_audio_policy_configuration.xml', text)
    # Native Linux HCI HAL uses /dev/rfkill. Keep access scoped to Bluetooth.
    path = STAGE / 'etc/ueventd.rc'
    assert not re.search(r'^\s*/dev/rfkill\s', path.read_text(), re.M)
    with path.open('a') as stream:
        stream.write('\n# Native Linux Bluetooth controller power ownership.\n/dev/rfkill 0660 bluetooth bluetooth\n')
    # bt_device already grants the native Bluetooth HAL access to radio
    # control nodes. DAC alone would leave this new Linux node as device:s0.
    contexts = STAGE/'etc/selinux/vendor_file_contexts'
    assert not re.search(r'^/dev/rfkill\s', contexts.read_text(), re.M)
    with contexts.open('a') as stream:
        stream.write('\n/dev/rfkill u:object_r:bt_device:s0\n')

    changed = []
    for path in sorted(STAGE.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(STAGE)
        original = BASE / relative
        if not original.is_file() or digest(path) != digest(original):
            changed.append(str(relative))
            assert str(relative) == 'build.prop' or str(relative).startswith('etc/')
    assert digest(STAGE/'apex/com.android.hardware.audio.desktop-arpal.apex') == digest(BASE/'apex/com.android.hardware.audio.desktop-arpal.apex')
    assert digest(STAGE/'bin/hw/googlebook-audio-hal') == digest(BASE/'bin/hw/googlebook-audio-hal')
    for relative in ['etc/selinux/vendor_sepolicy.cil']:
        assert digest(STAGE/relative) == digest(BASE/relative)
    for path in (STAGE/'etc').rglob('*.xml'):
        if path.name in [Path(p).name for p in changed]:
            ET.parse(path)
    result = {'stage': str(STAGE), 'base': str(BASE), 'changed': changed,
              'properties': props, 'original_audio_APEX_unchanged': True,
              'original_Rust_binary_unchanged': True, 'SELinux_policy_unchanged': True,
              'rfkill_SELinux_type': 'bt_device', 'new_SELinux_allow_rules': False,
              'standalone_factory_not_staged': True,
              'internal_speaker_protection_unchanged': True,
              'local_runtime_pass': False, 'physical_device_written': False,
              'hardware_verified': False, 'headphone_audio_verified': False}
    (WORK/'m1-bluetooth-audio-stage.json').write_text(json.dumps(result, indent=2)+'\n')
    print('M1_BLUETOOTH_AUDIO_CONFIG_STAGE_READY', changed)


if __name__ == '__main__':
    main()

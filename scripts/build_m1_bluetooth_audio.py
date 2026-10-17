#!/usr/bin/env python3
"""Build the owner for the installed, unchanged AOSP Bluetooth audio factory."""
import hashlib
import json
import subprocess
from project_paths import BASE, WORK, NDK, SYSTEM_ORIGINAL

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    root=WORK/'native-radio-build';root.mkdir(exist_ok=True)
    vendor=WORK/'vendor-input-stage'
    source=BASE/'scripts/m1_bluetooth_audio_service.c'
    binary=root/'android.hardware.bluetooth.audio-service.m1'
    includes=[WORK/'aosp-binder-ndk'/p for p in ['include_ndk','include_platform','include_cpp']]
    command=[NDK/'bin/aarch64-linux-android35-clang','-std=c11','-O2','-Wall','-Wextra','-Werror']+['-I'+str(p) for p in includes]+[source,'-Wl,-z,max-page-size=16384','-Wl,--no-undefined']
    for directory in [vendor/'lib64',SYSTEM_ORIGINAL/'lib64']:
        command+=['-L'+str(directory),'-Wl,-rpath-link,'+str(directory)]
    command+=['-l:android.hardware.bluetooth.audio-impl.so','-lbinder_ndk','-llog','-o',binary]
    result=subprocess.run(list(map(str,command)),capture_output=True,text=True)
    (root/'bluetooth-factory-build.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(result.stderr)
    receipt={'binary':str(binary),'sha256':digest(binary),'source_sha256':digest(source),
      'entrypoint_contract_source':'native-radios-aosp-aa229558cbf0/bluetooth/audio/aidl/default/service.cpp',
      'factory_implementation':'Unchanged installed android.hardware.bluetooth.audio-impl.so; binder_status_t createIBluetoothAudioProviderFactory(void)',
      'factory_sha256':digest(vendor/'lib64/android.hardware.bluetooth.audio-impl.so'),
      'interface_version':'unchanged actual V6 implementation; no generated/fake interface metadata',
      'physical_device_written':False,'hardware_verified':False,'audio_datapath_verified':False}
    (root/'bluetooth-factory-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('BLUETOOTH_FACTORY_OWNER_BUILD_PASS',binary.stat().st_size)
if __name__=='__main__':main()

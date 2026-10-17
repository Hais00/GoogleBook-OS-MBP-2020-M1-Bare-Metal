#!/usr/bin/env python3
"""Stage only the matched native Wi-Fi provider over installed vendor9 inputs."""
import hashlib
import argparse
import json
import re
from pathlib import Path
import shutil
import stat
import xml.etree.ElementTree as ET
from project_paths import WORK
from stage_native_egl import copy_labeled,getlabel
from stage_m1_input import label

base=WORK/'vendor-input-stage'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--stage-name',default='vendor-wifi-stage')
options=parser.parse_args()
assert re.fullmatch(r'vendor-wifi-[a-z0-9-]+',options.stage_name)
stage=WORK/options.stage_name
build=WORK/'native-radio-build/wifi'
receipt=json.loads((build/'build-receipt.json').read_text())
assert receipt['interface_version']==3 and receipt['library_backend_same_legacy_header']
for file,record in receipt['files'].items():assert hashlib.sha256(Path(file).read_bytes()).hexdigest()==record['sha256']
for file,expected in receipt['sources'].items():assert hashlib.sha256(Path(file).read_bytes()).hexdigest()==expected
cpu=json.loads((WORK/'native-radio-build/wifi-cpu-v2-build.json').read_text())
assert cpu['runtime_pass'] and cpu['transport_mocked']
assert not stage.exists(),'Refusing to overwrite an existing staged generation'
shutil.copytree(base,stage,symlinks=True)
# macOS copy2 does not preserve this non-native SELinux xattr. Copy it
# explicitly for every inode, including root directories and symlinks.
for source in [base]+sorted(base.rglob('*')):
    target=stage/source.relative_to(base)
    mode=stat.S_IMODE(target.lstat().st_mode)
    change=not target.is_symlink() and not (mode & stat.S_IWUSR)
    try:
        if change:target.chmod(mode | stat.S_IWUSR)
        label(target,getlabel(source).rstrip(b'\0').decode())
    finally:
        if change:target.chmod(mode)
changed=[]
for source,relative,context in [
    (build/'android.hardware.wifi-service.m1','bin/hw/android.hardware.wifi-service.m1','u:object_r:hal_wifi_default_exec:s0'),
    (build/'libwifi-hal.so','lib64/libwifi-hal.so','u:object_r:vendor_file:s0'),
    (build/'android.hardware.wifi-V3-ndk.so','lib64/android.hardware.wifi-V3-ndk.so','u:object_r:vendor_file:s0'),
    (build/'android.hardware.wifi.common-V2-m1.so','lib64/android.hardware.wifi.common-V2-m1.so','u:object_r:vendor_file:s0')]:
    target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    target.chmod(0o755 if relative.startswith('bin/') else 0o644);label(target,context)
    changed.append({'file':relative,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
old=stage/'bin/hw/android.hardware.wifi-service'
assert old.is_file();old.unlink()
rc=stage/'etc/init/android.hardware.wifi-service.rc'
rc.write_text('''service vendor.wifi_hal_legacy /vendor/bin/hw/android.hardware.wifi-service.m1
    interface aidl android.hardware.wifi.IWifi/default
    class hal
    capabilities NET_ADMIN NET_RAW
    user wifi
    group wifi gps
''');rc.chmod(0o644);label(rc,getlabel(base/'etc/init/android.hardware.wifi-service.rc').rstrip(b'\0').decode())
count=0
for path in (stage/'etc/vintf/manifest').rglob('*.xml'):
    tree=ET.parse(path);modified=False
    for hal in tree.getroot().findall('hal'):
        if hal.findtext('name')=='android.hardware.wifi':
            assert hal.attrib.get('format')=='aidl';versions=hal.findall('version');assert len(versions)==1
            versions[0].text='3';modified=True;count+=1
    if modified:tree.write(path,encoding='utf-8',xml_declaration=True);label(path,getlabel(base/path.relative_to(stage)).rstrip(b'\0').decode())
assert count==1,'Wi-Fi service must have exactly one VINTF declaration'
contexts=stage/'etc/selinux/vendor_file_contexts'
with contexts.open('a') as f:f.write('\n/vendor/bin/hw/android\\.hardware\\.wifi-service\\.m1 u:object_r:hal_wifi_default_exec:s0\n')
result={'stage':str(stage),'base':'installed vendor9/input R3','changes':changed,
        'wifi_interface':3,'init_user':'wifi','module_loading_capability_removed':True,
        'provided_wificond_and_supplicant_unchanged':True,'bluetooth_unchanged':True,
        'no_framework_or_apk_changes':True,'neverallow_policy_changes':False,
        'cpu_runtime_tests':cpu['runtime_evidence'],'namespace_runtime_verified':False,'hardware_verified':False}
(WORK/'m1-wifi-stage.json').write_text(json.dumps(result,indent=2)+'\n')
print('M1_WIFI_ONLY_STAGE_READY',stage)

#!/usr/bin/env python3
"""Compose both native USB owners in the separate M1 cleanup candidate."""
import hashlib
import json
from pathlib import Path
import shutil
from project_paths import BASE, WORK
from stage_native_egl import lib, getlabel, copy_labeled


def setlabel(path,label):
    data=label.encode()+b'\0'
    assert lib.setxattr(str(path).encode(),b'security.selinux',data,len(data),0,1)==0
    assert getlabel(path)==data


def main():
    vendor=WORK/'vendor-linux-cleanup-stage'
    assert vendor.is_dir() and vendor!=(WORK/'vendor-egl-stage')
    port=json.loads((WORK/'usb-linux-build.json').read_text())
    gadget=json.loads((WORK/'usb-gadget-linux-build.json').read_text())
    assert port['android_callback_tests_pass'] and port['actual_vendor_namespace_link_pass'] and port['host_typec_sanitizers_pass']
    assert gadget['android_callback_test_pass'] and gadget['actual_vendor_namespace_link_pass']
    assert gadget['exact_kernel17_functionfs_lifecycle_pass']
    installed={}
    for receipt,label in [(port,'u:object_r:hal_usb_default_exec:s0'),
                          (gadget,'u:object_r:hal_usb_gadget_default_exec:s0')]:
        source=Path(receipt['binary']);assert hashlib.sha256(source.read_bytes()).hexdigest()==receipt['sha256']
        destination=vendor/'bin/hw'/source.name;shutil.copy2(source,destination);setlabel(destination,label)
        installed[str(destination.relative_to(vendor))]=receipt['sha256']
    rc=vendor/'etc/init/init.googlebook-usb-linux.rc'
    reference=vendor/'etc/init/allocator-minigbm.rc'
    copy_labeled(BASE/'scripts/init.googlebook-usb-linux.rc',rc,reference)
    contexts=vendor/'etc/selinux/vendor_file_contexts';text=contexts.read_text()
    for name,label in [('android.hardware.usb-service.linux','hal_usb_default_exec'),
                       ('android.hardware.usb.gadget-service.linux','hal_usb_gadget_default_exec')]:
        rule=r'/(vendor|system/vendor)/bin/hw/'+name.replace('.',r'\.')+' u:object_r:'+label+':s0'
        if rule not in text:text+='\n'+rule+'\n'
    contexts.write_text(text)
    for package,version,interface,name in [('usb',3,'IUsb','usb-linux.xml'),
                                         ('usb.gadget',1,'IUsbGadget','usb-gadget-linux.xml')]:
        target=vendor/'etc/vintf/manifest'/name
        target.write_text('<manifest version="1.0" type="device">\n  <hal format="aidl">\n'
                          '    <name>android.hardware.'+package+'</name>\n    <version>'+str(version)+'</version>\n'
                          '    <fqname>'+interface+'/default</fqname>\n  </hal>\n</manifest>\n')
        setlabel(target,getlabel(reference).rstrip(b'\0').decode())
    removed=[]
    for name in ['etc/init/android.hardware.usb-service.qti.rc',
                 'bin/hw/android.hardware.usb-service.qti',
                 'etc/vintf/manifest/android.hardware.usb-service.qti.xml',
                 'etc/vintf/manifest/android.hardware.usb.gadget-service.qti.xml',
                 'bin/init.qcom.usb.sh']:
        path=vendor/name
        if path.exists():
            removed.append({'file':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()});path.unlink()
    # Each standard USB interface must have exactly one remaining declaration.
    import xml.etree.ElementTree as ET
    names=[]
    for path in (vendor/'etc/vintf').rglob('*.xml'):
        for hal in ET.parse(path).getroot().iter('hal'):names.append(hal.findtext('name'))
    assert names.count('android.hardware.usb')==1 and names.count('android.hardware.usb.gadget')==1
    for path in (vendor/'etc/init').rglob('*.rc'):
        text=path.read_text()
        assert 'android.hardware.usb-service.qti' not in text and 'init.qcom.usb.sh' not in text
    (WORK/'usb-linux-stage.json').write_text(json.dumps({'stage':str(vendor),'composed_interfaces':['IUsb/default V3','IUsbGadget/default V1'],
        'installed':installed,'removed':removed,'init_owner_mode':2,'new_selinux_allow_rules':0,
        'hardware_verified':False,'physical_device_written':False,'full_usb_controls_qualified':False,
        'remaining_unqualified_controls':port['unqualified_controls']},indent=2)+'\n')
    print('BOTH_NATIVE_USB_OWNERS_STAGED; hardware qualification pending')


if __name__=='__main__':main()

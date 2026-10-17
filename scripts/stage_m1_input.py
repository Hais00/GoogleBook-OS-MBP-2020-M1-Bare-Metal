#!/usr/bin/env python3
"""Stage a separate input-only generation from installed native vendor generation7."""
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from project_paths import BASE, WORK
from stage_native_egl import copy_labeled, getlabel, lib

POLICY = '''
; Native M1 input owners. No raw MMIO, DAC override or permissive domains.
(type vendor_m1_touchbar)
(roletype object_r vendor_m1_touchbar)
(type vendor_m1_touchbar_exec)
(roletype object_r vendor_m1_touchbar_exec)
(typeattributeset domain (vendor_m1_touchbar))
(typeattributeset exec_type (vendor_m1_touchbar_exec))
(typeattributeset file_type (vendor_m1_touchbar_exec))
(typeattributeset vendor_file_type (vendor_m1_touchbar_exec))
(typeattributeset hal_light_client (vendor_m1_touchbar))
(typeattributeset halclientdomain (vendor_m1_touchbar))
(allow init vendor_m1_touchbar_exec (file (read getattr map execute open)))
(allow init vendor_m1_touchbar (process (transition siginh rlimitinh)))
(dontaudit init vendor_m1_touchbar (process (noatsecure)))
(typetransition init vendor_m1_touchbar_exec process vendor_m1_touchbar)
(allow vendor_m1_touchbar vendor_m1_touchbar_exec (file (read getattr map execute open entrypoint)))
(allow vendor_m1_touchbar init (process (sigchld)))
(allow vendor_m1_touchbar self (process (fork sigchld getsched setsched)))
(allow vendor_m1_touchbar self (fd (use)))
(allow vendor_m1_touchbar self (unix_dgram_socket (create connect write read getattr getopt setopt shutdown)))
(allow vendor_m1_touchbar logdw_socket (sock_file (write)))
(allow vendor_m1_touchbar logd (unix_dgram_socket (sendto)))
(allow vendor_m1_touchbar binder_device (chr_file (read write open getattr map ioctl)))
(allow vendor_m1_touchbar servicemanager (binder (call transfer)))
(allow servicemanager vendor_m1_touchbar (binder (transfer)))
(allow vendor_m1_touchbar input_device (dir (read open getattr search)))
(allow vendor_m1_touchbar input_device (chr_file (read open getattr ioctl)))
(allowx vendor_m1_touchbar input_device (ioctl chr_file (0x4506 0x450a 0x4518 0x4590 (range 0x4520 0x457f))))
(allow vendor_m1_touchbar uhid_device (chr_file (write open getattr ioctl)))
(allowx vendor_m1_touchbar uhid_device (ioctl chr_file (0x5501 0x5502 0x5503 0x5564 0x5565)))
(allow vendor_m1_touchbar gpu_device (dir (search read open getattr)))
(allow vendor_m1_touchbar gpu_device (chr_file (read write open getattr ioctl map)))
(allowx vendor_m1_touchbar gpu_device (ioctl chr_file ((range 0x6400 0x64ff))))
(allow vendor_m1_touchbar sysfs (dir (read open getattr search)))
(allow vendor_m1_touchbar sysfs (lnk_file (read getattr)))
(allow vendor_m1_touchbar sysfs_gpu (dir (read open getattr search)))
(allow vendor_m1_touchbar sysfs_gpu (lnk_file (read getattr)))
(allow vendor_m1_touchbar sysfs_leds (dir (read open getattr search)))
(allow vendor_m1_touchbar sysfs_leds (lnk_file (read getattr)))
(allow vendor_m1_touchbar sysfs_leds (file (read open getattr)))
(allow hal_light_default sysfs (dir (read open getattr search)))
(allow hal_light_default sysfs (lnk_file (read getattr)))
(allow hal_light_default sysfs (file (read open getattr)))
'''


def label(path, text):
    value=text.encode()+b'\0'
    assert lib.setxattr(str(path).encode(),b'security.selinux',value,len(value),0,1)==0
    assert getlabel(path)==value


def main():
    vendor=WORK/'vendor-input-stage'
    assert vendor.is_dir() and vendor != WORK/'vendor-linux-cleanup-stage'
    lights=json.loads((WORK/'m1-lights-build.json').read_text())
    row=json.loads((WORK/'m1-touchbar-build.json').read_text())
    hwc=json.loads((WORK/'hwc-drm-build.json').read_text())
    ownership=json.loads((WORK/'hwc-owner-test.json').read_text())
    assert lights['fixture_pass'] and lights['namespace_runtime_pass']
    assert row['namespace_runtime_pass'] and row['model_sanitizers_pass']
    assert ownership['runtime_tested'] and ownership['negative_control_rejected']
    rc_reference=vendor/'etc/init/allocator-minigbm.rc'
    lib_reference=vendor/'lib64/libdrm.so'
    installed={}
    def install(source, relative, kind):
        target=vendor/relative
        copy_labeled(source,target,rc_reference if kind=='rc' else lib_reference)
        if kind not in ['rc','lib']:label(target,kind)
        target.chmod(0o755 if relative.startswith('bin/') else 0o644)
        installed[relative]=hashlib.sha256(target.read_bytes()).hexdigest()
    for p,attrs in lights['files'].items():
        source=Path(p)
        if source.name=='m1-lights-test':continue
        assert hashlib.sha256(source.read_bytes()).hexdigest()==attrs['sha256']
        install(source,('lib64/' if source.suffix=='.so' else 'bin/hw/')+source.name,
                'lib' if source.suffix=='.so' else 'u:object_r:hal_light_default_exec:s0')
    assert hashlib.sha256(Path(row['binary']).read_bytes()).hexdigest()==row['sha256']
    install(Path(row['binary']),'bin/m1-touchbar','u:object_r:vendor_m1_touchbar_exec:s0')
    assert hashlib.sha256(Path(hwc['binary']).read_bytes()).hexdigest()==hwc['sha256']
    install(Path(hwc['binary']),'bin/hw/android.hardware.composer.hwc3-service.drm','u:object_r:hal_graphics_composer_default_exec:s0')
    old='android.hardware.lights-service.android-desktop'
    removed=[]
    for relative in ['bin/hw/'+old,'etc/init/'+old+'.rc','etc/vintf/manifest/'+old+'.xml']:
        target=vendor/relative
        if target.exists():removed.append({'file':relative,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()});target.unlink()
    font_dir=vendor/'etc/m1-touchbar'
    font_dir.mkdir(exist_ok=True);font_dir.chmod(0o755);label(font_dir,'u:object_r:vendor_file:s0')
    from project_paths import SYSTEM_ORIGINAL
    install(SYSTEM_ORIGINAL/'fonts/Roboto-Regular.ttf','etc/m1-touchbar/Roboto-Regular.ttf','lib')
    rc=vendor/'etc/init/init.googlebook-m1-input.rc'
    rc.write_text('''service vendor.lights.m1 /vendor/bin/hw/android.hardware.lights-service.m1
    interface aidl android.hardware.light.ILights/default
    class hal
    user system
    group system

service vendor.m1-touchbar /vendor/bin/m1-touchbar
    class hal
    user system
    group system input graphics
    restart_period 5
''');label(rc,getlabel(rc_reference).rstrip(b'\0').decode());rc.chmod(0o644)
    manifest=vendor/'etc/vintf/manifest/lights-m1.xml'
    manifest.write_text('<manifest version="1.0" type="device">\n  <hal format="aidl">\n    <name>android.hardware.light</name>\n    <version>2</version>\n    <fqname>ILights/default</fqname>\n  </hal>\n</manifest>\n')
    label(manifest,getlabel(rc_reference).rstrip(b'\0').decode());manifest.chmod(0o644)
    exclusion=vendor/'etc/excluded-input-devices.xml'
    tree=ET.parse(exclusion) if exclusion.exists() else ET.ElementTree(ET.Element('devices'))
    if not any(node.get('name')=='MacBookPro17,1 Touch Bar' for node in tree.getroot()):ET.SubElement(tree.getroot(),'device',{'name':'MacBookPro17,1 Touch Bar'})
    ET.indent(tree);tree.write(exclusion,encoding='utf-8',xml_declaration=True);label(exclusion,getlabel(rc_reference).rstrip(b'\0').decode());exclusion.chmod(0o644)
    contexts=vendor/'etc/selinux/vendor_file_contexts'
    text=contexts.read_text()
    for name,kind in [('bin/m1-touchbar','vendor_m1_touchbar_exec'),('bin/hw/android.hardware.lights-service.m1','hal_light_default_exec')]:
        rule='/(vendor|system/vendor)/'+name.replace('.',r'\.')+' u:object_r:'+kind+':s0'
        if rule not in text:text+='\n'+rule+'\n'
    contexts.write_text(text)
    uevent=vendor/'etc/ueventd.rc';text=uevent.read_text()
    rules='\n# Native M1 function row: UID system, input/graphics groups; no world-write.\n/dev/uinput 0660 system input\n'
    paths=['/devices/platform/led-controller/leds/kbd_backlight',
           '/devices/platform/soc/led-controller/leds/kbd_backlight']
    led_roots=['/devices/platform/led-controller/leds','/devices/platform/soc/led-controller/leds']
    for prefix in ['/devices/platform','/devices/platform/soc']:
        led_roots += [prefix+'/231c00000.dcp/backlight',prefix+'/228600000.dsi/228600000.dsi.0/backlight']
        paths += [prefix+'/231c00000.dcp/backlight/apple-panel-bl',prefix+'/228600000.dsi/228600000.dsi.0/backlight/228600000.dsi.0']
    for path in paths:rules+='/sys'+path+' brightness 0660 system system\n'
    if '# Native M1 function row:' not in text:uevent.write_text(text+rules)
    cil=vendor/'etc/selinux/vendor_sepolicy.cil';text=cil.read_text()
    if '; Native M1 input owners.' in text:
        text=text.split('; Native M1 input owners.',1)[0].rstrip()+'\n'
    text+=POLICY
    for path in led_roots:text+='(genfscon sysfs "'+path+'" (u object_r sysfs_leds ((s0) (s0))))\n'
    cil.write_text(text)
    declarations=[]
    for p in (vendor/'etc/vintf').rglob('*.xml'):
        declarations += [hal for hal in ET.parse(p).getroot().iter('hal') if hal.findtext('name')=='android.hardware.light']
    assert len(declarations)==1 and declarations[0].findtext('version')=='2'
    record={'stage':str(vendor),'base':'unchanged clone of native generation7 vendor-codec-stage',
            'installed':installed,'removed':removed,'light_interface':2,'input_model_cpu_verified':True,
            'full_policy_compile_pass':False,'hardware_verified':False,'physical_device_written':False,
            'admitted':False,'standard_android_per_device_keyboard_backlight_slider':False,
            'remaining': ['Exact policy neverallow compilation', 'EROFS contents/ownership validation',
                          'Kernel22 diskless boot validation','Actual M1 ADP mode/render/flip/touch/brightness qualification']}
    (WORK/'m1-input-stage.json').write_text(json.dumps(record,indent=2)+'\n')
    print('M1_INPUT_ONLY_CANDIDATE_STAGED; hardware admission remains false')


if __name__=='__main__':main()

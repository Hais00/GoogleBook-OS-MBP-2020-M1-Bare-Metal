#!/usr/bin/env python3
"""Stage a native Mesa EGL profile without writing any physical target disk."""
import ctypes
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from project_paths import BASE, WORK, BUILD_VOLUME

lib=ctypes.CDLL(None,use_errno=True)
lib.getxattr.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_int]
lib.getxattr.restype=ctypes.c_ssize_t
lib.setxattr.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_int]
lib.setxattr.restype=ctypes.c_int

def getlabel(path):
    buf=ctypes.create_string_buffer(1024)
    n=lib.getxattr(str(path).encode(),b'security.selinux',buf,len(buf),0,1)
    if n<=0:raise OSError(ctypes.get_errno(),f'Missing SELinux label on {path}')
    return bytes(buf[:n])

def copy_labeled(source,target,label_source):
    data=getlabel(label_source)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
    if lib.setxattr(str(target).encode(),b'security.selinux',data,len(data),0,1):
        raise OSError(ctypes.get_errno(),str(target))
    assert getlabel(target)==data

def clone_tree(source,target):
    if not target.exists():
        subprocess.run(['/bin/cp','-a','-c',str(source),str(target)],check=True)

def main():
    vendor=WORK/'vendor-egl-stage';ext=WORK/'system-ext-egl-stage'
    clone_tree(BASE/'vendor_work',vendor)
    clone_tree(BUILD_VOLUME/'system-ext-work',ext)
    stage=WORK/'mesa-stage/vendor/lib64'
    reference=BASE/'vendor_work/lib64/hw/vulkan.asahi.so'
    outputs={}
    for name in ('libEGL_mesa.so','libGLESv1_CM_mesa.so','libGLESv2_mesa.so'):
        dst=vendor/'lib64/egl'/name
        copy_labeled(stage/name,dst,reference);outputs[str(dst)]=hashlib.sha256(dst.read_bytes()).hexdigest()
    for name in ('libgallium_dri.so','libdrm.so'):
        dst=vendor/'lib64'/name
        copy_labeled(stage/name,dst,reference);outputs[str(dst)]=hashlib.sha256(dst.read_bytes()).hexdigest()
    # Select real upstream GLES rendering; do not advertise a missing Vulkan WSI extension.
    props={'ro.hardware.egl':'mesa','debug.renderengine.backend':'skiaglthreaded',
           'debug.renderengine.vulkan':'false','debug.renderengine.graphite_desktop_optin':'false',
           'ro.gfx.angle.supported':'false','ro.hwui.use_vulkan':'false','debug.hwui.renderer':'skiagl'}
    p=vendor/'build.prop';rows=[]
    for line in p.read_text().splitlines():
        if line.split('=',1)[0].strip() not in props:rows.append(line)
    rows+=['# Native Mesa/Asahi Android EGL profile']+[f'{k}={v}' for k,v in props.items()]
    p.write_text('\n'.join(rows)+'\n')
    copy_labeled(WORK/'graphics-out/googlebook-eglprobe',ext/'bin/googlebook-eglprobe',
                 BUILD_VOLUME/'system-ext-work/bin/googlebook-native-vkprobe')
    rc=ext/'etc/init/googlebook-egl-probe.rc'
    rc.write_text('''# One real EGL/GLES + AHB job through the Android loader, diagnostic opt-in.
service googlebook.egl-probe /system_ext/bin/googlebook-eglprobe
    class core
    user gpu_service
    group graphics
    disabled
    oneshot
    timeout_period 25

on boot && property:ro.boot.googlebook.debug=1 && property:ro.hardware.egl=mesa
    start googlebook.egl-probe
''')
    data=getlabel(BUILD_VOLUME/'system-ext-work/etc/init/googlebook-gpu-probe.rc')
    if lib.setxattr(str(rc).encode(),b'security.selinux',data,len(data),0,1):raise OSError(ctypes.get_errno(),str(rc))
    result={'vendor_stage':str(vendor),'system_ext_stage':str(ext),'outputs':outputs,
            'properties':props,'physical_disk_written':False,'runtime_verified':False,
            'qualcomm_removal_complete':False,'framework_binary_modified_by_this_stage':False}
    (WORK/'native-egl-stage.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Persist Vulkan SF/HWUI only after native-queue, interop and actual HWUI proof."""
import argparse,hashlib,json,stat
from pathlib import Path
from project_paths import BASE,WORK
from stage_native_egl import clone_tree,copy_labeled

def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-stage',type=Path,default=WORK/'vendor-vulkan17-mq-stage');p.add_argument('--stage-name',default='vendor-vulkan18-stage');p.add_argument('--qualification',type=Path,default=WORK/'vulkan-hwui-qualified.json');p.add_argument('--resume',action='store_true');a=p.parse_args()
 parent=a.parent_stage.resolve();stage=WORK/a.stage_name;assert parent.parent==WORK.resolve() and stage.parent==WORK and not '/' in a.stage_name;assert not stage.exists() or a.resume
 proof=json.loads(a.qualification.read_text());assert proof['actual_HWUI_pipeline']=='Skia (Vulkan)' and proof['actual_HWUI_frames']>0 and proof['two_queue_GPU_ordering_pass'] and proof['Android_AHB_and_native_window_pass']
 lock=json.loads((WORK/'vulkan-android-multiqueue-source-lock.json').read_text());assert proof['actual_driver_sha256']==digest(parent/'lib64/hw/vulkan.asahi.so')==lock['driver_sha256']
 fw=json.loads((WORK/'avd-fw-build.json').read_text());assert fw['vectors_address']==0 and fw['reset_vector_in_executable_text'] and digest(Path(fw['file']))==fw['sha256']
 clone_tree(parent,stage);props={'debug.renderengine.backend':'skiavkthreaded','debug.renderengine.vulkan':'true','ro.hwui.use_vulkan':'true','debug.hwui.renderer':'skiavk'};p=stage/'build.prop';rows=[x for x in p.read_text().splitlines() if x.split('=',1)[0].strip() not in props];rows+=['# Native Vulkan: actual two-queue and Android HWUI hardware proof recorded']+[f'{k}={v}' for k,v in props.items()];p.write_text('\n'.join(rows)+'\n')
 f='firmware/apple/avd-fw-v2-t0.bin';copy_labeled(Path(fw['file']),stage/f,parent/f);(stage/f).chmod(stat.S_IMODE((parent/f).stat().st_mode));p=stage/'etc/m1-graphics/integration.json';r=json.loads(p.read_text());r['native_source_lock']=lock;r['AVD_firmware']=fw;r['actual_HWUI_qualification']=proof;r['product_renderer_properties']=props;r['qualifications'].update(native_Vulkan_AHB_swapchain=True,Vulkan_system_renderer=False,AVD_hardware_decode=False,Android_hardware_Codec2=False);r['system_renderer_scope']='Persistent Vulkan configured after actual app proof; actual SurfaceFlinger execution must be verified after boot';p.write_text(json.dumps(r,indent=2)+'\n')
 changed=[]
 for path in stage.rglob('*'):
  if path.is_file() and not path.is_symlink():
   rel=str(path.relative_to(stage));old=parent/rel
   if not old.exists() or digest(path)!=digest(old):changed.append(rel)
 assert set(changed)<={'build.prop',f,'etc/m1-graphics/integration.json'} and 'build.prop' in changed
 r={'stage':str(stage),'parent':str(parent),'changed':changed,'actual_HWUI_qualification':proof,'Vulkan_HAL_unchanged_from_actual_two_queue_GPU_test':lock['driver_sha256'],'renderer_properties':props,'AVD_firmware':fw,'policy_and_audio_unchanged':True,'physical_device_written':False,'actual_SurfaceFlinger_Vulkan_qualified':False,'hardware_video_Codec2_connected':False};(WORK/(a.stage_name+'-profile.json')).write_text(json.dumps(r,indent=2)+'\n');print('NATIVE_VULKAN_PERSISTENT_PROFILE_STAGE_PASS',stage)
if __name__=='__main__':main()

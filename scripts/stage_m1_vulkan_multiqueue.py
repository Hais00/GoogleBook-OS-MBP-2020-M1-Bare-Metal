#!/usr/bin/env python3
"""Stage two native Vulkan queues for bounded hardware tests; system UI remains GL."""
from pathlib import Path
import hashlib,json,stat
from project_paths import WORK,LARGE_WORK
from stage_native_egl import clone_tree,copy_labeled

def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 parent=WORK/'vendor-vulkan17-stage';stable=WORK/'vendor-vulkan16-stage';stage=WORK/'vendor-vulkan17-mq-stage';assert not stage.exists()
 lock=json.loads((WORK/'vulkan-android-multiqueue-source-lock.json').read_text());binary=WORK/'mesa-android-native/src/asahi/vulkan/libvulkan_asahi.so';assert digest(binary)==lock['driver_sha256']
 clone_tree(parent,stage);name='lib64/hw/vulkan.asahi.so';copy_labeled(binary,stage/name,parent/name);(stage/name).chmod(stat.S_IMODE((parent/name).stat().st_mode));copy_labeled(stable/'build.prop',stage/'build.prop',parent/'build.prop')
 p=stage/'etc/m1-graphics/integration.json';r=json.loads(p.read_text());r['native_source_lock']=lock;r['qualifications'].update(native_Vulkan_AHB_swapchain=False,Vulkan_system_renderer=False,AVD_hardware_decode=False);r['candidate_reason']='Actual HWUI rejected the one-queue driver. Two distinct native queues, async waits and observed shared-heap serialization implemented; all new hardware tests pending. System GL retained.';r['product_renderer_properties']={'debug.renderengine.backend':'skiaglthreaded','debug.renderengine.vulkan':'false','ro.hwui.use_vulkan':'false','debug.hwui.renderer':'skiagl'};r['AVD_firmware']=json.loads((WORK/'avd-fw-build.json').read_text());p.write_text(json.dumps(r,indent=2)+'\n')
 changed=[str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file() and not p.is_symlink() and digest(p)!=digest(parent/p.relative_to(stage))]
 assert set(changed)=={name,'build.prop','etc/m1-graphics/integration.json'},changed
 r={'stage':str(stage),'parent':str(parent),'changed':changed,'new_driver_sha256':digest(stage/name),'source_lock':lock,'system_renderer_initial':'OpenGL while native two-queue tests run','firmware_sha256':digest(stage/'firmware/apple/avd-fw-v2-t0.bin'),'policy_and_audio_unchanged':True,'physical_device_written':False,'hardware_verified':False};(WORK/'vulkan17-mq-stage.json').write_text(json.dumps(r,indent=2)+'\n');print('VULKAN17_NATIVE_MULTIQUEUE_CANDIDATE_STAGE_PASS')
if __name__=='__main__':main()

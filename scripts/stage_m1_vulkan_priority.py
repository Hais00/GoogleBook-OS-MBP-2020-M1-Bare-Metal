#!/usr/bin/env python3
"""Stage the source-locked kernel/Mesa privileged GPU priority integration."""
from pathlib import Path
import hashlib
import json
import stat
from project_paths import WORK, LARGE_WORK
from stage_native_egl import clone_tree, copy_labeled

def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def main():
    parent = WORK/'vendor-vulkan18-stage'
    stage = WORK/'vendor-vulkan19-priority-stage'
    assert not stage.exists()
    lock = json.loads((WORK/'vulkan-full-priority-source-lock.json').read_text())
    kernel = json.loads((LARGE_WORK/'kernel25/clean-kernel-profile.json').read_text())
    assert kernel['privileged_gpu_priority']
    assert digest(Path(kernel['gpu_priority_patch']['file'])) == kernel['gpu_priority_patch']['sha256']
    binary = WORK/'mesa-android-native/src/asahi/vulkan/libvulkan_asahi.so'
    assert digest(binary) == lock['driver_sha256']
    clone_tree(parent, stage)
    name = 'lib64/hw/vulkan.asahi.so'
    copy_labeled(binary, stage/name, parent/name)
    (stage/name).chmod(stat.S_IMODE((parent/name).stat().st_mode))
    path = stage/'etc/m1-graphics/integration.json'
    receipt = json.loads(path.read_text())
    receipt['native_source_lock'] = lock
    receipt['kernel_priority_integration'] = kernel['gpu_priority_patch']
    receipt['qualifications'].update(native_Vulkan_AHB_swapchain=False,
        Vulkan_system_renderer=False, AVD_hardware_decode=False)
    receipt['candidate_reason'] = 'Capability-checked native HIGH/REALTIME queues; caller-scoped discovery, old-kernel and virtio fallback, real owner errors retained. New hardware qualification pending.'
    receipt['product_renderer_properties'] = {'debug.renderengine.backend':'skiavkthreaded',
        'debug.renderengine.vulkan':'true', 'ro.hwui.use_vulkan':'true', 'debug.hwui.renderer':'skiavk'}
    path.write_text(json.dumps(receipt, indent=2)+'\n')
    changed = [str(p.relative_to(stage)) for p in stage.rglob('*')
        if p.is_file() and not p.is_symlink() and digest(p) != digest(parent/p.relative_to(stage))]
    assert set(changed) == {name, 'etc/m1-graphics/integration.json'}, changed
    result = {'stage':str(stage), 'parent':str(parent), 'changed':changed,
        'driver_sha256':lock['driver_sha256'], 'kernel_profile':str(LARGE_WORK/'kernel25/clean-kernel-profile.json'),
        'SELinux_and_audio_WiFi_TouchBar_unchanged':True, 'physical_device_written':False,
        'hardware_verified':False}
    (WORK/'vulkan19-stage.json').write_text(json.dumps(result, indent=2)+'\n')
    print('FULL_PRIORITY_VENDOR19_STAGE_PASS', lock['driver_sha256'])

if __name__ == '__main__':
    main()

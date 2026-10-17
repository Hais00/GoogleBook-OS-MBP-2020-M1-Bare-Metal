"""Apple DRM labels using Android's existing gpu_device and sysfs_gpu types."""

DRM_FILE_CONTEXTS = {
    r'/dev/dri/card[0-9]+': 'u:object_r:gpu_device:s0',
    r'/dev/dri/renderD[0-9]+': 'u:object_r:gpu_device:s0',
}

# Asahi and DCP are OF platform devices. Cover both platform parent layouts;
# only the two device-identification files receive this read-only GPU type.
GPU_UEVENT_PATHS = [
    '/devices/platform/soc/206400000.gpu/uevent',
    '/devices/platform/206400000.gpu/uevent',
    '/devices/platform/soc/soc:display-subsystem/uevent',
    '/devices/platform/soc:display-subsystem/uevent',
]


def graphics_cil():
    text = '\n; Apple DRM device identification for the existing GPU SPHAL policy.\n'
    for path in GPU_UEVENT_PATHS:
        text += f'(genfscon sysfs "{path}" (u object_r sysfs_gpu ((s0) (s0))))\n'
    # GPU SPHAL clients already have read access to sysfs_gpu. Add only the
    # same metadata read to the opt-in UID2000 diagnostic shell/Vulkan probe.
    text += '(allow shell sysfs_gpu (file (read open getattr)))\n'
    return text

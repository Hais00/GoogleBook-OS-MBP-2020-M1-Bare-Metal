echo GOS_HARDWARE_CAPTURE_BEGIN
id
getenforce
cat /proc/cmdline
ls -lZ /dev/dri
for gos_card in /sys/class/drm/card[0-9]; do
    echo "GOS_DRM_CARD=$gos_card"
    readlink -f "$gos_card/device"
    readlink -f "$gos_card/device/driver"
    ls -lZ "$gos_card/device/uevent"
    cat "$gos_card/device/uevent"
done
logcat -b main -b system -b crash -v threadtime '*:W' SystemServer:I SystemServiceManager:I ActivityManager:I AndroidRuntime:V Watchdog:V SurfaceFlinger:I GraphicBufferAllocator:V dras:I googlebook-audio:V googlebook-keymint:V googlebook-vulkan:V Zygote:I &
gos_hardware_logcat_pid=$!
/system_ext/bin/googlebook-labelprobe /vendor/etc/selinux/vendor_file_contexts
gos_sample=0
while [ "$gos_sample" -lt 40 ]; do
    echo "GOS_HARDWARE_SAMPLE=$gos_sample"
    echo "GOS_BOOT_COMPLETED=$(getprop sys.boot_completed)"
    echo "GOS_SYSTEM_SERVER=$(pidof system_server)"
    echo "GOS_SURFACEFLINGER=$(pidof surfaceflinger)"
    echo "GOS_ZYGOTE=$(getprop init.svc.zygote)"
    echo "GOS_BOOTANIM=$(getprop init.svc.bootanim)"
    sleep 30
    gos_sample=$((gos_sample+1))
done
kill "$gos_hardware_logcat_pid"
echo GOS_HARDWARE_CAPTURE_END

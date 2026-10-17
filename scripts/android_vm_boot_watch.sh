echo GOS_WATCH_BEGIN
id
logcat -b main -b system -b crash -v threadtime '*:S' SystemServer:V SystemServiceManager:V ActivityManager:V AndroidRuntime:V Watchdog:V SurfaceFlinger:I GraphicBufferAllocator:W libc:F DEBUG:F AudioFlinger:V AudioPolicyManager:V dras:V googlebook-audio:V googlebook-drm:V googlebook-keymint:V Zygote:I &
gos_android_logcat_pid=$!
sleep 30
/system_ext/bin/googlebook-vkprobe /vendor/lib64/hw/vulkan.pastel.so
i=0
while [ "$i" -lt 60 ]; do
    echo "GOS_WATCH_SAMPLE=$i"
    echo "GOS_BOOT_COMPLETED=$(getprop sys.boot_completed)"
    echo "GOS_ZYGOTE=$(getprop init.svc.zygote)"
    echo "GOS_SURFACEFLINGER=$(getprop init.svc.surfaceflinger)"
    echo "GOS_ODSIGN=$(getprop init.svc.odsign)"
    df -h /data
    echo "GOS_SYSTEM_SERVER=$(pidof system_server)"
    logcat -b events -d -t 100
    if [ "$(getprop sys.boot_completed)" = 1 ]; then
        gos_server_before=$(pidof system_server)
        gos_flinger_before=$(pidof surfaceflinger)
        sleep 120
        echo "GOS_STABLE_BOOT_COMPLETED=$(getprop sys.boot_completed)"
        echo "GOS_SERVER_BEFORE=$gos_server_before"
        echo "GOS_SERVER_AFTER=$(pidof system_server)"
        echo "GOS_FLINGER_BEFORE=$gos_flinger_before"
        echo "GOS_FLINGER_AFTER=$(pidof surfaceflinger)"
        screencap -p /data/local/tmp/googlebook-vm-screen.png
        sync
        sha256sum /data/local/tmp/googlebook-vm-screen.png
        dumpsys SurfaceFlinger
        break
    fi
    sleep 30
    i=$((i+1))
done
kill "$gos_android_logcat_pid"
echo GOS_WATCH_END

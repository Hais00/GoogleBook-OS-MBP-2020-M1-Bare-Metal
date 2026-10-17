echo GOS_PROBE_WAIT
sleep 30
echo GOS_PROBE_BEGIN
id
/system_ext/bin/googlebook-vkprobe /vendor/lib64/hw/vulkan.pastel.so
echo "GOS_BOOT_COMPLETED=$(getprop sys.boot_completed)"
echo "GOS_AB_UPDATE=$(getprop ro.build.ab_update)"
echo "GOS_VIRTUAL_AB=$(getprop ro.virtual_ab.enabled)"
echo "GOS_PROTECTED_VM=$(getprop ro.boot.hypervisor.protected_vm.supported)"
echo "GOS_KEYSTORE=$(getprop init.svc.keystore2)"
echo "GOS_ZYGOTE=$(getprop init.svc.zygote)"
echo "GOS_SURFACEFLINGER=$(getprop init.svc.surfaceflinger)"
ls -ldZ /data /data/misc /data/misc/keystore
logcat -b all -d -t 2500
sleep 45
echo GOS_SECOND_PROBE_BEGIN
getprop
logcat -b all -d -t 2500
echo GOS_SECOND_PROBE_END
echo GOS_PROBE_END

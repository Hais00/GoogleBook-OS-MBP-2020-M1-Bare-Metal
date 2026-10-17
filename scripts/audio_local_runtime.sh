#!/bin/sh
# Executed only by the diskless VM's BusyBox shell, outside the Bionic chroot.
set -eu
hfp=${1:-true}
test "$hfp" = true || test "$hfp" = false
test -f /audio-root/GOS_LOCAL_AUDIO_TEST
test ! -e /audio-root/dev/snd
test -c /audio-root/dev/binder
run() { chroot /audio-root "$@"; }
probe() { timeout 4 /bin/busybox chroot /audio-root /vendor/bin/hw/audio-local-binder-probe "$@"; }
mkdir -p /audio-root/dev/socket
chmod 0777 /audio-root/dev/socket
props='vendor.audio.dras.default_nothing=true ro.bluetooth.a2dp_offload.supported=false persist.bluetooth.a2dp_offload.disabled=true ro.bluetooth.leaudio_offload.supported=false persist.bluetooth.leaudio_offload.disabled=true persist.bluetooth.bluetooth_audio_hal.disabled=false ro.debuggable=1 ro.build.version.sdk=36 ro.product.first_api_level=36 ro.vndk.version=36 sys.use_memfd=true'
cleanup() {
    kill ${logcat:-} ${rust:-} ${cpp:-} ${manager:-} ${logd:-} ${properties:-} ${log_sink:-} 2>/dev/null || true
    sleep 1
    for file in /audio-root/tmp/*.log; do
        echo LOCAL_LOG_FILE=$file
        cat "$file"
        cp "$file" /results/ 2>/dev/null || true
    done
}
trap cleanup EXIT
run /system/bin/audio-local-log-capture > /audio-root/tmp/android.log 2>&1 &
log_sink=$!
run /system/bin/audio-local-properties $props bluetooth.hfp.software_datapath.enabled=$hfp --serve &
properties=$!
sleep 1
kill -0 "$properties"
run /system/bin/servicemanager > /audio-root/tmp/servicemanager.log 2>&1 &
manager=$!
sleep 1
cat /audio-root/tmp/servicemanager.log
kill -0 "$manager"
run /vendor/bin/hw/googlebook-audio-hal > /audio-root/tmp/rust.log 2>&1 &
rust=$!
sleep 2
cat /audio-root/tmp/rust.log
kill -0 "$rust"
run /vendor/bin/hw/dras.core-cpp.audio > /audio-root/tmp/cpp.log 2>&1 &
cpp=$!
sleep 1
cat /audio-root/tmp/cpp.log
status=1
for n in $(seq 1 5); do
    sleep 1
    if probe --owners; then
        if [ "$hfp" = false ]; then
            if probe --expect-absent; then status=0; break; fi
        elif probe; then status=0; break
        fi
    fi
done
echo LOCAL_AUDIO_SOFTWARE_RUNTIME_RC=$status
for p in "$rust" "$cpp" "$manager"; do
    echo LOCAL_SERVICE_PROCESS=$p
    test -d /proc/$p
done
exit "$status"

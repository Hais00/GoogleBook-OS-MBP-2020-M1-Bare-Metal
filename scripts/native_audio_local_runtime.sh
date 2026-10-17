#!/bin/sh
set -eu
test -f /audio-root/GOS_LOCAL_AUDIO_TEST
test ! -e /audio-root/dev/snd
run(){ chroot /audio-root "$@"; }
cleanup(){
 kill ${native:-} ${manager:-} ${properties:-} ${logs:-} 2>/dev/null || true
 for file in /audio-root/tmp/*.log; do echo LOCAL_LOG_FILE=$file;cat "$file";cp "$file" /results/ || true;done
}
trap cleanup EXIT
mkdir -p /audio-root/dev/socket
chmod 0777 /audio-root/dev/socket
run /system/bin/audio-local-log-capture > /audio-root/tmp/android.log 2>&1 & logs=$!
run /system/bin/audio-local-properties ro.debuggable=1 ro.build.version.sdk=36 ro.product.first_api_level=36 ro.vndk.version=36 sys.use_memfd=true --serve & properties=$!
sleep 1
run /system/bin/servicemanager > /audio-root/tmp/servicemanager.log 2>&1 & manager=$!
sleep 1
insmod /host/snd-aloop.ko index=7 id=Loopback pcm_substreams=1
cp -a /dev/snd /audio-root/dev/
test -c /audio-root/dev/snd/controlC7
run /vendor/bin/hw/audio-service-local-loopback-test > /audio-root/tmp/native.log 2>&1 & native=$!
sleep 1
kill -0 "$native"
timeout 15 /bin/busybox chroot /audio-root /vendor/bin/hw/audio-local-pcm-probe > /audio-root/tmp/probe.log 2>&1
cat /audio-root/tmp/probe.log
printf 'LOCAL_AUDIO_SOFTWARE_RUNTIME_RC=0\n'

#!/system/bin/sh
# Compare the diagnostic logcat process's CPU ticks; retain every log record.
echo GOS_LOG_COST_BEGIN
lp=$(pidof logcat)
echo GOS_LOG_STREAM_START
cat /proc/uptime
for p in $lp; do cat /proc/$p/stat; done
sleep 20
echo GOS_LOG_STREAM_END
cat /proc/uptime
for p in $lp; do cat /proc/$p/stat; done
ts=$(date '+%m-%d %H:%M:%S.000')
killall -q logcat
logcat -b all -v threadtime -T "$ts" -f /data/local/tmp/gos19fw-logcost-full.txt &
lp=$!
echo GOS_LOG_FILE_START
cat /proc/uptime
cat /proc/$lp/stat
sleep 20
echo GOS_LOG_FILE_END
cat /proc/uptime
cat /proc/$lp/stat
endts=$(date '+%m-%d %H:%M:%S.000')
kill "$lp"
wait "$lp"
echo GOS_LOG_COST_REPLAY_BEGIN
cat /data/local/tmp/gos19fw-logcost-full.txt
echo GOS_LOG_COST_REPLAY_END
logcat -b all -v threadtime -T "$endts" &
echo GOS_LOG_COST_END

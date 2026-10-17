# Initial UART capture is active before /data exists. A background worker switches
# only after a real file logger is alive and bound to its successfully opened file.
echo GOS_NATIVE_INPUT22_CAPTURE_BEGIN
umask 077
logcat -b all -v threadtime &
GOS_EARLY_UART_PID=$!
echo GOS_INPUT22_EARLY_UART_LOG_PID=$GOS_EARLY_UART_PID
(
 GOS_LOG_ATTEMPT=0
 while [ "$GOS_LOG_ATTEMPT" -lt 120 ]; do
  if [ -d /data/local/tmp ] && [ -w /data/local/tmp ]; then
   GOS_LOG_SPLIT=$(date '+%m-%d %H:%M:%S.000')
   GOS_FULL_FILE=/data/local/tmp/gos-input22-full-$(date +%s)-$$-$GOS_LOG_ATTEMPT.log
   if [ ! -e "$GOS_FULL_FILE" ] && : > "$GOS_FULL_FILE"; then
    logcat -b all -v threadtime -f "$GOS_FULL_FILE" &
    GOS_FILE_PID=$!
    sleep 1
    if kill -0 "$GOS_FILE_PID" 2>/dev/null && [ -s "$GOS_FULL_FILE" ] && grep -a -F -- "$GOS_FULL_FILE" /proc/$GOS_FILE_PID/cmdline >/dev/null; then
     if grep -a -F -- logcat /proc/$GOS_EARLY_UART_PID/cmdline >/dev/null 2>&1; then kill "$GOS_EARLY_UART_PID"; fi
     logcat -b crash -v threadtime -T "$GOS_LOG_SPLIT" &
     GOS_CRASH_PID=$!
     printf '\nGOS_INPUT22_FULL_LOG_PID=%s FILE=%s\nGOS_INPUT22_CRASH_LOG_PID=%s\nGOS_INPUT22_FILE_LOGGING_READY\n' "$GOS_FILE_PID" "$GOS_FULL_FILE" "$GOS_CRASH_PID"
     exit 0
    fi
    if grep -a -F -- "$GOS_FULL_FILE" /proc/$GOS_FILE_PID/cmdline >/dev/null 2>&1; then kill "$GOS_FILE_PID"; fi
    echo GOS_INPUT22_FILE_LOG_UNAVAILABLE_KEEP_FULL_UART
    exit 1
   fi
  fi
  GOS_LOG_ATTEMPT=$((GOS_LOG_ATTEMPT+1))
  sleep 1
 done
 echo GOS_INPUT22_FILE_LOG_UNAVAILABLE_KEEP_FULL_UART
) &
uname -a
getprop sys.boot_completed
pidof system_server surfaceflinger
echo GOS_NATIVE_INPUT22_INITIAL_STATUS_END

"""Parse observed logging readiness; uploaders still verify the live target PID."""
import re

def observed_file_logging(data):
    if not re.search(rb'(?:^|[\r\n])GOS_INPUT22_FILE_LOGGING_READY(?=[\r\n]|\[|$)',data):return None
    full=re.findall(rb'GOS_INPUT22_FULL_LOG_PID=(\d+) FILE=(/data/local/tmp/[A-Za-z0-9_.-]+)',data)
    crash=re.findall(rb'GOS_INPUT22_CRASH_LOG_PID=(\d+)',data)
    if not full or not crash:return None
    return {'mode':'file-plus-crash','full_pid':int(full[-1][0]),'full_remote_file':full[-1][1].decode(),
            'crash_stream_pid':int(crash[-1]),'remote_full_log_retrieved':False,
            'kernel_uart_and_hv_continuous_on_host':True,
            'readiness_source':'Target worker verified PID, readable file and matching cmdline before marker; uploader independently rechecks'}

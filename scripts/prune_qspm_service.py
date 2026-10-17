#!/usr/bin/env python3
"""Remove the Qualcomm QSPM boot service from the isolated M1 stage."""
import hashlib
import json
from project_paths import WORK

stage = WORK/'system-ext-linux-cleanup-stage'
rc = stage/'etc/init/qspmsvc.rc'
assert 'Copyright (c) 2019 Qualcomm Technologies' in rc.read_text()
assert 'service vendor.qspmsvc /system_ext/bin/qspmsvc' in rc.read_text()
assert 'on property:sys.boot_completed=1\n    start vendor.qspmsvc' in rc.read_text()
assert (WORK/'vendor-linux-cleanup-stage/build.prop').read_text().find('ro.board.platform=t8103') >= 0
removed = []
for name in ['etc/init/qspmsvc.rc', 'bin/qspmsvc', 'bin/qspmsvc.fsv_meta']:
    path = stage/name
    if path.exists():
        assert not path.is_symlink()
        removed.append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
for entry in removed:
    (stage/entry['path']).unlink()
(WORK/'qspm-service-cleanup.json').write_text(json.dumps({
    'stage': str(stage), 'removed': removed,
    'reason': 'Qualcomm QSPM uses vendor.qti.qspmhal; the native M1 profile has no Qualcomm QSPM owner.',
    'boot_trigger_verified': True, 'elf_dependency_audit': str(WORK/'complete-stage-component-audit.json'),
    'physical_device_written': False, 'private_libraries_removed': False,
    'qualcomm_removal_complete': False}, indent=2)+'\n')
print('QSPM_FUTURE_STAGE_REMOVED', len(removed))

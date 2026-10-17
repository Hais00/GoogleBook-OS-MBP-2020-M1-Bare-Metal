#!/usr/bin/env python3
"""Stage only the upstream HCI rfkill fix over the installed audio vendor11."""
import hashlib
import json
from pathlib import Path
import stat
from project_paths import WORK, NDK
from stage_native_egl import clone_tree, getlabel, copy_labeled
import subprocess
import re

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    base = WORK/'vendor-audio-stage'
    stage = WORK/'vendor-btaudio12-stage'
    assert not stage.exists()
    receipt = json.loads((WORK/'bluetooth-linux-build.json').read_text())
    assert receipt['interface_version'] == 1 and receipt['rfkill_backport']['only_two_rfkill_calls_and_comments_changed']
    binary = Path(receipt['binary'])
    assert digest(binary) == receipt['binary_sha256']
    clone_tree(base, stage)
    for source in [base] + sorted(base.rglob('*')):
        target = stage/source.relative_to(base)
        assert getlabel(source) == getlabel(target), source
        assert stat.S_IMODE(source.lstat().st_mode) == stat.S_IMODE(target.lstat().st_mode), source
    relative = 'bin/hw/android.hardware.bluetooth-service.default'
    copy_labeled(binary, stage/relative, base/relative)
    (stage/relative).chmod(stat.S_IMODE((base/relative).stat().st_mode))
    def needed(p):
        return re.findall(r'\(NEEDED\).*?\[(.*?)\]', subprocess.check_output([str(NDK/'bin/llvm-readelf'), '-d', str(p)], text=True))
    assert needed(stage/relative) == needed(base/relative)
    changed = []
    for source in sorted(base.rglob('*')):
        if source.is_file() and not source.is_symlink():
            target = stage/source.relative_to(base)
            if digest(source) != digest(target): changed.append(str(source.relative_to(base)))
    assert changed == [relative], changed
    result = {'stage': str(stage), 'base': str(base), 'changed': changed,
              'binary_sha256': receipt['binary_sha256'], 'interface_version': 1,
              'DT_NEEDED_unchanged': True, 'all_labels_and_modes_preserved': True,
              'rfkill_backport': receipt['rfkill_backport'],
              'CIL_APEX_Rust_and_audio_config_unchanged_from_vendor11': True,
              'physical_device_written': False, 'hardware_verified': False}
    (WORK/'m1-btaudio12-stage.json').write_text(json.dumps(result, indent=2)+'\n')
    print('M1_BTAUDIO12_SINGLE_BINARY_STAGE_PASS', receipt['binary_sha256'])

if __name__ == '__main__': main()

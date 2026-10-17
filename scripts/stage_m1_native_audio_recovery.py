#!/usr/bin/env python3
"""Stage bounded PCM XRUN recovery and real MCA buffered pause, with no policy change."""
import hashlib,json,stat
from pathlib import Path
from project_paths import WORK,LARGE_WORK
from stage_native_egl import clone_tree,copy_labeled

def digest(p):
 with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
 parent=WORK/'vendor-native-audio14-stage';stage=WORK/'vendor-native-audio15-stage';assert not stage.exists()
 test=LARGE_WORK/'native-primary-audio-local-runtime-r9-xrun-pause/result.json'
 assert json.loads(test.read_text())['pass']
 negative=LARGE_WORK/'native-primary-audio-local-runtime-r9-xrun-before/result.json'
 assert json.loads(negative.read_text())['pass'] is False
 native=json.loads((WORK/'native-primary-audio-build/native-build.json').read_text());binary=Path(native['binary']);assert digest(binary)==native['sha256']
 clone_tree(parent,stage);name='bin/hw/android.hardware.audio.service.m1';copy_labeled(binary,stage/name,parent/name);(stage/name).chmod(stat.S_IMODE((parent/name).stat().st_mode))
 p=stage/'etc/m1-audio/integration.json';info=json.loads(p.read_text());info['native_binary_sha256']=native['sha256'];info['PCM_recovery']='Actual ALSA XRUN prepare; bounded retry, protection rechecked, conservative observed presentation';info['MCA_pause']='Real PCM stop; frozen kernel availability identifies retained tail; bounded queue during pause, replay only after protection check';info['diagnostics']='Read-only control values/locks and PCM state; actual signal peaks and recovery counters';p.write_text(json.dumps(info,indent=2)+'\n')
 changed=[str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file() and not p.is_symlink() and digest(p)!=digest(parent/p.relative_to(stage))]
 assert set(changed)=={name,'etc/m1-audio/integration.json'},changed
 receipt={'stage':str(stage),'parent':str(parent),'changed':changed,'native':native,'policy_unchanged_from_actual_Enforcing_M1_vendor14':True,'protector_unchanged':True,'real_Binder_FMQ_ALSA_XRUN_pause_standby_test':str(test),'original_binary_reproduces_failure':str(negative),'physical_device_written':False,'speaker_audibility_confirmed':False,'hardware_verified':False}
 (WORK/'native-audio15-stage.json').write_text(json.dumps(receipt,indent=2)+'\n');print('M1_NATIVE15_RECOVERY_STAGE_PASS')
if __name__=='__main__':main()

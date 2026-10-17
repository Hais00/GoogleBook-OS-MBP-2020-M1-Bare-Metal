#!/usr/bin/env python3
"""Stage canonical built-in speaker address; leave ALSA ownership/protection intact."""
from pathlib import Path
import json,hashlib,stat
from project_paths import WORK,LARGE_WORK
from stage_native_egl import clone_tree,copy_labeled

def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 parent=WORK/'vendor-native-audio13-r2-stage';stage=WORK/'vendor-native-audio14-stage';assert not stage.exists()
 assert json.loads((LARGE_WORK/'native-primary-audio-local-runtime-r9/result.json').read_text())['pass']
 native=json.loads((WORK/'native-primary-audio-build/native-build.json').read_text());binary=Path(native['binary']);assert digest(binary)==native['sha256']
 clone_tree(parent,stage);name='bin/hw/android.hardware.audio.service.m1';copy_labeled(binary,stage/name,parent/name);(stage/name).chmod(stat.S_IMODE((parent/name).stat().st_mode))
 p=stage/'etc/m1-audio/integration.json';info=json.loads(p.read_text());info['native_binary_sha256']=native['sha256'];info['internal_speaker_address']='Canonical AIDL id-tag empty string; actual ALSA card/device remain only in qualified backend';p.write_text(json.dumps(info,indent=2)+'\n')
 changed=[str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file() and not p.is_symlink() and digest(p)!=digest(parent/p.relative_to(stage))]
 assert set(changed)=={name,'etc/m1-audio/integration.json'},changed
 receipt={'stage':str(stage),'parent':str(parent),'changed':changed,'native':native,'policy_unchanged_from_actual_Enforcing_M1_vendor13':True,'protector_unchanged_from_actual_running_M1_PID590':True,'Binder_FMQ_ALSA_loopback_and_canonical_address_check_PASS':True,'physical_device_written':False,'hardware_verified':False}
 (WORK/'native-audio14-stage.json').write_text(json.dumps(receipt,indent=2)+'\n');print('M1_NATIVE14_ADDRESS_STAGE_PASS')
if __name__=='__main__':main()

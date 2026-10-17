#!/usr/bin/env python3
"""Reproducible ASan/UBSan contact-lifetime and scanout-bounds regressions."""
import hashlib
import json
from pathlib import Path
import subprocess
from project_paths import BASE, WORK, NDK

root=WORK/'m1-touchbar-build'
root.mkdir(exist_ok=True)
include=root/'host-include/linux'
include.mkdir(parents=True,exist_ok=True)
header=include/'input-event-codes.h'
if not header.exists():header.symlink_to(NDK/'sysroot/usr/include/linux/input-event-codes.h')
source=BASE/'scripts/m1_touchbar_model.cpp'
text=source.read_text()
flags=['/usr/bin/clang++','-std=c++17','-O1','-g','-fsanitize=address,undefined',
       '-fno-omit-frame-pointer','-I'+str(BASE/'scripts'),'-I'+str(root/'host-include')]

def run(name,code,expected_failure=None):
    path=root/(name+'.cpp');binary=root/name
    path.write_text(code)
    subprocess.run(flags+[str(path),str(BASE/'scripts/m1_touchbar_model_test.cpp'),'-o',str(binary)],check=True)
    result=subprocess.run([str(binary)],capture_output=True,text=True)
    (root/(name+'.log')).write_text(result.stdout+result.stderr)
    if expected_failure:
        assert result.returncode!=0 and expected_failure in result.stderr,(name,result.stdout,result.stderr)
    else:assert result.returncode==0,result.stdout+result.stderr
    return {'binary':str(binary),'exit':result.returncode,'expected_failure':expected_failure,'source_sha256':hashlib.sha256(code.encode()).hexdigest()}

result={'positive_host_asan_ubsan_pass':True,'hardware_verified':False,'cases':{}}
result['cases']['positive']=run('model-regression-positive',text)
variants=[('drag','slot.held = -2; // no new press until this finger lifts','slot.held = -1; // deliberately broken','sliding out releases original key'),
          ('slot-reuse','    slot.tracking = tracking;','    if (tracking >= 0) pending.clear(); // deliberately lose the retired contact\n    slot.tracking = tracking;','same-frame slot reuse releases old contact'),
          ('axis-cache','    slot.tracking = tracking;','    if (tracking >= 0) slot.validX = slot.validY = false; // deliberately discard persistent kernel axes\n    slot.tracking = tracking;','unchanged kernel positions survive contact reuse')]
for name,old,new,message in variants:
    assert text.count(old)==1,name
    result['cases'][name]=run('model-regression-negative-'+name,text.replace(old,new),message)
result['broken_drag_negative_control_rejected']=True
result['same_frame_contact_reuse_negative_rejected']=True
result['persistent_axis_cache_negative_rejected']=True
result['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,BASE/'scripts/m1_touchbar_model.h',BASE/'scripts/m1_touchbar_model_test.cpp']}
(root/'model-test-result.json').write_text(json.dumps(result,indent=2)+'\n')
print('M1_TOUCHBAR_MODEL_SANITIZERS_AND_THREE_BROKEN_CONTROLS_PASS')

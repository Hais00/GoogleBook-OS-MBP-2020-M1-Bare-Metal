#!/usr/bin/env python3
"""Build CPU-only Bionic Wi-Fi lifecycle fixtures, separate from the provider."""
import gzip
import hashlib
import json
import subprocess
from project_paths import BASE,WORK,NDK,VNDK,SYSTEM_ORIGINAL
root=WORK/'native-radio-build'
reference=WORK/'references/wifi-aosp-5688f7eb1e11'
sources=[BASE/'scripts/m1_wifi_hal.cpp',BASE/'scripts/m1_wifi_hal_test.cpp']
binary=root/'m1-wifi-cpu-test-v2'
command=[NDK/'bin/aarch64-linux-android35-clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-nostdinc++','-nostdlib++','-isystem',VNDK/'external/libcxx/include','-I'+str(reference/'wifi/legacy_headers/include'),'-I'+str(WORK/'references/aosp-wifi-hal-e7e8646a896f/libwifi_hal/include')]+sources
for directory in [WORK/'vendor-input-stage/lib64',SYSTEM_ORIGINAL/'lib64']:command+=['-L'+str(directory),'-Wl,-rpath-link,'+str(directory)]
command+=['-l:libc++.so','-llog','-Wl,-z,max-page-size=16384','-o',binary]
result=subprocess.run(list(map(str,command)),capture_output=True,text=True)
(root/'wifi-cpu-v2-build.log').write_text(result.stdout+result.stderr)
if result.returncode:raise RuntimeError(result.stderr)
packed=binary.with_suffix('.gz');packed.write_bytes(gzip.compress(binary.read_bytes(),mtime=0))
(root/'wifi-cpu-v2-build.json').write_text(json.dumps({'binary':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'gzip':str(packed),'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'transport_mocked':True,'kernel_wifi_not_accessed':True,'test_functions_not_linked_in_production':True,'runtime_pass':False},indent=2)+'\n')
print('BIONIC_WIFI_CPU_FIXTURE_V2_BUILT',binary.stat().st_size,packed.stat().st_size)

#!/usr/bin/env python3
"""Find declared consumers of product Qualcomm libraries across active/candidate roots.

This is declaration evidence, not proof about arbitrary reflection or runtime
class loading. No APK is patched or installed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile
from project_paths import BASE,WORK,LARGE_WORK,SYSTEM_ORIGINAL
from analyze_product_manifests import manifest

root=LARGE_WORK/'product-golden-audit';out=root/'cross-mount';out.mkdir(exist_ok=True);envelopes=out/'manifests';envelopes.mkdir(exist_ok=True)
aapt=WORK/'tools/aapt2';pin=json.loads(aapt.with_name('aapt2-provenance.json').read_text());assert hashlib.sha256(aapt.read_bytes()).hexdigest()==pin['binary_sha256']
mounts={'system_original':SYSTEM_ORIGINAL,'vendor_active_gen7':WORK/'vendor-codec-stage',
        'system_ext_active':WORK/'system-ext-egl-stage','vendor_cleanup_candidate':WORK/'vendor-linux-cleanup-stage',
        'system_ext_cleanup_candidate':WORK/'system-ext-linux-cleanup-stage'}
issues=[];packages=[];references=[];cache={}
needles=['com.qti.snapdragon.sdk.display','com.qti.extphone.extphonelib-product',
         'vendor.qti.hardware.data.connection-V1.0-java','vendor.qti.hardware.data.connection-V1.1-java',
         'vendor.qti.hardware.data.connectionaidl-V1-java','ims-ext-common']
for scope,base in mounts.items():
    assert base.is_dir(),base
    files=[]
    for sub in ['app','priv-app','overlay']:
        directory=base/sub
        if not directory.exists():continue
        def error(e):issues.append({'scope':scope,'error':str(e),'path':e.filename})
        for folder,dirs,names in os.walk(directory,onerror=error,followlinks=False):
            for name in names:
                if name.endswith('.apk'):files.append(Path(folder)/name)
    for path in sorted(files):
        relative=str(path.relative_to(base))
        try:
            with zipfile.ZipFile(path) as z:data=z.read('AndroidManifest.xml')
            h=hashlib.sha256(data).hexdigest()
            if h not in cache:
                envelope=envelopes/(h+'.apk')
                with zipfile.ZipFile(envelope,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('AndroidManifest.xml',data)
                cache[h]=manifest({'file':relative,'sha256':None,'inspection_envelope':envelope.name,'manifest_sha256':h},envelopes,out,aapt)
            parsed=cache[h]
            relevant=[item for item in parsed['used_libraries'] if any(n in str(item) for n in needles)]
            packages.append({'scope':scope,'file':relative,'package':parsed['package'],'manifest_sha256':h,
                             'used_product_qti_libraries':relevant,'provided_libraries':parsed['provided_libraries']})
        except (OSError,zipfile.BadZipFile,KeyError,AssertionError) as e:
            issues.append({'scope':scope,'file':relative,'error':str(e)})
    for sub in ['etc/init','etc/classpaths']:
        directory=base/sub
        if not directory.exists():continue
        for path in directory.rglob('*'):
            if not path.is_file() or path.is_symlink():continue
            try:
                data=path.read_bytes()
                hits=[n for n in needles+['vendor_sys_qti_display','/product/bin/init.qti.display.sh'] if n.encode() in data]
                if hits:references.append({'scope':scope,'file':str(path.relative_to(base)),'hits':hits,'sha256':hashlib.sha256(data).hexdigest(),'interpretation':'Exact byte reference; protobuf/classpath control flow not inferred'})
            except OSError as e:issues.append({'scope':scope,'file':str(path),'error':str(e)})
result={'scope':'Manifest declarations from base system/vendor/system_ext APKs in active and cleanup source trees, plus init/classpath exact references. Does not cover other APEX filesystems or arbitrary reflection.',
        'roots':{n:str(p) for n,p in mounts.items()},'packages':packages,'init_and_classpath_references':references,
        'issues':issues,'declared_consumers':[p for p in packages if p['used_product_qti_libraries']],
        'all_reflective_or_runtime_consumers_proven_absent':False,'physical_device_written':False}
(out/'product-library-users.json').write_text(json.dumps(result,indent=2)+'\n')
print('CROSS_MOUNT_APK_DECLARATIONS',len(packages),'unique_manifests',len(cache),'issues',len(issues))
print('DECLARED_PRODUCT_QTI_LIBRARY_CONSUMERS',[(p['scope'],p['package'],p['used_product_qti_libraries']) for p in result['declared_consumers']])
print('INIT_OR_CLASSPATH_REFERENCES',references)

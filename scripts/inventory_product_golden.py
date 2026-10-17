#!/usr/bin/env python3
"""Inventory a read-only mounted product EROFS without running its programs.

APK envelopes contain only original binary manifests for host aapt2 inspection;
no rebuilt envelope is installable or used as an Android package replacement.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile

root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);out.mkdir(exist_ok=False)
assert root in [Path('/product-golden'),Path('/product-gms-apex')]
mounts=Path('/proc/mounts').read_text().splitlines()
matching=[line for line in mounts if line.split()[1]==str(root)]
assert len(matching)==1 and matching[0].split()[2] in ['erofs','ext4'] and 'ro' in matching[0].split()[3].split(',')
reader=shutil.which('readelf');assert reader,'GNU readelf is required; missing native coverage must not look like zero dependencies'
(out/'manifests').mkdir();(out/'elf-evidence').mkdir()
qti=re.compile(r'(qualcomm|qcom|qti|adreno|qsee|qmi|fastrpc|adsprpc|cdsprpc|libcld80211|codeaurora)',re.I)
dex_pattern=re.compile(rb'(?:L?(?:com|vendor)[/.](?:qualcomm|qti|qcom)[/.][A-Za-z0-9_.$/;-]{0,160}|org[/.]codeaurora[/.][A-Za-z0-9_.$/;-]{0,160})')
metadata={};packages=[];elfs=[];issues=[];configs=[]

def sha_file(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def native(path,logical,member_hash=None):
    p=subprocess.run([reader,'--wide','--file-header','--dynamic',str(path)],capture_output=True,text=True)
    digest=hashlib.sha256(logical.encode()).hexdigest()
    evidence=digest+'.txt';(out/'elf-evidence'/evidence).write_text(p.stdout+p.stderr)
    if p.returncode:
        issues.append({'source':logical,'error':'readelf failed','exit':p.returncode,'evidence':evidence});return
    def field(name):
        value=re.search(r'^\s*'+name+r':\s*(.*?)\s*$',p.stdout,re.M)
        return value[1] if value else None
    needed=re.findall(r'\(NEEDED\).*?Shared library: \[(.*?)\]',p.stdout)
    elfs.append({'source':logical,'class':field('Class'),'machine':field('Machine'),
                 'needed':needed,'qualcomm_name_match':bool(qti.search(logical)),
                 'qualcomm_needed':[n for n in needed if qti.search(n)],
                 'member_sha256':member_hash,'evidence':evidence})

with tarfile.open(out/'configuration-files.tar','w',format=tarfile.PAX_FORMAT) as archive, tempfile.TemporaryDirectory(prefix='product-elf-audit-') as work:
    temporary=Path(work)/'member.so'
    for p in [root]+sorted(root.rglob('*')):
        s=p.lstat();name=str(p.relative_to(root));entry={'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'kind':stat.S_IFMT(s.st_mode),'bytes':s.st_size,'xattrs':{}}
        for attr in os.listxattr(p,follow_symlinks=False):
            if attr.startswith('security.'):
                entry['xattrs'][attr]=base64.b64encode(os.getxattr(p,attr,follow_symlinks=False)).decode()
        if stat.S_ISLNK(s.st_mode):entry['link']=os.readlink(p)
        if stat.S_ISREG(s.st_mode):
            entry['sha256']=sha_file(p)
            with p.open('rb') as f:magic=f.read(4)
            if magic==b'\x7fELF':native(p,name)
            if p.suffix.lower() in ['.apk','.jar','.apex']:
                package={'file':name,'bytes':s.st_size,'sha256':entry['sha256'],'format':p.suffix[1:],'native_members':[],'dex_qualcomm_references':[]}
                try:
                    with zipfile.ZipFile(p) as z:
                        if 'AndroidManifest.xml' in z.namelist():
                            info=z.getinfo('AndroidManifest.xml');assert info.file_size<16*1024*1024,'oversized binary manifest'
                            manifest=z.read(info);identifier=hashlib.sha256(name.encode()).hexdigest();envelope=out/'manifests'/(identifier+'.apk')
                            with zipfile.ZipFile(envelope,'w',compression=zipfile.ZIP_DEFLATED) as target:target.writestr('AndroidManifest.xml',manifest)
                            package.update(manifest_sha256=hashlib.sha256(manifest).hexdigest(),inspection_envelope=str(envelope.relative_to(out)),inspection_envelope_only=True)
                        for item in z.infolist():
                            if item.is_dir():continue
                            if item.filename.endswith('.so'):
                                package['native_members'].append({'file':item.filename,'bytes':item.file_size})
                                if item.file_size>512*1024*1024:
                                    issues.append({'source':name+'!'+item.filename,'error':'native entry exceeds bounded temporary memory budget; not parsed'});continue
                                h=hashlib.sha256()
                                with z.open(item) as source,temporary.open('wb') as target:
                                    while data:=source.read(1024*1024):h.update(data);target.write(data)
                                with temporary.open('rb') as f:elf=f.read(4)==b'\x7fELF'
                                if elf:native(temporary,name+'!'+item.filename,h.hexdigest())
                                else:issues.append({'source':name+'!'+item.filename,'error':'so entry is not ELF'})
                                temporary.unlink()
                            elif re.fullmatch(r'(?:[^/]+/)*classes\d*\.dex',item.filename):
                                if item.file_size>128*1024*1024:
                                    issues.append({'source':name+'!'+item.filename,'error':'DEX entry exceeds bounded memory budget; string coverage incomplete'});continue
                                references=sorted(set(v.decode('ascii') for v in dex_pattern.findall(z.read(item))))
                                if references:package['dex_qualcomm_references'].append({'dex':item.filename,'references':references[:500],'total_distinct':len(references),'truncated':len(references)>500})
                        if p.suffix=='.apex':
                            package['embedded_payload_inventory_complete']=False
                            issues.append({'source':name,'error':'APEX inner filesystem needs a separate audit'})
                except (zipfile.BadZipFile,KeyError,AssertionError) as error:
                    issues.append({'source':name,'error':str(error)})
                packages.append(package)
            if (name.startswith('etc/') or name.startswith('bin/') or name=='build.prop') and (p.suffix in ['.xml','.rc','.json','.prop','.conf','.cfg','.sh'] or name=='build.prop' or magic.startswith(b'#!')):
                if s.st_size<=4*1024*1024:
                    data=p.read_bytes();archive.add(p,arcname=name,recursive=False)
                    hits=sorted(set(m.group(0) for m in qti.finditer(data.decode(errors='replace'))))
                    configs.append({'file':name,'sha256':entry['sha256'],'qualcomm_markers':hits})
                else:issues.append({'source':name,'error':'configuration exceeds bounded text inventory size'})
        metadata[name]=entry
result={'scope':'Every inode/hash/owner/security xattr in the specified read-only source filesystem; original APK/JAR manifests and native ELF dependencies including so entries; bounded DEX Qualcomm string candidates. No source program executed.',
        'mount_proof':matching[0],'source_root':str(root),'read_only_source':True,'physical_device_opened':False,
        'script_sha256':sha_file(Path(__file__)),'readelf_version':subprocess.check_output([reader,'--version'],text=True).splitlines()[0],
        'file_count':len(metadata),'regular_file_count':sum(v['kind']==stat.S_IFREG for v in metadata.values()),
        'package_count':len(packages),'elf_count':len(elfs),'packages':packages,'elfs':elfs,'configs':configs,'issues':issues,
        'qualcomm_removal_complete':False,'dlopen_runtime_coverage_complete':False,'all_java_bytecode_behavior_proven':False}
(out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(out/'inventory.json').write_text(json.dumps(result,indent=2)+'\n')
print('PRODUCT_GOLDEN_READONLY_INVENTORY_COMPLETE',len(metadata),'inodes',len(packages),'packages',len(elfs),'ELFs',len(issues),'explicit issues',flush=True)

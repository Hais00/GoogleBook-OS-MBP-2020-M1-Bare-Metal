#!/usr/bin/env python3
"""Inventory active vendor services and their Qualcomm-specific ELF dependencies."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import tarfile
from project_paths import BASE, SYSTEM_ORIGINAL, WORK, NDK

QUALCOMM = re.compile(r'(qualcomm|qcom|qti|adreno|qsee|qmi|mink|cdsprpc|adsprpc|fastrpc|libsdm|libagm|arpal|libar-pal|libpal\.|libcld80211|libcnss)',re.I)
ELFS = {}
ISSUES = {}

def scan(paths):
    pending=[]
    for path in sorted(set(paths)):
        if path in ELFS or path in ISSUES:continue
        try:
            with path.open('rb') as f:magic=f.read(4)
            if magic!=b'\x7fELF':
                ISSUES[path]='not ELF (script, placeholder or other data)';continue
            pending.append(path)
        except OSError as error:ISSUES[path]=str(error)
    for offset in range(0,len(pending),96):
        batch=pending[offset:offset+96]
        result=subprocess.run([str(NDK/'bin/llvm-readobj'),'--needed-libs','--elf-output-style=JSON',
                               *map(str,batch)],capture_output=True,text=True)
        try:rows=json.loads(result.stdout)
        except ValueError:rows=[]
        for row in rows:
            summary=row['FileSummary'];path=Path(summary['File'])
            ELFS[path]={'needed':row.get('NeededLibraries',[]),'bits':summary['AddressSize']}
        for path in batch:
            if path not in ELFS:ISSUES[path]='LLVM parse unresolved: '+result.stderr[:500]

def audio_apex(vendor):
    """Read-only extraction of original audio APEX ELF/RC data for this audit."""
    archive=Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance/build/audio-apex-original-files.tar')
    packaged=vendor/'apex/com.android.hardware.audio.desktop-arpal.apex'
    original=BASE/'vendor_work/apex/com.android.hardware.audio.desktop-arpal.apex'
    if not archive.exists() or not packaged.exists():return None
    assert packaged.read_bytes()==original.read_bytes(), 'Original APEX inventory cannot describe a changed APEX'
    cache=WORK/'references/audio-apex-elf-audit';cache.mkdir(parents=True,exist_ok=True)
    pb=None
    with tarfile.open(archive) as source:
        for member in source:
            name=member.name.removeprefix('./')
            path=PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts
            if not (member.isfile() or member.islnk()):continue
            if member.islnk():
                target=PurePosixPath(member.linkname.removeprefix('./'))
                assert not target.is_absolute() and '..' not in target.parts
            with source.extractfile(member) as stream:data=stream.read()
            if name=='apex_manifest.pb':pb=data
            if data.startswith(b'\x7fELF') or name.endswith('.rc'):
                dest=cache/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    assert pb and pb[0]==0x0a
    length=0;shift=0;position=1
    while True:
        byte=pb[position];position+=1;length|=(byte&127)<<shift
        if not byte&128:break
        shift+=7;assert shift<32
    name=pb[position:position+length].decode();assert re.fullmatch('[A-Za-z0-9_.]+',name)
    return '/apex/'+name,cache

def services(vendor, apex=False):
    roots=[vendor/('etc' if apex else 'etc/init')]
    result=[]
    for directory in roots:
        for rc in sorted(directory.rglob('*.rc')):
            current=None
            logical=re.sub(r'\\\r?\n', ' ', rc.read_text(errors='replace'))
            for line in logical.splitlines():
                if line.startswith('service '):
                    words=shlex.split(line,comments=True)
                    if len(words)<3:continue
                    current={'name':words[1],'executable':words[2],'rc':str(rc.relative_to(vendor)),
                             'arguments':words[3:],'interfaces':[],'disabled':False}
                    result.append(current)
                elif line and not line[0].isspace() and not line.startswith('#'):
                    current=None
                elif current:
                    words=line.strip().split()
                    if words and words[0]=='interface':current['interfaces'].append(' '.join(words[1:]))
                    if words==['disabled']:current['disabled']=True
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--vendor',type=Path,default=BASE/'vendor_work')
    ap.add_argument('--output',type=Path,default=WORK/'m1-component-audit.json')
    ap.add_argument('--system-ext',type=Path,default=WORK/'system-ext-linux-cleanup-stage')
    args=ap.parse_args();vendor=args.vendor
    mounts={'/vendor':vendor,'/system':SYSTEM_ORIGINAL,'/system_ext':args.system_ext}
    audio=audio_apex(vendor)
    if audio:mounts[audio[0]]=audio[1]
    paths={};owner={};out=[];executables=[]
    def physical(logical):
        for prefix,root in sorted(mounts.items(),key=lambda x:-len(x[0])):
            if logical.startswith(prefix+'/'):return root/logical[len(prefix)+1:]
        return None
    for prefix,root in mounts.items():
        for libdir in ('lib64','lib'):
            for path in (root/libdir).rglob('*.so'):
                paths.setdefault(path.name,[]).append(path);owner[path]=prefix
        for item in services(root,apex=prefix.startswith('/apex/')):
            item['source_mount']=prefix;path=physical(item['executable'])
            item['resolved_executable']=str(path) if path else None
            if path:executables.append(path);owner[path]=next(
                (p for p,r in mounts.items() if path.is_relative_to(r)),prefix)
            out.append(item)
    scan([p for values in paths.values() for p in values]+executables)
    for item in out:
        executable=physical(item['executable']);info=ELFS.get(executable)
        item['executable_issue']=None if info else ISSUES.get(executable,'outside audited mounts')
        queue=[(executable,[]) ] if info else [];seen=set();names=set();unresolved=set();qcom_paths=[];ambiguous=[]
        while queue:
            node,chain=queue.pop()
            if node in seen:continue
            seen.add(node)
            if QUALCOMM.search(node.name):qcom_paths.append([str(p) for p in chain+[node]])
            for lib in ELFS[node]['needed']:
                names.add(lib)
                candidates=[p for p in paths.get(lib,[]) if p in ELFS and ELFS[p]['bits']==ELFS[node]['bits']]
                own=[p for p in candidates if owner.get(p)==owner.get(node)]
                candidates=own or candidates
                if not candidates:unresolved.add(lib);continue
                if len(candidates)>1:ambiguous.append({'library':lib,'candidates':list(map(str,candidates))})
                queue.extend((p,chain+[node]) for p in candidates)
        item['qualcomm_name_match']=bool(QUALCOMM.search(item['name']+' '+item['executable']))
        item['qualcomm_dependencies']=sorted(n for n in names if QUALCOMM.search(n))
        item['qualcomm_dependency_paths']=qcom_paths
        item['dependencies']=sorted(names);item['unresolved_dependencies']=sorted(unresolved)
        item['ambiguous_resolutions']=ambiguous
    candidates=[x for x in out if x['qualcomm_name_match'] or x['qualcomm_dependencies'] or x['qualcomm_dependency_paths']]
    duplicates={n:[x['source_mount']+'/'+x['rc'] for x in out if x['name']==n]
                for n in {x['name'] for x in out} if sum(x['name']==n for x in out)>1}
    result={'scope':'Init declarations across vendor/system/system_ext and original audio APEX; LLVM DT_NEEDED candidate graph, not runtime/namespace proof',
            'vendor':str(vendor),'service_count':len(out),'qualcomm_candidate_count':len(candidates),
            'qualcomm_removal_complete':False,'linker_namespace_validation_performed':False,
            'scripts_and_dlopen_coverage_complete':False,'duplicate_service_declarations':duplicates,
            'elfs_parsed':len(ELFS),'parse_and_path_issues':{str(p):e for p,e in ISSUES.items()},
            'services':out}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{len(out)} service declarations; {len(candidates)} Qualcomm candidates')
    for x in candidates:
        print(x['name'],x['executable'],'disabled='+str(x['disabled']),','.join(x['qualcomm_dependencies'][:6]))

if __name__=='__main__':main()

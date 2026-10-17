#!/usr/bin/env python3
"""Parse original binary manifests through pinned aapt2, retaining unresolved values."""
import concurrent.futures
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import xml.etree.ElementTree as ET
from project_paths import BASE,WORK,LARGE_WORK

qti=re.compile(r'(qualcomm|qcom|qti|codeaurora)',re.I)

def value(raw):
    quoted=re.match(r'("(?:[^"\\]|\\.)*")',raw)
    if quoted:
        try:return json.loads(quoted[1])
        except ValueError:return {'unresolved':raw}
    if raw in ['true','false']:return raw=='true'
    return {'unresolved':raw}


def manifest(package,source,out,aapt):
    if 'inspection_envelope' not in package:return {'file':package['file'],'manifest_not_available':True}
    envelope=source/package['inspection_envelope'];identifier=envelope.stem
    result=subprocess.run([str(aapt),'dump','xmltree','--file','AndroidManifest.xml',str(envelope)],capture_output=True,text=True)
    (out/(identifier+'.txt')).write_text(result.stdout+result.stderr)
    assert result.returncode==0,(package['file'],result.stderr)
    nodes=[];stack=[]
    for line in result.stdout.splitlines():
        found=re.match(r'^(\s*)E: ([^ ]+)',line)
        if found:
            depth=len(found[1])
            while stack and stack[-1]['indent']>=depth:stack.pop()
            node={'tag':found[2],'indent':depth,'attributes':{},'parent':stack[-1]['tag'] if stack else None}
            nodes.append(node);stack.append(node);continue
        found=re.match(r'^\s*A: (.*?)(?:\(0x[0-9a-f]+\))?=(.*)$',line)
        if found and stack:
            name=found[1].replace('http://schemas.android.com/apk/res/android:','android:')
            stack[-1]['attributes'][name]=value(found[2])
    top=[n for n in nodes if n['tag']=='manifest'];assert len(top)==1
    name=top[0]['attributes'].get('package');assert isinstance(name,str),(package['file'],top)
    record={'file':package['file'],'sha256':package['sha256'],'package':name,'manifest_sha256':package['manifest_sha256'],
            'qti_package_marker':bool(qti.search(name)),
            'elements':[{'tag':n['tag'],'attributes':n['attributes'],'parent':n['parent']} for n in nodes],
            'evidence':str(out/(identifier+'.txt')),'inspection_only':True}
    for category,tags in [('provided_libraries',['library','static-library','sdk-library']),
                          ('used_libraries',['uses-library','uses-native-library','uses-static-library','uses-sdk-library']),
                          ('overlays',['overlay'])]:
        record[category]=[{'tag':n['tag'],**n['attributes']} for n in nodes if n['tag'] in tags]
    return record

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,default=Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance/build/product-golden-inventory'))
    parser.add_argument('--output-dir',type=Path,default=LARGE_WORK/'product-golden-audit')
    args=parser.parse_args();source=args.source_dir;root=args.output_dir;root.mkdir(parents=True,exist_ok=True)
    out=root/'aapt2';out.mkdir(exist_ok=True)
    summary=json.loads((source/'inventory.json').read_text())
    aapt=WORK/'tools/aapt2';pin=json.loads(aapt.with_name('aapt2-provenance.json').read_text())
    assert hashlib.sha256(aapt.read_bytes()).hexdigest()==pin['binary_sha256']
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:packages=list(pool.map(lambda p:manifest(p,source,out,aapt),summary['packages']))
    xml=[];init=[]
    with tarfile.open(source/'configuration-files.tar') as archive:
        for member in archive:
            assert member.isfile()
            data=archive.extractfile(member).read();name=member.name
            if name.endswith('.xml'):
                try:tree=ET.fromstring(data)
                except ET.ParseError:continue
                entries=[]
                for node in tree.iter():
                    if node.attrib and (node.tag in ['library','apex-library','privapp-permissions','hidden-api-whitelisted-app'] or any(qti.search(str(x)) for x in node.attrib.values())):
                        entries.append({'tag':node.tag,'attributes':node.attrib})
                if entries:xml.append({'file':name,'sha256':hashlib.sha256(data).hexdigest(),'entries':entries})
            if name.endswith('.rc') or name.startswith('bin/'):
                text=data.decode(errors='replace')
                if qti.search(name+' '+text):
                    destination=out/(hashlib.sha256(name.encode()).hexdigest()+'.config.txt');destination.write_text(text)
                    init.append({'file':name,'sha256':hashlib.sha256(data).hexdigest(),'evidence':str(destination)})
    result={'scope':'Original product manifests parsed by pinned aapt2; XML provider/dependency declarations and QTI init artifacts. String references are candidates, not proof of an active driver.',
            'source_inventory':str(source/'inventory.json'),'source_inventory_sha256':hashlib.sha256((source/'inventory.json').read_bytes()).hexdigest(),
            'aapt2':pin,'packages':packages,'xml_declarations':xml,'qti_init_artifacts':init,
            'manifest_packages_parsed':sum('package' in p for p in packages),'physical_device_written':False,'qualcomm_removal_complete':False}
    (root/'manifest-and-library-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PRODUCT_ORIGINAL_MANIFESTS_PARSED',result['manifest_packages_parsed'])
    print('QTI_PACKAGE_MARKERS',[(p['file'],p.get('package')) for p in packages if p.get('qti_package_marker')])
    print('QTI_INIT_ARTIFACTS',[p['file'] for p in init])

if __name__=='__main__':main()

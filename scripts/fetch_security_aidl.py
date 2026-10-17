import urllib.request,json,base64,pathlib,concurrent.futures,subprocess
root=pathlib.Path('/opt/googlebook/build/aosp-port/security-aidl');root.mkdir(exist_ok=True)
repo='https://android.googlesource.com/platform/hardware/interfaces/+/refs/heads/main/'
specs=[('keymint','android.hardware.security.keymint','4'),('rkp','android.hardware.security.rkp','3'),('secureclock','android.hardware.security.secureclock','1'),('sharedsecret','android.hardware.security.sharedsecret','1')]
def one(spec):
 package,iface,ver=spec; prefix=f'security/{package}/aidl/aidl_api/{iface}/{ver}/'; dest=root/iface
 files=[]
 def tree(p):
  entries=json.loads(urllib.request.urlopen(repo+prefix+p+'?format=JSON').read()[4:])['entries']
  for e in entries:
   path=p+e['name']
   if e['type']=='tree':tree(path+'/')
   else:files.append(path)
 tree('')
 def fetch(p):
  dst=dest/p;dst.parent.mkdir(exist_ok=True,parents=True)
  if not dst.exists():dst.write_bytes(base64.b64decode(urllib.request.urlopen(repo+prefix+p+'?format=TEXT').read()))
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(fetch,files))
 print(iface,len(files),flush=True)
 return dest,ver
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,specs))
out=root.parent/'security-generated';out.mkdir(exist_ok=True)
common=[str(pathlib.Path('.work/aosp/aidl').absolute()),'--lang=ndk','--structured','--stability=vintf','--min_sdk_version=34','-o',str(out/'src'),'-h',str(out/'include')]
for dest,_ in results:common+=['-I',str(dest)]
for dest,ver in results:
 files=sorted(str(p) for p in dest.rglob('*.aidl'))
 subprocess.run(common+['--version='+ver,'--hash='+ (dest/'.hash').read_text().splitlines()[-1]]+files,check=True)
print('SECURITY_HEADERS_READY')

#!/usr/bin/env python3
"""Fetch public pinned AOSP references for the separate native M1 HAL."""
import concurrent.futures,urllib.request,tarfile,io,json,hashlib
from project_paths import WORK
ROOT=WORK/'references/native-audio-aosp16'
GROUPS=[('system/libfmq','674a2103f2bd9bd5505c58e83af3042be2a24adf','','libfmq'),('frameworks/av','4b2111885ff934799e70eddae2527a9848c3be29','media/liberror/include','liberror-include'),('hardware/interfaces','5688f7eb1e117ed26e642a695de300b7683acb87','audio/aidl','audio-aidl'),('hardware/interfaces','5688f7eb1e117ed26e642a695de300b7683acb87','common/aidl','common-aidl'),('hardware/interfaces','5688f7eb1e117ed26e642a695de300b7683acb87','common/fmq/aidl','fmq-aidl'),('system/hardware/interfaces','f3d42be8ff32eb4ff00873bf2762d13c013d314a','media','media-audio-aidl'),('system/media','f01e84b958fb6a887dc0e74e4b5ebd159f03860a','audio/include','media-audio-include'),('system/media','f01e84b958fb6a887dc0e74e4b5ebd159f03860a','audio_utils/include','audio-utils-include')]
def one(g):
 repo,rev,path,name=g
 url=f'https://android.googlesource.com/platform/{repo}/+archive/{rev}'+('/'+path if path else '')+'.tar.gz'
 archive=ROOT/(name+'.tar.gz');d=ROOT/name
 if not archive.exists():archive.write_bytes(urllib.request.urlopen(url,timeout=60).read())
 if not (d/'.source-extraction-complete').exists():
  d.mkdir(exist_ok=True)
  with tarfile.open(fileobj=io.BytesIO(archive.read_bytes()),mode='r:gz') as t:
   t.extractall(d,members=[m for m in t.getmembers() if m.isfile() or m.isdir()],filter='data')
  (d/'.source-extraction-complete').write_text('Public source files only; external build symlinks omitted.\n')
 return {'name':name,'repository':repo,'commit':rev,'path':path,'url':url,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
def main():
 ROOT.mkdir(exist_ok=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rs=list(pool.map(one,GROUPS))
 (ROOT/'provenance.json').write_text(json.dumps(rs,indent=2)+'\n');print('NATIVE_AUDIO_PUBLIC_REFERENCES_READY',len(rs))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Fetch frozen public AOSP AIDL, then generate matching NDK headers."""
import base64
import concurrent.futures
import hashlib
import json
import subprocess
import tarfile
import io
import urllib.request
from project_paths import BASE, WORK

API = 'https://android.googlesource.com/platform/hardware/interfaces/+/'
DEST = WORK/'hwc-aidl'
GEN = WORK/'hwc-generated'

def get(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()

def main():
    DEST.mkdir(exist_ok=True)
    receipt = DEST/'provenance.json'
    if receipt.exists():
        pin = json.loads(receipt.read_text())['commit']
    else:
        pin = json.loads(get(API+'refs/heads/android16-qpr2-release?format=JSON').decode()[4:])['commit']
    groups = [('graphics/composer/aidl/aidl_api/android.hardware.graphics.composer3/4', 4),
              ('graphics/common/aidl/aidl_api/android.hardware.graphics.common/6', 6),
              ('common/aidl/aidl_api/android.hardware.common/2', 2),
              ('drm/common/aidl/aidl_api/android.hardware.drm.common/1', 1)]
    receipt.write_text(json.dumps({'commit': pin, 'branch': 'android16-qpr2-release'}, indent=2)+'\n')
    for n, (remote, _) in enumerate(groups):
        archive = DEST/(str(n)+('-drm-common' if n == 3 else '')+'.tar.gz')
        if not archive.exists():
            archive.write_bytes(get(API.replace('/+/', '/+archive/')+pin+'/'+remote+'.tar.gz'))
        with tarfile.open(fileobj=io.BytesIO(archive.read_bytes())) as tf:
            tf.extractall(DEST/str(n), filter='data')
    hashes = [{'path': str(path.relative_to(DEST)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
              for path in sorted(DEST.rglob('*.aidl'))]
    receipt.write_text(json.dumps({'commit': pin, 'branch': 'android16-qpr2-release', 'files': hashes}, indent=2)+'\n')
    GEN.mkdir(exist_ok=True)
    for n, (_, version) in enumerate(groups):
        files = sorted((DEST/str(n)).rglob('*.aidl'))
        if n == 3:
            files = [p for p in files if p.name in ('HdcpLevel.aidl', 'HdcpLevels.aidl')]
        hashfile = DEST/str(n)/'.hash'
        args = [BASE/'build/aosp/aidl', '--lang=ndk', '--structured', '--stability=vintf',
                '--min_sdk_version=34', '--version='+str(version),
                '-o', GEN/'src', '-h', GEN/'include']
        if hashfile.exists():
            args += ['--hash='+hashfile.read_text().splitlines()[-1]]
        for i in range(len(groups)):
            args += ['-I', DEST/str(i)]
        subprocess.run(list(map(str, args + files)), check=True)
    print('Generated public Composer V4/common V6 NDK headers:', GEN)

if __name__ == '__main__':
    main()

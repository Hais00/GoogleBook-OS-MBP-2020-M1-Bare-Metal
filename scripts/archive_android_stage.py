#!/usr/bin/env python3
"""Archive Android trees with ownership recovered from installed EROFS images."""
import argparse
import base64
import ctypes
import json
from pathlib import Path
import stat
import tarfile

lib = ctypes.CDLL(None, use_errno=True)
lib.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
lib.getxattr.restype = ctypes.c_ssize_t

def label(path):
    buf = ctypes.create_string_buffer(4096)
    n = lib.getxattr(str(path).encode(), b'security.selinux', buf, len(buf), 0, 1)
    if n < 1:
        raise OSError(ctypes.get_errno(), 'Missing SELinux label: '+str(path))
    return bytes(buf[:n])

def archive(source, metadata, output):
    owners = json.loads(metadata.read_text())
    changes = []
    with tarfile.open(output, 'w', format=tarfile.PAX_FORMAT) as out:
        for p in [source] + sorted(source.rglob('*')):
            rel = str(p.relative_to(source))
            info = out.gettarinfo(str(p), arcname=rel)
            old = owners.get(rel)
            info.uid = old['uid'] if old else 0
            info.gid = old['gid'] if old else 0
            info.uname = info.gname = ''
            if old:
                info.mode = old['mode']
            attrs = dict(old.get('xattrs', {})) if old else {}
            attrs['security.selinux'] = base64.b64encode(label(p)).decode()
            info.pax_headers.update({'LIBARCHIVE.xattr.'+k: v for k, v in attrs.items()})
            if info.isfile():
                with p.open('rb') as inp:
                    out.addfile(info, inp)
            else:
                out.addfile(info)
            if not old:
                changes.append(rel)
    output.with_suffix('.metadata.json').write_text(json.dumps({'source': str(source), 'ownership_source': str(metadata), 'new_root_owned_paths': changes, 'selinux_labels_required': True}, indent=2)+'\n')

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('metadata', type=Path)
    ap.add_argument('output', type=Path)
    a = ap.parse_args()
    archive(a.source, a.metadata, a.output)

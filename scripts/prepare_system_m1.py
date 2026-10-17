#!/usr/bin/env python3
"""Disable OEM repair-partition lifecycle actions on this custom Apple board.

The original service waits for Google GSC manufacturing data and can remove a
repair partition. Neither action is applicable to the Mac's GPT layout. Keep
the class intact but make its two public SystemService lifecycle hooks inert.
All other DEX bytes and archive offsets are kept. The filesystem is rebuilt
from an extraction preserving its Android ownership, modes and security xattrs.
"""
import ctypes
import hashlib
import io
import json
import os
import pathlib
import plistlib
import shutil
import stat
import struct
import subprocess
import sys
import zipfile
import zlib

BASE = pathlib.Path(__file__).resolve().parents[1]
ORIGINAL = pathlib.Path('/opt/googlebook/build/system-labelled-original')
CLASS = 'Lcom/android/server/desktop/repairmode/DesktopRepairModeService;'
JAR = 'system/framework/desktop-services.jar'


def patch_dex(data):
    data = bytearray(data)
    assert data[:8] == b'dex\n039\0'
    u32 = lambda at: struct.unpack_from('<I', data, at)[0]
    assert u32(32) == len(data)
    assert data[12:32] == hashlib.sha1(data[32:]).digest()
    assert u32(8) == zlib.adler32(data[12:])

    def leb(at):
        value, shift = 0, 0
        while True:
            byte = data[at]
            at += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, at
            shift += 7
            assert shift < 35

    strings = []
    for i in range(u32(56)):
        at = u32(u32(60)+4*i)
        _, at = leb(at)
        strings.append(bytes(data[at:data.index(0, at)]).decode('utf8', errors='replace'))
    types = [strings[u32(u32(68)+4*i)] for i in range(u32(64))]
    target = types.index(CLASS)
    definitions = [u32(100)+i*32 for i in range(u32(96))
                   if u32(u32(100)+i*32) == target]
    assert len(definitions) == 1
    at = u32(definitions[0]+24)
    counts = []
    for _ in range(4):
        value, at = leb(at)
        counts.append(value)
    for _ in range(counts[0]+counts[1]):
        _, at = leb(at)
        _, at = leb(at)
    changes = []
    for count in counts[2:]:
        method = 0
        for _ in range(count):
            diff, at = leb(at)
            method += diff
            flags, at = leb(at)
            code, at = leb(at)
            cls, proto, name_id = struct.unpack_from('<HHI', data, u32(92)+method*8)
            name = strings[name_id]
            if name not in ['onStart', 'onBootPhase']:
                continue
            assert cls == target and flags & 1 and not flags & (8 | 0x100 | 0x400)
            proto_at = u32(76)+proto*12
            assert types[u32(proto_at+4)] == 'V'
            params = u32(proto_at+8)
            signature = [] if params == 0 else [types[struct.unpack_from('<H', data, params+4+2*i)[0]]
                                                for i in range(u32(params))]
            assert signature == ([] if name == 'onStart' else ['I'])
            registers, ins, outs, tries, debug, units = struct.unpack_from('<HHHHII', data, code)
            assert tries == 0 and 1 <= units < 256 and code+16+2*units <= len(data)
            original = bytes(data[code+16:code+16+2*units])
            # RETURN_VOID is one code unit. Keeping the full code-item size
            # preserves every DEX offset; all unreachable words remain valid.
            data[code+16:code+16+2*units] = b'\x0e\x00'*units
            changes.append({'method': name, 'code_offset': code, 'code_units': units,
                            'original_code_sha256': hashlib.sha256(original).hexdigest()})
    assert {c['method'] for c in changes} == {'onStart', 'onBootPhase'}
    data[12:32] = hashlib.sha1(data[32:]).digest()
    struct.pack_into('<I', data, 8, zlib.adler32(data[12:]))
    return bytes(data), changes


def patch_jar(original):
    raw = bytearray(original)
    with zipfile.ZipFile(io.BytesIO(raw)) as jar:
        info = jar.getinfo('classes.dex')
        assert info.compress_type == zipfile.ZIP_STORED and info.flag_bits == 0
        dex, changes = patch_dex(jar.read(info))
        assert len(dex) == info.file_size
    local = info.header_offset
    assert raw[local:local+4] == b'PK\x03\x04'
    name_len, extra_len = struct.unpack_from('<HH', raw, local+26)
    start = local+30+name_len+extra_len
    raw[start:start+len(dex)] = dex
    crc = zlib.crc32(dex)
    struct.pack_into('<I', raw, local+14, crc)
    eocd = len(raw)-22
    assert raw[eocd:eocd+4] == b'PK\x05\x06'
    count = struct.unpack_from('<H', raw, eocd+10)[0]
    central = struct.unpack_from('<I', raw, eocd+16)[0]
    found = 0
    for _ in range(count):
        assert raw[central:central+4] == b'PK\x01\x02'
        nl, el, cl = struct.unpack_from('<HHH', raw, central+28)
        if raw[central+46:central+46+nl] == b'classes.dex':
            struct.pack_into('<I', raw, central+16, crc)
            found += 1
        central += 46+nl+el+cl
    assert found == 1 and len(raw) == len(original)
    with zipfile.ZipFile(io.BytesIO(raw)) as jar:
        assert jar.testzip() is None and jar.read('classes.dex') == dex
    return bytes(raw), changes


def main():
    if os.geteuid() != 0:
        subprocess.run(['sudo', '-n', sys.executable, str(pathlib.Path(__file__).resolve())], check=True)
        return
    source = BASE/'extracted_partitions/system_a.img'
    expected = '9d855c83aa359a245d2141afbbdd655d69be38ab2b19b915216612661ae25c9a'
    with source.open('rb') as inp:
        assert hashlib.file_digest(inp, 'sha256').hexdigest() == expected
    volume = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', '/opt/googlebook/build']))
    assert volume['BusProtocol'] == 'Disk Image' and volume['VolumeName'] == 'GOSBuild'
    if not volume['GlobalPermissionsEnabled']:
        subprocess.run(['diskutil', 'enableOwnership', '/opt/googlebook/build'], check=True)
    marker = BASE/'.work/system-original-owners.json'
    if not marker.exists():
        subprocess.run(['fsck.erofs', '--xattrs', '--preserve', '--overwrite',
                        '--extract='+str(ORIGINAL), str(source)], check=True,
                       stdout=subprocess.DEVNULL)
        sample = (ORIGINAL/'system/bin/run-as').stat()
        assert sample.st_uid == 0 and sample.st_gid == 2000
        marker.write_text(json.dumps({'source_image_sha256': expected,
                                     'ownership_preserved': True})+'\n')
    assert json.loads(marker.read_text())['source_image_sha256'] == expected
    original = subprocess.check_output(['dump.erofs', '--cat', '--path=/'+JAR, str(source)])
    assert original == (ORIGINAL/JAR).read_bytes()
    patched, changes = patch_jar(original)
    work = pathlib.Path('/opt/googlebook/build/system-m1-work')
    if not work.exists():
        subprocess.run(['/bin/cp', '-a', '-c', str(ORIGINAL), str(work)], check=True)
    (work/JAR).write_bytes(patched)
    stale = [JAR+'.fsv_meta', 'system/framework/oat/arm64/desktop-services.odex',
             'system/framework/oat/arm64/desktop-services.odex.fsv_meta',
             'system/framework/oat/arm64/desktop-services.vdex',
             'system/framework/oat/arm64/desktop-services.vdex.fsv_meta']
    for rel in stale:
        (work/rel).unlink(missing_ok=True)
    lib = ctypes.CDLL('libSystem.B.dylib', use_errno=True)
    lib.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                            ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.getxattr.restype = ctypes.c_ssize_t
    lib.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                            ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    for rel in ['', 'system', 'system/framework', JAR]:
        path, old = work/rel, ORIGINAL/rel
        path.chmod(stat.S_IMODE(old.stat().st_mode))
        buf = ctypes.create_string_buffer(4096)
        n = lib.getxattr(str(old).encode(), b'security.selinux', buf, len(buf), 0, 1)
        assert n > 0, 'Original SELinux xattr missing: '+str(old)
        assert lib.setxattr(str(path).encode(), b'security.selinux', buf, n, 0, 1) == 0
    output = BASE/'extracted_partitions/system_m1_fixed.img'
    output.unlink(missing_ok=True)
    subprocess.run(['mkfs.erofs', '--quiet', '-b4096', '-zlz4hc,12', '--workers=4',
                    '-U34499ea0-afa4-5418-a737-6f989ba753f6', str(output), str(work)], check=True)
    readback = subprocess.check_output(['dump.erofs', '--cat', '--path=/'+JAR, str(output)])
    assert readback == patched
    check = subprocess.run(['fsck.erofs', '--extract', str(output)], capture_output=True, text=True)
    (BASE/'.work/system-m1-erofs-check.log').write_text(check.stdout+check.stderr)
    assert check.returncode == 0
    with output.open('rb') as inp:
        image_hash = hashlib.file_digest(inp, 'sha256').hexdigest()
    result = {'source_image_sha256': expected, 'image': str(output), 'image_sha256': image_hash,
              'class': CLASS, 'disabled_lifecycle_methods': changes,
              'source_jar_sha256': hashlib.sha256(original).hexdigest(),
              'patched_jar_sha256': hashlib.sha256(patched).hexdigest(),
              'jar_length_and_zip_offsets_preserved': True,
              'image_build': 'full EROFS from original preserved ownership, modes and security xattrs',
              'stale_verity_metadata_and_precompiled_code_removed': stale,
              'erofs_full_integrity_check_passed': True,
              'runtime_validation': 'pending Android boot; no physical install performed'}
    (BASE/'.work/system-m1-repair-policy.json').write_text(json.dumps(result, indent=2)+'\n')
    print('SYSTEM_M1_PREPARED:', output, image_hash)


if __name__ == '__main__':
    main()

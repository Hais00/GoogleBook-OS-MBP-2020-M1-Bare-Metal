"""Validate this board's liblp layout and preserve writable state on updates."""
import hashlib
import os
import pathlib
import struct
import subprocess
import tempfile

STATE_SIZES = {'misc': 4*1024*1024,
               'desktop_security_storage': 32*1024*1024,
               'desktop_security_persist': 16*1024*1024}


def _checked_hash(data, offset, length):
    expected = data[offset:offset+length]
    cleared = bytearray(data)
    cleared[offset:offset+length] = bytes(length)
    assert hashlib.sha256(cleared).digest() == expected, 'Invalid liblp checksum'


def read_layout(path, size, offset=0):
    """Accept only checked, identical metadata copies and linear local extents."""
    assert offset >= 0 and offset % 4096 == 0
    with open(path, 'rb', buffering=0) as inp:
        geometries = []
        for geometry_offset in [4096, 8192]:
            inp.seek(offset + geometry_offset)
            raw = inp.read(4096)
            magic, length = struct.unpack_from('<II', raw)
            assert magic == 0x616c4467 and 52 <= length <= len(raw)
            _checked_hash(raw[:length], 8, 32)
            geometries.append(raw[:length])
        assert geometries[0] == geometries[1], 'liblp geometries disagree'
        maximum, slots, block_size = struct.unpack_from('<III', geometries[0], 40)
        assert maximum % 4096 == 0 and 4096 <= maximum <= 1024*1024
        assert slots == 2 and block_size == 4096
        copies = []
        for i in range(2*slots):
            inp.seek(offset+12288+i*maximum)
            raw = inp.read(maximum)
            assert struct.unpack_from('<I', raw)[0] == 0x414c5030
            hs = struct.unpack_from('<I', raw, 8)[0]
            ts = struct.unpack_from('<I', raw, 44)[0]
            assert 128 <= hs <= len(raw) and hs+ts <= len(raw)
            _checked_hash(raw[:hs], 12, 32)
            assert hashlib.sha256(raw[hs:hs+ts]).digest() == raw[48:80]
            copies.append(raw[:hs+ts])
        assert len(set(copies)) == 1, 'liblp metadata copies disagree'
    raw = copies[0]
    tables = []
    for at in [80, 92, 104, 116]:
        offset, count, stride = struct.unpack_from('<III', raw, at)
        assert stride > 0 and offset+count*stride <= ts
        tables.append((hs+offset, count, stride))
    po, pn, ps = tables[0]
    eo, en, es = tables[1]
    bo, bn, bs = tables[3]
    assert ps == 52 and es == 24 and bn == 1 and bs == 64
    first_sector = struct.unpack_from('<Q', raw, bo)[0]
    device_size = struct.unpack_from('<Q', raw, bo+16)[0]
    assert device_size == size and first_sector*512 >= 12288+2*slots*maximum
    result = {}
    ranges = []
    for i in range(pn):
        name, attrs, first, count, group = struct.unpack_from('<36sIIII', raw, po+i*ps)
        name = name.split(b'\0')[0].decode('ascii')
        assert name and name not in result and first+count <= en
        extents = []
        for j in range(first, first+count):
            sectors, kind, start, dev = struct.unpack_from('<QIQI', raw, eo+j*es)
            assert kind == 0 and dev == 0, 'Unsupported non-linear liblp extent'
            assert start >= first_sector and (start+sectors)*512 <= size
            if sectors:
                extents.append((start*512, sectors*512))
                ranges.append((start*512, (start+sectors)*512))
        result[name] = {'attributes': attrs, 'extents': extents,
                        'bytes': sum(n for _, n in extents)}
    ranges.sort()
    assert all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])), 'Overlapping liblp extents'
    return result


def stage_preserving_state(template, current, manifest, workspace, size, current_offset=0):
    """Clone a blank template privately, preserving state read from actual disk.

    The public template stays reproducible. Backups and the staged image contain
    private secure-storage data and are created with restricted permissions.
    Nothing writes to the physical disk here.
    """
    old = read_layout(current, size, current_offset)
    new = read_layout(template, size)
    pair = ['desktop_security_storage', 'desktop_security_persist']
    assert (pair[0] in old) == (pair[1] in old), 'Incomplete old security-storage layout'
    for name, required_size in STATE_SIZES.items():
        assert new[name]['attributes'] == 0 and new[name]['bytes'] == required_size
        assert len(new[name]['extents']) == 1
        if name in old:
            assert old[name]['attributes'] == 0 and old[name]['bytes'] == required_size
            assert len(old[name]['extents']) == 1
    directory = pathlib.Path(tempfile.mkdtemp(prefix='install-state-', dir=workspace))
    directory.chmod(0o700)
    staged = directory/'super-install.img'
    subprocess.run(['/bin/cp', '-c', str(template), str(staged)], check=True)
    staged.chmod(0o600)
    installed = [dict(part) for part in manifest]
    preserved = []
    with open(current, 'rb', buffering=0) as inp, staged.open('r+b') as out:
        for part in installed:
            name = part['partition']
            assert new[name]['extents'] == [(part['offset'], part['bytes'])]
            # Verify source payloads before incorporating private runtime state.
            out.seek(part['offset'])
            h = hashlib.sha256()
            remaining = part['bytes']
            while remaining:
                chunk = out.read(min(4*1024*1024, remaining))
                assert chunk
                h.update(chunk)
                remaining -= len(chunk)
            assert h.hexdigest() == part['sha256'], 'Template payload differs: '+name
            if name not in STATE_SIZES or name not in old:
                continue
            start, length = old[name]['extents'][0]
            inp.seek(current_offset+start)
            payload = inp.read(length)
            assert len(payload) == length
            backup = directory/(name+'.bin')
            with backup.open('xb') as saved:
                backup.chmod(0o600)
                saved.write(payload)
                saved.flush()
                os.fsync(saved.fileno())
            out.seek(part['offset'])
            assert out.write(payload) == length
            part['sha256'] = hashlib.sha256(payload).hexdigest()
            part['source'] = 'preserved physical runtime state; private backup: '+str(backup)
            preserved.append(name)
        out.flush()
        os.fsync(out.fileno())
    return staged, installed, preserved

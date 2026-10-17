#!/usr/bin/env python3
"""Exercise update preservation on sparse image files, never physical disks."""
import hashlib
import json
import pathlib
import struct
import tempfile
from android_lp_state import read_layout, stage_preserving_state, STATE_SIZES

BASE = pathlib.Path(__file__).resolve().parents[1]


def main():
    template = BASE/'dist/super_vm_debug.img'
    manifest = json.loads(template.with_suffix('.manifest.json').read_text())
    size = template.stat().st_size
    layout = read_layout(template, size)
    with tempfile.TemporaryDirectory(prefix='lp-state-test-', dir=BASE/'.work') as tmp:
        tmp = pathlib.Path(tmp)
        current = tmp/'old-runtime.img'
        # Keep real checked metadata but store only synthetic private state.
        with template.open('rb') as inp, current.open('wb') as out:
            out.write(inp.read(1024*1024))
            out.truncate(size)
            expected = {}
            for name, length in STATE_SIZES.items():
                payload = bytearray(length)
                payload[:len(name)+12] = (name+'-saved-state').encode()
                out.seek(layout[name]['extents'][0][0])
                out.write(payload)
                expected[name] = hashlib.sha256(payload).hexdigest()
        staged, installed, preserved = stage_preserving_state(
            template, current, manifest, tmp, size)
        assert set(preserved) == set(STATE_SIZES)
        assert staged.stat().st_mode & 0o777 == 0o600
        assert staged.parent.stat().st_mode & 0o777 == 0o700
        by_name = {p['partition']: p for p in installed}
        with staged.open('rb') as inp:
            for name, expected_hash in expected.items():
                part = by_name[name]
                inp.seek(part['offset'])
                assert hashlib.sha256(inp.read(part['bytes'])).hexdigest() == expected_hash
                assert part['sha256'] == expected_hash
        assert json.loads(template.with_suffix('.manifest.json').read_text()) == manifest
        # The initial physical install has no added raw-state partitions yet.
        legacy = tmp/'legacy-super.img'
        with (BASE/'dist/super.img').open('rb') as inp, legacy.open('wb') as out:
            out.write(inp.read(1024*1024))
            out.truncate(size)
        fresh, fresh_parts, fresh_preserved = stage_preserving_state(
            template, legacy, manifest, tmp, size)
        assert fresh_preserved == [] and fresh_parts == manifest
        # A corrupted copy must stop an update before a physical write.
        with current.open('r+b') as out:
            out.seek(12288+80)
            byte = out.read(1)
            out.seek(-1, 1)
            out.write(bytes([byte[0] ^ 1]))
        try:
            read_layout(current, size)
        except AssertionError:
            pass
        else:
            raise AssertionError('Corrupt liblp metadata was accepted')
    print('LP_STATE_PASS: existing writable state preserved, first-install migration valid, private file modes, corrupt metadata rejected')


if __name__ == '__main__':
    main()

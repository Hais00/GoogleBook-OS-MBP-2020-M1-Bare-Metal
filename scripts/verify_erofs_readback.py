#!/usr/bin/env python3
"""Compare every archived Android entry with metadata read from mounted EROFS."""
import argparse
import hashlib
import json
import stat
from pathlib import Path
import tarfile


def verify(archive, readback, image, output):
    actual = json.loads(readback.read_text())
    checked = set()
    regular = 0
    with tarfile.open(archive) as source:
        for member in source:
            name = member.name
            assert name not in checked, ('duplicate archive entry', name)
            checked.add(name)
            entry = actual[name]
            expected_kind = (stat.S_IFDIR if member.isdir() else stat.S_IFLNK if member.issym()
                             else stat.S_IFREG if member.isfile() or member.islnk() else None)
            assert expected_kind is not None and entry['kind'] == expected_kind, (name, 'file type')
            if member.issym():
                assert entry['link'] == member.linkname, (name, 'symlink target')
            for key in ('uid', 'gid', 'mode'):
                assert entry[key] == getattr(member, key), (name, key)
            attrs = {key.removeprefix('LIBARCHIVE.xattr.'): value
                     for key, value in member.pax_headers.items()
                     if key.startswith('LIBARCHIVE.xattr.security.')}
            assert attrs == entry['xattrs'], (name, 'security xattrs')
            if member.isfile() or member.islnk():
                with source.extractfile(member) as data:
                    digest = hashlib.file_digest(data, 'sha256').hexdigest()
                assert digest == entry['sha256'], (name, 'payload')
                regular += 1
    assert checked == set(actual), 'EROFS entries differ from archive'
    with image.open('rb') as data:
        digest = hashlib.file_digest(data, 'sha256').hexdigest()
    receipt = {'pass': True, 'image': str(image), 'sha256': digest,
               'bytes': image.stat().st_size, 'entries': len(checked),
               'regular_files_hashed': regular,
               'ownership_modes_security_xattrs_and_payloads_verified': True,
               'symlink_targets_checked': True, 'file_types_checked': True,
               'hardware_verified': False}
    output.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'readback', 'image', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    verify(args.archive, args.readback, args.image, args.output)

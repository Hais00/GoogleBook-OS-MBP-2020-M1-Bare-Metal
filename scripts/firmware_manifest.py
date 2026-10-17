"""Recover firmware hardlink contents using the package's FILE/LINK manifest."""
import hashlib
from pathlib import PurePosixPath
import re
import stat


def _name(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or str(p) != value or '\\' in value or '\0' in value or any(
            part in ('.', '..') for part in p.parts):
        raise ValueError('Unsafe firmware manifest path: '+repr(value))
    return value


def repair_firmware_entries(members, prefix='lib/firmware/'):
    """Return independent regular files; reject unknown data or ambiguous links.

    newc inode identities may have been lost by a previous repacker. The
    manifest supplies the intended names, alias graph and content hashes.
    Actual bytes must still be present and match those hashes in the archive.
    """
    manifest = members[prefix+'.vendorfw.manifest'][2]
    records = {}
    for line in manifest.decode('ascii').splitlines():
        a = line.split()
        if len(a) == 4 and a[0] == 'FILE' and a[2] == 'SHA256' and re.fullmatch('[0-9a-f]{64}', a[3]):
            record = ('FILE', a[3])
        elif len(a) == 3 and a[0] == 'LINK':
            record = ('LINK', _name(a[2]))
        else:
            raise ValueError('Invalid firmware manifest record')
        name = _name(a[1])
        if name in records:
            raise ValueError('Duplicate firmware manifest name: '+name)
        records[name] = record
    resolved = {}

    def resolve(name, seen=()):
        if name in resolved:
            return resolved[name]
        if name in seen:
            raise ValueError('Firmware link cycle: '+name)
        if name not in records:
            raise ValueError('Unknown firmware link target: '+name)
        kind, value = records[name]
        result = (name, value) if kind == 'FILE' else resolve(value, seen+(name,))
        resolved[name] = result
        return result

    data_by_hash = {}
    for name in records:
        full = prefix+name
        if full not in members or stat.S_IFMT(members[full][1][1]) != stat.S_IFREG:
            raise ValueError('Missing or non-regular firmware member: '+full)
        data = members[full][2]
        canonical, expected = resolve(name)
        if data:
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                raise ValueError('Firmware payload differs from manifest: '+full)
            data_by_hash.setdefault(actual, (full, data))
    output = dict(members)
    repaired = []
    for full, (name, values, data) in members.items():
        if not full.startswith(prefix) or stat.S_IFMT(values[1]) != stat.S_IFREG:
            continue
        vals = list(values)
        vals[4] = 1  # Materialize aliases; pack() assigns fresh inode identities.
        if full != prefix+'.vendorfw.manifest':
            relative = full[len(prefix):]
            if relative in records:
                canonical, expected = resolve(relative)
                if not data:
                    if expected not in data_by_hash:
                        raise ValueError('No verified bytes for firmware member: '+full)
                    source, data = data_by_hash[expected]
                    repaired.append({'path': full, 'canonical': prefix+canonical,
                                     'data_source': source, 'sha256': expected, 'bytes': len(data)})
                if not data or hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError('Unresolved firmware payload: '+full)
            elif not data and values[4] > 1:
                raise ValueError('Unidentified empty firmware hardlink: '+full)
        output[full] = (name, vals, data)
    return output, {'manifest_sha256': hashlib.sha256(manifest).hexdigest(),
                    'manifest_entries': len(records), 'repaired_members': repaired,
                    'all_manifest_payload_hashes_verified': True,
                    'aliases_materialized_without_inventing_names': True}

#!/usr/bin/env python3
"""Stage authentic J293 Wi-Fi firmware and a separate initrd candidate.

Use the pinned Asahi extractor and its normal names, with the full BCM4378 B1
subtree as input. No generic firmware alias or guessed board identifier is
created. The kernel19 payload and installed partitions remain untouched.
"""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from project_paths import WORK, LARGE_WORK
from prepare_m1_install import entries, regular
from build_ram_bootstrap import pack

REFERENCE = Path('/opt/googlebook/workspace/sources/asahi-installer')
PIN = 'e93743d52178b3e26e428fa05174ef549abf30cb'
SOURCE = Path('/usr/share/firmware/wifi/C-4378__s-B1')
PREFIX = 'brcm/brcmfmac4378b1-pcie.apple,honshu'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REFERENCE,
                                   text=True).strip() == PIN
    dts = Path('/opt/googlebook/kernel-build/linux-asahi/arch/arm64/boot/dts/apple/t8103-j293.dts')
    assert '&wifi0 {\n\tbrcm,board-type = "apple,honshu";' in dts.read_text()
    assert (SOURCE/'honshu.trx').stat().st_size > 0
    sys.path.insert(0, str(REFERENCE))
    from asahi_firmware.wifi import WiFiFWCollection
    dest = WORK/'wifi-firmware-candidate'
    dest.mkdir(exist_ok=False)
    records = []
    with tempfile.TemporaryDirectory(prefix='gos-wifi-input-') as temporary:
        view = Path(temporary)/SOURCE.name
        view.mkdir()
        # Keep all boards/revisions in this chip subtree so extractor pruning
        # has the same information as a normal full firmware collection.
        for source in SOURCE.iterdir():
            if source.is_file() and source.suffix[1:] in WiFiFWCollection.EXTMAP:
                (view/source.name).symlink_to(source)
        collection = WiFiFWCollection(temporary)
        for name, fw in sorted(collection.files()):
            if not name.startswith(PREFIX):
                continue
            assert fw.data
            origin = SOURCE.parent/fw.name
            assert origin.is_file()
            out = dest/'lib/firmware'/name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(fw.data)
            out.chmod(0o644)
            records.append({'name': name, 'source': str(origin),
                            'source_sha256': sha(origin.read_bytes()),
                            'bytes': len(fw.data), 'sha256': sha(fw.data)})
    names = {record['name'] for record in records}
    assert PREFIX+'.bin' in names and PREFIX+'.clm_blob' in names and PREFIX+'.txcap_blob' in names
    assert (dest/'lib/firmware'/(PREFIX+'.bin')).read_bytes() == (SOURCE/'honshu.trx').read_bytes()
    original = LARGE_WORK/'ram-bootstrap/android-initrd.img'
    original_bytes = original.read_bytes()
    original_entries = list(entries(gzip.decompress(original_bytes)))
    old = {n: (n, v, d) for n, v, d in original_entries}
    assert len(old) == len(original_entries)
    new = {n: row for n, row in old.items() if not n.startswith('lib/firmware/'+PREFIX)}
    for record in records:
        name = 'lib/firmware/'+record['name']
        new[name] = regular(name, (dest/name).read_bytes())
    uncompressed = pack(list(new.values()))
    roundtrip = {n: (v, d) for n, v, d in entries(uncompressed)}
    assert len(roundtrip) == len(new)
    changed = []
    for name in set(old) | set(roundtrip):
        before = old.get(name)
        after = roundtrip.get(name)
        # pack() deliberately assigns inode IDs; compare actual file type,
        # ownership, modes, link counts and payload rather than inode numbers.
        a = (before[1][1:5], before[2]) if before else None
        b = (after[0][1:5], after[1]) if after else None
        if a != b:
            assert name.startswith('lib/firmware/'+PREFIX), name
            changed.append(name)
    assert roundtrip['init'][1] == old['init'][2]
    assert roundtrip['lib/firmware/'+PREFIX+'.bin'][1] == (SOURCE/'honshu.trx').read_bytes()
    candidate = LARGE_WORK/'android-initrd-wifi-candidate'
    candidate.mkdir(exist_ok=False)
    data = gzip.compress(uncompressed, compresslevel=6, mtime=0)
    (candidate/'initrd.img').write_bytes(data)
    note = {'source_initrd': str(original), 'source_initrd_sha256': sha(original_bytes),
            'candidate_initrd': str(candidate/'initrd.img'), 'initrd_sha256': sha(data),
            'compressed_bytes': len(data), 'uncompressed_bytes': len(uncompressed),
            'entries': len(roundtrip), 'changed_paths': sorted(changed),
            'extractor_commit': PIN, 'extractor_source_sha256': sha((REFERENCE/'asahi_firmware/wifi.py').read_bytes()),
            'firmware': records, 'board_type': 'apple,honshu', 'static_dts_board_type_verified': True,
            'generic_aliases_added': False, 'android_init_binary_unchanged': True,
            'roundtrip_nonfirmware_entries_unchanged': True,
            'frozen_kernel19_initrd_unchanged': sha(original.read_bytes()) == sha(original_bytes),
            'physical_installation_performed': False, 'hardware_compatibility_verified': False}
    (candidate/'manifest.json').write_text(json.dumps(note, indent=2)+'\n')
    (dest/'provenance.json').write_text(json.dumps(note, indent=2)+'\n')
    print('M1_WIFI_FIRMWARE_CANDIDATE_PREPARED', len(records), len(data), flush=True)


if __name__ == '__main__':
    main()

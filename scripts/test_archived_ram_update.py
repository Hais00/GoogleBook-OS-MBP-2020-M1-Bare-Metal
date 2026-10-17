#!/usr/bin/env python3
"""Regular-file integration tests for archived inactive LP extent reuse.

Never calls target_device(), opens a serial port, or accepts a block device.
The real generation8/9 host images seed a private sparse mock super file.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from project_paths import LARGE_WORK
from prepare_ram_update_plan import prepare, SIZE
from m1_ram_image_update import validate, apply, hash_region

MAINT=Path('/opt/googlebook/external/middleOS-development-20261016/m1n1-android-maintenance')
ROOT=Path(tempfile.mkdtemp(prefix='archived-installer-test-',dir=LARGE_WORK))
OLD=MAINT/'shared/inbox-generation9-input'
PREFIX=LARGE_WORK/'target-before-kernel23-pitch/super-metadata-prefix.bin'
ARCHIVE=MAINT/'build/vendor-generation8-input-r2.erofs'
CURRENT=MAINT/'build/vendor-generation9-input-lz4.erofs'
ARCHIVE_OFFSET=8002732032
CURRENT_OFFSET=8470396928
ARCHIVE_SHA='04c2e312cfd31f2ccdbf2fbc85ec8dcce925750cbdc44af97acdc548150d7e88'
CURRENT_SHA='471853eade7fe1414b5d5152883bfb30f64764ef780770263bba7b0d8b27c7f4'

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    assert digest(ARCHIVE)==ARCHIVE_SHA and digest(CURRENT)==CURRENT_SHA
    archived={'partition':'vendor_a','offset':ARCHIVE_OFFSET,'bytes':ARCHIVE.stat().st_size,'source':str(ARCHIVE),'sha256':ARCHIVE_SHA}
    protected=[OLD/r['file'] for r in json.loads((OLD/'update-plan.json').read_text())['protected_prefixes']]
    dummy=ROOT/'new-vendor-fixture.erofs'
    with dummy.open('wb') as f:f.truncate(403701760)
    destination=ROOT/'plan'
    plan=prepare(PREFIX,{'vendor_a':dummy},destination,protected,[archived])
    assert plan['images'][0]['offset']==ARCHIVE_OFFSET
    assert plan['old_payloads_preserved'] is False and plan['active_payloads_preserved'] is True
    device=ROOT/'super-fixture.img'
    with device.open('wb') as disk:
        disk.truncate(SIZE);disk.seek(0);disk.write(PREFIX.read_bytes())
        for source,offset in [(ARCHIVE,ARCHIVE_OFFSET),(CURRENT,CURRENT_OFFSET)]:
            disk.seek(offset)
            with source.open('rb') as f:shutil.copyfileobj(f,disk,1024*1024)
        disk.flush();os.fsync(disk.fileno())
    assert stat.S_ISREG(device.stat().st_mode) and device.is_relative_to(ROOT)
    failures=[]
    def reject(label,mutate):
        selected=copy.deepcopy(plan);undo=mutate(selected)
        attempted=[];original=Path.open
        def guarded(path,mode='r',*a,**k):
            if path==device and any(c in mode for c in 'wax+'):
                attempted.append(mode);raise AssertionError('Unexpected writable open during validation')
            return original(path,mode,*a,**k)
        Path.open=guarded
        try:
            try:validate(selected,destination,device)
            except (AssertionError,ValueError):failures.append(label)
            else:raise RuntimeError('Unsafe plan was admitted: '+label)
            assert not attempted,label
        finally:
            Path.open=original
            if undo:undo()
    reject('wrong archive digest',lambda p:p['archived_extents'][0].update(sha256='0'*64))
    reject('wrong archive boundary',lambda p:p['archived_extents'][0].update(bytes=p['archived_extents'][0]['bytes']-4096))
    reject('archive overlaps active vendor',lambda p:p['archived_extents'][0].update(offset=CURRENT_OFFSET,bytes=CURRENT.stat().st_size))
    reject('missing rollback archive',lambda p:p['archived_extents'][0].update(file='missing.erofs'))
    reject('archive path traversal',lambda p:p['archived_extents'][0].update(file='../new-vendor-fixture.erofs'))
    reject('incorrect history disclosure',lambda p:p.update(old_payloads_preserved=True))
    reject('unapproved partition role',lambda p:p['images'][0].update(partition='product_a'))
    reject('unreleased active overlap',lambda p:p['images'][0].update(offset=CURRENT_OFFSET))
    reject('stale LP prefix',lambda p:p.update(old_prefix_sha256='0'*64))
    def corrupt_inactive(p):
        with device.open('r+b') as f:f.seek(ARCHIVE_OFFSET);byte=f.read(1);f.seek(ARCHIVE_OFFSET);f.write(bytes([byte[0]^1]))
        def undo():
            with device.open('r+b') as f:f.seek(ARCHIVE_OFFSET);f.write(byte)
        return undo
    reject('on-device inactive bytes differ',corrupt_inactive)
    metadata=validate(plan,destination,device)
    apply(plan,destination,device,metadata)
    with device.open('rb') as f:
        assert hash_region(f,CURRENT_OFFSET,CURRENT.stat().st_size)==CURRENT_SHA
    # Restoring the old metadata still selects the untouched previously active
    # generation9 payload. Generation8 requires its archived payload too.
    from android_lp_state import read_layout
    assert read_layout(device,SIZE)['vendor_a']['extents']==[(ARCHIVE_OFFSET,403701760)]
    with device.open('r+b') as f:f.write(PREFIX.read_bytes());f.flush();os.fsync(f.fileno())
    assert read_layout(device,SIZE)['vendor_a']['extents']==[(CURRENT_OFFSET,CURRENT.stat().st_size)]
    result={'pass':True,'negative_cases':failures,'negative_count':len(failures),
        'validation_never_opens_target_writable':True,'positive_write_readback_and_four_LP_copies_pass':True,
        'previous_active_payload_hash_unchanged':CURRENT_SHA,'metadata_only_rollback_to_previous_active_pass':True,
        'archived_payload_readback_compared_before_write':True,'all_devices_regular_fixtures':True,'hardware_verified':False}
    # Remove only this test's large generated files; keep receipts and LP data.
    generated=[device,dummy,destination/'vendor_a.erofs',destination/plan['archived_extents'][0]['file']]
    for path in generated:assert path.is_relative_to(ROOT) and path.is_file();path.unlink()
    result['large_generated_fixture_files_removed']=[str(p) for p in generated]
    (ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('ARCHIVED_EXTENT_VALIDATION_AND_ROLLBACK_TESTS_PASS',ROOT,flush=True)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Replace slot-A system/vendor images and update all liblp metadata copies."""
import hashlib
import json
import pathlib
import struct
import subprocess
import zlib
import argparse

BASE = pathlib.Path(__file__).resolve().parents[1]

def add_boot_storage(raw, image):
    """Allocate the board's raw boot/security storage inside existing super space."""
    hs = struct.unpack_from('<I', raw, 8)[0]
    desc = [struct.unpack_from('<III', raw, off) for off in [80, 92, 104, 116]]
    tables = [bytes(raw[hs+at:hs+at+n*size]) for at, n, size in desc]
    pn, ps = desc[0][1:]; en, es = desc[1][1:]
    assert ps == 52 and es == 24
    specs = [('misc',4*1024*1024),('desktop_security_storage',32*1024*1024),
             ('desktop_security_persist',16*1024*1024)]
    assert all(tables[0][i*ps:i*ps+36].split(b'\0')[0].decode() not in dict(specs) for i in range(pn))
    ranges = []
    for i in range(en):
        count, kind, start, dev = struct.unpack_from('<QIQI', tables[1], i*es)
        assert kind == 0 and dev == 0
        ranges.append((start, start+count))
    start = (max(z for _, z in ranges)+2047)//2048*2048
    image.seek(0, 2)
    limit = image.tell()//512
    results = []
    for index,(name,size) in enumerate(specs):
        sectors = size//512
        assert start+sectors <= limit
        assert all(start >= z or start+sectors <= a for a,z in ranges)
        tables[0] += struct.pack('<36sIIII',name.encode(),0,en+index,1,0)
        tables[1] += struct.pack('<QIQI',sectors,0,start,0)
        payload = bytearray(size)
        if name == 'misc':
            state = bytearray(32)
            state[:2] = b'_a'; struct.pack_into('<I',state,4,0x42414342)
            state[8],state[9],state[12]=1,1,15|(7<<4)
            struct.pack_into('<I',state,28,zlib.crc32(state[:28]))
            payload[2048:2080]=state
        image.seek(start*512);image.write(payload)
        results.append({'partition':name,'bytes':size,'offset':start*512,
                        'source':'raw state allocated only inside Android super',
                        'sha256':hashlib.sha256(payload).hexdigest()})
        start += sectors
    at = 0
    for i, (data, (_, n, size)) in enumerate(zip(tables, desc)):
        struct.pack_into('<III', raw, 80+i*12, at, n+(len(specs) if i < 2 else 0), size)
        raw[hs+at:hs+at+len(data)] = data
        at += len(data)
    assert hs+at <= len(raw)
    struct.pack_into('<I', raw, 44, at)
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vendor-image', type=pathlib.Path, default=BASE/'extracted_partitions/vendor_m1_fixed.img')
    parser.add_argument('--system-image', type=pathlib.Path, default=BASE/'extracted_partitions/system_m1_fixed.img')
    parser.add_argument('--output', type=pathlib.Path, default=BASE/'dist/super_m1_fixed.img')
    args = parser.parse_args()
    assert args.system_image.is_file(), 'Prepare the M1 system image before rebuilding super'
    if args.system_image == BASE/'extracted_partitions/system_m1_fixed.img':
        proof = json.loads((BASE/'.work/system-m1-repair-policy.json').read_text())
        with args.system_image.open('rb') as inp:
            assert hashlib.file_digest(inp, 'sha256').hexdigest() == proof['image_sha256']
    src = BASE / "dist/super.img"
    dst = args.output
    if dst.exists():
        dst.unlink()
    subprocess.run(["/bin/cp", "-c", str(src), str(dst)], check=True)
    replacements = {"system_a": args.system_image,
                    "vendor_a": args.vendor_image,
                    "system_ext_a": BASE / "extracted_partitions/system_ext_m1_fixed.img"}
    results = []
    with dst.open("r+b") as f:
        f.seek(4096)
        geometry = f.read(4096)
        assert struct.unpack_from("<I", geometry)[0] == 0x616c4467
        maximum, slots, block_size = struct.unpack_from("<III", geometry, 40)
        offsets = [12288 + i * maximum for i in range(slots * 2)]
        f.seek(offsets[0])
        raw = bytearray(f.read(maximum))
        assert struct.unpack_from("<I", raw)[0] == 0x414c5030
        hs = struct.unpack_from("<I", raw, 8)[0]
        ts = struct.unpack_from("<I", raw, 44)[0]
        po, count, ps = struct.unpack_from("<III", raw, 80)
        eo, ec, es = struct.unpack_from("<III", raw, 92)
        for i in range(count):
            p = hs + po + i * ps
            name = bytes(raw[p:p+36]).split(b"\0")[0].decode()
            if name not in replacements:
                continue
            first, n = struct.unpack_from("<II", raw, p+40)
            assert n == 1, "This installer expects the checked single-linear-extent layout"
            e = hs + eo + first * es
            old_sectors, kind, at, device = struct.unpack_from("<QIQI", raw, e)
            assert kind == 0 and device == 0
            payload = replacements[name]
            size = payload.stat().st_size
            assert size % block_size == 0
            # Rebuilt images may use the adjacent unallocated space, while
            # preserving every other extent and the physical partition size.
            later = []
            for index in range(ec):
                other = hs + eo + index * es
                _, other_kind, other_at, other_dev = struct.unpack_from('<QIQI', raw, other)
                if other_kind == 0 and other_dev == 0 and other_at > at:
                    later.append(other_at*512)
            limit = min(later) if later else src.stat().st_size
            if at*512+size > limit:
                # Use a verified free logical range inside this same super.
                # In particular system_a was reduced from the old system-other
                # payload, leaving a large unused hole before vendor/product.
                occupied = []
                for index in range(ec):
                    if index == first:
                        continue
                    other = hs + eo + index*es
                    length, typ, begin, source = struct.unpack_from('<QIQI', raw, other)
                    assert typ == 0 and source == 0
                    occupied.append((begin, begin+length))
                bo = struct.unpack_from('<I', raw, 116)[0]
                cursor = struct.unpack_from('<Q', raw, hs+bo)[0]
                needed = size//512
                chosen = None
                for begin, end in sorted(occupied) + [(src.stat().st_size//512, src.stat().st_size//512)]:
                    cursor = (cursor+2047)//2048*2048
                    if cursor+needed <= begin:
                        chosen = cursor
                        break
                    cursor = max(cursor,end)
                assert chosen is not None, (name,'no free range inside allocated super')
                at = chosen
                struct.pack_into('<Q', raw, e+12, at)
            struct.pack_into("<Q", raw, e, size // 512)
            f.seek(at * 512)
            digest = hashlib.sha256()
            with payload.open("rb") as inp:
                for chunk in iter(lambda: inp.read(4*1024*1024), b""):
                    f.write(chunk)
                    digest.update(chunk)
            results.append({"partition": name, "bytes": size, "offset": at*512,
                            "source": str(payload), "sha256": digest.hexdigest()})
        assert {r["partition"] for r in results} == set(replacements)
        ranges=[]
        for index in range(ec):
            length, typ, begin, device=struct.unpack_from('<QIQI',raw,hs+eo+index*es)
            assert typ==0 and device==0 and begin+length <= src.stat().st_size//512
            ranges.append((begin,begin+length))
        ranges.sort()
        assert all(a[1] <= z[0] for a,z in zip(ranges,ranges[1:])), 'overlapping logical extents'
        results.extend(add_boot_storage(raw, f))
        ts = struct.unpack_from('<I', raw, 44)[0]
        raw[48:80] = hashlib.sha256(raw[hs:hs+ts]).digest()
        raw[12:44] = b"\0"*32
        raw[12:44] = hashlib.sha256(raw[:hs]).digest()
        for off in offsets:
            f.seek(off)
            f.write(raw)
        f.flush()
    with dst.open("rb") as f:
        for off in offsets:
            f.seek(off)
            actual = bytearray(f.read(maximum))
            assert actual == raw
            checksum = bytes(actual[12:44]); actual[12:44] = b"\0"*32
            assert hashlib.sha256(actual[:hs]).digest() == checksum
            assert hashlib.sha256(actual[hs:hs+ts]).digest() == actual[48:80]
        for r in results:
            f.seek(r["offset"])
            h = hashlib.sha256(); remaining = r["bytes"]
            while remaining:
                b = f.read(min(remaining, 4*1024*1024)); assert b
                h.update(b); remaining -= len(b)
            assert h.hexdigest() == r["sha256"]
    manifest = BASE/'.work/fixed-super-manifest.json' if dst == BASE/'dist/super_m1_fixed.img' else dst.with_suffix('.manifest.json')
    manifest.write_text(json.dumps(results, indent=2)+"\n")
    print("Validated", dst, "with", len(offsets), "matching liblp metadata copies")
    for r in results:
        print(r["partition"], r["bytes"], r["sha256"])

if __name__ == "__main__":
    main()

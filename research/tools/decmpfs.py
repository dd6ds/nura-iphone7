#!/usr/bin/env python3
"""APFS/HFS decmpfs entpacken: decmpfs.py <datei:com.apple.decmpfs> <datei:com.apple.ResourceFork> <ausgabe>
Typen: 3 (zlib inline), 4 (zlib Resource-Fork), 7/8 (LZVN), 11/12 (LZFSE) – LZVN/LZFSE via pyliblzfse/lzfse, falls vorhanden."""
import struct, sys, zlib
hdr = open(sys.argv[1], "rb").read()
magic, typ, size = struct.unpack_from("<4sIQ", hdr)
assert magic == b"fpmc", magic
print(f"decmpfs Typ {typ}, Größe {size}")
rf = open(sys.argv[2], "rb").read() if len(sys.argv) > 2 else b""

def chunks_zlib(rf):
    data_off = struct.unpack_from(">I", rf, 0)[0]
    base = data_off + 4
    n = struct.unpack_from("<I", rf, base)[0]
    for i in range(n):
        off, ln = struct.unpack_from("<II", rf, base + 4 + 8 * i)
        yield rf[base + off: base + off + ln]

def chunks_lz(rf):
    first = struct.unpack_from("<I", rf, 0)[0]
    offs = [struct.unpack_from("<I", rf, 4 * i)[0] for i in range(first // 4)]
    for a, b in zip(offs, offs[1:]):
        yield rf[a:b]

out = b""
if typ == 3:
    d = hdr[16:]; out = d[1:] if d[:1] == b"\xff" else zlib.decompress(d)
elif typ == 4:
    for c in chunks_zlib(rf):
        out += c[1:] if c[:1] == b"\xff" else zlib.decompress(c)
elif typ in (7, 8, 11, 12):
    import lzfse  # pip install pyliblzfse  (kann auch LZVN-Blöcke mit Header)
    for c in chunks_lz(rf):
        if c[:1] == b"\x06": out += c[1:]; continue
        if typ in (7, 8):
            out += lzfse.decompress(b"bvxn" + struct.pack("<II", 65536, len(c)) + c + b"bvx$")[:65536]
        else:
            out += lzfse.decompress(c)
else:
    sys.exit(f"Typ {typ} nicht unterstützt")
out = out[:size]
open(sys.argv[3], "wb").write(out)
print(f"{sys.argv[3]}: {len(out)} Bytes")

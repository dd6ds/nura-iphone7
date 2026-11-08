#!/usr/bin/env python3
"""Apple pbze/pbzx-Container entpacken (Blöcke: u64 roh, u64 komprimiert, Daten).
Blöcke mit 'bvx' am Anfang sind LZFSE, gleich große Blöcke sind unkomprimiert.
Aufruf: pbze_extract.py in.bin out.bin"""
import struct, sys
import liblzfse

d = open(sys.argv[1], "rb").read()
magic = d[:4]
assert magic in (b"pbze", b"pbzx"), magic
pos = 12  # magic + u64 Blockgröße
out = open(sys.argv[2], "wb")
n = 0
while pos + 16 <= len(d):
    usize, csize = struct.unpack(">QQ", d[pos:pos + 16]); pos += 16
    chunk = d[pos:pos + csize]; pos += csize
    if csize == usize:
        out.write(chunk)
    elif chunk[:3] == b"bvx":
        out.write(liblzfse.decompress(chunk))
    else:
        raise SystemExit(f"Unbekannter Block bei {pos}: {chunk[:4]!r}")
    n += 1
out.close()
print(f"{n} Blöcke entpackt -> {sys.argv[2]}")

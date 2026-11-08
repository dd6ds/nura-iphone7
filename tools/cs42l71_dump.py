#!/usr/bin/env python3
"""cs42l71_dump.py [seite] [von] [bis] – Register einer Seite einzeln per SPIv2 lesen (root, Maggie im Reset).
Ohne Argumente: Seiten 0,1,2,3 jeweils 0x00..0x1f."""
import sys
sys.path.insert(0, "/tmp")
from cs42l71_v2 import read

pages = [int(sys.argv[1], 0)] if len(sys.argv) > 1 else [0, 1, 2, 3]
lo = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
hi = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x1f
for p in pages:
    vals = []
    for r in range(lo, hi + 1):
        sts, d = read((p << 16) | r, 8, 0, verbose=False)   # Daten direkt nach dem ersten Status (d0)
        vals.append("--" if (sts[0] & 0x50) != 0x50 else f"{d[0]:02x}")
    for i in range(0, len(vals), 16):
        print(f"{(p << 16) | (lo + i):#08x}: " + " ".join(vals[i:i + 16]))

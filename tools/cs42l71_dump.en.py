#!/usr/bin/env python3
"""cs42l71_dump.en.py [page] [from] [to] – read the registers of a page one by one via SPIv2 (root, Maggie in reset).
Without arguments: pages 0,1,2,3, registers 0x00..0x1f each."""
import sys
sys.path.insert(0, "/tmp")
from cs42l71_v2 import read

pages = [int(sys.argv[1], 0)] if len(sys.argv) > 1 else [0, 1, 2, 3]
lo = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
hi = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x1f
for p in pages:
    vals = []
    for r in range(lo, hi + 1):
        sts, d = read((p << 16) | r, 8, 0, verbose=False)   # data right after the first status (d0)
        vals.append("--" if (sts[0] & 0x50) != 0x50 else f"{d[0]:02x}")
    for i in range(0, len(vals), 16):
        print(f"{(p << 16) | (lo + i):#08x}: " + " ".join(vals[i:i + 16]))

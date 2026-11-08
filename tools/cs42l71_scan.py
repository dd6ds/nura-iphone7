#!/usr/bin/env python3
"""cs42l71_scan.py – Adressbereiche des CS42L71 per SPIv2 lesen und Nicht-Null-Werte zeigen (root, Maggie im Reset)."""
import sys
sys.path.insert(0, "/tmp")
from cs42l71 import xfer

def read(addr, n, word):
    cmd = 0xC4 if word else 0xC6
    xfer([0xA1, 0x00])
    k = min(n, 32)
    rx = xfer([0x80, addr & 0xff, (addr >> 8) & 0xff, (addr >> 16) & 0xff, 0x81, n & 0xff, n >> 8, cmd, 0]
              + [0] * (2 * k) + [cmd, 0])
    st, i = rx[-1], 0
    while (st & 0x50) != 0x50 and i < 31:
        rx = xfer([0] * (2 * k + 2) + [cmd, 0]); st = rx[-1]; i += 1
    nb = n * 4 if word else n
    d = xfer([0] * (nb + 2))[:nb]
    xfer([0xA1, 0x40])
    return st, d

word = "word" in sys.argv
step = 8 if word else 16
# Adressen = Seite<<16 | Register (aus AppleCS42L71Audio: 0x10001, 0x200003, 0x300000, 0x3000c …)
ranges = [(p << 16, (p << 16) + 0x40) for p in range(0, 8)] if not word else \
         [(0x0, 0x400), (0x1000, 0x1100), (0x4000, 0x4100), (0x10000, 0x10100), (0x14000, 0x14100)]
for lo, hi in ranges:
    for a in range(lo, hi, step):
        st, d = read(a, step, word)
        if any(d) or (st & 0x50) != 0x50:
            print(f"{a:#07x} st={st:#04x}: {d.hex(' ')}")
print("fertig")

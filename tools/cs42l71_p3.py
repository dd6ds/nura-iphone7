#!/usr/bin/env python3
"""cs42l71_p3.py – Byte- und Wortlesen vergleichen (Seite 0/1 bekannt, Seite 3 = Status, 0x3000c RCO)
(root, Maggie im Reset). Wortmodus wie iOS _readReg: Kommando C4, Anzahl 1, 4 Datenbytes."""
import sys
sys.path.insert(0, "/tmp")
from cs42l71 import xfer

def rd_word(addr, words=1, cmd=0xC4):
    k = min(words, 32)
    xfer([0xA1, 0])
    tx = [0x80, addr & 0xff, (addr >> 8) & 0xff, (addr >> 16) & 0xff, 0x81, words & 0xff, words >> 8, cmd, 0]
    tx += [0] * (2 * k) + [cmd, 0]
    st = len(tx) - 1
    tx += [0] * (4 * words + 2)
    rx = xfer(tx)
    xfer([0xA1, 0x40])
    return rx[st], rx[st + 1:st + 1 + 4 * words]

for a in (0x0, 0x1, 0x4, 0x10000, 0x10001, 0x10004, 0x20000, 0x30000, 0x3000c, 0x40000, 0x50000):
    for w in (1, 2):
        st, d = rd_word(a, w)
        print(f"{a:#08x} x{w}: st={st:02x} {d.hex(' ')}")

#!/usr/bin/env python3
"""cs42l71_p3.py – Seite 3 (Status, z. B. 0x3000c RCO) byte- und wortweise lesen (root, Maggie im Reset)."""
import sys
sys.path.insert(0, "/tmp")
from cs42l71_v2 import read

for a in (0x30000, 0x30004, 0x30008, 0x3000c, 0x30010, 0xc000 | 0x3000c >> 2):
    sb, db = read(a, 8, 0, cmd=0xC6, verbose=False)
    sw, dw = read(a, 2, 0, cmd=0xC4, verbose=False)
    print(f"{a:#08x}: byte st={sb[0]:02x} {db.hex(' ')} | wort st={sw[0]:02x} {dw.hex(' ')}")

#!/usr/bin/env python3
"""cs42l71_wrtest.py – Schreibtest: Register der iOS-Hochfahrsequenz lesen, eines ändern und
zurückschreiben (root, Maggie im Reset)."""
import sys
sys.path.insert(0, "/tmp")
from cs42l71_v2 import rd, wr, update

regs = [0x200003, 0x200004, 0x300000, 0x300002, 0x10001, 0x10007, 0x1000a, 0x3000c]
print("vorher:", " ".join(f"{a:#x}={rd(a):#04x}" for a in regs))
a = 0x200003                       # iOS: maskWrite(0x200003, 0x7f, 0x40)
old = rd(a)
wr(a, old ^ 0x01, verbose=True)
print(f"{a:#x}: {old:#04x} -> geschrieben {old ^ 1:#04x}, gelesen {rd(a):#04x}")
wr(a, old)
print(f"{a:#x}: zurückgesetzt, gelesen {rd(a):#04x}")

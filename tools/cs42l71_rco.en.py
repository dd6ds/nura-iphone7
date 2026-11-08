#!/usr/bin/env python3
"""cs42l71_rco.en.py – test RCO start with an edge: set 0x10001 bit 6, wait, clear it, poll 0x3000c
(root, Maggie im Reset)."""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71_v2 import rd, update, init

init()                              # basic SPIv2 init like iOS (_initializeCodecRegisters)
update(0x10001, 0x40, 0x40)
time.sleep(0.1)
update(0x10001, 0x40, 0x00)
for i in range(100):
    s = rd(0x3000c)
    if s & 0x08:
        print(f"RCO running after {i * 10} ms (0x3000c = {s:#04x})"); break
    time.sleep(0.01)
else:
    print(f"RCO did NOT start (0x3000c = {s:#04x})")
for p in (1, 3):
    print(f"Page {p}:", " ".join(f"{rd((p << 16) + r):02x}" for r in range(0x20)))

#!/usr/bin/env python3
"""cs42l71_powerup.en.py – CS42L71 power-up sequence like iOS AppleCS42L71Audio (around 0x…6bc5b68)
(root, Maggie in reset). Addresses = page<<16 | register, maskWrite(addr, mask, value)."""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71_v2 import rd, update

SEQ = [  # from the disassembly, same order as iOS
    (0x200003, 0x7f, 0x40), (0x200004, 0x7f, 0x40),
    (0x300000, 0x3f, 0x3f), (0x300002, 0x3f, 0x3f),
    (0x10007, 0x01, 0x01), (0x10001, 0x0e, 0x0e),
    (0x1000a, 0x04, 0x04),
    (0x10001, 0x40, 0x00),           # then wait for the RCO to start
]
for a, m, v in SEQ:
    update(a, m, v)
for i in range(100):                 # iOS: 100 x 10 ms, bit 3 of 0x3000c
    s = rd(0x3000c)
    if s & 0x08:
        print(f"RCO running after {i * 10} ms (0x3000c = {s:#04x})")
        break
    time.sleep(0.01)
else:
    print(f"RCO did NOT start (0x3000c = {s:#04x})")

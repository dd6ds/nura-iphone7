#!/usr/bin/env python3
"""cs42l71_recover.en.py – get the CS42L71 SPIv2 bridge out of the "not ready" state (root, Maggie in reset).
Tries several control values [A1, x] and then checks whether 0x000000 is readable again (chip ID 0x42)."""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71 import xfer
from cs42l71_v2 import read_poll

def ok():
    st, d = read_poll(0x0, 8)
    return st, (d[0] if d is not None else None)

print("start:", ok())
for c in (0x00, 0x40, 0x10, 0x50, 0x20, 0x80, 0x01, 0x04, 0x08, 0x02):
    xfer([0xA1, c]); time.sleep(0.05)
    st = xfer([0x90, 0x00])[1]
    r = ok()
    print(f"[A1,{c:#04x}] -> status {st:#04x}, read 0x0: {r}")
    if r[1] == 0x42:
        print("readable again"); break

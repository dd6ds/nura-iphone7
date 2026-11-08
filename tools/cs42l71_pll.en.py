#!/usr/bin/env python3
"""cs42l71_pll.en.py – switch on the SPIv2 bridge PLL like iOS AppleCSSPIv2Audio::_enableControlPLL
(0x…5f735a8), then check the codec RCO start (root, Maggie in reset).
  read control register: [91 00 00] (value in the 3rd byte); write: [A1, value]
  PLL on: [A1, current | 0x20], then poll status [90 00] until bit 3 (PLL locked), max. 51 ms."""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71 import xfer
from cs42l71_v2 import rd, update

def ctrl_rd():
    return xfer([0x91, 0x00, 0x00])[2]          # iOS: command 0x91 = 3 bytes, value in the 3rd

def status():
    return xfer([0x90, 0x00])[1]

xfer([0xA1, 0x01]); time.sleep(0.01)          # wake the bridge reliably (see cs42l71_recover.en.py)
c = ctrl_rd()
print(f"control register before {c:#04x}, status {status():#04x}")
if c & 0x10:
    sys.exit("control register has bit 4 set – implausible read, aborting (bridge would hang)")
xfer([0xA1, c | 0x20])
for i in range(51):
    s = status()
    if s & 0x08:
        print(f"PLL locked after {i} ms (status {s:#04x}, control {ctrl_rd():#04x})"); break
    time.sleep(0.001)
else:
    print(f"PLL NOT locked (status {s:#04x}, control {ctrl_rd():#04x})")

try:
    print("Chip-ID:", hex(rd(0x0)))
    update(0x1000a, 0x04, 0x04)
    update(0x10001, 0x40, 0x40); time.sleep(0.05)
    update(0x10001, 0x40, 0x00)
    for i in range(100):
        r = rd(0x3000c)
        if r & 0x08:
            print(f"RCO running after {i * 10} ms (0x3000c = {r:#04x})"); break
        time.sleep(0.01)
    else:
        print(f"RCO did NOT start (0x3000c = {r:#04x})")
    print("Page 3:", " ".join(f"{rd(0x30000 + r):02x}" for r in range(16)))
except IOError as e:
    print("read error:", e)

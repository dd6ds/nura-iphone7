#!/usr/bin/env python3
"""cs42l71_v2probe.en.py – probe the CS42L71 SPIv2 control port (root, Maggie in reset!).
From iOS AppleCSSPIv2Audio: 2-byte commands [cmd, value]; 0x80/0x81 = write address/count,
0xC6/0xC4 = read status (0x50 = ready), 0xA1 = write control register."""
import sys
sys.path.insert(0, "/tmp")
from cs42l71 import xfer

for cmd in list(range(0xc0, 0xd0)) + list(range(0xe0, 0xe8)) + list(range(0x40, 0x48)):
    rx = xfer([cmd, 0x00, cmd, 0x00, cmd, 0x00])
    print(f"cmd {cmd:#04x}: " + rx.hex(" "))

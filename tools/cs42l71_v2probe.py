#!/usr/bin/env python3
"""cs42l71_v2probe.py – SPIv2-Steuerport des CS42L71 abtasten (root, Maggie im Reset!).
Aus iOS AppleCSSPIv2Audio: 2-Byte-Kommandos [cmd, wert]; 0x80/0x81 = Adresse/Anzahl schreiben,
0xC6/0xC4 = Status lesen (0x50 = bereit), 0xA1 = Steuerregister schreiben."""
import sys
sys.path.insert(0, "/tmp")
from cs42l71 import xfer

for cmd in list(range(0xc0, 0xd0)) + list(range(0xe0, 0xe8)) + list(range(0x40, 0x48)):
    rx = xfer([cmd, 0x00, cmd, 0x00, cmd, 0x00])
    print(f"cmd {cmd:#04x}: " + rx.hex(" "))

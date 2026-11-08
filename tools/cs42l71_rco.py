#!/usr/bin/env python3
"""cs42l71_rco.py – RCO-Hochlauf mit Flanke testen: 0x10001 Bit 6 setzen, warten, löschen, 0x3000c pollen
(root, Maggie im Reset)."""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71_v2 import rd, update, init

init()                              # SPIv2-Grundinitialisierung wie iOS (_initializeCodecRegisters)
update(0x10001, 0x40, 0x40)
time.sleep(0.1)
update(0x10001, 0x40, 0x00)
for i in range(100):
    s = rd(0x3000c)
    if s & 0x08:
        print(f"RCO läuft nach {i * 10} ms (0x3000c = {s:#04x})"); break
    time.sleep(0.01)
else:
    print(f"RCO NICHT hochgelaufen (0x3000c = {s:#04x})")
for p in (1, 3):
    print(f"Seite {p}:", " ".join(f"{rd((p << 16) + r):02x}" for r in range(0x20)))

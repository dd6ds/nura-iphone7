#!/usr/bin/env python3
"""cs42l71_powerup.py – Hochfahrsequenz des CS42L71 wie iOS AppleCS42L71Audio (um 0x…6bc5b68)
(root, Maggie im Reset). Adressen = Seite<<16 | Register, maskWrite(addr, maske, wert).
  cs42l71_powerup.py [clk]   clk = Wert für 0x10000 Bit 1 (iOS-Hilfsfunktion c3f04, abhängig von der
                             Abtastrate; Standard 0)"""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71_v2 import rd, update

CLK = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0
SEQ = [  # aus der Disassemblierung, Reihenfolge wie in iOS
    (0x200003, 0x7f, 0x40), (0x200004, 0x7f, 0x40),
    (0x300000, 0x3f, 0x3f), (0x300002, 0x3f, 0x3f),
    (0x10007, 0x01, 0x01), (0x10001, 0x0e, 0x0e),
    (0x1000a, 0x04, 0x04),
    (0x10000, 0x02, CLK << 1),       # c3f04
    (0x1000a, 0x04, 0x04),
    (0x10001, 0x40, 0x00),           # danach RCO-Hochlauf abwarten
]
for a, m, v in SEQ:
    update(a, m, v)
for i in range(100):                 # iOS: 100 x 10 ms, Bit 3 von 0x3000c
    s = rd(0x3000c)
    if s & 0x08:
        print(f"RCO läuft nach {i * 10} ms (0x3000c = {s:#04x})")
        break
    time.sleep(0.01)
else:
    print(f"RCO NICHT hochgelaufen (0x3000c = {s:#04x})")
print("Seite 3:", " ".join(f"{rd(0x30000 + r):02x}" for r in range(16)))

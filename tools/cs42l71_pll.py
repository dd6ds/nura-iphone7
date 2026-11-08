#!/usr/bin/env python3
"""cs42l71_pll.py – PLL der SPIv2-Brücke einschalten wie iOS AppleCSSPIv2Audio::_enableControlPLL
(0x…5f735a8), danach RCO-Hochlauf des Codecs prüfen (root, Maggie im Reset).
  Steuerregister lesen: [91 00 00] (Wert im 3. Byte); schreiben: [A1, wert]
  PLL an: [A1, aktuell | 0x20], dann Status [90 00] pollen bis Bit 3 (PLL eingerastet), max. 51 ms."""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71 import xfer
from cs42l71_v2 import rd, update

def ctrl_rd():
    return xfer([0x91, 0x00, 0x00])[2]          # iOS: Kommando 0x91 = 3 Bytes, Wert im 3.

def status():
    return xfer([0x90, 0x00])[1]

xfer([0xA1, 0x01]); time.sleep(0.01)          # Brücke sicher wecken (s. cs42l71_recover.py)
c = ctrl_rd()
print(f"Steuerregister vorher {c:#04x}, Status {status():#04x}")
if c & 0x10:
    sys.exit("Steuerregister hat Bit 4 gesetzt – Lesen unplausibel, Abbruch (Brücke würde hängen)")
xfer([0xA1, c | 0x20])
for i in range(51):
    s = status()
    if s & 0x08:
        print(f"PLL eingerastet nach {i} ms (Status {s:#04x}, Steuer {ctrl_rd():#04x})"); break
    time.sleep(0.001)
else:
    print(f"PLL NICHT eingerastet (Status {s:#04x}, Steuer {ctrl_rd():#04x})")

try:
    print("Chip-ID:", hex(rd(0x0)))
    update(0x1000a, 0x04, 0x04)
    update(0x10001, 0x40, 0x40); time.sleep(0.05)
    update(0x10001, 0x40, 0x00)
    for i in range(100):
        r = rd(0x3000c)
        if r & 0x08:
            print(f"RCO läuft nach {i * 10} ms (0x3000c = {r:#04x})"); break
        time.sleep(0.01)
    else:
        print(f"RCO NICHT hochgelaufen (0x3000c = {r:#04x})")
    print("Seite 3:", " ".join(f"{rd(0x30000 + r):02x}" for r in range(16)))
except IOError as e:
    print("Lesefehler:", e)

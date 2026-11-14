#!/usr/bin/env python3
"""cs42l71_kernbereit.py – Mikrofon-/ADC-Block des CS42L71 einschalten (root auf dem iPhone, Maggie im Reset).
iOS AppleCS42L71Audio (0x…6bc6840, Mikrofonpfad): 0x10001 Bit 0 = 0 (Block einschalten), dann bis 100×10 ms
warten, bis 0x310004 Bit 0 = 1 meldet, danach 0x310005 Bit 0 = 1 und 0x310007 Bit 0 = 0.
Gedacht als Takt-Nachweis; der Block braucht aber vermutlich mehr als nur den Takt (Mikrofon-Versorgung).
  cs42l71_kernbereit.py [--takt] [--zurueck]
  --takt: vorher das Ende von enableAudioHW (Codec auf MCLK statt RCO), --zurueck: danach wieder abschalten"""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71 import xfer
from cs42l71_v2 import rd, wr, update

xfer([0xA1, 0x01]); time.sleep(0.01)                    # Brücke wecken
print("Chip-ID:", hex(rd(0x0)))
print("vorher: 0x10000 =", hex(rd(0x10000)), " 0x10001 =", hex(rd(0x10001)), " 0x20000[1:0] =", hex(rd(0x20000) & 3),
      " 0x310004 =", hex(rd(0x310004)), " 0x3000c =", hex(rd(0x3000c)))
if "--takt" in sys.argv:
    # Ende von enableAudioHW (kalter Zweig): 0x10000 Bit 0 = 0, Taktwahl 0x6bc3f04(0): 0x10000 Bit 1 = 0
    # (MCLK statt RCO), 0x6bc4988: 0x10 = 0x99, 0x120025 = 0x130025 = 0x66, 0x10 = 0
    update(0x10000, 0x01, 0x00)
    update(0x10000, 0x02, 0x00)
    for a, v in ((0x10, 0x99), (0x120025, 0x66), (0x130025, 0x66), (0x10, 0x00)):
        print(f"{a:#08x} = {v:#04x}:", wr(a, v))
update(0x10001, 0x01, 0x00)
for i in range(100):
    r = rd(0x310004)
    if r & 1:
        print(f"BEREIT nach {i * 10} ms (0x310004 = {r:#04x})"); break
    time.sleep(0.01)
else:
    print(f"NICHT bereit nach 1 s (0x310004 = {r:#04x})")
print("0x310004..7:", " ".join(f"{rd(0x310004 + k):02x}" for k in range(4)), " 0x3000c =", hex(rd(0x3000c)))
if "--zurueck" in sys.argv:
    update(0x10001, 0x01, 0x01)
    if "--takt" in sys.argv:
        update(0x10000, 0x03, 0x03)

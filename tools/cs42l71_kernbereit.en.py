#!/usr/bin/env python3
"""cs42l71_kernbereit.en.py – power up the microphone/ADC block of the CS42L71 (root on the iPhone, Maggie held in reset).
iOS AppleCS42L71Audio (0x…6bc6840, microphone path): 0x10001 bit 0 = 0 (power the block up), then wait up to 100×10 ms
until 0x310004 bit 0 = 1, then 0x310005 bit 0 = 1 and 0x310007 bit 0 = 0.
Meant as proof of a running clock; the block probably needs more than the clock (microphone supply).
  cs42l71_kernbereit.en.py [--takt] [--zurueck]
  --takt: first run the end of enableAudioHW (codec on MCLK instead of RCO), --zurueck: switch everything off again afterwards"""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71 import xfer
from cs42l71_v2 import rd, wr, update

xfer([0xA1, 0x01]); time.sleep(0.01)                    # wake the bridge
print("Chip-ID:", hex(rd(0x0)))
print("before: 0x10000 =", hex(rd(0x10000)), " 0x10001 =", hex(rd(0x10001)), " 0x20000[1:0] =", hex(rd(0x20000) & 3),
      " 0x310004 =", hex(rd(0x310004)), " 0x3000c =", hex(rd(0x3000c)))
if "--takt" in sys.argv:
    # end of enableAudioHW (cold branch): 0x10000 bit 0 = 0, clock select 0x6bc3f04(0): 0x10000 bit 1 = 0
    # (MCLK instead of RCO), 0x6bc4988: 0x10 = 0x99, 0x120025 = 0x130025 = 0x66, 0x10 = 0
    update(0x10000, 0x01, 0x00)
    update(0x10000, 0x02, 0x00)
    for a, v in ((0x10, 0x99), (0x120025, 0x66), (0x130025, 0x66), (0x10, 0x00)):
        print(f"{a:#08x} = {v:#04x}:", wr(a, v))
update(0x10001, 0x01, 0x00)
for i in range(100):
    r = rd(0x310004)
    if r & 1:
        print(f"READY after {i * 10} ms (0x310004 = {r:#04x})"); break
    time.sleep(0.01)
else:
    print(f"NOT ready after 1 s (0x310004 = {r:#04x})")
print("0x310004..7:", " ".join(f"{rd(0x310004 + k):02x}" for k in range(4)), " 0x3000c =", hex(rd(0x3000c)))
if "--zurueck" in sys.argv:
    update(0x10001, 0x01, 0x01)
    if "--takt" in sys.argv:
        update(0x10000, 0x03, 0x03)

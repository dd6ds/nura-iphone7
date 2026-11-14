#!/usr/bin/env python3
"""cs42l71_kaltstart.en.py – cold start of the CS42L71 like iOS AppleCS42L71Audio::enableAudioHW
(0x…6bc5724, branch "not waking from RCO sleep"), root on the iPhone, Maggie held in reset.
iOS: MCLK on first (setInputMCLKEnabled via the clock provider, 12 MHz required), then
  0x50000 = 0xa5, 10 ms, 0x50000 = 0, 1 ms, 0x5 bit 1 = 0,
  _initializeCodecRegisters ([A1, ctrl|0x50], poll status until (st & 0x90) == 0x90) – presumably needs the clock,
  0x5 bit 1 = 1, (0x10000 bit 0 = 0 …).
The RCO (0x3000c bit 3) is only the idle clock in disableAudioHW – no sign of a missing MCLK.
  cs42l71_kaltstart.en.py [ctrl]   (ctrl = shadow value of the control register, default 0x01)"""
import sys, time
sys.path.insert(0, "/tmp")
from cs42l71 import xfer
from cs42l71_v2 import rd, wr, update, init

ctrl = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x01
xfer([0xA1, 0x01]); time.sleep(0.01)                    # wake the bridge
print("Chip-ID:", hex(rd(0x0)), " 0x5 =", hex(rd(0x5)))
print("0x50000 = 0xa5:", wr(0x50000, 0xa5)); time.sleep(0.01)
print("0x50000 = 0x00:", wr(0x50000, 0x00)); time.sleep(0.001)
update(0x5, 0x02, 0x00)
ok = init(ctrl=ctrl)
xfer([0xA1, 0x01]); time.sleep(0.01)                    # if the bridge hangs: bring it back
try:
    update(0x5, 0x02, 0x02)
    print("Status after cold start:", hex(xfer([0x90, 0x00])[1]),
          " page 2:", " ".join(f"{rd(0x20000 + r):02x}" for r in range(8)))
except IOError as e:
    print("Read error after cold start:", e)
print("RESULT:", "codec init OK" if ok else "codec init NOT ready")   # no proof of clock (also passes without MCLK)

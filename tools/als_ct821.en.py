#!/usr/bin/env python3
"""als_ct821.en.py [seconds] [gain 0-3] – read the ambient light sensor CT821 (I2C2 0x29) (root).
TSL257x-like: command bit 0x80; 0x00 ENABLE (PON=1, AEN=2), 0x01 ATIME, 0x0F CONTROL (gain),
0x12 ID, 0x13 STATUS (AVALID=1), 0x14/0x15 CH0 (visible+IR), 0x16/0x17 CH1 (IR).
Without a Linux driver (bus via /dev/mem, tools/i2c_poll.en.py); switches off again at the end."""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i2c_poll import Bus

A = 0x29
dauer = float(sys.argv[1]) if len(sys.argv) > 1 else 10
gain = int(sys.argv[2]) if len(sys.argv) > 2 else 1
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "pmgr_ps.en.py"), "0x801b8", "on"],
               stdout=subprocess.DEVNULL, check=True)
b = Bus(2)
rd = lambda r: b.read(A, bytes([0x80 | r]), 1)[0]
wr = lambda r, v: b.write(A, bytes([0x80 | r, v]))
print(f"ID {rd(0x12):#04x}, ENABLE {rd(0x00):#04x}, ATIME {rd(0x01):#04x}, CONTROL {rd(0x0f):#04x}")
print(f"PERS/CFG 0x0c {rd(0x0c):#04x}, STATUS {rd(0x13):#04x}")
# Order as in AppleCT821 (iOS): 0x0C |= 0x40 (first without, then with low nibble), ATIME, gain,
# ENABLE |= 0x13 (PON | AEN | AIEN), ATIME, 0x0C
cfg = rd(0x0c) | 0x40
wr(0x0c, cfg & 0xf0)
wr(0x0c, cfg)
wr(0x01, 0xdb)                    # 37 cycles of 2.73 ms ≈ 101 ms
wr(0x0f, gain & 3)
wr(0x00, 0x13)
wr(0x01, 0xdb)
wr(0x0c, cfg)
print(f"after ENABLE {rd(0x00):#04x}, ATIME {rd(0x01):#04x}, CONTROL {rd(0x0f):#04x}")
try:
    t0 = time.time()
    while time.time() - t0 < dauer:
        time.sleep(0.25)
        st = rd(0x13)
        c0 = rd(0x14) | rd(0x15) << 8
        c1 = rd(0x16) | rd(0x17) << 8
        print(f"{time.time() - t0:5.1f}s STATUS {st:#04x}  CH0 {c0:6d}  CH1(IR) {c1:6d}", flush=True)
finally:
    wr(0x00, 0x00)
    print("ALS off")

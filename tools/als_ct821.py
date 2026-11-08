#!/usr/bin/env python3
"""als_ct821.py [sekunden] [gain 0-7] – Umgebungslichtsensor CT821 (I2C2 0x29) auslesen (root).
TSL257x-artig: Befehlsbit 0x80; 0x00 ENABLE (PON=1, AEN=2), 0x01 ATIME, 0x0F CONTROL (Gain),
0x12 ID, 0x13 STATUS (AVALID=1), 0x14/0x15 CH0 (sichtbar+IR), 0x16/0x17 CH1 (IR).
Ohne Linux-Treiber (Bus per /dev/mem, tools/i2c_poll.py); schaltet am Ende wieder aus."""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i2c_poll import Bus

A = 0x29
dauer = float(sys.argv[1]) if len(sys.argv) > 1 else 10
gain = int(sys.argv[2]) if len(sys.argv) > 2 else 7
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "pmgr_ps.py"), "0x801b8", "on"],
               stdout=subprocess.DEVNULL, check=True)
b = Bus(2)
rd = lambda r: b.read(A, bytes([0x80 | r]), 1)[0]
wr = lambda r, v: b.write(A, bytes([0x80 | r, v]))
print(f"ID {rd(0x12):#04x}, ENABLE {rd(0x00):#04x}, ATIME {rd(0x01):#04x}, CONTROL {rd(0x0f):#04x}")
print(f"PERS/CFG 0x0c {rd(0x0c):#04x}, STATUS {rd(0x13):#04x}")
# Reihenfolge wie AppleCT821 (iOS): 0x0C |= 0x40 (erst ohne, dann mit Low-Nibble), ATIME, Gain,
# ENABLE |= 0x13 (PON | AEN | AIEN), ATIME, 0x0C
# Gemessen: AVALID kommt nach (256-ATIME)*2,73 ms; Gain-Feld 3 Bit (iOS nutzt 6/7), 0x0C Bit 6 = an.
wr(0x00, 0x00)
wr(0x0c, 0x40)
wr(0x01, 0x80)                    # 128 Zyklen à 2,73 ms ≈ 350 ms
wr(0x0f, gain & 7)
wr(0x00, 0x01)                    # PON
time.sleep(0.003)
wr(0x00, 0x03)                    # PON | AEN
print(f"nachher ENABLE {rd(0x00):#04x}, ATIME {rd(0x01):#04x}, CONTROL {rd(0x0f):#04x}")
try:
    t0 = time.time()
    while time.time() - t0 < dauer:
        time.sleep(0.5)
        st = rd(0x13)
        c0 = rd(0x14) | rd(0x15) << 8
        c1 = rd(0x16) | rd(0x17) << 8
        print(f"{time.time() - t0:5.1f}s STATUS {st:#04x}  CH0 {c0:6d}  CH1(IR) {c1:6d}", flush=True)
finally:
    wr(0x00, 0x00)
    print("ALS aus")

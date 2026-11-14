#!/usr/bin/env python3
"""cs35l26_an.py [SEK] – EXPERIMENT: Lautsprecher-Verstärker CS35L26 für einen Testton einschalten (root, iPhone 7).
Voraussetzung wie tools/cs35l26.py (PMGR i2c2 an, Reset GPIO 140 = 1) und ein laufender TDM-Strom auf pin2
(tools/mca_v4.py 1 init/start, tools/sio_ctl.py ton). Registerkarte CS35L35 (Linux sound/soc/codecs/cs35l35.h).
Einstellungen (Umgebung): QUELLE=1 (CLK_CTL1 Bit 1:0: 0 = MCLK, 1 = SCLK), CTL2=0x13 (12 MHz / 48 kHz),
SLOT=0 (AUDIN_RXLOC 0x52), TIEFE=2 (AUDIN_DEPTH 0x5a: 16 Bit), FMT1/FMT2/FMT3 = SP_FMT_CTL1-3 (0x0d-0x0f,
nur wenn gesetzt).
Ablauf (Linux-Treiber): MCLK_DIS aus, Entladefilter aus, PDN_ALL = 0, PDN_BST = 0, PDN_AMP = 0, Mute aus;
Status (INT_STATUS 0x74-0x77) lesen, SEK Sekunden halten, dann stumm und alles wieder aus."""
import os, sys, time
sys.path.insert(0, "/tmp")
from i2c_poll import Bus

ADR = 0x40
b = Bus(2)
def nochmal(f):
    # Beim Einschalten bricht vereinzelt ein I2C-Zugriff ab (Zeitüberschreitung) – bis zu 5 Versuche
    for i in range(5):
        try: return f()
        except OSError:
            if i == 4: raise
            time.sleep(0.02)
rd = lambda r: nochmal(lambda: b.read(ADR, bytes([r]), 1)[0])
def wr(r, v): nochmal(lambda: b.write(ADR, bytes([r, v & 0xff])))
def upd(r, mask, val): wr(r, (rd(r) & ~mask) | (val & mask))
def env(n, d): return int(os.environ.get(n, d), 0)
def status(): return [rd(0x74 + i) for i in range(4)]
def zeige(t):
    s = status()
    print(f"{t}: INT {' '.join(f'{x:02x}' for x in s)}  PWR {rd(6):02x} {rd(7):02x} {rd(8):02x}"
          f"  CLK {rd(0xa):02x} {rd(0xb):02x} {rd(0xc):02x}  PLL {rd(0x78):02x}")

def aus():
    upd(0x18, 0x20, 0x20)
    upd(0x07, 0x07, 0x07)
    upd(0x06, 0x03, 0x03)
    time.sleep(0.05)
    zeige("aus")

if len(sys.argv) > 1 and sys.argv[1] == "aus":
    aus(); sys.exit()
sek = float(sys.argv[1]) if len(sys.argv) > 1 else 5
zeige("vorher")
upd(0x0a, 0x03, env("QUELLE", "1"))
wr(0x0b, env("CTL2", "0x13"))
for n, r in (("FMT1", 0x0d), ("FMT2", 0x0e), ("FMT3", 0x0f)):
    if n in os.environ: wr(r, env(n, "0"))
upd(0x52, 0x0f, env("SLOT", "0"))
upd(0x5a, 0x03, env("TIEFE", "2"))
upd(0x0a, 0x04, 0)                 # MCLK_DIS aus
upd(0x06, 0x02, 0)                 # Entladefilter aus
upd(0x06, 0x01, 0)                 # PDN_ALL aus
upd(0x07, 0x06, 0)                 # Boost an
time.sleep(0.005)
upd(0x07, 0x01, 0)                 # Endstufe an
upd(0x14, 0x20, 0)                 # Eingang nicht stumm
upd(0x18, 0x20, 0)                 # PROTECT_CTL: Mute aus
time.sleep(0.05)
zeige("an")
t0 = time.time()
while time.time() - t0 < sek:
    time.sleep(1); zeige(f"{time.time() - t0:4.1f} s")
aus()

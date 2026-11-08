#!/usr/bin/env python3
"""
pmu_read.py – Stromversorgung des Touch-Controllers NUR LESEND prüfen.

Laut ADT (multi-touch power-sequence):
  1. function-power_ana = dpLE(0x302)  -> Display-PMU "chestnut", i2c0 @ 0x27
  2. function-power_ldo = pmuL(0x21e)  -> Haupt-PMU Dialog D2333, i2c1 @ 0x74
  3. function-clock_enable = TCLK(...)
Beide PMUs: 16-Bit-Registeradressen (wie m1n1 hw/pmu.py für d2333).

Ablauf: I2C-Blöcke per PMGR einschalten (sonst Bus-Hänger!), dann Register lesen.
Es wird NICHTS in PMU-Register geschrieben.
Aufruf: M1N1DEVICE=/dev/ttyACM0 .venv/bin/python research/tools/pmu_read.py
"""
import os, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "m1n1", "proxyclient"))
OUT = os.path.join(ROOT, "research", "live")
os.makedirs(OUT, exist_ok=True)
from m1n1.proxy import UartInterface, M1N1Proxy
from m1n1.proxyutils import ProxyUtils, bootstrap_port
from m1n1.hw.i2c import I2C

log = open(os.path.join(OUT, "pmu-read.log"), "w")
def say(*a):
    s = " ".join(str(x) for x in a); print(s); log.write(s + "\n"); log.flush()

iface = UartInterface(); p = M1N1Proxy(iface, debug=False); bootstrap_port(iface, p)
u = ProxyUtils(p)

TARGETS = [
    # (Name, I2C-Bus, I2C-Adresse, Register von, Anzahl)
    ("Haupt-PMU D2333 (pmuL 0x21e)", "/arm-io/i2c1", 0x74, 0x218, 16),
    ("Display-PMU chestnut (dpLE 0x302)", "/arm-io/i2c0", 0x27, 0x2f8, 24),
]

for name, bus, addr, start, n in TARGETS:
    say(f"\n== {name}: {bus} Adresse 0x{addr:02x}")
    try:
        r = p.pmgr_adt_power_enable(bus)
        say(f"  pmgr_adt_power_enable({bus}) -> {r}")
        i2c = I2C(u, bus)
        vals = []
        for reg in range(start, start + n):
            try:
                v = i2c.read_reg(addr, reg, 1, regaddrlen=2)[0]
                vals.append((reg, v))
            except Exception as e:
                vals.append((reg, None))
                say(f"  0x{reg:04x}: Lesefehler {e}")
                break
        for reg, v in vals:
            if v is not None:
                mark = "  <== Touch" if reg in (0x21e, 0x302) else ""
                say(f"  0x{reg:04x} = 0x{v:02x}  ({v:08b}){mark}")
    except Exception:
        say("  FEHLER:\n" + traceback.format_exc())

say("\nFertig (nur gelesen). Log:", os.path.join(OUT, "pmu-read.log"))

#!/usr/bin/env python3
"""
live_probe.py – Bestandsaufnahme am laufenden iPhone über den m1n1-USB-Proxy.

Liest (nur lesend, bis auf das Einschalten der spi2-Stromdomäne):
  1. den Live-ADT (inkl. von iBoot eingetragener Kalibrierdaten)
  2. alle Properties des multi-touch-Knotens als Rohdaten
  3. Registerfenster von spi2 (Touch-SPI), vor/nach Power-Enable
  4. GPIO-Pins von Touch-Reset / -IRQ / -CS

Aufruf (iPhone muss m1n1 im Proxy-Modus laufen lassen):
  M1N1DEVICE=/dev/ttyACM0 .venv/bin/python research/tools/live_probe.py
Ergebnis: research/live/
"""
import os, sys, struct, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "m1n1", "proxyclient"))
OUT = os.path.join(ROOT, "research", "live")
os.makedirs(OUT, exist_ok=True)

from m1n1.proxy import UartInterface, M1N1Proxy
from m1n1.proxyutils import ProxyUtils, bootstrap_port
from m1n1.adt import load_adt

log = open(os.path.join(OUT, "probe.log"), "w")
def say(*a):
    s = " ".join(str(x) for x in a)
    print(s); log.write(s + "\n"); log.flush()

iface = UartInterface()
p = M1N1Proxy(iface, debug=False)
bootstrap_port(iface, p)
u = ProxyUtils(p)
say(f"m1n1 base 0x{u.base:x}, Bootargs devtree 0x{u.ba.devtree:x} size {u.ba.devtree_size}")

SKIP_LIVE_ADT = os.environ.get("SKIP_ADT") == "1"
# 1) Live-ADT sichern
raw = u.get_adt()
open(os.path.join(OUT, "live.adt"), "wb").write(raw)
adt = load_adt(raw)
open(os.path.join(OUT, "live-adt.txt"), "w").write(str(adt))
say("Live-ADT gespeichert:", len(raw), "Bytes")

# 2) multi-touch-Knoten: alle Properties sichern (Kalibrierung = bytes, wenn iBoot sie eingetragen hat)
try:
    mt = adt["/arm-io/spi2/multi-touch"]
    mtdir = os.path.join(OUT, "multi-touch")
    os.makedirs(mtdir, exist_ok=True)
    for k, v in mt._properties.items():
        if isinstance(v, (bytes, bytearray)):
            data, kind = bytes(v), "bytes"
        else:
            data, kind = repr(v).encode(), type(v).__name__
        open(os.path.join(mtdir, k.replace("/", "_").replace(",", "_")), "wb").write(data)
        say(f"  prop {k:32s} {kind:14s} {len(data):6d} B  {data[:16].hex() if kind=='bytes' else data[:40].decode(errors='replace')}")
except Exception:
    say("multi-touch-Knoten Fehler:\n" + traceback.format_exc())

# 3) spi2-Register
def try_read_window(base, n=0x40):
    vals = []
    for off in range(0, n, 4):
        try:
            vals.append((off, p.read32(base + off)))
        except Exception as e:
            vals.append((off, f"ERR {e}"))
            break
    return vals

try:
    spi2 = adt["/arm-io/spi2"]
    base, size = spi2.get_reg(0)
    say(f"spi2: reg 0x{base:x} size 0x{size:x}")
    # NICHT vor dem Power-Enable lesen: Zugriff auf eine abgeschaltete
    # Domäne hängt den Bus auf und setzt das iPhone zurück (so passiert 2026-11-06).
    try:
        r = p.pmgr_adt_power_enable("/arm-io/spi2")
        say("pmgr_adt_power_enable(/arm-io/spi2) ->", r)
    except Exception as e:
        say("Power-Enable fehlgeschlagen:", e)
    say("spi2 Register NACH Power-Enable:")
    for off, v in try_read_window(base):
        say(f"  +0x{off:02x} = {v if isinstance(v,str) else hex(v)}")
except Exception:
    say("spi2-Probe Fehler:\n" + traceback.format_exc())

# 4) GPIO-Pins (Reset 0xa1, CS 0x51, IRQ 166) am AP-GPIO-Controller
try:
    gpio = adt["/arm-io/gpio"]
    gbase, _ = gpio.get_reg(0)
    say(f"gpio: reg 0x{gbase:x}")
    for name, pin in (("touch-reset", 0xa1), ("touch-cs/enable", 0x51), ("touch-irq", 166)):
        try:
            v = p.read32(gbase + pin * 4)
            say(f"  {name:16s} pin {pin:3d} (0x{pin:02x}) cfg = 0x{v:08x}")
        except Exception as e:
            say(f"  {name} Lesefehler: {e}")
except Exception:
    say("GPIO-Probe Fehler:\n" + traceback.format_exc())

say("Fertig. Ergebnisse in", OUT)

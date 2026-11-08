#!/usr/bin/env python3
"""
safe_shell.py – interaktive m1n1-Proxy-Shell für iPhone (A9/A10).

Die Standard-Shell (proxyclient/tools/shell.py -> m1n1.setup) schreibt beim Start
per I2C in den PMU (reset_panic_counter) – auf einem nicht eingeschalteten
I2C-Block hängt das den Bus auf und das iPhone stürzt ab. Diese Shell lässt das weg.

Variablen: p (Proxy), u (ProxyUtils), adt (Live-ADT), on(path) = Power-Enable
Aufruf: M1N1DEVICE=/dev/ttyACM0 .venv/bin/python research/tools/safe_shell.py
"""
import os, sys, code
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "m1n1", "proxyclient"))
from m1n1.proxy import UartInterface, M1N1Proxy
from m1n1.proxyutils import ProxyUtils, bootstrap_port

iface = UartInterface(); p = M1N1Proxy(iface, debug=False); bootstrap_port(iface, p)
u = ProxyUtils(p)
adt = u.adt

def on(path):
    """Stromdomäne eines ADT-Geräts einschalten – IMMER vor Registerzugriffen!"""
    return p.pmgr_adt_power_enable(path)

print(f"m1n1 base 0x{u.base:x}. VOR Registerzugriffen: on('/arm-io/<gerät>') aufrufen!")
code.interact(local=dict(globals()), banner="safe_shell – Strg+D beendet")

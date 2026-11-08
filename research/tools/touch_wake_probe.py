#!/usr/bin/env python3
"""
touch_wake_probe.py – lebt der Touch-Controller?

Ablauf (über m1n1-Proxy, nur GPIO, kein SPI):
  1. IRQ-Leitung (GPIO 166, Pull-up) beobachten, Reset (GPIO 0xa1) ist low = Reset aktiv
  2. Reset freigeben (Ausgang high)
  3. 300 ms lang IRQ-Pegel abtasten -> geht er auf 0, meldet sich der HBPP-Bootloader
     (apple_z2 wartet genau auf diesen IRQ innerhalb 20 ms)
  4. Reset wieder aktivieren (Ausgang low), ursprünglicher Zustand

Aufruf: M1N1DEVICE=/dev/ttyACM0 .venv/bin/python research/tools/touch_wake_probe.py
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "m1n1", "proxyclient"))
from m1n1.proxy import UartInterface, M1N1Proxy
from m1n1.proxyutils import ProxyUtils, bootstrap_port

GPIO_BASE = 0x20F100000
PIN_RESET, PIN_CS, PIN_IRQ = 0xA1, 0x51, 166
DATA = 1 << 0
MODE_MASK = 0b111 << 1
MODE_OUT = 1 << 1

iface = UartInterface(); p = M1N1Proxy(iface, debug=False); bootstrap_port(iface, p); u = ProxyUtils(p)
reg = lambda pin: GPIO_BASE + pin * 4
rd = lambda pin: p.read32(reg(pin))

orig_reset = rd(PIN_RESET)
print(f"vorher: reset=0x{orig_reset:08x} cs=0x{rd(PIN_CS):08x} irq=0x{rd(PIN_IRQ):08x} (irq-Pegel {rd(PIN_IRQ)&1})")

# SICHERHEIT: IRQ hat einen Pull-up. Liest er schon VOR der Reset-Freigabe 0,
# zieht ein stromloser Controller die Leitung über seine Schutzdioden runter.
# Dann NICHT den Reset-Pin hochziehen (Rückspeisung -> iPhone stürzte am
# 2026-11-06 genau dabei ab). Erst Stromversorgung (PMU-LDO 0x21e) klären.
if (rd(PIN_IRQ) & 1) == 0 and os.environ.get("FORCE_WAKE") != "1":
    print("==> IRQ ist schon LOW, obwohl Reset aktiv ist -> Controller vermutlich OHNE Strom.")
    print("    Abbruch ohne Reset-Freigabe (FORCE_WAKE=1 erzwingt den Test – nicht empfohlen).")
    sys.exit(2)

# Reset freigeben
p.write32(reg(PIN_RESET), (orig_reset & ~MODE_MASK) | MODE_OUT | DATA)
t0 = time.time()
samples = []
while time.time() - t0 < 0.3:
    samples.append((time.time() - t0, rd(PIN_IRQ) & 1))
# Reset wieder aktiv
p.write32(reg(PIN_RESET), orig_reset)

lows = [t for t, v in samples if v == 0]
print(f"{len(samples)} Abtastungen, IRQ low in {len(lows)} davon")
if lows:
    print(f"==> IRQ ging auf LOW nach {lows[0]*1000:.1f} ms  -> Touch-Controller hat Strom und meldet sich (HBPP)")
else:
    print("==> IRQ blieb HIGH -> Controller vermutlich ohne Strom (PMU-LDO 0x21e / dpLE aus) oder anderer Pegel")
print(f"nachher: reset=0x{rd(PIN_RESET):08x} irq=0x{rd(PIN_IRQ):08x}")

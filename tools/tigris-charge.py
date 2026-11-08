#!/usr/bin/env python3
"""tigris-charge – hält das USB-Eingangslimit des Ladechips Tigris (SN2400, i2c-1 @0x75)
auf einem sinnvollen Wert. Ohne iOS-Treiber steht es auf 90 mA: zu wenig, der Akku entlädt
sich trotz Kabel. Registerbelegung aus Project Sandcastle (sn2400-charger.c, GPL-2.0).

Ablauf bei angestecktem USB: Limit auf START_MA, dann in Schritten bis MAX_MA erhöhen,
solange die USB-Spannung nicht mehr als MAX_DROOP mV einbricht (wie Sandcastles 'foldback').
Umgebung: TIGRIS_MAX_MA (Standard 900), TIGRIS_START_MA (500)."""
import ctypes, fcntl, os, sys, time
ADDR, BUS = 0x75, "/dev/i2c-1"
MAX_MA = int(os.environ.get("TIGRIS_MAX_MA", "900"))
START_MA = int(os.environ.get("TIGRIS_START_MA", "500"))
STEP_MA, MAX_DROOP, POLL_S = 50, 400, 5

class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]
class Data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]
def xfer(msgs):
    with open(BUS, "rb", buffering=0) as f:
        fcntl.ioctl(f, 0x0707, Data((Msg * len(msgs))(*msgs), len(msgs)))
def rd(reg):
    w = (ctypes.c_uint8 * 1)(reg); r = (ctypes.c_uint8 * 1)()
    xfer([Msg(ADDR, 0, 1, w), Msg(ADDR, 1, 1, r)]); return r[0]
def wr(reg, val):
    xfer([Msg(ADDR, 0, 2, (ctypes.c_uint8 * 2)(reg, val))])
def adc(ch):
    wr(0x11, (ch << 1) | 0x10)
    for _ in range(20):
        if not rd(0x11) & 0x10: break
        time.sleep(0.005)
    return rd(0x12)
vbus = lambda: 25 * adc(0)
def set_limit(ma):
    wr(0x10, rd(0x10) & ~0x08)                  # Laderegler nicht abschalten
    wr(0x09, max(0, min(2000, ma) - 90) // 10)
limit = lambda: 10 * rd(0x09) + 90

def log(s): print(s, flush=True)

def ramp():
    """Limit ab START_MA hochfahren, bis MAX_MA oder bis VBUS zu stark einbricht."""
    set_limit(90); time.sleep(0.5)
    noload = vbus()
    ma = START_MA
    set_limit(ma); time.sleep(0.5)
    while ma + STEP_MA <= MAX_MA:
        set_limit(ma + STEP_MA); time.sleep(0.5)
        if noload - vbus() > MAX_DROOP:
            set_limit(ma); break
        ma += STEP_MA
    log(f"USB angesteckt: VBUS ohne Last {noload} mV, Limit {limit()} mA, VBUS jetzt {vbus()} mV")

target = None
while True:
    try:
        st = rd(0x07)
        if st & 0x20:                            # VBUS vorhanden
            if target is None or limit() < START_MA:
                ramp(); target = limit()
        else:
            if target is not None:
                log("USB abgesteckt")
            target = None
    except OSError as e:
        log(f"I2C-Fehler: {e}")
    time.sleep(POLL_S)

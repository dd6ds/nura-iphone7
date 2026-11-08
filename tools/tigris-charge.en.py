#!/usr/bin/env python3
"""tigris-charge – keeps the USB input limit of the Tigris charger chip (SN2400, i2c-1 @0x75)
at a sensible value. Without the iOS driver it sits at 90 mA: too little, the battery drains
despite the cable. Register layout from Project Sandcastle (sn2400-charger.c, GPL-2.0).

Procedure with USB plugged in: limit to START_MA, then raise in steps up to MAX_MA
as long as the USB voltage does not drop by more than MAX_DROOP mV (like Sandcastle's 'foldback').
Environment: TIGRIS_MAX_MA (default 900), TIGRIS_START_MA (500)."""
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
    wr(0x10, rd(0x10) & ~0x08)                  # do not switch off the charge regulator
    wr(0x09, max(0, min(2000, ma) - 90) // 10)
limit = lambda: 10 * rd(0x09) + 90

def log(s): print(s, flush=True)

def ramp():
    """Ramp the limit up from START_MA until MAX_MA or until VBUS drops too much."""
    set_limit(90); time.sleep(0.5)
    noload = vbus()
    ma = START_MA
    set_limit(ma); time.sleep(0.5)
    while ma + STEP_MA <= MAX_MA:
        set_limit(ma + STEP_MA); time.sleep(0.5)
        if noload - vbus() > MAX_DROOP:
            set_limit(ma); break
        ma += STEP_MA
    log(f"USB plugged in: VBUS without load {noload} mV, limit {limit()} mA, VBUS now {vbus()} mV")

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
        log(f"I2C error: {e}")
    time.sleep(POLL_S)

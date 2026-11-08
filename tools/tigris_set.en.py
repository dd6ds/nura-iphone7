#!/usr/bin/env python3
"""Tigris: set the USB input limit and measure VBUS/IBUS/VBAT via the ADC (root).
  tigris_set.en.py [mA]   (default 500; 90..2000)"""
import ctypes, fcntl, sys, time
I2C_RDWR, RD = 0x0707, 1
class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]
class Data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]
def xfer(msgs):
    with open("/dev/i2c-1", "rb", buffering=0) as f:
        fcntl.ioctl(f, I2C_RDWR, Data((Msg * len(msgs))(*msgs), len(msgs)))
def rd(reg):
    w = (ctypes.c_uint8 * 1)(reg); r = (ctypes.c_uint8 * 1)()
    xfer([Msg(0x75, 0, 1, w), Msg(0x75, RD, 1, r)]); return r[0]
def wr(reg, val):
    b = (ctypes.c_uint8 * 2)(reg, val); xfer([Msg(0x75, 0, 2, b)])
def adc(ch):
    wr(0x11, (ch << 1) | 0x10)
    for _ in range(20):
        if not rd(0x11) & 0x10: break
        time.sleep(0.005)
    return rd(0x12)
def measure(tag):
    vbus, ibus, vbat = 25 * adc(0), 10 * adc(1), 2500 + 10 * adc(5)
    st = rd(0x07)
    print(f"{tag}: VBUS {vbus} mV, IBUS {ibus} mA, VBAT {vbat} mV, "
          f"Limit {10 * rd(0x09) + 90} mA, charging={st >> 7 & 1}", flush=True)
ma = int(sys.argv[1]) if len(sys.argv) > 1 else 500
ma = max(90, min(2000, ma))
measure("before ")
wr(0x09, (ma - 90) // 10)
for i in range(3):
    time.sleep(1); measure(f"t+{i + 1}s  ")

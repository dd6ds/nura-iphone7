#!/usr/bin/env python3
"""Tigris (SN2400, i2c-1 @0x75) auslesen – nur lesend, Registerbelegung aus Sandcastle sn2400-charger.c.
Der ADC wird NICHT angestoßen (das wäre ein Schreibzugriff)."""
import ctypes, fcntl
I2C_RDWR, RD = 0x0707, 1
class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]
class Data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]
def rd(reg, n=1):
    w = (ctypes.c_uint8 * 1)(reg); r = (ctypes.c_uint8 * n)()
    m = (Msg * 2)(Msg(0x75, 0, 1, w), Msg(0x75, RD, n, r))
    with open("/dev/i2c-1", "rb", buffering=0) as f:
        fcntl.ioctl(f, I2C_RDWR, Data(m, 2))
    return list(r)
regs = rd(0x00, 0x20)
print("Register 0x00-0x1f:", " ".join(f"{v:02x}" for v in regs))
st = regs[0x07]
print(f"STAT 0x07 = {st:#04x}: power={st & 1} alive={st >> 4 & 1} VBUS={st >> 5 & 1} CHARGING={st >> 7 & 1}")
ctrl = regs[0x10]
print(f"CTRL 0x10 = {ctrl:#04x}: {'AUS (OFF-Bit)' if ctrl & 8 else 'an'}")
print(f"USB-Eingangslimit   : {10 * regs[0x09] + 90} mA" + (" (aber CTRL=OFF)" if ctrl & 8 else ""))
print(f"Ladestrom-Limit     : {10 * regs[0x0D]} mA")
print(f"Ladestrom (Soll)    : {10 * regs[0x0E]} mA")
print(f"Ladespannung        : {10 * regs[0x0F] + 3000} mV")
print(f"HDQ 0x1D            : {regs[0x1D]:#04x}")

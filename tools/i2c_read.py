#!/usr/bin/env python3
"""i2c_read.py <bus> <addr> [start] [anzahl] [--w16]  – I2C-Register NUR LESEN (root).
Ohne i2c-tools: I2C_RDWR-ioctl (Schreib-Adresse, Repeated Start, Lesen).
--w16: 16-Bit-Registeradresse (big endian).  Beispiel: i2c_read.py 2 0x29 0 16"""
import ctypes, fcntl, os, sys

I2C_RDWR, I2C_M_RD = 0x0707, 0x0001

class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]

class Data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]

def read(fd, addr, reg, n, w16=False):
    a = bytes([reg >> 8 & 0xff, reg & 0xff]) if w16 else bytes([reg & 0xff])
    wb = (ctypes.c_uint8 * len(a)).from_buffer_copy(a)
    rb = (ctypes.c_uint8 * n)()
    msgs = (Msg * 2)(Msg(addr, 0, len(a), wb), Msg(addr, I2C_M_RD, n, rb))
    fcntl.ioctl(fd, I2C_RDWR, Data(msgs, 2))
    return bytes(rb)

if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    w16 = "--w16" in sys.argv
    if len(args) < 2:
        sys.exit(__doc__)
    bus, addr = int(args[0], 0), int(args[1], 0)
    start = int(args[2], 0) if len(args) > 2 else 0
    cnt = int(args[3], 0) if len(args) > 3 else 16
    fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
    try:
        for r in range(start, start + cnt, 16):
            n = min(16, start + cnt - r)
            try:
                d = read(fd, addr, r, n, w16)
                print(f"{bus}-{addr:#04x} {r:#06x}: " + " ".join(f"{b:02x}" for b in d))
            except OSError as e:
                print(f"{bus}-{addr:#04x} {r:#06x}: Fehler {e.strerror}")
                break
    finally:
        os.close(fd)

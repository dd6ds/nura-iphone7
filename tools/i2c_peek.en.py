#!/usr/bin/env python3
"""Reads PMU registers via /dev/i2c-N (I2C_RDWR, even if a driver is bound).
i2c_peek.en.py <bus> <addr> <reg> [anzahl] [regbreite 8|16]"""
import fcntl, struct, ctypes, sys
I2C_RDWR, I2C_M_RD = 0x0707, 0x0001
class Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]
class Data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]
bus, addr, reg = int(sys.argv[1]), int(sys.argv[2], 0), int(sys.argv[3], 0)
n = int(sys.argv[4]) if len(sys.argv) > 4 else 1
w = int(sys.argv[5]) if len(sys.argv) > 5 else 8
wb = (struct.pack(">H", reg) if w == 16 else bytes([reg]))
wbuf = (ctypes.c_uint8 * len(wb))(*wb); rbuf = (ctypes.c_uint8 * n)()
msgs = (Msg * 2)(Msg(addr, 0, len(wb), wbuf), Msg(addr, I2C_M_RD, n, rbuf))
with open(f"/dev/i2c-{bus}", "rb", buffering=0) as f:
    fcntl.ioctl(f, I2C_RDWR, Data(msgs, 2))
print(f"i2c-{bus} 0x{addr:02x} reg 0x{reg:x}: " + " ".join(f"{b:02x}" for b in rbuf))

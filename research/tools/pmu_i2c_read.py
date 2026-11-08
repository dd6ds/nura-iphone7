#!/usr/bin/env python3
"""Auf dem iPhone unter Nura ausführen (root): PMU-Register über /dev/i2c-N lesen.
16-Bit-Registeradressen, 8-Bit-Werte (wie regmap_config_16r_8v / m1n1 d2333).
NUR LESEND (I2C_RDWR: write regaddr + read).
Aufruf: sudo python3 pmu_i2c_read.py [bus] [addr] [start] [count]"""
import fcntl, struct, sys, ctypes

I2C_RDWR = 0x0707
I2C_M_RD = 0x0001

class i2c_msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]

class i2c_rdwr_ioctl_data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(i2c_msg)), ("nmsgs", ctypes.c_uint32)]

def read_reg(fd, addr, reg, n=1):
    wbuf = (ctypes.c_uint8 * 2)(reg >> 8, reg & 0xff)
    rbuf = (ctypes.c_uint8 * n)()
    msgs = (i2c_msg * 2)(i2c_msg(addr, 0, 2, wbuf), i2c_msg(addr, I2C_M_RD, n, rbuf))
    data = i2c_rdwr_ioctl_data(msgs, 2)
    fcntl.ioctl(fd, I2C_RDWR, data)
    return bytes(rbuf)

bus = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0
addr = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x74
start = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x200
count = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x40

fd = open(f"/dev/i2c-{bus}", "rb+", buffering=0)
data = read_reg(fd, addr, start, count)
print(f"/dev/i2c-{bus} addr 0x{addr:02x}  regs 0x{start:04x}..0x{start+count-1:04x}")
for i in range(0, count, 16):
    row = data[i:i + 16]
    print(f"  0x{start+i:04x}: " + " ".join(f"{b:02x}" for b in row))

#!/usr/bin/env python3
"""aop_peek.en.py – state of the audio coprocessor (AOP, A10), READ ONLY (root).
Blocks per ADT: AKF control 0x2_10800000 (0x1c000), SRAM 0x2_10e00000 (0xa0000),
0x2_10000500 and 0x2_10000408 (probably auto-boot/reset registers). Register offsets as for the
GPU coprocessor (AppleA7IOPV2, research/GPU-ANALYSE.md). The outbox (+0x4038) is NOT read,
because reading there pops a message."""
import ctypes, mmap, os

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)


def reg(base):
    page = base & ~0x3fff
    m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
    va = ctypes.addressof(ctypes.c_char.from_buffer(m)) + (base - page)
    return m, (lambda o: ctypes.c_uint32.from_address(va + o).value)


m1, akf = reg(0x210800000)
print("AKF +0x00..+0x4c:", " ".join(f"{akf(o):x}" for o in range(0, 0x50, 4)))
print(f"CPU_CTRL +0x44 = {akf(0x44):#x} (bit 4 = RUN)")
m2, mb = reg(0x210804000)
print(f"MAILBOX_SET {mb(0):#x}  CLR {mb(4):#x}  INBOX_CTRL {mb(8):#x}  OUTBOX_CTRL {mb(0x20):#x}  IDLE {mb(0x40):#x}")
for a in (0x210000408, 0x210000500):
    m3, r = reg(a)
    print(f"{a:#x}: " + " ".join(f"{r(o):x}" for o in range(0, 0x10, 4)))
m4, sram = reg(0x210e00000)
print("SRAM +0x00..+0x1c:", " ".join(f"{sram(o):08x}" for o in range(0, 0x20, 4)))

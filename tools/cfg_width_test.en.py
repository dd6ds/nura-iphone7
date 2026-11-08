#!/usr/bin/env python3
"""Tests 8/16/32-bit accesses in PCIe config space (root port 2), one line BEFORE each access."""
import ctypes, mmap, os, sys
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x610010000)
base = ctypes.addressof(ctypes.c_char.from_buffer(m))
def rd(width, off):
    t = {8: ctypes.c_uint8, 16: ctypes.c_uint16, 32: ctypes.c_uint32}[width]
    print(f"  {width:2d}-Bit-Lesen @ +{off:#x} …", flush=True)
    v = t.from_address(base + off).value
    print(f"    = {v:#x}", flush=True)
for w in [int(a) for a in sys.argv[1:]] or [32, 16, 8]:
    rd(w, 0x34 if w != 16 else 0x0e - 2)
print("done", flush=True)

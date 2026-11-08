#!/usr/bin/env python3
"""Read MMIO via /dev/mem:  mmio_peek.en.py <phys-addr> [count-u32]"""
import mmap, os, struct, sys
addr = int(sys.argv[1], 0); n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
page = addr & ~0x3FFF; off = addr - page
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, off + 4 * n + 16, mmap.MAP_SHARED, mmap.PROT_READ, offset=page)
for i in range(n):
    v = struct.unpack_from("<I", m, off + 4 * i)[0]
    print(f"0x{addr + 4 * i:x}: 0x{v:08x}")

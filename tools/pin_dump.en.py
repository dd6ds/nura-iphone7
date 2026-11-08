#!/usr/bin/env python3
"""pin_dump.en.py [base] [first] [last] – print Apple GPIO pin registers read-only (root).
Bits: 0 value, 1-3 mode (1=output, 7=input), 5-6 peripheral function, 7-8 pull, 9 input enable."""
import mmap, os, struct, sys

base = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x20f100000
first = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
last = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0xd0
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
for p in range(first, last + 1):
    v = struct.unpack_from("<I", m, p * 4)[0]
    print(f"pin 0x{p:02x} ({p:3d}): 0x{v:08x}  val={v & 1} mode={(v >> 1) & 7} periph={(v >> 5) & 3} "
          f"pull={(v >> 7) & 3} ie={(v >> 9) & 1}")

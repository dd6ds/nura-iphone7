#!/usr/bin/env python3
"""mem_dump.py <phys-adresse> <länge> <datei> – physischen Speicher per /dev/mem in eine Datei schreiben (root).
Liest mit ausgerichteten 32-Bit-Zugriffen (geht auch für no-map-Bereiche/Gerätespeicher)."""
import ctypes, mmap, os, sys

if len(sys.argv) != 4:
    sys.exit(__doc__)
base, size, out = int(sys.argv[1], 0), int(sys.argv[2], 0), sys.argv[3]
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
w = (ctypes.c_uint32 * (size // 4)).from_buffer(m)
kopie = (ctypes.c_uint32 * (size // 4))(*w)
open(out, "wb").write(bytes(kopie))

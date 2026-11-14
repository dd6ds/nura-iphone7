#!/usr/bin/env python3
"""mem_suche.en.py [pattern …] – search all RAM ranges marked "reserved" in /proc/iomem (including the
iBoot reservations inside "System RAM") READ ONLY via /dev/mem for byte patterns (root).
Default patterns: markers of the AOP firmware (AppleSPUFirmwareBuilder, RTKit, config tags LCSD/SZSD).
Ranges are read block by block (device memory -> 32-bit words)."""
import ctypes, mmap, os, struct, sys

MUSTER = [m.encode() for m in sys.argv[1:]] or [b"AppleSPUFirmwareBuilder", b"RTKit_iOS", b"LCSD", b"SZSD",
                                                b"t8010aop", b"AOPfw", b"\xd3\x00\x00\x00\x02\x00\x00\x81"]
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
bereiche = []
for zeile in open("/proc/iomem"):
    if ": reserved" not in zeile or "Kernel" in zeile:
        continue
    a, b = (int(x, 16) for x in zeile.split(" : ")[0].strip().split("-"))
    if a >= 0x800000000:
        bereiche.append((a, b + 1))
BLOCK = 0x100000
for a, e in bereiche:
    print(f"== {a:#x}-{e:#x} ({(e - a) // 1024} KB)", flush=True)
    for s in range(a & ~0x3fff, e, BLOCK):
        n = min(BLOCK, e - s)
        n = (n + 0x3fff) & ~0x3fff
        try:
            m = mmap.mmap(fd, n, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=s)
        except OSError as err:
            print(f"   {s:#x}: not readable ({err.strerror})"); break
        w = (ctypes.c_uint32 * (n // 4)).from_address(ctypes.addressof(ctypes.c_char.from_buffer(m)))
        daten = struct.pack(f"<{n // 4}I", *w)
        for mu in MUSTER:
            p = daten.find(mu)
            while p >= 0:
                umg = daten[max(0, p - 16):p + 48]
                print(f"   {mu!r} @ {s + p:#x}: {umg!r}"[:200], flush=True)
                p = daten.find(mu, p + 1)
                if p > 0 and daten.count(mu) > 6:
                    print(f"   … ({daten.count(mu)} Treffer in diesem Block)"); break
        del w; m.close()

#!/usr/bin/env python3
"""mem_suche.py [muster …] – alle als „reserved“ markierten RAM-Bereiche aus /proc/iomem (auch die
iBoot-Reservierungen innerhalb von „System RAM“) per /dev/mem NUR LESEN nach Byte-Mustern durchsuchen (root).
Standard-Muster: Kennzeichen der AOP-Firmware (AppleSPUFirmwareBuilder, RTKit, Konfig-Kennungen LCSD/SZSD).
Bereiche werden blockweise gelesen (Gerätespeicher -> 32-Bit-Wörter)."""
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
            print(f"   {s:#x}: nicht lesbar ({err.strerror})"); break
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

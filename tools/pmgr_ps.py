#!/usr/bin/env python3
"""pmgr_ps.py OFFSET [on|off] – PMGR-Power-State (A10, PMGR 0x2_0e000000) lesen/schalten (root).
Bits 3:0 = Soll-Zustand (0xf = aktiv), 7:4 = Ist-Zustand. Beispiel mca0: pmgr_ps.py 0x80178 on
Achtung: Domains, die Linux für unbenutzt hält, bleiben nur bis zur nächsten genpd-Aktion an."""
import mmap, os, struct, sys, time

PMGR = 0x20e000000
off = int(sys.argv[1], 0)
page = (PMGR + off) & ~0x3fff
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
o = PMGR + off - page
rd = lambda: struct.unpack_from("<I", m, o)[0]
v = rd()
print(f"vorher  {off:#x} = {v:#010x}  soll={v & 0xf:#x} ist={(v >> 4) & 0xf:#x}")
if len(sys.argv) > 2:
    tgt = 0xf if sys.argv[2] == "on" else 0x0
    struct.pack_into("<I", m, o, (v & ~0xf) | tgt)
    for _ in range(100):
        v = rd()
        if ((v >> 4) & 0xf) == tgt: break
        time.sleep(0.001)
    print(f"nachher {off:#x} = {v:#010x}  soll={v & 0xf:#x} ist={(v >> 4) & 0xf:#x}")

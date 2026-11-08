#!/usr/bin/env python3
"""pmgr_ps.en.py OFFSET [on|off] – read/switch a PMGR power state (A10, PMGR 0x2_0e000000) (root).
Bits 3:0 = target state (0xf = active), 7:4 = actual state. Example mca0: pmgr_ps.en.py 0x80178 on
Note: domains Linux considers unused only stay on until the next genpd action."""
import mmap, os, struct, sys, time

PMGR = 0x20e000000
off = int(sys.argv[1], 0)
page = (PMGR + off) & ~0x3fff
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
o = PMGR + off - page
rd = lambda: struct.unpack_from("<I", m, o)[0]
v = rd()
print(f"before {off:#x} = {v:#010x}  target={v & 0xf:#x} actual={(v >> 4) & 0xf:#x}")
if len(sys.argv) > 2:
    tgt = 0xf if sys.argv[2] == "on" else 0x0
    struct.pack_into("<I", m, o, (v & ~0xf) | tgt)
    for _ in range(100):
        v = rd()
        if ((v >> 4) & 0xf) == tgt: break
        time.sleep(0.001)
    print(f"after  {off:#x} = {v:#010x}  target={v & 0xf:#x} actual={(v >> 4) & 0xf:#x}")

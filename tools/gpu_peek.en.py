#!/usr/bin/env python3
"""gpu_peek.en.py [--on] [block] [count] – explore the A10 GPU (AGX G9P), READ ONLY (root).
--on first switches on the PMGR domain "gfx" (0x2_0e080328). block: pmgr (state only), sgx,
shared, kf (gfx-kf IOP). Only the first <count> bytes are read (default 0x40), word by word
with immediate output – if an access hangs, the last line shows the address. Mailbox/FIFO areas
are not touched. pmgr, kf and shared are safe; sgx freezes (see below).
Blocks per ADT: sgx 0x2_01000000 (1 MB), shared 0x2_01d00000 (128 KB), kf 0x2_01d20000 (64 KB)."""
import ctypes, mmap, os, sys, time

PMGR_GFX = 0x20e080328
BLOECKE = {"sgx": 0x201000000, "shared": 0x201d00000, "kf": 0x201d20000}
args = [a for a in sys.argv[1:] if not a.startswith("--")]
block = args[0] if args else "pmgr"
anzahl = int(args[1], 0) if len(args) > 1 else 0x40
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)


class Reg:
    def __init__(self, base):
        page = base & ~0x3fff
        self.m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
        self.va = ctypes.addressof(ctypes.c_char.from_buffer(self.m)) + (base - page)

    def rd(self, off):
        return ctypes.c_uint32.from_address(self.va + off).value

    def wr(self, off, v):
        ctypes.c_uint32.from_address(self.va + off).value = v


def log(*a, **k):
    print(*a, flush=True, **k)


pm = Reg(PMGR_GFX)
v = pm.rd(0)
log(f"PMGR gfx {PMGR_GFX:#x} = {v:#010x}  target={v & 0xf:#x} actual={(v >> 4) & 0xf:#x}")
if "--on" in sys.argv and (v >> 4) & 0xf != 0xf:
    pm.wr(0, (v & ~0xf) | 0xf)
    for _ in range(1000):
        v = pm.rd(0)
        if (v >> 4) & 0xf == 0xf:
            break
        time.sleep(0.001)
    log(f"  after switching on: {v:#010x}  actual={(v >> 4) & 0xf:#x}")
if block == "pmgr":
    sys.exit(0)
if (v >> 4) & 0xf != 0xf:
    sys.exit("gfx domain is off – registers not read (switch on with --on)")
if block == "sgx" and "--force" not in sys.argv:
    # confirmed twice on 2026-11-14: a single read of 0x2_01000000 already freezes the iPhone
    # while the sub-domain GFX-SGX is off (the PMGR domain "gfx" alone is not enough).
    sys.exit("sgx: reading freezes the iPhone while GFX-SGX is off – only with --force")
base = BLOECKE[block]
r = Reg(base)
log(f"== {block} {base:#x}")
for off in range(0, anzahl, 4):
    log(f"  reading +{off:#05x} …", end=" ")
    log(f"{r.rd(off):08x}")

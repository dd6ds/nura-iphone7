#!/usr/bin/env python3
"""gpu_fw_boot.en.py <firmware-section.bin> [seconds] – EXPERIMENT: start the A10 GPU coprocessor (gfx-kf) (root).
Sequence as in iOS (AppleA7IOPV2GFX, see research/GPU-ANALYSE.md):
  gfx domain on -> firmware into the reserved RAM 0x8_4000_0000 (DT gfx-fw, no-map) ->
  set address window -> mask interrupts -> start CPU (akf+0x44 bit 4) ->
  poll the outbox and print every message (no replies) -> stop the CPU again.
The file is the section __TEXT.__const from com.apple.AGXFirmwareKextG9PRTBuddy (iOS kernelcache);
it is Apple firmware and is NOT shipped. Options: --laufen (keep the CPU running), --neu (stop a running CPU first)."""
import ctypes, mmap, os, struct, sys, time

FW_OFF, FW_LEN = 9, 0x5B320            # from requestFirmwareBinary: pointer +9, length 0x5b320
RUNTIME = 0x8F000                      # getRuntimeBinSize
RAM, RAM_LEN = 0x840000000, 0x100000   # DT reserved-memory gfx-fw@840000000
PMGR_GFX = 0x20E080328
AKF, AGX = 0x201D20000, 0x201D00000    # gfx-kf block / shared GFX block
IOP_ADR = 0                            # firmware address as seen by the coprocessor

if len(sys.argv) < 2:
    sys.exit(__doc__)
dauer = float(sys.argv[2]) if len(sys.argv) > 2 else 5
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)


def log(*a, **k):
    print(*a, flush=True, **k)


class Mem:
    def __init__(self, base, size=0x4000):
        page = base & ~0x3fff
        self.m = mmap.mmap(fd, (base - page + size + 0x3fff) & ~0x3fff, mmap.MAP_SHARED,
                           mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
        self.va = ctypes.addressof(ctypes.c_char.from_buffer(self.m)) + (base - page)

    def r32(self, o):
        return ctypes.c_uint32.from_address(self.va + o).value

    def w32(self, o, v):
        ctypes.c_uint32.from_address(self.va + o).value = v & 0xffffffff

    def r64(self, o):
        return ctypes.c_uint64.from_address(self.va + o).value


# 0) Prerequisites
if not os.path.exists("/proc/device-tree/reserved-memory/gfx-fw@840000000"):
    sys.exit("DT region gfx-fw@840000000 missing – boot the new boot payload (./build.en.sh payload)")
blob = open(sys.argv[1], "rb").read()
fw = blob[FW_OFF:FW_OFF + FW_LEN]
if len(fw) != FW_LEN or struct.unpack_from("<I", fw, 0)[0] >> 24 != 0xEA:
    sys.exit("Firmware does not match (expected ARM branch at the start, length 0x5b320)")
log(f"Firmware: {len(fw)} Byte, Version-Text {blob[1:FW_OFF - 1]!r}, erstes Wort {struct.unpack_from('<I', fw, 0)[0]:#010x}")

# 1) gfx domain on
pm = Mem(PMGR_GFX)
v = pm.r32(0)
if (v >> 4) & 0xf != 0xf:
    pm.w32(0, (v & ~0xf) | 0xf)
    for _ in range(1000):
        if (pm.r32(0) >> 4) & 0xf == 0xf:
            break
        time.sleep(0.001)
log(f"PMGR gfx = {pm.r32(0):#010x}")
akf, agx = Mem(AKF, 0x10000), Mem(AGX, 0x4000)
if akf.r32(0x44) & 0x10:
    if "--neu" not in sys.argv:
        sys.exit("CPU already running (akf+0x44 bit 4) – nothing done (--neu stops it first)")
    akf.w32(0x44, akf.r32(0x44) & ~0x10)
    time.sleep(0.01)
    log(f"CPU stopped first: akf+0x44 = {akf.r32(0x44):#x}")

# 2) Firmware into the reserved RAM
# /dev/mem maps the no-map region as device memory: memset/memmove (DC ZVA, unaligned
# accesses) raise SIGBUS there -> aligned 32-bit accesses only.
ram = Mem(RAM, RAM_LEN)
words = (ctypes.c_uint32 * (RAM_LEN // 4)).from_address(ram.va)
daten = struct.unpack(f"<{(len(fw) + 3) // 4}I", fw + b"\0" * (-len(fw) % 4))
for i, w in enumerate(daten):
    words[i] = w
for i in range(len(daten), RAM_LEN // 4):
    words[i] = 0
ok = all(words[i] == daten[i] for i in range(0, len(daten), 997))
log(f"RAM {RAM:#x}: firmware copied ({len(daten)} words), sample check ok: {ok}")

# 3) Address window (GFX extra first, then base – as AppleA7IOPV2GFX::_mapFirmware)
laenge = RAM_LEN & ~0xfff
for blk, o in ((agx, 0x2000), (akf, 0)):
    s = 0x14 if blk is agx else 0x18          # IOP address lo
    blk.w32(o + s, IOP_ADR); blk.w32(o + s + (4 if blk is agx else 8), IOP_ADR >> 32)
    blk.w32(o + (0x1c if blk is agx else 0x28), laenge)
    blk.w32(o + (0x20 if blk is agx else 0x30), 0)
    blk.w32(o + (0x0c if blk is agx else 0x08), RAM); blk.w32(o + (0x10 if blk is agx else 0x10), RAM >> 32)
akf.w32(0x38, 1)
log(f"Window: akf 08/10/18/20/28/38 = " + " ".join(f"{akf.r32(x):#x}" for x in (0x08, 0x10, 0x18, 0x20, 0x28, 0x38)))
log(f"         agx 200c/2010/2014/2018/201c = " + " ".join(f"{agx.r32(x):#x}" for x in (0x200c, 0x2010, 0x2014, 0x2018, 0x201c)))

# 4) Mask interrupts (Linux has no handler, we poll) + init as in iOS
akf.w32(0x4000, 0x1111); akf.w32(0xc00, 0x1111)
akf.w32(0xc004, 0x11); akf.w32(0xc024, 1)
log(f"before start: CPU {akf.r32(0x44):#x}, IN {akf.r32(0x4008):#x}, OUT {akf.r32(0x4020):#x}, IDLE {akf.r32(0x4040):#x}")

# 5) GFX switch (agx+0x2048 bit 0, set by AppleA7IOPV2GFX), then start the CPU and poll the outbox.
# 2026-11-14: without this bit the CPU does not run (RAM stays unchanged).
agx.w32(0x2048, agx.r32(0x2048) | 1)
log(f"agx+0x2048 = {agx.r32(0x2048):#x}")
akf.w32(0x44, akf.r32(0x44) | 0x10)
log(f"CPU started: akf+0x44 = {akf.r32(0x44):#x}")
t0, n = time.time(), 0
try:
    while time.time() - t0 < dauer:
        out = akf.r32(0x4020)
        if out & 0xc0000:
            log(f"  outbox error {out:#x}"); break
        if not out & (1 << 17):                 # not empty -> fetch message (reading pops it)
            msg = akf.r64(0x4038)
            n += 1
            log(f"  {time.time() - t0:6.3f}s message {n}: {msg:#018x}  (ep? {msg >> 56:#x}, type? {(msg >> 52) & 0xf:#x})")
        time.sleep(0.002)
finally:
    log(f"after {time.time() - t0:.1f}s: {n} message(s); CPU {akf.r32(0x44):#x}, IDLE {akf.r32(0x4040):#x}")
    if "--laufen" not in sys.argv:
        akf.w32(0x44, akf.r32(0x44) & ~0x10)
        log(f"CPU stopped: akf+0x44 = {akf.r32(0x44):#x}")

#!/usr/bin/env python3
"""aop_fw_boot.en.py <main.bin> <ext.bin> [seconds] [--laufen] – EXPERIMENT: start the audio coprocessor (AOP) (root).
Both parts come from aopfw.bin (IPSW Firmware/AOP/aopfw-t8010aop.im4p), split with
research/tools/osbin.py: firmware[0] = main part (code from IOP 0x0100_0000), firmware[1] = AOP_ext
(segment __ETEXT from IOP 0x010d_8000). Apple firmware – NOT shipped.
Sequence as for the GPU coprocessor (research/GPU-ANALYSE.md), but without power domain/GFX bit:
stop CPU -> discard old messages -> firmware into the reserved RAM 0x8_4040_0000
(DT aop-fw, no-map) -> window 0 (IOP 0x0100_0000 -> RAM) -> start CPU (akf+0x44 bit 4 + auto-boot) ->
poll the outbox -> without --laufen stop the CPU again.
Status 2026-11-14: with IOP_BASIS=0 FENSTER2=1 the firmware starts (builds page tables), but no HELLO yet."""
import ctypes, mmap, os, struct, sys, time

AKF = 0x210800000                      # AOP control block (ADT aop reg[0])
AUTOBOOT = 0x210000500                 # auto-boot register (ADT aop reg[2], AppleA7IOP index 2)
RAM, RAM_LEN = 0x840400000, 0x100000   # DT reserved-memory aop-fw@840400000
IOP_BASIS = int(os.environ.get("IOP_BASIS", "0x01000000"), 0)   # window start address as seen by the AOP
EXT_OFF = 0xD8000

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) < 2:
    sys.exit(__doc__)
haupt, ext = open(args[0], "rb").read(), open(args[1], "rb").read()
dauer = float(args[2]) if len(args) > 2 else 5
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)


def log(*a):
    print(*a, flush=True)


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


if not os.path.exists("/proc/device-tree/reserved-memory/aop-fw@840400000"):
    sys.exit("DT region aop-fw@840400000 missing – boot the new boot payload (./build.en.sh payload)")
if struct.unpack_from("<I", haupt, 0)[0] >> 24 != 0xEA or len(haupt) > EXT_OFF or EXT_OFF + len(ext) > RAM_LEN:
    sys.exit("Firmware parts do not match (ARM branch at the start, main part < 0xd8000, ext fits in 1 MB)")
akf = Mem(AKF, 0x10000)
log("before: CPU {:#x}, window 08/10/18/20/28/38 = {}".format(
    akf.r32(0x44), " ".join(f"{akf.r32(o):#x}" for o in (0x08, 0x10, 0x18, 0x20, 0x28, 0x38))))

# 1) Stop the CPU, discard old messages
akf.w32(0x44, akf.r32(0x44) & ~0x10)
Mem(AUTOBOOT).w32(0, 0)
time.sleep(0.01)
for _ in range(64):
    if akf.r32(0x4020) & (1 << 17):
        break
    log(f"  old message discarded: {akf.r64(0x4038):#018x}")

# 2) Firmware into the reserved RAM (device memory -> aligned 32-bit accesses only)
ram = Mem(RAM, RAM_LEN)
words = (ctypes.c_uint32 * (RAM_LEN // 4)).from_address(ram.va)
bild = bytearray(RAM_LEN)
bild[0:len(haupt)] = haupt

# NOCACHE=1: do not enable the AOP data cache (boot code sets SCTLR |= 0x1005 -> only 0x1001 = MMU +
# instruction cache). Every write then lands in RAM immediately and a RAM dump shows the real state
# (stack, variables). Debugging only – it slows the firmware down.
if os.environ.get("NOCACHE") == "1":
    if bytes(bild[0x29c:0x2a0]) != bytes.fromhex("051001e3"):     # movw r1, #0x1005 @ IOP 0x0100_029c
        sys.exit("NOCACHE: unexpected instruction at 0x29c – different firmware?")
    bild[0x29c] = 0x01                                             # -> movw r1, #0x1001
    log("  NOCACHE: data cache stays off (SCTLR 0x1001)")

# TLV=1: fill the firmware's configuration list (entries tag/length/value, starting at "GKTS")
# the way the iOS kernel (RTBuddyFirmware) does – see research/AUDIO-ANALYSE.md.
if os.environ.get("TLV") == "1":
    tlv = bild.find(b"GKTS")
    eintraege = {}
    o = tlv
    while o > 0 and all(0x20 <= c < 0x7f for c in bild[o:o + 4]):
        laenge = struct.unpack_from("<I", bild, o + 4)[0]
        eintraege[bytes(bild[o:o + 4]).decode()] = (o + 8, laenge)
        o += 8 + laenge

    def setze(kennung, wert):
        if kennung not in eintraege:
            log(f"  TLV {kennung}: missing"); return
        o, laenge = eintraege[kennung]
        wert = wert if isinstance(wert, bytes) else int(wert).to_bytes(laenge, "little")
        bild[o:o + laenge] = wert[:laenge]
        log(f"  TLV {kennung} @ IOP {0x01000000 + o:#x} = {bytes(bild[o:o + laenge]).hex()}")

    zufall = bytearray(os.urandom(4)); zufall[zufall[0] % 4] = 0
    setze("GKTS", bytes(zufall))                                  # stack guard, one byte 0
    setze("GNRP", os.urandom(32))                                 # random seed
    setze("CNON", os.urandom(8))
    setze("DICE", int(os.environ.get("ECID", "0"), 0))            # /chosen unique-chip-id
    setze("_COS", 0x8010)                                         # /chosen chip-id
    setze("RCOS", int(os.environ.get("CHIPREV", "0x11"), 0))      # /arm-io chip-revision
    setze("dArW", int(os.environ.get("DARW", "0xe0000"), 0))      # 128 KB buffer (firmware default size 0x20000)
    # p0CE = IOP address of AOP_ext. The firmware maps its virtual address 0x010d_8000 with it;
    # if it is 0, 0x010d_8000 points to the start of the main part and the first constructor in the
    # ext part (0x010d_c7c1) raises a data abort (found with NOCACHE=1 in the RAM dump).
    setze("p0CE", IOP_BASIS + EXT_OFF)
    if "OTTR" in os.environ:
        setze("OTTR", int(os.environ["OTTR"], 0))
bild[EXT_OFF:EXT_OFF + len(ext)] = ext
daten = struct.unpack(f"<{RAM_LEN // 4}I", bytes(bild))
for i, w in enumerate(daten):
    words[i] = w
ok = all(words[i] == daten[i] for i in range(0, len(daten), 997))
log(f"RAM {RAM:#x}: main {len(haupt):#x} + ext {len(ext):#x} @ +{EXT_OFF:#x} copied, sample check ok: {ok}")

# 3) Window 0: IOP 0x0100_0000 -> RAM (as AppleA7IOPV2::_mapFirmware)
akf.w32(0x18, IOP_BASIS); akf.w32(0x20, 0)
akf.w32(0x28, RAM_LEN & ~0xfff); akf.w32(0x30, 0)
akf.w32(0x08, RAM); akf.w32(0x10, RAM >> 32)
akf.w32(0x38, 1)
log("Window 08/10/18/20/28/38 = " + " ".join(f"{akf.r32(o):#x}" for o in (0x08, 0x10, 0x18, 0x20, 0x28, 0x38)))
# The AOP starts at IOP address 0 (vectors), but the code is linked for 0x0100_0000 (absolute pointers).
# FENSTER2=1: put the second window set (+0x0c/+0x14/+0x1c/+0x24/+0x2c/+0x34/+0x3c) as an alias onto the same RAM
# -> window 0 = IOP 0, window 1 = IOP 0x0100_0000. iBoot's old values are printed.
if os.environ.get("FENSTER2") == "1":
    log("Window 1 before 0c/14/1c/24/2c/34/3c = " + " ".join(f"{akf.r32(o):#x}" for o in (0x0c, 0x14, 0x1c, 0x24, 0x2c, 0x34, 0x3c)))
    akf.w32(0x1c, 0x01000000); akf.w32(0x24, 0)
    akf.w32(0x2c, RAM_LEN & ~0xfff); akf.w32(0x34, 0)
    akf.w32(0x0c, RAM); akf.w32(0x14, RAM >> 32)
    akf.w32(0x3c, 1)
    log("Window 1 now    0c/14/1c/24/2c/34/3c = " + " ".join(f"{akf.r32(o):#x}" for o in (0x0c, 0x14, 0x1c, 0x24, 0x2c, 0x34, 0x3c)))
elif os.environ.get("FENSTER2") == "sram":
    # Experiment: map the AOP SRAM (0x2_10e00000, 0xa0000) at IOP 0x0116_0000 (firmware uses 0x011f_8000)
    log("Window 1 before 0c/14/1c/24/2c/34/3c = " + " ".join(f"{akf.r32(o):#x}" for o in (0x0c, 0x14, 0x1c, 0x24, 0x2c, 0x34, 0x3c)))
    akf.w32(0x1c, 0x01160000); akf.w32(0x24, 0)
    akf.w32(0x2c, 0xa0000); akf.w32(0x34, 0)
    akf.w32(0x0c, 0x10e00000); akf.w32(0x14, 2)
    akf.w32(0x3c, 1)
    log("Window 1 now    0c/14/1c/24/2c/34/3c = " + " ".join(f"{akf.r32(o):#x}" for o in (0x0c, 0x14, 0x1c, 0x24, 0x2c, 0x34, 0x3c)))

# TUNE=1: apply the "AOP Global" tunables like iBoot 7459.140.15 for t8010 (register, mask, value)
if os.environ.get("TUNE") == "1":
    glob = Mem(0x210000000, 0x8000)
    glob.w32(0x124, glob.r32(0x124) | 1)
    for reg, maske, wert in ((0x00c, 0x10, 0), (0x200, 0xfff, 0), (0x218, 0xffffff, 0xc0),
                             (0x21c, 0xffffff, 0x60), (0x220, 0xffffff, 0x493e00), (0x4014, 1, 1)):
        alt = glob.r32(reg)
        glob.w32(reg, (alt & ~maske) | wert)
        log(f"  Tunable {0x210000000 + reg:#x}: {alt:#x} -> {glob.r32(reg):#x}")

# 4) Start the CPU, poll the outbox. The AOP has "auto-boot": AppleA7IOP maps register index 2 for it
#    (ADT reg[2] = 0x2_10000500) and writes 1 on start, 0 on stop (in addition to +0x44).
auto = Mem(AUTOBOOT)
akf.w32(0x44, akf.r32(0x44) | 0x10)
auto.w32(0, 1)
log(f"CPU started: akf+0x44 = {akf.r32(0x44):#x}, auto-boot {AUTOBOOT:#x} = {auto.r32(0):#x}")
t0, n = time.time(), 0
# WECKEN=1: after 0.5 s send the RTKit management message IOP_PWR_STATE(0x220) – this is how Linux/Asahi
# wakes a coprocessor that is already running but has not sent HELLO yet.
geweckt = os.environ.get("WECKEN") != "1"
try:
    while time.time() - t0 < dauer:
        if not geweckt and time.time() - t0 > 0.5:
            ctypes.c_uint64.from_address(akf.va + 0x4010).value = 0x0060000000000220
            geweckt = True
            log(f"  {time.time() - t0:6.3f}s IOP_PWR_STATE 0x220 sent, inbox {akf.r32(0x4008):#x}")
        out = akf.r32(0x4020)
        if out & 0xc0000:
            log(f"  outbox error {out:#x}"); break
        if not out & (1 << 17):
            msg = akf.r64(0x4038)
            n += 1
            log(f"  {time.time() - t0:6.3f}s message {n}: {msg:#018x}")
        time.sleep(0.002)
finally:
    gesehen = sum(1 for i in range(0, RAM_LEN // 4, 7) if words[i] != daten[i])
    log(f"after {time.time() - t0:.1f}s: {n} message(s), RAM sample changed: {gesehen} words, "
        f"CPU {akf.r32(0x44):#x}, IDLE {akf.r32(0x4040):#x}")
    if "--laufen" not in sys.argv:
        akf.w32(0x44, akf.r32(0x44) & ~0x10)
        auto.w32(0, 0)
        log(f"CPU stopped: akf+0x44 = {akf.r32(0x44):#x}, auto-boot = {auto.r32(0):#x}")

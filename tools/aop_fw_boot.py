#!/usr/bin/env python3
"""aop_fw_boot.py <haupt.bin> <ext.bin> [sekunden] [--laufen] – EXPERIMENT: Audio-Coprozessor (AOP) starten (root).
Die beiden Teile stammen aus aopfw.bin (IPSW Firmware/AOP/aopfw-t8010aop.im4p), zerlegt mit
research/tools/osbin.py: firmware[0] = Hauptteil (Code ab IOP 0x0100_0000), firmware[1] = AOP_ext
(Segment __ETEXT ab IOP 0x010d_8000). Apple-Firmware – wird NICHT mitgeliefert.
Ablauf wie beim GPU-Coprozessor (research/GPU-ANALYSE.md), aber ohne Strom-Domain/GFX-Bit:
CPU anhalten -> alte Nachrichten verwerfen -> Firmware in den reservierten RAM 0x8_4040_0000
(DT aop-fw, no-map) -> Fenster 0 (IOP 0x0100_0000 -> RAM) -> CPU starten (akf+0x44 Bit 4 + Auto-Boot) ->
Ausgang pollen -> ohne --laufen CPU wieder anhalten.
Stand 2026-11-14: mit IOP_BASIS=0 FENSTER2=1 läuft die Firmware an (baut Seitentabellen), aber noch kein HELLO."""
import ctypes, mmap, os, struct, sys, time

AKF = 0x210800000                      # AOP-Steuerblock (ADT aop reg[0])
AUTOBOOT = 0x210000500                 # Auto-Boot-Register (ADT aop reg[2], AppleA7IOP Index 2)
RAM, RAM_LEN = 0x840400000, 0x100000   # DT reserved-memory aop-fw@840400000
IOP_BASIS = int(os.environ.get("IOP_BASIS", "0x01000000"), 0)   # Fenster-Startadresse aus Sicht des AOP
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
    sys.exit("DT-Bereich aop-fw@840400000 fehlt – neues Boot-Paket booten (./build.sh payload)")
if struct.unpack_from("<I", haupt, 0)[0] >> 24 != 0xEA or len(haupt) > EXT_OFF or EXT_OFF + len(ext) > RAM_LEN:
    sys.exit("Firmware-Teile passen nicht (ARM-Sprung am Anfang, Hauptteil < 0xd8000, ext passt in 1 MB)")
akf = Mem(AKF, 0x10000)
log("vorher: CPU {:#x}, Fenster 08/10/18/20/28/38 = {}".format(
    akf.r32(0x44), " ".join(f"{akf.r32(o):#x}" for o in (0x08, 0x10, 0x18, 0x20, 0x28, 0x38))))

# 1) CPU anhalten, alte Nachrichten verwerfen
akf.w32(0x44, akf.r32(0x44) & ~0x10)
Mem(AUTOBOOT).w32(0, 0)
time.sleep(0.01)
for _ in range(64):
    if akf.r32(0x4020) & (1 << 17):
        break
    log(f"  alte Nachricht verworfen: {akf.r64(0x4038):#018x}")

# 2) Firmware in den reservierten RAM (Gerätespeicher -> nur ausgerichtete 32-Bit-Zugriffe)
ram = Mem(RAM, RAM_LEN)
words = (ctypes.c_uint32 * (RAM_LEN // 4)).from_address(ram.va)
bild = bytearray(RAM_LEN)
bild[0:len(haupt)] = haupt
bild[EXT_OFF:EXT_OFF + len(ext)] = ext
daten = struct.unpack(f"<{RAM_LEN // 4}I", bytes(bild))
for i, w in enumerate(daten):
    words[i] = w
ok = all(words[i] == daten[i] for i in range(0, len(daten), 997))
log(f"RAM {RAM:#x}: Hauptteil {len(haupt):#x} + ext {len(ext):#x} @ +{EXT_OFF:#x} kopiert, Stichprobe ok: {ok}")

# 3) Fenster 0: IOP 0x0100_0000 -> RAM (wie AppleA7IOPV2::_mapFirmware)
akf.w32(0x18, IOP_BASIS); akf.w32(0x20, 0)
akf.w32(0x28, RAM_LEN & ~0xfff); akf.w32(0x30, 0)
akf.w32(0x08, RAM); akf.w32(0x10, RAM >> 32)
akf.w32(0x38, 1)
log("Fenster 08/10/18/20/28/38 = " + " ".join(f"{akf.r32(o):#x}" for o in (0x08, 0x10, 0x18, 0x20, 0x28, 0x38)))
# Der AOP startet an IOP-Adresse 0 (Vektoren), der Code ist aber für 0x0100_0000 gelinkt (absolute Zeiger).
# FENSTER2=1: zweiten Fenstersatz (+0x0c/+0x14/+0x1c/+0x24/+0x2c/+0x34/+0x3c) als Alias auf denselben RAM
# legen -> Fenster 0 = IOP 0, Fenster 1 = IOP 0x0100_0000. iBoots alte Werte werden ausgegeben.
if os.environ.get("FENSTER2") == "1":
    log("Fenster 1 vorher 0c/14/1c/24/2c/34/3c = " + " ".join(f"{akf.r32(o):#x}" for o in (0x0c, 0x14, 0x1c, 0x24, 0x2c, 0x34, 0x3c)))
    akf.w32(0x1c, 0x01000000); akf.w32(0x24, 0)
    akf.w32(0x2c, RAM_LEN & ~0xfff); akf.w32(0x34, 0)
    akf.w32(0x0c, RAM); akf.w32(0x14, RAM >> 32)
    akf.w32(0x3c, 1)
    log("Fenster 1 jetzt  0c/14/1c/24/2c/34/3c = " + " ".join(f"{akf.r32(o):#x}" for o in (0x0c, 0x14, 0x1c, 0x24, 0x2c, 0x34, 0x3c)))

# 4) CPU starten, Ausgang pollen. Der AOP hat „auto-boot“: AppleA7IOP bildet dafür Register-Index 2
#    (ADT reg[2] = 0x2_10000500) ab und schreibt beim Start 1, beim Anhalten 0 hinein (zusätzlich zu +0x44).
auto = Mem(AUTOBOOT)
akf.w32(0x44, akf.r32(0x44) | 0x10)
auto.w32(0, 1)
log(f"CPU gestartet: akf+0x44 = {akf.r32(0x44):#x}, Auto-Boot {AUTOBOOT:#x} = {auto.r32(0):#x}")
t0, n = time.time(), 0
try:
    while time.time() - t0 < dauer:
        out = akf.r32(0x4020)
        if out & 0xc0000:
            log(f"  Ausgang-Fehler {out:#x}"); break
        if not out & (1 << 17):
            msg = akf.r64(0x4038)
            n += 1
            log(f"  {time.time() - t0:6.3f}s Nachricht {n}: {msg:#018x}")
        time.sleep(0.002)
finally:
    gesehen = sum(1 for i in range(0, RAM_LEN // 4, 7) if words[i] != daten[i])
    log(f"nach {time.time() - t0:.1f}s: {n} Nachricht(en), RAM-Stichprobe verändert: {gesehen} Wörter, "
        f"CPU {akf.r32(0x44):#x}, IDLE {akf.r32(0x4040):#x}")
    if "--laufen" not in sys.argv:
        akf.w32(0x44, akf.r32(0x44) & ~0x10)
        auto.w32(0, 0)
        log(f"CPU angehalten: akf+0x44 = {akf.r32(0x44):#x}, Auto-Boot = {auto.r32(0):#x}")

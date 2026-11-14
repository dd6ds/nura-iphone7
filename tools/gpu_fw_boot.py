#!/usr/bin/env python3
"""gpu_fw_boot.py <firmware-section.bin> [sekunden] – EXPERIMENT: GPU-Coprozessor (gfx-kf) des A10 starten (root).
Ablauf wie iOS (AppleA7IOPV2GFX, siehe research/GPU-ANALYSE.md):
  gfx-Domain an -> Firmware in den reservierten RAM 0x8_4000_0000 (DT gfx-fw, no-map) ->
  Adressfenster setzen -> Interrupts maskieren -> CPU starten (akf+0x44 Bit 4) ->
  Ausgangs-Postfach pollen und jede Nachricht ausgeben (keine Antworten) -> CPU wieder anhalten.
Die Datei ist die Section __TEXT.__const aus com.apple.AGXFirmwareKextG9PRTBuddy (iOS-Kernelcache);
sie ist Apple-Firmware und wird NICHT mitgeliefert. Optionen: --laufen (CPU nicht anhalten), --neu (laufende CPU vorher anhalten)."""
import ctypes, mmap, os, struct, sys, time

FW_OFF, FW_LEN = 9, 0x5B320            # aus requestFirmwareBinary: Zeiger +9, Länge 0x5b320
RUNTIME = 0x8F000                      # getRuntimeBinSize
RAM, RAM_LEN = 0x840000000, 0x100000   # DT reserved-memory gfx-fw@840000000
PMGR_GFX = 0x20E080328
AKF, AGX = 0x201D20000, 0x201D00000    # gfx-kf-Block / gemeinsamer GFX-Block
IOP_ADR = 0                            # Adresse der Firmware aus Sicht des Coprozessors

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


# 0) Voraussetzungen
if not os.path.exists("/proc/device-tree/reserved-memory/gfx-fw@840000000"):
    sys.exit("DT-Bereich gfx-fw@840000000 fehlt – neues Boot-Paket booten (./build.sh payload)")
blob = open(sys.argv[1], "rb").read()
fw = blob[FW_OFF:FW_OFF + FW_LEN]
if len(fw) != FW_LEN or struct.unpack_from("<I", fw, 0)[0] >> 24 != 0xEA:
    sys.exit("Firmware passt nicht (erwartet ARM-Sprung am Anfang, Länge 0x5b320)")
log(f"Firmware: {len(fw)} Byte, Version-Text {blob[1:FW_OFF - 1]!r}, erstes Wort {struct.unpack_from('<I', fw, 0)[0]:#010x}")

# 1) gfx-Domain an (mit --neu vorher einmal aus = echter Reset des Coprozessors;
#    nur CPU anhalten und neu starten reicht nicht, dann kommt kein zweites HELLO)
pm = Mem(PMGR_GFX)
if "--neu" in sys.argv and (pm.r32(0) >> 4) & 0xf == 0xf:
    akf0 = Mem(AKF, 0x4000)
    akf0.w32(0x44, akf0.r32(0x44) & ~0x10)
    agx0 = Mem(AGX, 0x4000)                    # GFX-Schaltbit übersteht sonst den Reset und
    agx0.w32(0x2048, agx0.r32(0x2048) & ~1)    # startet den Coprozessor schon beim Einschalten
    pm.w32(0, pm.r32(0) & ~0xf)
    for _ in range(1000):
        if (pm.r32(0) >> 4) & 0xf == 0:
            break
        time.sleep(0.001)
    log(f"gfx-Domain aus (Reset): {pm.r32(0):#010x}")
    time.sleep(0.05)
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
        sys.exit("CPU läuft schon (akf+0x44 Bit 4) – nichts getan (--neu hält sie vorher an)")
    akf.w32(0x44, akf.r32(0x44) & ~0x10)
    time.sleep(0.01)
    log(f"CPU vorher angehalten: akf+0x44 = {akf.r32(0x44):#x}")

# 2) Firmware in den reservierten RAM
# /dev/mem bildet den no-map-Bereich als Gerätespeicher ab: memset/memmove (DC ZVA, unausgerichtete
# Zugriffe) lösen dort SIGBUS aus -> nur ausgerichtete 32-Bit-Zugriffe.
ram = Mem(RAM, RAM_LEN)
words = (ctypes.c_uint32 * (RAM_LEN // 4)).from_address(ram.va)
daten = struct.unpack(f"<{(len(fw) + 3) // 4}I", fw + b"\0" * (-len(fw) % 4))
for i, w in enumerate(daten):
    words[i] = w
for i in range(len(daten), RAM_LEN // 4):
    words[i] = 0
ok = all(words[i] == daten[i] for i in range(0, len(daten), 997))
log(f"RAM {RAM:#x}: Firmware kopiert ({len(daten)} Wörter), Stichprobe stimmt: {ok}")

# 3) Adressfenster (erst GFX-Zusatz, dann Basis – wie AppleA7IOPV2GFX::_mapFirmware)
laenge = RAM_LEN & ~0xfff
for blk, o in ((agx, 0x2000), (akf, 0)):
    s = 0x14 if blk is agx else 0x18          # IOP-Adresse lo
    blk.w32(o + s, IOP_ADR); blk.w32(o + s + (4 if blk is agx else 8), IOP_ADR >> 32)
    blk.w32(o + (0x1c if blk is agx else 0x28), laenge)
    blk.w32(o + (0x20 if blk is agx else 0x30), 0)
    blk.w32(o + (0x0c if blk is agx else 0x08), RAM); blk.w32(o + (0x10 if blk is agx else 0x10), RAM >> 32)
akf.w32(0x38, 1)
log(f"Fenster: akf 08/10/18/20/28/38 = " + " ".join(f"{akf.r32(x):#x}" for x in (0x08, 0x10, 0x18, 0x20, 0x28, 0x38)))
log(f"         agx 200c/2010/2014/2018/201c = " + " ".join(f"{agx.r32(x):#x}" for x in (0x200c, 0x2010, 0x2014, 0x2018, 0x201c)))

# 4) Interrupts maskieren (Linux hat keinen Handler, wir pollen) + Init wie iOS
if os.environ.get("MASK", "1") == "1":         # MASK=0: Masken-Register nicht anfassen
    akf.w32(0x4000, 0x1111); akf.w32(0xc00, 0x1111)
if os.environ.get("INIT", "1") == "1":         # INIT=0: +0xc004/+0xc024 nicht schreiben
    akf.w32(0xc004, 0x11); akf.w32(0xc024, 1)
log(f"vor Start: CPU {akf.r32(0x44):#x}, IN {akf.r32(0x4008):#x}, OUT {akf.r32(0x4020):#x}, IDLE {akf.r32(0x4040):#x}")
# Alte Nachrichten aus einem vorigen Lauf überstehen den Domain-Reset (OUT ohne Bit 17 = nicht leer)
for _ in range(64):
    if akf.r32(0x4020) & (1 << 17):
        break
    log(f"  alte Nachricht im Ausgang verworfen: {akf.r64(0x4038):#018x}")
log(f"Ausgang leer: OUT {akf.r32(0x4020):#x}")

# 5) GFX-Schalter (agx+0x2048 Bit 0, setzt AppleA7IOPV2GFX), dann CPU starten und Ausgang pollen.
# 2026-11-14: ohne dieses Bit läuft die CPU nicht an (RAM bleibt unverändert).
agx.w32(0x2048, agx.r32(0x2048) | 1)
log(f"agx+0x2048 = {agx.r32(0x2048):#x}")
akf.w32(0x44, akf.r32(0x44) | 0x10)
log(f"CPU gestartet: akf+0x44 = {akf.r32(0x44):#x}")
t0, n = time.time(), 0
try:
    while time.time() - t0 < dauer:
        out = akf.r32(0x4020)
        if out & 0xc0000:
            log(f"  Ausgang-Fehler {out:#x}"); break
        if not out & (1 << 17):                 # nicht leer -> Nachricht holen (Lesen entnimmt)
            msg = akf.r64(0x4038)
            n += 1
            log(f"  {time.time() - t0:6.3f}s Nachricht {n}: {msg:#018x}  (ep? {msg >> 56:#x}, typ? {(msg >> 52) & 0xf:#x})")
        time.sleep(0.002)
finally:
    log(f"nach {time.time() - t0:.1f}s: {n} Nachricht(en); CPU {akf.r32(0x44):#x}, IDLE {akf.r32(0x4040):#x}")
    if "--laufen" not in sys.argv:
        akf.w32(0x44, akf.r32(0x44) & ~0x10)
        log(f"CPU angehalten: akf+0x44 = {akf.r32(0x44):#x}")

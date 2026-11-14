#!/usr/bin/env python3
"""gpu_peek.py [--on] [block] [anzahl] [start] – A10-GPU (AGX G9P) erkunden, NUR LESEN (root).
--on schaltet vorher die PMGR-Domain "gfx" (0x2_0e080328) ein. block: pmgr (nur Zustand), sgx,
shared, kf (gfx-kf-IOP). Gelesen werden nur die ersten <anzahl> Bytes (Standard 0x40), Wort für Wort
mit sofortiger Ausgabe – hängt ein Zugriff, zeigt die letzte Zeile die Adresse. Mailbox-/FIFO-Bereiche
werden nicht angefasst. pmgr, kf und shared sind gefahrlos; sgx friert ein (siehe unten).
Blöcke laut ADT: sgx 0x2_01000000 (1 MB), shared 0x2_01d00000 (128 KB), kf 0x2_01d20000 (64 KB)."""
import ctypes, mmap, os, sys, time

PMGR_GFX = 0x20e080328
BLOECKE = {"sgx": 0x201000000, "shared": 0x201d00000, "kf": 0x201d20000}
args = [a for a in sys.argv[1:] if not a.startswith("--")]
block = args[0] if args else "pmgr"
anzahl = int(args[1], 0) if len(args) > 1 else 0x40
start = int(args[2], 0) if len(args) > 2 else 0   # z. B. kf 0x48 0x4000 = AKF-V2-Steuerung
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
log(f"PMGR gfx {PMGR_GFX:#x} = {v:#010x}  soll={v & 0xf:#x} ist={(v >> 4) & 0xf:#x}")
if "--on" in sys.argv and (v >> 4) & 0xf != 0xf:
    pm.wr(0, (v & ~0xf) | 0xf)
    for _ in range(1000):
        v = pm.rd(0)
        if (v >> 4) & 0xf == 0xf:
            break
        time.sleep(0.001)
    log(f"  nach Einschalten: {v:#010x}  ist={(v >> 4) & 0xf:#x}")
if block == "pmgr":
    sys.exit(0)
if (v >> 4) & 0xf != 0xf:
    sys.exit("gfx-Domain ist aus – Register nicht gelesen (mit --on einschalten)")
if block == "sgx" and "--force" not in sys.argv:
    # 2026-11-14 zweimal bestätigt: schon 1 Lesezugriff auf 0x2_01000000 friert das iPhone ein,
    # solange die Unter-Domain GFX-SGX aus ist (die PMGR-Domain "gfx" allein reicht nicht).
    sys.exit("sgx: Lesen friert das iPhone ein, solange GFX-SGX aus ist – nur mit --force")
base = BLOECKE[block]
r = Reg(base + (start & ~0x3fff))
log(f"== {block} {base:#x} ab +{start:#x}")
for off in range(start, start + anzahl, 4):
    log(f"  lese +{off:#05x} …", end=" ")
    log(f"{r.rd(off & 0x3fff):08x}")

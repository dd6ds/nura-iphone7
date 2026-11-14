#!/usr/bin/env python3
"""sio_boot.py <siofw.bin> [sekunden] – EXPERIMENT: SIO-Coprozessor (KF-SIO, A7IOP wie der AOP) starten (root).
Die Firmware (aus tools/sio_fw_extract.py, Ladeadresse 0, Bild ~0xa2f2 Byte + BSS bis ~0x88300) kommt nach
RAM_BASIS (Standard 0x8_4070_0000 = oberstes MB des reservierten aop-fw-Bereichs; der AOP nutzt dort nur bis
IOP 0x2e8000 -> beim AOP PUFFER_BIS=0x300000 setzen). Fenster 0 und 1 (AKF +0x08..+0x3c, iBoot-Vorgabe
IOP 0 -> 0x2_0d000000, 0xff3000) zeigen danach auf diesen RAM, dann CPU an (+0x44 Bit 4) und Mailbox-
Nachrichten der SIO für N Sekunden mitschreiben (keine Antworten). LOGDATEI=<pfad> wie gpu_rtkit.py.
Ergebnis 2026-11-14: nach sauberem Reset meldet die SIO 0x036d0000 (EP 0, OP 0x6d, Protokollversion 3)."""
import ctypes, mmap, os, sys, time

AKF = 0x20ae00000
RAM = int(os.environ.get("RAM_BASIS", "0x840700000"), 0)
LEN = int(os.environ.get("RAM_LEN", "0x100000"), 0)
dauer = float(sys.argv[2]) if len(sys.argv) > 2 else 5
fw = open(sys.argv[1], "rb").read()
if fw[:4] != bytes.fromhex("0e0400ea") or len(fw) > LEN:
    sys.exit("unerwartete Firmware (ARM-Sprung 0e0400ea am Anfang erwartet)")
_logf = open(os.environ["LOGDATEI"], "a") if "LOGDATEI" in os.environ else None


def log(*a):
    print(*a, flush=True)
    if _logf:
        print(*a, file=_logf, flush=True); os.fsync(_logf.fileno())


fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
am = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
ava = ctypes.addressof(ctypes.c_char.from_buffer(am))
r32 = lambda o: ctypes.c_uint32.from_address(ava + o).value
r64 = lambda o: ctypes.c_uint64.from_address(ava + o).value


def w32(o, v):
    ctypes.c_uint32.from_address(ava + o).value = v & 0xffffffff


log("vorher: CPU +0x44 = %#x, Fenster " % r32(0x44) + " ".join(f"{r32(o):#x}" for o in range(0x08, 0x40, 4)))
if r32(0x44) & 0x10 and os.environ.get("NEUSTART") != "1":
    sys.exit("SIO läuft schon (NEUSTART=1 erzwingt)")
w32(0x44, r32(0x44) & ~0x10)
# Fehlerbits in den Postfächern (0xc0000) lassen sich nur per PMGR-Reset der SIO (ps_sio 0x2_0e080170 Bit 31)
# löschen; der Reset setzt auch die Fenster auf die iBoot-Vorgabe zurück. RESET=1 macht das vorher.
if os.environ.get("RESET") == "1" or (r32(0x4008) | r32(0x4020)) & 0xc0000:
    pm = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x20e080000)
    ps = ctypes.c_uint32.from_address(ctypes.addressof(ctypes.c_char.from_buffer(pm)) + 0x170)
    alt = ps.value
    ps.value = alt | 0x80000000; time.sleep(0.01); ps.value = alt & ~0x80000000; time.sleep(0.01)
    log(f"  PMGR-Reset ps_sio: {alt:#x} -> {ps.value:#x}")
# Achtung: 0x4038 nie bei leerem Ausgang lesen – das löst in der SIO „outbox/inbox“-Fehler und einen
# Panic (OP 0x6a) aus. Nur verwerfen, wenn VERWERFEN=1 und der Ausgang wirklich etwas meldet.
log(f"  Postfächer: IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")
if os.environ.get("VERWERFEN") == "1":
    for _ in range(16):
        st = r32(0x4020)
        if st & (1 << 17) or st & 0xc0000:
            break
        log(f"  alte Nachricht verworfen: {r64(0x4038):#018x}")
# Firmware + BSS (Nullen) in den RAM, wortweise (Gerätespeicher)
rm = mmap.mmap(fd, LEN, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=RAM)
rva = ctypes.addressof(ctypes.c_char.from_buffer(rm))
bild = fw + bytes(-len(fw) % 4)
for i in range(0, LEN, 4):
    ctypes.c_uint32.from_address(rva + i).value = int.from_bytes(bild[i:i + 4], "little") if i < len(bild) else 0
log(f"Firmware {len(fw):#x} Byte nach {RAM:#x} geladen, Rest bis {LEN:#x} genullt")
for basis in (0x08, 0x0c):                            # Fenster 0 (+0x08..) und 1 (+0x0c..): IOP 0 -> RAM
    w32(basis + 0x10, 0); w32(basis + 0x18, 0)        # IOP-Start (+0x18/+0x20 bzw. +0x1c/+0x24)
    w32(basis + 0x20, LEN & ~0xfff); w32(basis + 0x28, 0)
    w32(basis, RAM); w32(basis + 0x08, RAM >> 32)
    w32(basis + 0x30, 1)
log("Fenster jetzt " + " ".join(f"{r32(o):#x}" for o in range(0x08, 0x40, 4)))
w32(0x44, r32(0x44) | 0x10)
log(f"CPU gestartet: +0x44 = {r32(0x44):#x}")
t0 = time.time()
while time.time() - t0 < dauer:
    out = r32(0x4020)
    if out & 0xc0000:
        log(f"Ausgang-Fehler {out:#x}"); break
    if out & (1 << 17):
        time.sleep(0.002); continue
    m = r64(0x4038)
    # AppleSmartIO-Nachricht: Byte 0 = Endpunkt, 1 = Tag, 2 = Opcode, 3 = Parameter, Bit 63:32 = Daten
    ep, tag, op, par, dat = m & 0xff, m >> 8 & 0xff, m >> 16 & 0xff, m >> 24 & 0xff, m >> 32
    info = {(0, 0x6d): "Hallo/bereit (PARAM = Protokollversion)", (0, 0x6a): "PANIC"}.get((ep, op), "")
    log(f"{time.time() - t0:6.3f}s <- {m:#018x}  EP {ep} TAG {tag} OP {op:#x} PARAM {par:#x} DATA {dat:#x} {info}")
log(f"Ende: CPU {r32(0x44):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}, 0x48 {r32(0x48):#x}")

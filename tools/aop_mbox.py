#!/usr/bin/env python3
"""aop_mbox.py [status | wecken | lesen] – Mailbox des laufenden AOP vorsichtig ansehen/bedienen (root).
status: nur Steuerregister lesen (nichts entnehmen). lesen: Ausgang leeren, solange er weder leer noch im
Fehlerzustand ist. wecken: RTKit IOP_PWR_STATE(0x220) senden, dann 3 s lang wie „lesen“.
Registerbedeutung (A7IOP V2): +0x4008 Eingang-Steuerung, +0x4010 senden, +0x4020 Ausgang-Steuerung,
+0x4038 Ausgang lesen (entnimmt), Bit 17 = leer, Bit 16 = voll, Bits 18/19 = Fehler (Über-/Unterlauf)."""
import ctypes, mmap, os, sys, time

AKF = 0x210800000
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
va = ctypes.addressof(ctypes.c_char.from_buffer(m))


def r32(o):
    return ctypes.c_uint32.from_address(va + o).value


def status(t=""):
    print(f"{t}CPU {r32(0x44):#x} IDLE {r32(0x4040):#x} | Eingang {r32(0x4008):#x} | Ausgang {r32(0x4020):#x}", flush=True)


def lesen(dauer):
    t0 = time.time()
    while time.time() - t0 < dauer:
        aus = r32(0x4020)
        if aus & 0xc0000:
            print(f"  Ausgang im Fehlerzustand {aus:#x} – höre auf"); return
        if not aus & (1 << 17):
            print(f"  {time.time() - t0:6.3f}s Nachricht {ctypes.c_uint64.from_address(va + 0x4038).value:#018x}", flush=True)
        time.sleep(0.002)


was = sys.argv[1] if len(sys.argv) > 1 else "status"
status("vorher:  ")
if was == "lesen":
    lesen(2)
elif was == "wecken":
    ein = r32(0x4008)
    if ein & 0xc0000 or ein & (1 << 16):
        sys.exit(f"Eingang nicht bereit ({ein:#x}) – nichts gesendet")
    ctypes.c_uint64.from_address(va + 0x4010).value = 0x0060000000000220
    print("IOP_PWR_STATE 0x220 gesendet", flush=True)
    lesen(3)
status("nachher: ")

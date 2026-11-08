#!/usr/bin/env python3
"""mca_init.py N [mclk_hz] – MCA N (A10, mca,s5l8950x) wie iOS AppleAE2MCA initialisieren (root).
Schritte: PMGR-Power (0x80178+8N) an, NCO-Kanal N auf mclk (Standard 12 MHz), MCLK-Steuerung
(0x20a002000+4N) = 0x50 (Quelle nclk==f, Ausgang an), MCA-Reset (0x11=3, 0x12=1 bis Bit 0 = 0),
Grundregister 4=0, 7=0xd, 0xc=0xd, 2 (16-bit-Rahmen), FIFO-Schwellen 8/0xd, Slot-Masken 9/0xe = 3,
Taktquellen 6/0xb, Freigabe 4=1, 0x10=0xb0003000, Sync/Start 3.
Register = Basis 0x20a0a0000 + N*0x4000 + idx*4 (AppleAE2MCA 0x…644e6b4/e734).
Vorsicht: Werte für 6/0xb/3 geschätzt (iOS berechnet sie aus der Stream-Konfiguration)."""
import mmap, os, struct, subprocess, sys, time

N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
F = int(sys.argv[2], 0) if len(sys.argv) > 2 else 12000000
BASE = 0x20a0a0000 + N * 0x4000
HERE = os.path.dirname(os.path.abspath(__file__))

def run(*a):
    print(subprocess.run([sys.executable, *a], capture_output=True, text=True).stdout.strip())

run(f"{HERE}/pmgr_ps.py", hex(0x80178 + 8 * N), "on")
run(f"{HERE}/nco_set.py", str(N), str(F))
run(f"{HERE}/peek.py", hex(0x20a002000 + 4 * N), "0x50")

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=BASE)
rd = lambda i: struct.unpack_from("<I", m, i * 4)[0]
def wr(i, v):
    struct.pack_into("<I", m, i * 4, v & 0xffffffff)

print(f"MCA{N} Version {rd(0):#x}, Reg1 {rd(1):#010x}")
wr(0x11, 3); wr(0x12, 1)
for _ in range(100):
    if not rd(0x12) & 1: break
    time.sleep(0.01)
print(f"Reset: 0x11={rd(0x11):#x} 0x12={rd(0x12):#x}")
for i, v in ((4, 0), (7, 0xd), (0xc, 0xd), (2, 0x1010), (8, 0x00030004), (0xd, 0x00030004),
             (5, 0), (9, 3), (0xe, 3), (6, 0x40b), (0xb, 0x408), (4, 1), (0x10, 0xb0003000), (3, 0x1003)):
    wr(i, v)
print("Register:", " ".join(f"{i:#x}={rd(i):#x}" for i in (2, 3, 4, 5, 6, 7, 8, 9, 0xb, 0xc, 0xd, 0xe, 0x10, 0x11, 0x12)))

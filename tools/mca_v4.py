#!/usr/bin/env python3
"""mca_v4.py N [start|stop|zeige] – MCA N (mca-version >= 4, A10) wie iOS AppleAE2MCA::_setIISConfig_v4 einrichten (root).
Format aus ADT mca1/virtual-mca1a/audio-speaker-top `reg` (cs35l26): 48 kHz, 15 Slots à 16 Bit + 10 Bit Füllung
= 250 Bittakte/Rahmen, Bittakt 12 MHz (= MCLK), TX-Slotmaske 3 (2 Kanäle), RX-Slotmaske 0x3e (5 Kanäle).
Hilfsfunktion 0x…5ab760c liefert daraus: Slotbreite 16, Rahmen 250, Füllung 10, Teiler 1.
Folge (0x…644c5f0): 3=3 (warten Bit 1:0 = 0), 9=1 (warten Bit 0 = 0), 8=7=0x1fff, 2=0x1010,
0x19 = TX-FIFO ((Tiefe-1)<<16 | Tiefe, Tiefe = min(48, FIFO-Größe aus Reg 1 − 3) auf 4 gerundet),
0x21 = RX-FIFO 0x30004, 5 = Füllung 10, 0x1a = 3, 0x1b = 0, 0x22 = 0x3e, 0x23 = 0,
0x18 = 0x132 (TX-Serialisierer, Bit 0 aus), 0x20 = 0x136, 8 = 0x1fa4, 4 = 0x10e000.
Start (0x…644d17c): 0x18 = 0x133 (Bit 0 = an), 4 |= 2.
Vorher: PMGR-Power (0x80178+8N), NCO N auf 12 MHz, ClkCon (0x20a002000+4N) = 0x50,
I2S-Schalter (0x20a004000): pin2 <- audN, audN <- pin2, Pin-2-Freigabe 0x44 |= 0x11.
Nur Register 0x00–0xff lesen – ab 0x100 hängt das System."""
import mmap, os, struct, subprocess, sys, time

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
CMD = sys.argv[2] if len(sys.argv) > 2 else "init"
BASE = 0x20a0a0000 + N * 0x4000
SW = 0x20a004000
HERE = os.path.dirname(os.path.abspath(__file__))

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
def karte(adr):
    return mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=adr)
def run(*a):
    print(subprocess.run([sys.executable, *a], capture_output=True, text=True).stdout.strip())

def zeige(m):
    rd = lambda i: struct.unpack_from("<I", m, i * 4)[0]
    for z in range(0, 0x28, 8):
        print(f"  {z:#04x}: " + " ".join(f"{rd(i):08x}" for i in range(z, z + 8)))

if CMD == "zeige":
    zeige(karte(BASE)); sys.exit()

m = karte(BASE)
rd = lambda i: struct.unpack_from("<I", m, i * 4)[0]
def wr(i, v):
    struct.pack_into("<I", m, i * 4, v & 0xffffffff)
def warte(i, maske):
    for _ in range(200):
        if not rd(i) & maske: return True
        time.sleep(0.01)
    print(f"  Zeitüberschreitung: Reg {i:#x} = {rd(i):#x}"); return False

if CMD == "stop":
    wr(0x18, rd(0x18) & ~1); wr(4, rd(4) & ~3); zeige(m); sys.exit()

if CMD == "start":
    # iOS lässt Bit 0 von Reg 4 aus (mca1 ist dort Takt-Slave, Bittakt kommt vom Codec). Ohne Codec-Takt
    # zieht der MCA keine Daten aus dem Shim – mit Bit 0 (Sync-/Bittakt-Erzeugung) läuft der DMA (MASTER=0: aus).
    master = int(os.environ.get("MASTER", "1"))
    wr(0x18, 0x133); wr(4, rd(4) | 2 | master)
    time.sleep(0.05); zeige(m); sys.exit()

# init
run(f"{HERE}/pmgr_ps.py", hex(0x80178 + 8 * N), "on")
run(f"{HERE}/nco_set.py", str(N), "12000000")
run(f"{HERE}/peek.py", hex(0x20a002000 + 4 * N), "0x50")
s = karte(SW)
sw = lambda i, v: struct.pack_into("<I", s, i * 4, v)
swr = lambda i: struct.unpack_from("<I", s, i * 4)[0]
sw(2, N * 0x010101)                 # pin2 <- audN
sw(5 + N, 0x0a0a0a)                 # audN <- pin2 (Ziel audN = Index 5+N)
if swr(2 + N) == 0x0a0a0a and 2 + N != 5 + N:
    sw(2 + N, 0x181818)             # früherer Fehler dieses Skripts: pin(2+N) <- pin2 wieder freigeben
sw(17, swr(17) | 0x11)              # Pin-2-Freigabe
print(f"Schalter: pin2={swr(2):#x} aud{N}={swr(5 + N):#x} Freigabe={swr(17):#x}")

print(f"MCA{N} Version {rd(0):#x}, Reg1 (FIFO-Größen) {rd(1):#010x}")
fifo = rd(1) & 0x3ff
tiefe = max(4, min(48, fifo - 3) & ~3)
wr(3, 3); warte(3, 3)
wr(9, 1); warte(9, 1)
wr(8, 0x1fff); wr(7, 0x1fff)
for i, v in ((2, 0x1010), (0x19, ((tiefe - 1) << 16) | tiefe), (0x21, 0x30004), (5, 10),
             (0x1a, int(os.environ.get("TXMASKE", "3"), 0)), (0x1b, 0), (0x22, 0x3e), (0x23, 0), (0x18, 0x132), (0x20, 0x136),
             (8, 0x1fa4), (4, 0x10e000)):
    wr(i, v)
print(f"TX-FIFO-Tiefe {tiefe}")
zeige(m)

#!/usr/bin/env python3
"""Panel/MIPI-DSI neu initialisieren (Port von Sandcastle hx-mipi-dsi.c turn_off/turn_on)
für A10 (iPhone 7). Ziel: Display-Controller (in-cell Touch) aus dem Reset-Default starten.
Aufruf (root):  dsi_reinit.py [--dry]"""
import mmap, os, struct, sys, time
DRY = "--dry" in sys.argv
DSI, DISP, PMGR_DSI, GPIO = 0x206600000, 0x206400000, 0x20E0802C0, 0x20F100000
RESET_PIN = 172
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
def mp(base, size):
    return mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=base)
dsi, disp = mp(DSI, 0x100000), mp(DISP, 0x4000)
pm = mp(PMGR_DSI & ~0x3FFF, 0x4000); pmo = PMGR_DSI & 0x3FFF
gp = mp(GPIO, 0x4000); gpo = 4 * RESET_PIN
def rd(m, o): return struct.unpack_from("<I", m, o)[0]
def wr(m, o, v):
    if DRY: print(f"  w {o:#x} = {v:#010x}"); return
    struct.pack_into("<I", m, o, v & 0xFFFFFFFF)
def r(o): return rd(dsi, o)
def w(o, v): wr(dsi, o, v)
def rmw(o, clr, set_): w(o, (r(o) & ~clr) | set_)
def us(t): time.sleep(t / 1e6)

def wait(cond, what, n=100):
    for _ in range(n):
        if DRY or cond(): return True
        us(1500)
    print(f"  WARN: {what} timeout"); return False

def send_short(cmd, data=0):
    w(0x6c, 0x05 | ((cmd | (data << 8)) << 8))
    wait(lambda: r(0x74) & 1, f"DCS {cmd:#x}")

def disp_run(state):
    v = rd(disp, 8); wr(disp, 8, (v & ~(1 << 31)) | ((1 << 31) if state else 0))
    wait(lambda: bool(rd(disp, 8) & (1 << 30)) == bool(state), f"disp_run {state}")

def gpio_reset(level):
    v = rd(gp, gpo); wr(gp, gpo, (v & ~1) | (1 if level else 0))

def dsi_reset():
    v = rd(pm, pmo); m = 0xEFFFFCFF
    if v & 0x10000000: wr(pm, pmo, v & m); us(1)
    wr(pm, pmo, (v & m) | 0x400); us(1)
    wr(pm, pmo, (v & m) | 0x80000400); us(1)
    wr(pm, pmo, v & m)
    if v & 0x10000000: us(1); wr(pm, pmo, v)

def phy_write(cmd, val):
    w(0xb4, 2); w(0xb8, cmd & 0xff); rmw(0xb8, 0, 1 << 16); us(300)
    rmw(0xb4, 2, 0); us(300)
    rmw(0xb8, 1 << 16, 0); rmw(0xb8, 0xff, 0); rmw(0xb8, 0, val & 0xff); us(300)
    rmw(0xb4, 0, 2); us(300); rmw(0xb4, 2, 0)

# --- Setup aus dem laufenden (iBoot-)Zustand sichern -----------------------
S = {k: r(o) for k, o in dict(pkt=0x3c, hsa=0x48, hbp=0x4c, hline=0x50, vsa=0x54, vbp=0x58,
                             vact=0x60, vfp=0x5c, clkmgr=0x08, phyif=0xa4).items()}
VIF = [r(0x80028 + 4 * i) for i in range(5)]
print("Setup:", {k: hex(v) for k, v in S.items()}, "VIF:", [hex(v) for v in VIF])
print(f"PWR_UP={r(0x04):#x} MODE={r(0x34):#x} PHY_STATUS={r(0xb0):#x} DISP_STATE={rd(disp, 8):#x} GPIO{RESET_PIN}={rd(gp, gpo):#x}")
lanes = (S["phyif"] & 3) + 1

# --- turn_off ---------------------------------------------------------------
print("turn_off …")
send_short(0x28); send_short(0x10); us(40000)
disp_run(0)
gpio_reset(0)
rmw(0x94, 1, 0)
w(0xb4, 1); us(3000)
w(0x04, 0); us(3000)
rmw(0xa0, 0b1101, 0); us(3000)
rmw(0xa0, 0b0010, 0); us(1500)
dsi_reset(); us(12000)

# --- turn_on ----------------------------------------------------------------
print("turn_on …")
w(0x80034, 0x80000000)
w(0x08, S["clkmgr"]); w(0x34, 1); w(0xa4, S["phyif"])
w(0x2c, (1 << 4) | (1 << 3) | (1 << 2))          # PCKHDL_CFG: CRC_RX|ECC_RX|BTA
w(0x0c, 0); w(0x10, 5); w(0x8000c, 5); w(0x14, 0)
w(0x38, 0x8000 | (60 << 8)); rmw(0x38, 0, 3 << 8); rmw(0x38, 0, 3)
w(0x3c, S["pkt"]); w(0x48, S["hsa"]); w(0x4c, S["hbp"]); w(0x50, S["hline"])
w(0x54, S["vsa"]); w(0x58, S["vbp"]); w(0x60, S["vact"]); w(0x5c, S["vfp"])
w(0x94, 0); w(0x18, 0); w(0x90, 0); w(0x108, 0)
w(0x9c, (35 << 24) | (60 << 16) | 936)
w(0x98, (67 << 16) | 159)
w(0x68, sum(1 << b for b in (14, 13, 12, 11, 10, 9, 8)))
w(0xb4, 0); us(300); w(0xb4, 0); us(300); w(0xb4, 1); us(300)
rmw(0x80034, 0, 0x10000000)
w(0x04, 1)
w(0xa0, 1 << 2)
rmw(0x80034, 0, 0x02000000 | (VIF[3] & 0xFF0))
rmw(0x80034, 0, 4)
wait(lambda: not (r(0x80034) & 4), "phy init")
w(0x80038, VIF[4]); us(300)
rmw(0x80034, 0, 0x08000000); us(300)
rmw(0x80034, 0x08000000, 0); us(300)
w(0x8002c, VIF[1]); w(0x80030, VIF[2])
rmw(0x80034, 0x10000000, 0)
w(0x80028, VIF[0])
w(0xa0, 0b1101); us(300)
w(0xa0, 0b1111); us(300)
wait(lambda: r(0x80004) & 0x10, "reset")
w(0x80, 25); w(0x8c, 25)
mask = 1 | sum({0: 1 << 4, 1: 1 << 7, 2: 1 << 9, 3: 1 << 11}[i] for i in range(lanes))
wait(lambda: (r(0xb0) & mask) == mask, "phy lock")
us(15000)
gpio_reset(1); us(9000)
send_short(0x11); us(1000)
phy_write(0x71, 0x85 if VIF[0] == 2 else 0x8D)
for c in (0x32, 0x42, 0x52, 0x82, 0x52): phy_write(c, 0x80)
us(1000)
w(0x94, 1); us(28000)
disp_run(1); us(90000)
send_short(0x29)
w(0x34, 0)
print(f"fertig: PWR_UP={r(0x04):#x} MODE={r(0x34):#x} PHY_STATUS={r(0xb0):#x} DISP_STATE={rd(disp, 8):#x}")

#!/usr/bin/env python3
"""nco_set.en.py CHANNEL FREQ_HZ | CHANNEL off | show – set the A10 audio NCO (nco,s5l8960x @ 0x2_0e044000) (root).
Rebuild of iOS AppleS5L8960XNCO::setFrequency (kernelcache 0x…657453c):
  fin = 2.4 GHz / 7 (342.857 MHz);  div = 2*2.4G / (7*f),  rest = 2*2.4G - div*7*f
  DIV = (LFSR(0x7ff, poly 0xa01) after (div/4 - 3) steps) << 2 | (div & 3)
  INC1 = rest, INC2 = rest - 7f, ACCINIT = (rest ^ 0x80000000) - 7f, CTRL = 0x80001000 (on)
Registers per channel (page size 0x4000): 0 CTRL, 4 DIV, 8 INC1, 0xc INC2, 0x10 ACCINIT.
ADT: mca0 (CS42L71 codec) MCLK = NCO channel 0, 12 MHz (audio-data reg 0x00b71b00)."""
import mmap, os, struct, sys, time

BASE, PAGE = 0x20e044000, 0x4000
FIN2, MUL = 2 * 2400000000, 7
M32 = 0xffffffff

def regs(ch):
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    m = mmap.mmap(fd, PAGE, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=BASE + ch * PAGE)
    os.close(fd)
    return m

def rd(m, o): return struct.unpack_from("<I", m, o)[0]

def wr(m, o, v):
    for _ in range(100):                  # iOS: wait while CTRL bit 30 (busy) is set
        if not rd(m, 0) & (1 << 30): break
        time.sleep(0.001)
    struct.pack_into("<I", m, o, v & M32)

def lfsr(steps):
    s = 0x7ff
    for _ in range(steps):
        s = (s << 1) if not (s & 0x400) else ((s << 1) ^ 0xa01)
        s &= 0x7ff
    return s

def show(ch):
    m = regs(ch)
    print(f"NCO{ch}: " + " ".join(f"{n}={rd(m, o):#010x}" for n, o in
                                  (("CTRL", 0), ("DIV", 4), ("INC1", 8), ("INC2", 0xc), ("ACC", 0x10))))

def set_freq(ch, f):
    m = regs(ch)
    x20 = MUL * f
    div, rest = FIN2 // x20, FIN2 % x20
    coarse = div >> 2
    if not (3 <= coarse < 0x800):
        sys.exit(f"frequency {f} out of range (div={div})")
    divreg = (0x1ffc if coarse == 3 else lfsr(coarse - 3) << 2) | (div & 3)
    wr(m, 0, 0)
    wr(m, 4, divreg)
    wr(m, 8, rest)
    wr(m, 0xc, rest - x20)
    wr(m, 0x10, (rest ^ 0x80000000) - x20)
    wr(m, 0, 0x80001000)
    real = FIN2 / (MUL * (div + rest / x20)) if x20 else 0
    print(f"NCO{ch} -> {f} Hz (div={div}, rest={rest}, DIV={divreg:#x}, computed {real:.1f} Hz)")

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "show":
        for c in range(5): show(c)
    elif sys.argv[2] == "off":
        wr(regs(int(sys.argv[1])), 0, 0); show(int(sys.argv[1]))
    else:
        set_freq(int(sys.argv[1]), int(sys.argv[2], 0)); show(int(sys.argv[1]))

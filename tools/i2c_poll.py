#!/usr/bin/env python3
"""i2c_poll.py <bus> <addr> [start] [anzahl] [--w16] [--scan] – I2C NUR LESEN ohne Linux-Treiber (root).
Spricht den PA-Semi-Controller (A10: 0x2_0a110000 + bus*0x1000) per /dev/mem an, ohne Interrupt.
Die PMGR-Power-Domain muss an sein (pmgr_ps.py 0x801b8 on für i2c2, 0x801c0 für i2c3).
--scan: jede Adresse 0x08..0x77 mit 1-Byte-Lesen anfragen (ACK = vorhanden)."""
import ctypes, mmap, os, sys, time

MTX, MRX, SMSTA, IMASK, CTL = 0x00, 0x04, 0x14, 0x18, 0x1c
RD, STOP, START, EMPTY = 1 << 10, 1 << 9, 1 << 8, 1 << 8
XIP, XEN, JAM, MTO, MTA, MTN, TOM = 1 << 28, 1 << 27, 1 << 24, 1 << 23, 1 << 22, 1 << 21, 1 << 6
CLKDIV = 0x0f                                   # wie i2c0/i2c1 unter Linux


class Bus:
    def __init__(self, bus):
        base = 0x20a110000 + 0x1000 * bus
        self.fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        self.m = mmap.mmap(self.fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                           offset=base & ~0x3fff)
        self.o = base & 0x3fff
        # echte 32-Bit-Zugriffe (struct/mmap kopieren evtl. byteweise -> FIFO bekäme 4 Einträge)
        self.va = ctypes.addressof(ctypes.c_char.from_buffer(self.m)) + self.o

    def rd(self, r):
        return ctypes.c_uint32.from_address(self.va + r).value

    def wr(self, r, v):
        ctypes.c_uint32.from_address(self.va + r).value = v

    def reset(self):
        self.wr(CTL, (1 << 9) | (1 << 10) | (1 << 8) | CLKDIV)   # MTR|MRR|UJM|div

    def clear(self):
        self.wr(IMASK, 0)
        for _ in range(100):
            st = self.rd(SMSTA)
            if not st & (XIP | JAM):
                break
            time.sleep(0.001)
        else:
            raise OSError(f"Bus hängt, SMSTA={st:#010x}")
        self.reset()
        self.wr(SMSTA, self.rd(SMSTA))

    def wait(self):
        for _ in range(100):
            st = self.rd(SMSTA)
            if st & (XEN | MTN | MTA | TOM | MTO):
                break
            time.sleep(0.001)
        else:
            raise OSError(f"Timeout, SMSTA={st:#010x}")
        for bit, txt in ((TOM, "Controller-Timeout"), (MTO, "Peripherie-Timeout"), (XIP, "hängt"),
                         (MTA, "Arbitrierung verloren"), (MTN, "NACK")):
            if st & bit:
                self.reset()
                raise OSError(f"{txt}, SMSTA={st:#010x}")
        self.wr(SMSTA, XEN)

    def read(self, addr, regbytes, n):
        """Registeradresse schreiben (ohne STOP), Repeated Start, n Bytes lesen."""
        self.clear()
        if regbytes:
            self.wr(MTX, START | addr << 1)
            for b in regbytes:
                self.wr(MTX, b)
        self.wr(MTX, START | addr << 1 | 1)
        self.wr(MTX, n | RD | STOP)
        self.wait()
        out = []
        for _ in range(n):
            v = self.rd(MRX)
            if v & EMPTY:
                self.reset()
                raise OSError("RX-FIFO leer")
            out.append(v & 0xff)
        return bytes(out)

    def write(self, addr, data):
        """Bytes schreiben (z. B. Registeradresse + Wert) mit STOP."""
        self.clear()
        self.wr(MTX, START | addr << 1)
        for b in data[:-1]:
            self.wr(MTX, b)
        self.wr(MTX, data[-1] | STOP)
        self.wait()


if __name__ == "__main__":
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not args:
        sys.exit(__doc__)
    b = Bus(int(args[0], 0))
    if "--scan" in sys.argv:
        found = []
        for a in range(0x08, 0x78):
            try:
                b.read(a, b"", 1)
                found.append(f"{a:#04x}")
            except OSError:
                pass
        print("gefunden:", " ".join(found) or "-")
        sys.exit(0)
    addr = int(args[1], 0)
    start = int(args[2], 0) if len(args) > 2 else 0
    cnt = int(args[3], 0) if len(args) > 3 else 16
    w16 = "--w16" in sys.argv
    # Register einzeln lesen (Blocklesen liefert bei manchen Chips ab Byte 2 nur 0xff)
    for r0 in range(start, start + cnt, 16):
        line = []
        for r in range(r0, min(r0 + 16, start + cnt)):
            rb = bytes([r >> 8 & 0xff, r & 0xff]) if w16 else bytes([r & 0xff])
            try:
                line.append(f"{b.read(addr, rb, 1)[0]:02x}")
            except OSError as e:
                line.append("--")
                err = e
        print(f"{addr:#04x} {r0:#06x}: " + " ".join(line))
        if all(x == "--" for x in line):
            print(f"   ({err})")
            break

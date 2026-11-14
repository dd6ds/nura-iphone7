#!/usr/bin/env python3
"""maggie_reg.en.py – EXPERIMENT: read/write registers of the loaded Maggie FPGA via spi1 CS1 (root, iPhone 7).
Format from AppleMaggieArcAudio (kext text 0x…64e5000): header 3 bytes = address 16 bit big-endian + control byte
(0x00 = write, 0x80 = read, 0x…64eac84), then 16-bit values big-endian (_writeMultipleRegisters 0x…64ea768,
at most 0x80 values per transfer). Prerequisites: tools/maggie_load.en.py (CDONE = 1) and MCLK (maggie_reg.en.py takt).
Without a running MCLK Maggie does not answer (MISO stays 0); ID: 0x7002 = 0x2e8b, version 0x7000.
  maggie_reg.en.py takt              AOP power domain 0x15 on (0x2_1028_0038 = 0x80f) and MCLK (0x2_10c0_2000 = 0x48)
  maggie_reg.en.py rd ADR [N]        read N registers from ADR
  maggie_reg.en.py wr ADR WERT [...]  write starting at ADR
  maggie_reg.en.py init              basic setup like iOS (0x…64e854c, part 1)
  maggie_reg.en.py dump              read 0x0000-0x004f, 0x3000-0x3003, 0x6000-0x6003
Environment: OFF = offset of the read data after the header (default 3), MAGGIE_HZ (default 1 MHz)."""
import ctypes, fcntl, glob, os, struct, sys

HZ = int(os.environ.get("MAGGIE_HZ", "1000000"))
OFF = int(os.environ.get("OFF", "3"))


def spidev():
    for d in glob.glob("/sys/bus/spi/devices/spi*.1"):
        if "20a084000" in os.path.realpath(d):
            return "/dev/" + os.path.basename(d).replace("spi", "spidev", 1)
    sys.exit("no spidev for spi1 CS1")


fd = os.open(spidev(), os.O_RDWR)
if "MODUS" in os.environ:                                  # SPI mode 0-3 (SPI_IOC_WR_MODE)
    fcntl.ioctl(fd, 0x40016b01, struct.pack("B", int(os.environ["MODUS"])))


def xfer(tx):
    tb = ctypes.create_string_buffer(bytes(tx), len(tx))
    rb = ctypes.create_string_buffer(len(tx))
    s = struct.pack("<QQIIHBBBBBB", ctypes.addressof(tb), ctypes.addressof(rb), len(tx), HZ, 0, 8, 0, 0, 0, 0, 0)
    sb = ctypes.create_string_buffer(s, len(s))
    req = (1 << 30) | (len(s) << 16) | (ord('k') << 8) | 0
    if ctypes.CDLL(None, use_errno=True).ioctl(fd, req, sb) < 0:
        raise OSError(ctypes.get_errno(), "SPI_IOC_MESSAGE")
    return rb.raw


def rd(adr, n=1):
    r = xfer(struct.pack(">HB", adr, 0x80) + bytes(2 * n + 2))
    return [struct.unpack_from(">H", r, OFF + 2 * i)[0] for i in range(n)], r


def wr(adr, *werte):
    xfer(struct.pack(">HB", adr, 0) + b"".join(struct.pack(">H", w & 0xffff) for w in werte))


def zeige(adr, n):
    w, roh = rd(adr, n)
    for i in range(0, n, 8):
        print(f"  {adr + i:#06x}: " + " ".join(f"{x:04x}" for x in w[i:i + 8]))
    return roh


cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
a = [int(x, 0) for x in sys.argv[2:]]
if cmd == "takt":
    # like the AOP mca service on enableMClk: setState(0x15, 2) -> PMGR-mini 0x80038, then 0x48 into the MCLK register
    import mmap
    mf = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    for basis, off, wert in ((0x210280000, 0x38, None), (0x210c00000, 0x2000, 0x48)):
        m = mmap.mmap(mf, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=basis)
        if wert is None:
            wert = (struct.unpack_from("<I", m, off)[0] & ~0x30f) | 0xf
        struct.pack_into("<I", m, off, wert)
        print(f"{basis + off:#x} = {struct.unpack_from('<I', m, off)[0]:#010x}")
    w, _ = rd(0x7002)
    print(f"Maggie 0x7002 = {w[0]:#06x} ({'ok' if w[0] == 0x2e8b else 'no answer'})")
elif cmd == "rd":
    roh = zeige(a[0], a[1] if len(a) > 1 else 1)
    print("  roh:", roh.hex(" "))
elif cmd == "wr":
    wr(a[0], *a[1:]); zeige(a[0], len(a) - 1)
elif cmd == "dump":
    for adr, n in ((0, 0x50), (0x3000, 4), (0x6000, 4)):
        zeige(adr, n)
elif cmd == "init":
    # AppleMaggieArcAudio 0x…64e854c: 0x6001 = 0, 0x46 = 0xffff, 0x47 = 1, 0x48 = 1, 0x49 = 3, 0x3000 = 0x3001 = 0xff
    for adr, v in ((0x6001, 0), (0x46, 0xffff), (0x47, 1), (0x48, 1), (0x49, 3), (0x3000, 0xff), (0x3001, 0xff)):
        wr(adr, v)
    for adr, n in ((0x40, 0x10), (0x3000, 2), (0x6000, 4)):
        zeige(adr, n)
else:
    sys.exit(__doc__)

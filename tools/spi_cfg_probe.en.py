#!/usr/bin/env python3
"""spi_cfg_probe.en.py [cs] – samples the spi1 CONFIG register (0x20a084004) during a long
spidev transfer (root). Bit1 = CPHA, bit2 = CPOL."""
import ctypes, mmap, os, struct, sys, threading, time

CS = int(sys.argv[1]) if len(sys.argv) > 1 else 0
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x20a084000)
cfg = lambda: struct.unpack_from("<I", m, 4)[0]

def xfer():
    f = os.open("/dev/spidev1.%d" % CS, os.O_RDWR)
    buf = (ctypes.c_char * 100000)()
    x = struct.pack("<QQIIHBBBBBB", ctypes.addressof(buf), 0, len(buf), 1000000, 0, 8, 0, 0, 0, 0, 0)
    xb = ctypes.create_string_buffer(x, len(x))
    ctypes.CDLL(None).ioctl(f, ctypes.c_ulong((1 << 30) | (len(x) << 16) | (ord('k') << 8)), xb)
    os.close(f)

t = threading.Thread(target=xfer); t.start()
seen = set()
while t.is_alive():
    seen.add(cfg()); time.sleep(0.002)
print("CS%d CONFIG seen:" % CS, " ".join("%#x" % v for v in sorted(seen)))

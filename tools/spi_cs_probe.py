#!/usr/bin/env python3
"""spi_cs_probe.py [cs] – prüft, ob der CS-Pin von spi1 während einer langen spidev-Übertragung
wirklich umschaltet (root). Sendet Nullbytes langsam und liest dabei das Pinregister mit."""
import ctypes, mmap, os, struct, sys, threading, time

CS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
PIN = {0: 0x83, 1: 0xb1}[CS]
base = 0x20f100000
fd = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
pin = lambda: struct.unpack_from("<I", m, PIN * 4)[0] & 1

dev = None
for d in os.listdir("/sys/bus/spi/devices"):
    if d.endswith(".%d" % CS) and "20a084000" in os.path.realpath("/sys/bus/spi/devices/" + d):
        dev = "/dev/" + d.replace("spi", "spidev", 1)
print("spidev", dev, "CS-Pin 0x%x vorher =" % PIN, pin())

def xfer():
    f = os.open(dev, os.O_RDWR)
    buf = (ctypes.c_char * 200000)()
    x = struct.pack("<QQIIHBBBBBB", ctypes.addressof(buf), 0, len(buf), 1000000, 0, 8, 0, 0, 0, 0, 0)
    xb = ctypes.create_string_buffer(x, len(x))
    ctypes.CDLL(None).ioctl(f, ctypes.c_ulong((1 << 30) | (len(x) << 16) | (ord('k') << 8)), xb)
    os.close(f)

t = threading.Thread(target=xfer); t.start()
seen = set()
while t.is_alive():
    seen.add(pin()); time.sleep(0.005)
print("während Übertragung gesehen:", sorted(seen), " nachher =", pin())

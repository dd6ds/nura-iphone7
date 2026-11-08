#!/usr/bin/env python3
"""cs42l71.en.py – read/write registers of the CS42L71 codec (spi1 CS0) (root).
SPI format from iOS AppleCSSPIAudio (v1, AppleEmbeddedAudio.kext):
  read:     6d, addr>>8, addr&0x7f, 00, 00   (full duplex, value in the 5th byte)
  write:    6c, addr>>8, addr&0x7f, 00, value
MISO is shared with Maggie -> keep Maggie in reset meanwhile (CRESET=0).

  cs42l71.en.py dump [start] [count]      e.g. dump 0x0000 0x80
  cs42l71.en.py rd ADDR
  cs42l71.en.py wr ADDR WERT"""
import ctypes, os, struct, sys

DEV, HZ = "/dev/spidev1.0", int(os.environ.get("CS_HZ", "1000000"))

def xfer(tx):
    fd = os.open(DEV, os.O_RDWR)
    tb = (ctypes.c_char * len(tx)).from_buffer_copy(bytes(tx))
    rb = (ctypes.c_char * len(tx))()
    x = struct.pack("<QQIIHBBBBBB", ctypes.addressof(tb), ctypes.addressof(rb), len(tx), HZ, 0, 8, 0, 0, 0, 0, 0)
    xb = ctypes.create_string_buffer(x, len(x))
    r = ctypes.CDLL(None, use_errno=True).ioctl(fd, ctypes.c_ulong((1 << 30) | (len(x) << 16) | (ord('k') << 8)), xb)
    os.close(fd)
    if r < 0:
        raise OSError(ctypes.get_errno(), "spidev")
    return bytes(rb)

def rd(a):
    return xfer([0x6d, (a >> 8) & 0xff, a & 0x7f, 0, 0])[4]

def wr(a, v):
    xfer([0x6c, (a >> 8) & 0xff, a & 0x7f, 0, v & 0xff])

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if cmd == "dump":
        start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
        n = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x80
        for row in range(start, start + n, 16):
            print(f"{row:04x}: " + " ".join(f"{rd(a):02x}" for a in range(row, min(row + 16, start + n))))
    elif cmd == "rd":
        a = int(sys.argv[2], 0); print(f"{a:#06x} = {rd(a):#04x}")
    elif cmd == "wr":
        wr(int(sys.argv[2], 0), int(sys.argv[3], 0))

#!/usr/bin/env python3
"""codec_probe.en.py – query the CS42L71 (spi1 CS0) with common Cirrus SPI read formats (root, read-only).
If nobody answers, MISO (pull-up) only returns 0xff."""
import ctypes, os, struct, sys

DEV = sys.argv[1] if len(sys.argv) > 1 else "/dev/spidev1.0"
HZ = 1000000

def xfer(*msgs):
    """several sub-transfers in one message; cs_change=1 separates them (CS briefly high)."""
    fd = os.open(DEV, os.O_RDWR)
    bufs, raw = [], b""
    for i, (tx, cs_change) in enumerate(msgs):
        tb = (ctypes.c_char * len(tx)).from_buffer_copy(tx)
        rb = (ctypes.c_char * len(tx))()
        bufs += [tb, rb]
        raw += struct.pack("<QQIIHBBBBBB", ctypes.addressof(tb), ctypes.addressof(rb), len(tx), HZ,
                           0, 8, cs_change, 0, 0, 0, 0)
    xb = ctypes.create_string_buffer(raw, len(raw))
    req = (1 << 30) | (len(raw) << 16) | (ord('k') << 8)
    r = ctypes.CDLL(None, use_errno=True).ioctl(fd, ctypes.c_ulong(req), xb)
    os.close(fd)
    if r < 0:
        return "ioctl error %d" % ctypes.get_errno()
    return " | ".join(bytes(bufs[2 * i + 1]).hex(" ") for i in range(len(msgs)))

tests = {
    # classic (CS42L73/CS42L52 SPI): chip address 1001010 + R/W, MAP, then read separately
    "addr4A MAP01 then read": [(bytes([0x94, 0x81]), 1), (bytes([0x95]) + bytes(4), 0)],
    "addr48 MAP01 then read": [(bytes([0x90, 0x81]), 1), (bytes([0x91]) + bytes(4), 0)],
    "addr4A in one go":        [(bytes([0x95, 0x81]) + bytes(4), 0)],
    # 16-bit register with read bit (CS42L42 style 0x1001..0x1003 = device ID)
    "16bit 0x9001 read":       [(bytes([0x90, 0x01]) + bytes(4), 0)],
    "16bit 0x1001 + R-Flag":   [(bytes([0x80, 0x10, 0x01]) + bytes(4), 0)],
    # 32-bit address with read bit + 4 bytes padding (newer Cirrus parts)
    "32bit 0x00000000 R":      [(bytes([0x80, 0, 0, 0]) + bytes(4) + bytes(8), 0)],
}
for name, msgs in tests.items():
    print(f"{name:26s}: {xfer(*msgs)}")

#!/usr/bin/env python3
"""peek.en.py ADDR [VALUE] – read/write 32 bits via /dev/mem (root)."""
import mmap, os, struct, sys

def access(addr, val=None):
    page = addr & ~0x3fff
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    try:
        m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
        off = addr - page
        if val is not None:
            m[off:off + 4] = struct.pack("<I", val)
        r = struct.unpack("<I", m[off:off + 4])[0]
        m.close()
        return r
    finally:
        os.close(fd)

if __name__ == "__main__":
    a = int(sys.argv[1], 0)
    v = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    print("0x%x = 0x%08x" % (a, access(a, v)))

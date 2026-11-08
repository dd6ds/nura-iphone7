#!/usr/bin/env python3
"""Inspect an APFS container READ-ONLY (under Linux, without an APFS driver):
size, used/free (space manager of the newest checkpoint).  apfs_info.en.py [/dev/nvme0n1p1]"""
import os, struct, sys

dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/nvme0n1p1"
fd = os.open(dev, os.O_RDONLY)

def blk(n, bs):
    return os.pread(fd, bs, n * bs)

sb0 = os.pread(fd, 4096, 0)
magic, bs, nblocks = struct.unpack_from("<4sIQ", sb0, 32)
assert magic == b"NXSB", f"not an APFS container ({magic!r})"
desc_blocks, data_blocks, desc_base = struct.unpack_from("<IIQ", sb0, 104)
desc_blocks &= 0x7fffffff

# newest valid NX superblock in the checkpoint descriptor area
best = None
for i in range(desc_blocks):
    b = blk(desc_base + i, bs)
    oid, xid, otype = struct.unpack_from("<QQI", b, 8)
    if (otype & 0xffff) == 0x1 and b[32:36] == b"NXSB":
        if best is None or xid > best[0]:
            best = (xid, i, b)
xid, idx, sb = best
desc_index, desc_len = struct.unpack_from("<II", sb, 136)
nblocks = struct.unpack_from("<Q", sb, 40)[0]   # size according to the NEWEST checkpoint (block 0 may be stale)
spaceman_oid = struct.unpack_from("<Q", sb, 152)[0]

# checkpoint maps before this checkpoint's superblock -> physical address of the space manager
paddr = None
for k in range(desc_len - 1):
    b = blk(desc_base + (desc_index + k) % desc_blocks, bs)
    otype = struct.unpack_from("<I", b, 24)[0] & 0xffff
    if otype != 0xc:
        continue
    count = struct.unpack_from("<I", b, 36)[0]
    for e in range(count):
        t, st, size, pad, fs_oid, oid, pa = struct.unpack_from("<IIIIQQQ", b, 40 + 40 * e)
        if oid == spaceman_oid:
            paddr = pa
sm = blk(paddr, bs)
dev_blocks, chunks, cibs, cabs, free = struct.unpack_from("<QQIIQ", sm, 48)

GB = 1e9
print(f"Container: {nblocks * bs / GB:.2f} GB  (block {bs} B, {nblocks} blocks), checkpoint xid {xid}")
print(f"belegt:    {(dev_blocks - free) * bs / GB:.2f} GB")
print(f"frei:      {free * bs / GB:.2f} GB")
print(f"BLOCKS={nblocks}")

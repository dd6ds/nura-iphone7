#!/usr/bin/env python3
"""kc_kext_segs.py <kernelcache.bin> <kext-header-fileoffset> [dump-dir]
Segmente/Sections eines eingebetteten Kexts ausgeben, optional jede Section als Rohdatei ablegen
(Name: <seg>.<sect>.<vmaddr>.bin)."""
import os, struct, sys

kc = open(sys.argv[1], "rb").read()
if kc[:4] == b"\xca\xfe\xba\xbe":
    fo, fs = struct.unpack_from(">II", kc, 16)
    kc = kc[fo:fo + fs]
# Datei-Offsets im Kernelcache: vm -> file über die Kernel-Segmente
ncmds = struct.unpack_from("<I", kc, 16)[0]
off, ksegs = 32, []
for _ in range(ncmds):
    cmd, sz = struct.unpack_from("<II", kc, off)
    if cmd == 0x19:
        vm, vms, fo, fs = struct.unpack_from("<QQQQ", kc, off + 24)
        ksegs.append((vm, vms, fo))
    off += sz
v2f = lambda v: next(fo + v - vm for vm, vms, fo in ksegs if vm <= v < vm + vms)

h = int(sys.argv[2], 0)
out = sys.argv[3] if len(sys.argv) > 3 else None
if out: os.makedirs(out, exist_ok=True)
ncmds = struct.unpack_from("<I", kc, h + 16)[0]
off = h + 32
for _ in range(ncmds):
    cmd, sz = struct.unpack_from("<II", kc, off)
    if cmd == 0x19:
        seg = kc[off + 8:off + 24].rstrip(b"\0").decode()
        vm, vms = struct.unpack_from("<QQ", kc, off + 24)
        nsect = struct.unpack_from("<I", kc, off + 64)[0]
        print(f"{seg:18s} vm {vm:#x} +{vms:#x}")
        for i in range(nsect):
            s = off + 72 + i * 80
            sect = kc[s:s + 16].rstrip(b"\0").decode()
            addr, size = struct.unpack_from("<QQ", kc, s + 32)
            print(f"   {sect:20s} {addr:#x} +{size:#x}")
            if out and size and seg != "__LINKEDIT":
                try:
                    f = v2f(addr)
                    open(f"{out}/{seg}.{sect}.{addr:x}.bin", "wb").write(kc[f:f + size])
                except StopIteration:
                    pass
    off += sz

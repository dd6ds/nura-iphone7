#!/usr/bin/env python3
"""Baut eine iOS-kompatible SysCfg-Datei ("gfCS") aus den Kalibrier-Blobs
der Live-ADT (research/live/multi-touch/*), damit hx-touchd sie lesen kann.
Schlüssel wie in mtfw.c: MtCl, OrbG, OFCl, SDAC, PxCl (alle als 'BTNC'-Jumbo)."""
import os, struct, sys
src = sys.argv[1] if len(sys.argv) > 1 else "research/live/multi-touch"
out = sys.argv[2] if len(sys.argv) > 2 else "out/hx-touch/syscfg.bin"
KEYS = [("MtCl", "multi-touch-calibration"), ("OrbG", "orb-gap-cal"),
        ("OFCl", "orb-force-cal"), ("SDAC", "shape-dynamic-accel-cal"),
        ("PxCl", "prox-calibration")]
blobs = [(k, open(os.path.join(src, f), "rb").read()) for k, f in KEYS
         if os.path.exists(os.path.join(src, f))]
hdr_sz, key_sz = 24, 20
off = hdr_sz + key_sz * len(blobs)
keys, data = b"", b""
for k, b in blobs:
    keys += b"BTNC" + k[::-1].encode() + struct.pack("<III", len(b), off + len(data), 0xFFFFFFFF)
    data += b + b"\0" * (-len(b) % 4)
total = off + len(data)
img = b"gfCS" + struct.pack("<IIIII", 0x7C, total, 0x00030000, 0, len(blobs)) + keys + data
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
open(out, "wb").write(img)
print(f"{out}: {total} Bytes, Schlüssel: " + ", ".join(f"{k}({len(b)})" for k, b in blobs))

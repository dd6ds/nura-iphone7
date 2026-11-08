#!/usr/bin/env python3
"""Sucht eingebettete Broadcom-.hcd-Blobs (HCI-Befehlsfolgen 0xfc4c Write_RAM ... 0xfc4e Launch_RAM)
in einer Binärdatei (z.B. iOS BlueTool). hcd_scan.py <datei> [ausgabeverzeichnis]"""
import sys, os, re
data = open(sys.argv[1], "rb").read()
outdir = sys.argv[2] if len(sys.argv) > 2 else None
found = []
pos = 0
for m in re.finditer(rb"\x4c\xfc", data):
    s = m.start()
    if s < pos:
        continue
    # vom Treffer aus Befehle verketten
    p, n, launch = s, 0, False
    while p + 3 <= len(data):
        op = data[p] | data[p + 1] << 8
        ln = data[p + 2]
        if (op >> 8) != 0xfc or p + 3 + ln > len(data):
            break
        p += 3 + ln; n += 1
        if op == 0xfc4e:
            launch = True
            break
    if n >= 20 and launch:
        found.append((s, p)); pos = p
for i, (a, b) in enumerate(found):
    blob = data[a:b]
    print(f"#{i}: off=0x{a:x} len={b-a} cmds-start={blob[:6].hex()}")
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        open(os.path.join(outdir, f"blob{i:02d}_0x{a:x}.hcd"), "wb").write(blob)

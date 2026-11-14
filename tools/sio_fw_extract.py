#!/usr/bin/env python3
"""sio_fw_extract.py <kernelcache.bin> <ziel.bin> – SIO-Firmware („KF-SIO“) aus dem iOS-Kernelcache holen.
Sie liegt im __DATA-Segment von com.apple.driver.AppleT8010SmartIO: Ladeadresse 0, ARM-Sprung auf 0x1040,
Bild 0xa2f2 Byte, danach Nullen (BSS bis ca. 0x88300). Apple-Firmware – wird NICHT mitgeliefert, nur lokal
erzeugen."""
import hashlib, sys

SIG = bytes.fromhex("0e0400eafeffffeafeffffeafeffffeafeffffeafeffffeafeffffeafeffffea00f020e300f020e3")
LAENGE = 0x882a8          # Bild + BSS wie im Kext-Segment
SHA = "459e2140623c68e8a747d2ff8ef4adca0b188be0189b0cf04f12dae3512375da"

d = open(sys.argv[1], "rb").read()
i = d.find(SIG)
if i < 0:
    sys.exit("SIO-Firmware nicht gefunden (anderer Kernelcache?)")
fw = d[i:i + LAENGE]
h = hashlib.sha256(fw).hexdigest()
print(f"gefunden bei Datei-Offset {i:#x}, {len(fw):#x} Byte, sha256 {h}" + ("" if h == SHA else "  (ABWEICHEND)"))
open(sys.argv[2], "wb").write(fw[:0xa400])     # nur das Bild; BSS legt sio_boot.py als Nullen an

#!/usr/bin/env python3
"""sio_fw_extract.en.py <kernelcache.bin> <target.bin> – fetch the SIO firmware ("KF-SIO") from the iOS kernelcache.
It sits in the __DATA segment of com.apple.driver.AppleT8010SmartIO: load address 0, ARM branch to 0x1040,
image 0xa2f2 bytes, then zeros (BSS up to about 0x88300). Apple firmware – NOT shipped, only create it
locally."""
import hashlib, sys

SIG = bytes.fromhex("0e0400eafeffffeafeffffeafeffffeafeffffeafeffffeafeffffeafeffffea00f020e300f020e3")
LAENGE = 0x882a8          # image + BSS as in the kext segment
SHA = "459e2140623c68e8a747d2ff8ef4adca0b188be0189b0cf04f12dae3512375da"

d = open(sys.argv[1], "rb").read()
i = d.find(SIG)
if i < 0:
    sys.exit("SIO firmware not found (different kernelcache?)")
fw = d[i:i + LAENGE]
h = hashlib.sha256(fw).hexdigest()
print(f"found at file offset {i:#x}, {len(fw):#x} bytes, sha256 {h}" + ("" if h == SHA else "  (DIFFERENT)"))
open(sys.argv[2], "wb").write(fw[:0xa400])     # image only; sio_boot.en.py creates the BSS as zeros

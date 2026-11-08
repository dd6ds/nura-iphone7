#!/usr/bin/env python3
"""WLAN-Firmware (BCM4355 "elsa", iPhone 7) aus der iOS-Rootfs für brcmfmac aufbereiten.
Quelle:  research/firmware/wifi/C-4355__s-C0/  (elsa.trx/.clmb/.txcb, P-elsa_*.txt)
Ziel:    out/wifi-fw/brcm/brcmfmac<chip>-pcie.apple,elsa*.{bin,txt,clm_blob,txcap_blob}
Namenslogik aus dem Asahi-Installer (asahi_firmware/wifi.py, MIT). Weil die Chip-Revision
noch unbekannt ist, entstehen die Präfixe 4355c0 (Asahi), 4355 (rev <= 10) und 4355c1 (rev >= 11)."""
import os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src/asahi-installer"))
from asahi_firmware.wifi import WiFiFWCollection

src = os.path.join(ROOT, "research/firmware/wifi")
dst = os.path.join(ROOT, "out/wifi-fw")
shutil.rmtree(dst, ignore_errors=True)
os.makedirs(os.path.join(dst, "brcm"))
n = 0
for name, fw in WiFiFWCollection(src).files():
    for chip in ("4355c0", "4355", "4355c1"):
        out = os.path.join(dst, name.replace("brcmfmac4355c0-", f"brcmfmac{chip}-"))
        with open(out, "wb") as f:
            f.write(fw.data)
        n += 1
# brcmfmac (Apple-Pfad) sucht zuerst "<board>-<Modul>-<Hersteller>-<Version>-<Antenne>".
# Fehlt der Name, wartet der Firmware-Loader auf einen Userspace-Helfer (Standard 60 s je
# Datei). Daher die exakten Namen für alle Varianten aus der iOS-Firmware anlegen
# (Antennen-Platzhalter X0 aus dem Device-Tree). Vom iPhone 7 gemeldet: PRNL-u-5.9.
import glob, re
b = os.path.join(dst, "brcm")
for txt in glob.glob(os.path.join(src, "C-4355__s-C0", "P-elsa_M-*_V-*__m-*.txt")):
    mo = re.search(r"P-elsa_M-(\w+)_V-(\w+)__m-([\d.]+)\.txt$", txt)
    if not mo:
        continue
    mod, ven, ver = mo.groups()
    for chip in ("4355", "4355c1"):
        pre = f"brcmfmac{chip}-pcie.apple,elsa"
        full = f"{pre}-{mod}-{ven}-{ver}-X0"
        for ext in ("bin", "clm_blob", "txcap_blob"):
            shutil.copy(os.path.join(b, f"{pre}.{ext}"), os.path.join(b, f"{full}.{ext}"))
        shutil.copy(txt, os.path.join(b, f"{full}.txt")); n += 4

print(f"{n} Dateien in {dst}/brcm:")
for f in sorted(os.listdir(os.path.join(dst, "brcm"))):
    print("  ", f)

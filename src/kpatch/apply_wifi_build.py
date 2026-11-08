#!/usr/bin/env python3
"""Einmalige Anpassung von tools/wifi-fw.py und build.sh für dauerhaftes WLAN (idempotent)."""
import os
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

p = os.path.join(R, "tools/wifi-fw.py"); s = open(p).read()
if "exakten Namen" not in s:
    old = 'print(f"{n} Dateien in {dst}/brcm:")'
    new = '''# brcmfmac (Apple-Pfad) sucht zuerst "<board>-<Modul>-<Hersteller>-<Version>-<Antenne>".
# Fehlt der Name, wartet der Firmware-Loader auf einen Userspace-Helfer (Standard 60 s je
# Datei). Daher die exakten Namen für alle Varianten aus der iOS-Firmware anlegen
# (Antennen-Platzhalter X0 aus dem Device-Tree). Vom iPhone 7 gemeldet: PRNL-u-5.9.
import glob, re
b = os.path.join(dst, "brcm")
for txt in glob.glob(os.path.join(src, "C-4355__s-C0", "P-elsa_M-*_V-*__m-*.txt")):
    mo = re.search(r"P-elsa_M-(\\w+)_V-(\\w+)__m-([\\d.]+)\\.txt$", txt)
    if not mo:
        continue
    mod, ven, ver = mo.groups()
    for chip in ("4355", "4355c1"):
        pre = f"brcmfmac{chip}-pcie.apple,elsa"
        full = f"{pre}-{mod}-{ven}-{ver}-X0"
        for ext in ("bin", "clm_blob", "txcap_blob"):
            shutil.copy(os.path.join(b, f"{pre}.{ext}"), os.path.join(b, f"{full}.{ext}"))
        shutil.copy(txt, os.path.join(b, f"{full}.txt")); n += 4

print(f"{n} Dateien in {dst}/brcm:")'''
    assert old in s; s = s.replace(old, new, 1); open(p, "w").write(s); print("wifi-fw.py angepasst")

p = os.path.join(R, "build.sh"); s = open(p).read()
if "firmware-timeout.conf" not in s:
    old = '''    sudo cp "$w"/* "$m/lib/firmware/brcm/"'''
    new = old + '''
    # Firmware-Loader: nicht 60 s je fehlender Datei auf einen Userspace-Helfer warten
    sudo mkdir -p "$m/etc/tmpfiles.d"
    echo 'w /sys/class/firmware/timeout - - - - 1' | sudo tee "$m/etc/tmpfiles.d/firmware-timeout.conf" >/dev/null'''
    assert old in s; s = s.replace(old, new, 1)
s = s.replace('PCIE_BOOT="${PCIE_BOOT:-0}"', 'PCIE_BOOT="${PCIE_BOOT:-1}"   # 0 = Notschalter (PCIe/WLAN aus, per SSH startbar)', 1)
s = s.replace('''# PCIe (WLAN) ist noch in Arbeit: der Treiber startet nicht beim Booten, sondern wird per
# SSH gestartet (echo 0 > /sys/module/pcie_apple_t8010/parameters/disable; … bind).
# PCIE_BOOT=1 ./build.sh payload  -> PCIe direkt beim Booten starten.''', '''# PCIe/WLAN startet beim Booten. Notschalter, falls das iPhone dabei hängt:
#   PCIE_BOOT=0 ./build.sh payload   (Treiber dann per SSH startbar:
#   echo 0 > /sys/module/pcie_apple_t8010/parameters/disable;
#   echo 610000000.pcie > /sys/bus/platform/drivers/pcie-apple-t8010/bind)''', 1)
open(p, "w").write(s); print("build.sh angepasst")

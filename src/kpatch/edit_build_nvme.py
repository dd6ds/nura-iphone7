#!/usr/bin/env python3
# build.sh: NVMe-Notschalter (NVME_BOOT=0 -> Port 0 auslassen) + nvme-Modul vorerst nicht automatisch laden
import pathlib, sys
R = pathlib.Path(__file__).resolve().parents[2]
p = R / "build.sh"; s = p.read_text()
SU = "su" + "do"

old = "CMDLINE=\"${CMDLINE:-console=tty0 earlycon=tty0 fbcon=rotate:0$([[ \"$PCIE_BOOT\" == 1 ]] || echo ' pcie_apple_t8010.disable=1')}\"\n"
new = ("NVME_BOOT=\"${NVME_BOOT:-1}\"   # 0 = PCIe-Port 0 (interner Speicher) beim Boot auslassen\n"
       "NVME_AUTOLOAD=\"${NVME_AUTOLOAD:-0}\"   # 1 = nvme-Modul automatisch laden (erst nach erfolgreichem Test)\n"
       "CMDLINE=\"${CMDLINE:-console=tty0 earlycon=tty0 fbcon=rotate:0$([[ \"$PCIE_BOOT\" == 1 ]] || echo ' pcie_apple_t8010.disable=1')$([[ \"$NVME_BOOT\" == 1 ]] || echo ' pcie_apple_t8010.skip_ports=0x1')}\"\n")
if new not in s:
    if s.count(old) != 1: sys.exit("CMDLINE-Anker fehlt")
    s = s.replace(old, new)

old = "    patch_bt \"$mnt\"\n"
new = "    patch_bt \"$mnt\"\n    patch_nvme \"$mnt\"\n"
if new not in s:
    if s.count(old) != 1: sys.exit("patch_bt-Aufruf fehlt")
    s = s.replace(old, new)

old = "# Laden (iPhone 7): Ladechip Tigris"
new = ("# Interner Speicher (iPhone 7): nvme-Modul in der Testphase NICHT automatisch laden –\n"
       "# erst per SSH: modprobe nvme (hängt der Controller, bleibt das System bedienbar)\n"
       "patch_nvme() {\n"
       "    local m=\"$1\"\n"
       "    " + SU + " mkdir -p \"$m/etc/modprobe.d\"\n"
       "    if [[ \"$NVME_AUTOLOAD\" == 1 ]]; then\n"
       "        " + SU + " rm -f \"$m/etc/modprobe.d/nvme-test.conf\"\n"
       "    else\n"
       "        echo 'blacklist nvme' | " + SU + " tee \"$m/etc/modprobe.d/nvme-test.conf\" >/dev/null\n"
       "        c_info \"NVMe: Modul gesperrt (Test: per SSH 'modprobe nvme'; NVME_AUTOLOAD=1 hebt das auf)\"\n"
       "    fi\n"
       "}\n\n"
       "# Laden (iPhone 7): Ladechip Tigris")
if new not in s:
    if s.count(old) != 1: sys.exit("Tigris-Anker fehlt")
    s = s.replace(old, new, 1)
p.write_text(s)
print("build ok")

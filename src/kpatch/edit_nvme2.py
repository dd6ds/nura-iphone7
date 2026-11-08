#!/usr/bin/env python3
# NVMe Runde 2 (Erkenntnisse vom iPhone):
#  - Befehlsnummern ohne Generationszähler (skip_cid_gen) + identify_cns wie beim Apple-T2 -> nötig
#  - Controller meldet SGL-Unterstützung, stürzt bei SGL-Befehlen (>8 KiB) aber ab -> SGL abschalten
import pathlib, sys
T = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12"

def sub(path, old, new):
    p = T / path; s = p.read_text()
    if new in s: return
    if s.count(old) != 1: sys.exit(f"{path}: Anker {s.count(old)}x: {old[:70]!r}")
    p.write_text(s.replace(old, new))

sub("drivers/nvme/host/pci.c",
    "\t\t.driver_data = NVME_QUIRK_APPLE_EMBEDDED |\n"
    "\t\t\t\tNVME_QUIRK_SINGLE_VECTOR |\n"
    "\t\t\t\tNVME_QUIRK_SHARED_TAGS, },\n",
    "\t\t.driver_data = NVME_QUIRK_APPLE_EMBEDDED |\n"
    "\t\t\t\tNVME_QUIRK_SINGLE_VECTOR |\n"
    "\t\t\t\tNVME_QUIRK_SHARED_TAGS |\n"
    "\t\t\t\tNVME_QUIRK_SKIP_CID_GEN |\n"
    "\t\t\t\tNVME_QUIRK_IDENTIFY_CNS, },\n")
sub("drivers/nvme/host/core.c",
    "\tctrl->sgls = le32_to_cpu(id->sgls);\n",
    "\tctrl->sgls = le32_to_cpu(id->sgls);\n"
    "\t/* Apple embedded NVMe meldet SGL, stürzt bei SGL-Datenzeigern aber ab */\n"
    "\tif (ctrl->quirks & NVME_QUIRK_APPLE_EMBEDDED)\n"
    "\t\tctrl->sgls = 0;\n")
print("nvme2 ok")

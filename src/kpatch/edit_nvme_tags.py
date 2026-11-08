#!/usr/bin/env python3
# NVMe: Befehls-Tags < 36 halten (Befund: Tags 52/54 bekamen nie einen Interrupt -> 30-s-Timeouts;
# Sandcastle nutzt ebenfalls nur 36 Tags, MAX_SGL_TAG 36)
import pathlib, sys
p = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12/drivers/nvme/host/pci.c"
s = p.read_text()
old = ("\t\t/* Befehls-Tag = NVMMU-Tag: alle Tags (inkl. Admin) müssen < 64 bleiben */\n"
       "\t\tdev->q_depth = min_t(u32, dev->q_depth, APPLE_NVMMU_TAGS);\n")
new = ("\t\t/*\n\t\t * Befehls-Tag = NVMMU-Tag. Der Controller bedient nur Tags < 36 zuverlässig\n"
       "\t\t * (darüber fehlen die Interrupts); Sandcastle nutzt ebenso 36. Mit SHARED_TAGS\n"
       "\t\t * belegt Admin 0..31, I/O bekommt 32..35.\n\t\t */\n"
       "\t\tdev->q_depth = min_t(u32, dev->q_depth, 36);\n")
if new not in s:
    if s.count(old) != 1: sys.exit("Anker fehlt")
    s = s.replace(old, new)
p.write_text(s)
print("tags ok")

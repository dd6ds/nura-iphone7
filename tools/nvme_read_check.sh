#!/bin/sh
# NVMe nur lesend prüfen: Sektorgröße, GPT, APFS-Magie, Lesetempo (als root auf dem iPhone)
D=/dev/nvme0n1
for b in /dev/nvme0n*; do [ -b "$b" ] && blockdev --setro "$b"; done
echo "Sektor/phys: $(blockdev --getss $D) / $(blockdev --getpbsz $D)"
printf 'APFS-Magie p1: '; dd if=${D}p1 bs=4096 count=1 2>/dev/null | dd bs=1 skip=32 count=4 2>/dev/null; echo
sfdisk -d $D 2>/dev/null
echo "-- Lesetempo (256 MiB, direkt)"
dd if=${D}p1 of=/dev/null bs=1M count=256 iflag=direct 2>&1 | tail -1
dmesg | grep -iE "nvme|serror|timeout" | tail -5

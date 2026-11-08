#!/bin/sh
# Check NVMe read-only: sector size, GPT, APFS magic, read speed (as root on the iPhone)
D=/dev/nvme0n1
for b in /dev/nvme0n*; do [ -b "$b" ] && blockdev --setro "$b"; done
echo "Sektor/phys: $(blockdev --getss $D) / $(blockdev --getpbsz $D)"
printf 'APFS-Magie p1: '; dd if=${D}p1 bs=4096 count=1 2>/dev/null | dd bs=1 skip=32 count=4 2>/dev/null; echo
sfdisk -d $D 2>/dev/null
echo "-- read speed (256 MiB, direct)"
dd if=${D}p1 of=/dev/null bs=1M count=256 iflag=direct 2>&1 | tail -1
dmesg | grep -iE "nvme|serror|timeout" | tail -5

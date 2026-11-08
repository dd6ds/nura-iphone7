#!/bin/sh
# NVMe sustained read test (READ only): 2 GiB in one go + repeated checksum of a 256 MiB area
D=/dev/nvme0n1p1
for b in /dev/nvme0n*; do [ -b "$b" ] && blockdev --setro "$b"; done
echo 64 > /sys/block/nvme0n1/queue/nr_requests 2>/dev/null
echo "-- 2 GiB direkt ab 4 GiB"
dd if=$D of=/dev/null bs=1M count=2048 skip=4096 iflag=direct 2>&1 | tail -1
echo "-- checksum 256 MiB from 10 GiB, twice (must match)"
a=$(dd if=$D bs=1M count=256 skip=10240 iflag=direct 2>/dev/null | md5sum)
b=$(dd if=$D bs=1M count=256 skip=10240 iflag=direct 2>/dev/null | md5sum)
echo "$a"; echo "$b"; [ "$a" = "$b" ] && echo "   gleich" || echo "   UNTERSCHIEDLICH"
echo "Zustand: $(cat /sys/class/nvme/nvme0/state)"
dmesg | grep -iE "nvme|NVMMU" | tail -3

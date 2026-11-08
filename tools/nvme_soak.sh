#!/bin/sh
# NVMe-Dauerlesetest (nur LESEN): 2 GiB am Stück + Prüfsummen-Wiederholung eines 256-MiB-Bereichs
D=/dev/nvme0n1p1
for b in /dev/nvme0n*; do [ -b "$b" ] && blockdev --setro "$b"; done
echo 64 > /sys/block/nvme0n1/queue/nr_requests 2>/dev/null
echo "-- 2 GiB direkt ab 4 GiB"
dd if=$D of=/dev/null bs=1M count=2048 skip=4096 iflag=direct 2>&1 | tail -1
echo "-- Prüfsumme 256 MiB ab 10 GiB, zweimal (muss gleich sein)"
a=$(dd if=$D bs=1M count=256 skip=10240 iflag=direct 2>/dev/null | md5sum)
b=$(dd if=$D bs=1M count=256 skip=10240 iflag=direct 2>/dev/null | md5sum)
echo "$a"; echo "$b"; [ "$a" = "$b" ] && echo "   gleich" || echo "   UNTERSCHIEDLICH"
echo "Zustand: $(cat /sys/class/nvme/nvme0/state)"
dmesg | grep -iE "nvme|NVMMU" | tail -3

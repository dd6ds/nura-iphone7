#!/bin/sh
# Restart NVMe after a crash without rebooting and load it with extra quirks (as root).
#   nvme_retry.en.sh [quirks]   default: skip_cid_gen,identify_cns
Q="${1:-skip_cid_gen,identify_cns}"
modprobe -r nvme 2>/dev/null
H=/sys/bus/platform/drivers/pcie-apple-t8010
echo "-- rebind PCIe host (Wi-Fi briefly gone)"
echo 610000000.pcie > $H/unbind; sleep 2
echo 610000000.pcie > $H/bind; sleep 3
dmesg | grep -E "port0: (link|SART)" | tail -3
echo "-- modprobe nvme quirks=106b:2002:$Q"
modprobe nvme "quirks=106b:2002:$Q"
for i in $(seq 1 20); do ls /dev/nvme0n1 >/dev/null 2>&1 && break; sleep 1; done
for b in /dev/nvme0n*; do [ -b "$b" ] && blockdev --setro "$b"; done
sleep 5
dmesg | grep -iE "nvme" | grep -v "Buffer I/O" | tail -8
echo "-- Lesetest"
for o in 0 6 7 100 5000 100000; do
  if dd if=/dev/nvme0n1 of=/dev/null bs=4096 skip=$o count=8 iflag=direct 2>/dev/null; then echo "LBA $o ok"; else echo "LBA $o FEHLER"; fi
done
printf 'APFS-Magie p1: '; dd if=/dev/nvme0n1p1 bs=4096 count=1 iflag=direct 2>/dev/null | dd bs=1 skip=32 count=4 2>/dev/null; echo
dd if=/dev/nvme0n1p1 of=/dev/null bs=1M count=256 iflag=direct 2>&1 | tail -1
cat /sys/class/nvme/nvme0/state 2>/dev/null

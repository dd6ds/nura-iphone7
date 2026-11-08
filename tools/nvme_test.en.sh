#!/bin/sh
# NVMe test on the iPhone (as root). READ only – all namespaces are made read-only immediately.
#   nvme_test.en.sh [quirks] [io_queue_depth]
#   default: Apple T2 quirks skip_cid_gen,identify_cns and queue depth 32
Q="${1-skip_cid_gen,identify_cns}"
QD="${2:-32}"
echo "== $(uname -v)"
for d in /sys/bus/pci/devices/*; do printf '%s %s %s\n' "${d##*/}" "$(cat $d/vendor)" "$(cat $d/device)"; done
[ -e /sys/bus/pci/devices/0000:01:00.0 ] || { echo "no device behind port 0 – aborting"; exit 1; }
# do not let blkid/udev loose on all namespaces in parallel
udevadm control --stop-exec-queue 2>/dev/null
echo "-- modprobe nvme quirks=106b:2002:$Q io_queue_depth=$QD"
if [ -n "$Q" ]; then modprobe nvme "quirks=106b:2002:$Q" io_queue_depth=$QD
else modprobe nvme io_queue_depth=$QD; fi
for i in $(seq 1 30); do ls /dev/nvme0n1 >/dev/null 2>&1 && break; sleep 1; done
for b in /dev/nvme0n*; do [ -b "$b" ] && blockdev --setro "$b"; done
dmesg | grep -iE "nvme" | grep -v "Buffer I/O" | tail -8
echo "-- read test (one at a time, sequential)"
for o in 0 6 7 100 5000 100000 1000000; do
  if dd if=/dev/nvme0n1 of=/dev/null bs=4096 skip=$o count=8 iflag=direct 2>/dev/null; then echo "LBA $o ok"; else echo "LBA $o FEHLER"; break; fi
done
printf 'APFS magic p1 (should be NXSB): '; dd if=/dev/nvme0n1p1 bs=4096 count=1 iflag=direct 2>/dev/null | dd bs=1 skip=32 count=4 2>/dev/null; echo
echo "-- Lesetempo 256 MiB"
dd if=/dev/nvme0n1p1 of=/dev/null bs=1M count=256 iflag=direct 2>&1 | tail -1
echo "Zustand: $(cat /sys/class/nvme/nvme0/state 2>/dev/null)"
udevadm control --start-exec-queue 2>/dev/null
lsblk -o NAME,SIZE,RO,TYPE 2>/dev/null | grep -E "nvme|NAME"

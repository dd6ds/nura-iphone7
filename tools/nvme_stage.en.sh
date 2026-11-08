#!/bin/sh
# NVMe load in stages (READ only). If the controller drops out, the last stage shows the trigger.
# Before: the nvme_test.en.sh load step (or this script loads it itself).
Q="${Q-}"; QD="${QD:-32}"   # since r112 the Apple quirks are built into the kernel
if [ ! -e /dev/nvme0n1 ]; then
  udevadm control --stop-exec-queue 2>/dev/null
  if [ -n "$Q" ]; then modprobe nvme "quirks=106b:2002:$Q" io_queue_depth=$QD
  else modprobe nvme io_queue_depth=$QD; fi
  for i in $(seq 1 30); do ls /dev/nvme0n1 >/dev/null 2>&1 && break; sleep 1; done
fi
for b in /dev/nvme0n*; do [ -b "$b" ] && blockdev --setro "$b"; done
D=/dev/nvme0n1p1; Q1=/sys/block/nvme0n1/queue
ok() { [ "$(cat /sys/class/nvme/nvme0/state)" = live ] && echo "   -> ok" || { echo "   -> CONTROLLER $(cat /sys/class/nvme/nvme0/state)"; exit 1; }; }
st() { echo "== Stufe $1: $2"; }
echo "max_hw_sectors_kb=$(cat $Q1/max_hw_sectors_kb) nr_requests=$(cat $Q1/nr_requests)"
echo 1 > $Q1/nr_requests 2>/dev/null
dmesg | grep -E "Apple-NVMe|NVMMU" | tail -3
printf 'APFS magic p1 (should be NXSB): '; dd if=$D bs=4K count=1 iflag=direct 2>/dev/null | dd bs=1 skip=32 count=4 2>/dev/null; echo
st 1 "4K einzeln, 200x"; dd if=$D of=/dev/null bs=4K count=200 iflag=direct 2>&1 | tail -1; ok
st 1b "8K einzeln, 200x"; dd if=$D of=/dev/null bs=8K count=200 iflag=direct 2>&1 | tail -1; ok
st 2 "32K einzeln, 200x"; dd if=$D of=/dev/null bs=32K count=200 iflag=direct 2>&1 | tail -1; ok
st 3 "64K einzeln, 100x"; dd if=$D of=/dev/null bs=64K count=100 iflag=direct 2>&1 | tail -1; ok
st 4 "128K einzeln, 100x"; dd if=$D of=/dev/null bs=128K count=100 iflag=direct 2>&1 | tail -1; ok
a=$(dd if=$D bs=4K count=1 iflag=direct 2>/dev/null | md5sum); b=$(dd if=$D bs=128K count=1 iflag=direct 2>/dev/null | head -c 4096 | md5sum)
[ "$a" = "$b" ] && echo "   Datenvergleich 4K/128K: gleich" || echo "   Datenvergleich 4K/128K: UNTERSCHIEDLICH"
echo 4 > $Q1/nr_requests 2>/dev/null
st 5 "1M (=8x128K, 4 parallel), 32x"; dd if=$D of=/dev/null bs=1M count=32 iflag=direct 2>&1 | tail -1; ok
echo 32 > $Q1/nr_requests 2>/dev/null
st 6 "1M (up to 32 in parallel), 64x"; dd if=$D of=/dev/null bs=1M count=64 iflag=direct 2>&1 | tail -1; ok
st 7 "buffered 256M (readahead)"; dd if=$D of=/dev/null bs=1M count=256 2>&1 | tail -1; ok
echo "ALLE STUFEN OK"

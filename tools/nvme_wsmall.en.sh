#!/bin/sh
# Small NVMe write test in the free area behind the APFS container (as root, start via systemd-run)
QD="${QD:-32}"
D=/dev/nvme0n1
OFF=$((4882944 * 4096 + 268435456))     # 256 MiB after the start of the future p2
echo "== $(date +%T) reloading nvme (io_queue_depth=$QD)"
modprobe -r nvme; sleep 1
modprobe nvme io_queue_depth=$QD
for i in $(seq 1 30); do [ -b ${D}p1 ] && break; sleep 1; done
blockdev --setro ${D}p1; blockdev --setrw $D
dmesg | grep "Apple-NVMe: Daten" | tail -1
head -c 1048576 /dev/urandom > /dev/shm/w1
for bs in 4096 131072; do
  t0=$(date +%s)
  dd if=/dev/shm/w1 of=$D bs=$bs seek=$((OFF / bs)) oflag=direct conv=fsync 2>&1 | tail -1
  r=$(dd if=$D bs=$bs skip=$((OFF / bs)) count=$((1048576 / bs)) iflag=direct 2>/dev/null | md5sum)
  w=$(md5sum < /dev/shm/w1)
  echo "bs=$bs 1 MiB: $([ "$r" = "$w" ] && echo GLEICH || echo UNTERSCHIEDLICH), $(( $(date +%s) - t0 )) s"
done
dmesg | grep -iE "nvme.*timeout|nvme.*error" | tail -5
echo "== done $(date +%T)"

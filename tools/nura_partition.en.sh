#!/bin/sh
# Create the Linux partition on internal storage – AFTER tools/ios_resize.en.sh (as root on the iPhone).
#   nura_partition.en.sh check       check APFS size, show the plan (read-only)
#   nura_partition.en.sh writetest   write/read test in the freed area BEHIND the APFS container
#   nura_partition.en.sh gpt         partition table: p1 at container size, p2 "Nura" (Linux) after it
#   nura_partition.en.sh mkfs        create and test ext4 on p2
set -eu
D=/dev/nvme0n1
DIR="$(dirname "$0")"
SS=4096
LAST=$(python3 -c "import os,struct;f=os.open('$D',os.O_RDONLY);h=os.pread(f,$SS,$SS);print(struct.unpack_from('<Q',h,48)[0])")
NB=$(python3 "$DIR/apfs_info.en.py" ${D}p1 | sed -n 's/^BLOCKS=//p')
[ -n "$NB" ] || { echo "APFS container not readable"; exit 1; }
P1END=$((6 + NB - 1))
P2START=$(( (P1END + 1 + 255) / 256 * 256 ))     # align to 1 MiB
P2SECT=$((LAST - P2START + 1))
plan() {
  echo "APFS container: $NB blocks ($((NB * SS / 1000000)) MB)"
  echo "Plan: p1 6..$P1END (APFS)  |  p2 $P2START..$LAST = $((P2SECT * SS / 1000000)) MB (Nura)"
}
case "${1:-check}" in
check)
  plan; python3 "$DIR/gpt_info.en.py" $D
  [ "$P2SECT" -gt 1000000 ] || { echo "Container is not shrunk (yet) – run tools/ios_resize.en.sh first"; exit 1; }
  ;;
writetest)
  plan
  [ "$P2SECT" -gt 1000000 ] || { echo "no free area"; exit 1; }
  blockdev --setrw $D
  T=/dev/shm/nvme-wtest.bin   # RAM instead of the NBD rootfs (NBD stalls with heavy I/O)
  head -c 67108864 /dev/urandom > $T
  W=$(md5sum < $T | cut -d' ' -f1)
  for bs in 4096 32768 131072 1048576; do
    off=$((P2START * SS + 268435456))   # 256 MiB after the start of the free area
    dd if=$T of=$D bs=$bs seek=$((off / bs)) oflag=direct conv=fsync 2>/dev/null
    R=$(dd if=$D bs=$bs skip=$((off / bs)) count=$((67108864 / bs)) iflag=direct 2>/dev/null | md5sum | cut -d' ' -f1)
    [ "$W" = "$R" ] && echo "write/read 64 MiB with bs=$bs: OK" || { echo "bs=$bs: ERROR ($W != $R)"; exit 1; }
  done
  echo "-- speed (write 256 MiB direct)"
  dd if=/dev/zero of=$D bs=1M count=256 seek=$((P2START * SS / 1048576 + 512)) oflag=direct conv=fsync 2>&1 | tail -1
  rm -f $T
  python3 "$DIR/apfs_info.en.py" ${D}p1     # the iOS container must still be readable unchanged
  echo "Zustand: $(cat /sys/class/nvme/nvme0/state)"
  ;;
gpt)
  plan
  [ "$P2SECT" -gt 1000000 ] || { echo "no free area"; exit 1; }
  sfdisk -d $D > /tmp/gpt-vorher.txt
  cp /tmp/gpt-vorher.txt "/root/gpt-vorher-$(date +%s).txt" 2>/dev/null || true
  # p1 keeps type, UUID and name – only the size follows the container
  awk -v sz="$NB" '/^\/dev\/nvme0n1p1 /{sub(/size= *[0-9]+/,"size=" sz)}1' /tmp/gpt-vorher.txt > /tmp/gpt-neu.txt
  echo "${D}p2 : start=$P2START, size=$P2SECT, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name=\"Nura\"" >> /tmp/gpt-neu.txt
  echo "--- new:"; cat /tmp/gpt-neu.txt
  blockdev --setrw $D
  sfdisk --no-reread $D < /tmp/gpt-neu.txt
  partx -u $D 2>/dev/null || blockdev --rereadpt $D 2>/dev/null || true
  python3 "$DIR/gpt_info.en.py" $D
  python3 "$DIR/apfs_info.en.py" ${D}p1
  ;;
mkfs)
  [ -b ${D}p2 ] || { echo "${D}p2 missing"; exit 1; }
  blockdev --setrw ${D}p2
  mkfs.ext4 -F -b 4096 -L nura ${D}p2
  mkdir -p /mnt/nura && mount ${D}p2 /mnt/nura
  dd if=/dev/urandom of=/mnt/nura/test.bin bs=1M count=128 conv=fsync 2>&1 | tail -1
  a=$(md5sum < /mnt/nura/test.bin); sync; echo 3 > /proc/sys/vm/drop_caches
  b=$(md5sum < /mnt/nura/test.bin); [ "$a" = "$b" ] && echo "Dateitest OK" || echo "Dateitest FEHLER"
  rm /mnt/nura/test.bin; df -h /mnt/nura; umount /mnt/nura
  ;;
esac

#!/bin/sh
# Linux-Partition auf dem internen Speicher anlegen – NACH tools/ios_resize.sh (als root auf dem iPhone).
#   nura_partition.sh check       APFS-Größe prüfen, Plan anzeigen (nur lesen)
#   nura_partition.sh writetest   Schreib-/Lesetest im frei gewordenen Bereich HINTER dem APFS-Container
#   nura_partition.sh gpt         Partitionstabelle: p1 auf Containergröße, p2 "Nura" (Linux) dahinter
#   nura_partition.sh mkfs        ext4 auf p2 anlegen und testen
set -eu
D=/dev/nvme0n1
DIR="$(dirname "$0")"
SS=4096
LAST=$(python3 -c "import os,struct;f=os.open('$D',os.O_RDONLY);h=os.pread(f,$SS,$SS);print(struct.unpack_from('<Q',h,48)[0])")
NB=$(python3 "$DIR/apfs_info.py" ${D}p1 | sed -n 's/^BLOCKS=//p')
[ -n "$NB" ] || { echo "APFS-Container nicht lesbar"; exit 1; }
P1END=$((6 + NB - 1))
P2START=$(( (P1END + 1 + 255) / 256 * 256 ))     # auf 1 MiB ausrichten
P2SECT=$((LAST - P2START + 1))
plan() {
  echo "APFS-Container: $NB Blöcke ($((NB * SS / 1000000)) MB)"
  echo "Plan: p1 6..$P1END (APFS)  |  p2 $P2START..$LAST = $((P2SECT * SS / 1000000)) MB (Nura)"
}
case "${1:-check}" in
check)
  plan; python3 "$DIR/gpt_info.py" $D
  [ "$P2SECT" -gt 1000000 ] || { echo "Container ist (noch) nicht verkleinert – erst tools/ios_resize.sh"; exit 1; }
  ;;
writetest)
  plan
  [ "$P2SECT" -gt 1000000 ] || { echo "kein freier Bereich"; exit 1; }
  blockdev --setrw $D
  T=/dev/shm/nvme-wtest.bin   # RAM statt NBD-Rootfs (NBD stockt bei viel I/O)
  head -c 67108864 /dev/urandom > $T
  W=$(md5sum < $T | cut -d' ' -f1)
  for bs in 4096 32768 131072 1048576; do
    off=$((P2START * SS + 268435456))   # 256 MiB hinter dem Anfang des freien Bereichs
    dd if=$T of=$D bs=$bs seek=$((off / bs)) oflag=direct conv=fsync 2>/dev/null
    R=$(dd if=$D bs=$bs skip=$((off / bs)) count=$((67108864 / bs)) iflag=direct 2>/dev/null | md5sum | cut -d' ' -f1)
    [ "$W" = "$R" ] && echo "Schreiben/Lesen 64 MiB mit bs=$bs: OK" || { echo "bs=$bs: FEHLER ($W != $R)"; exit 1; }
  done
  echo "-- Tempo (256 MiB direkt schreiben)"
  dd if=/dev/zero of=$D bs=1M count=256 seek=$((P2START * SS / 1048576 + 512)) oflag=direct conv=fsync 2>&1 | tail -1
  rm -f $T
  python3 "$DIR/apfs_info.py" ${D}p1     # iOS-Container muss unverändert lesbar sein
  echo "Zustand: $(cat /sys/class/nvme/nvme0/state)"
  ;;
gpt)
  plan
  [ "$P2SECT" -gt 1000000 ] || { echo "kein freier Bereich"; exit 1; }
  sfdisk -d $D > /tmp/gpt-vorher.txt
  cp /tmp/gpt-vorher.txt "/root/gpt-vorher-$(date +%s).txt" 2>/dev/null || true
  # p1 behält Typ, UUID und Namen – nur die Größe passt sich dem Container an
  awk -v sz="$NB" '/^\/dev\/nvme0n1p1 /{sub(/size= *[0-9]+/,"size=" sz)}1' /tmp/gpt-vorher.txt > /tmp/gpt-neu.txt
  echo "${D}p2 : start=$P2START, size=$P2SECT, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name=\"Nura\"" >> /tmp/gpt-neu.txt
  echo "--- neu:"; cat /tmp/gpt-neu.txt
  blockdev --setrw $D
  sfdisk --no-reread $D < /tmp/gpt-neu.txt
  partx -u $D 2>/dev/null || blockdev --rereadpt $D 2>/dev/null || true
  python3 "$DIR/gpt_info.py" $D
  python3 "$DIR/apfs_info.py" ${D}p1
  ;;
mkfs)
  [ -b ${D}p2 ] || { echo "${D}p2 fehlt"; exit 1; }
  blockdev --setrw ${D}p2
  mkfs.ext4 -F -b 4096 -L nura ${D}p2
  mkdir -p /mnt/nura && mount ${D}p2 /mnt/nura
  dd if=/dev/urandom of=/mnt/nura/test.bin bs=1M count=128 conv=fsync 2>&1 | tail -1
  a=$(md5sum < /mnt/nura/test.bin); sync; echo 3 > /proc/sys/vm/drop_caches
  b=$(md5sum < /mnt/nura/test.bin); [ "$a" = "$b" ] && echo "Dateitest OK" || echo "Dateitest FEHLER"
  rm /mnt/nura/test.bin; df -h /mnt/nura; umount /mnt/nura
  ;;
esac

#!/bin/sh
# Laufendes Rootfs (NBD) auf die interne Partition nvme0n1p2 kopieren (als root auf dem iPhone).
# Per Bind-Mount nur das Root-Dateisystem selbst – ohne /proc, /sys, /dev, /run usw.
#   nura_copy_root.sh          kopieren + fstab
#   nura_copy_root.sh fstab    nur fstab/Abschluss (Kopie schon da)
set -u
P=/dev/nvme0n1p2
SRC=/mnt/rootsrc; DST=/mnt/nura
mkdir -p $SRC $DST
mountpoint -q $SRC || mount --bind -o ro / $SRC
mountpoint -q $DST || mount $P $DST
if [ "${1:-}" != fstab ]; then
  echo "== $(date +%T) Kopiere $(du -sh $SRC 2>/dev/null | cut -f1) …"
  # Rückgabewert ignorieren: cp meldet "recursion detected" für /mnt/nura (gewollt ausgelassen)
  cp -a $SRC/. $DST/ || echo "(cp meldete Warnungen – siehe oben)"
fi
sync
rm -rf $DST/tmp/* $DST/var/tmp/* 2>/dev/null
rmdir $DST/mnt/rootsrc 2>/dev/null; mkdir -p $DST/mnt/nura
UUID=$(blkid -s UUID -o value $P)
# fstab: Root = interne Partition, keine NBD-/boot-Partition
cat > $DST/etc/fstab <<EOF
# <file system> <mount point> <type> <options> <dump> <pass>
# Nura auf dem internen Speicher (nvme0n1p2, Partition "Nura")
UUID=$UUID / ext4 defaults,noatime 0 1
EOF
echo "nura-internal $(date -Iseconds)" > $DST/etc/nura-root-source
sync
echo "== $(date +%T) fertig. UUID=$UUID"
du -sh $DST 2>/dev/null; df -h $DST | tail -1
cat $DST/etc/fstab
ls $DST
umount $DST; umount $SRC

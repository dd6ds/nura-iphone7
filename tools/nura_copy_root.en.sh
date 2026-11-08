#!/bin/sh
# Copy the running rootfs (NBD) to the internal partition nvme0n1p2 (as root on the iPhone).
# Via bind mount only the root file system itself – without /proc, /sys, /dev, /run etc.
#   nura_copy_root.en.sh          copy + fstab
#   nura_copy_root.en.sh fstab    only fstab/finishing (copy already there)
set -u
P=/dev/nvme0n1p2
SRC=/mnt/rootsrc; DST=/mnt/nura
mkdir -p $SRC $DST
mountpoint -q $SRC || mount --bind -o ro / $SRC
mountpoint -q $DST || mount $P $DST
if [ "${1:-}" != fstab ]; then
  echo "== $(date +%T) Kopiere $(du -sh $SRC 2>/dev/null | cut -f1) …"
  # Ignore the return value: cp reports "recursion detected" for /mnt/nura (intentionally skipped)
  cp -a $SRC/. $DST/ || echo "(cp reported warnings – see above)"
fi
sync
rm -rf $DST/tmp/* $DST/var/tmp/* 2>/dev/null
rmdir $DST/mnt/rootsrc 2>/dev/null; mkdir -p $DST/mnt/nura
UUID=$(blkid -s UUID -o value $P)
# fstab: root = internal partition, no NBD/boot partition
cat > $DST/etc/fstab <<EOF
# <file system> <mount point> <type> <options> <dump> <pass>
# Nura on internal storage (nvme0n1p2, partition "Nura")
UUID=$UUID / ext4 defaults,noatime 0 1
EOF
echo "nura-internal $(date -Iseconds)" > $DST/etc/nura-root-source
sync
echo "== $(date +%T) done. UUID=$UUID"
du -sh $DST 2>/dev/null; df -h $DST | tail -1
cat $DST/etc/fstab
ls $DST
umount $DST; umount $SRC

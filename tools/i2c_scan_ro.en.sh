#!/bin/sh
# I2C overview (root, on the iPhone): buses, bound devices, read test of known ADT addresses.
# Read only (i2cget/i2cdump -r), writes nothing.
echo "== Buses"
for b in /sys/bus/i2c/devices/i2c-*; do
  echo "$(basename $b): $(cat $b/name 2>/dev/null) ($(readlink -f $b/device 2>/dev/null | sed 's|.*/||'))"
done
echo "== Devices"
for d in /sys/bus/i2c/devices/[0-9]*-*; do
  [ -e "$d" ] || continue
  drv=$(basename "$(readlink -f $d/driver 2>/dev/null)" 2>/dev/null)
  echo "$(basename $d): $(cat $d/name 2>/dev/null) driver=${drv:--}"
done
command -v i2cget >/dev/null || { echo "i2c-tools missing"; exit 0; }
# ADT: i2c2 als 0x29, convoy 0x21, cs35l26 0x40; i2c3 mic-temp 0x54/0x56
for b in 0 1 2 3; do
  [ -e /dev/i2c-$b ] || continue
  for a in 0x21 0x29 0x40 0x54 0x56; do
    v=$(i2cget -y -f $b $a 0x00 b 2>/dev/null) && echo "i2c-$b $a reg0 = $v"
  done
done

#!/bin/sh
# I2C-Controller-Diagnose (root, auf dem iPhone): PMGR-Zustand i2c0..3, Pins, Register.
# BUS=2 ON=1 schaltet die Power-Domain von i2c2 ein (sonst nur lesen).
BUS=${BUS:-2}
cd /tmp
for i in 0 1 2 3; do
  echo "-- PMGR i2c$i"; python3 pmgr_ps.py $((0x801a8 + 8 * i)) | head -1
done
echo "-- Pins"
case $BUS in 2) P="132 133";; 3) P="41 42";; 0) P="196 197";; 1) P="39 40";; esac
for p in $P; do python3 pin_dump.py 0x20f100000 $p $p 2>/dev/null; done
OFF=$((0x801a8 + 8 * BUS))
[ "${ON:-0}" = 1 ] && python3 pmgr_ps.py $OFF on
st=$(python3 pmgr_ps.py $OFF | head -1 | sed 's/.*ist=//')
if [ "$st" = "0xf" ]; then
  B=$((0x20a110000 + 0x1000 * BUS))
  echo "-- Register i2c$BUS ($(printf %#x $B))"
  for r in 0x00 0x04 0x0c 0x14 0x18 0x1c 0x28; do
    printf '%s: ' $r; python3 peek.py $(printf %#x $((B + r))) | tail -1
  done
else
  echo "i2c$BUS ist aus (ist=$st) – Register nicht gelesen"
fi
grep -E ' (232|233|234|235) ' /proc/interrupts | head

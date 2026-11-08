#!/bin/bash
# Set the I2S signal path mca0 -> codec like iOS (AppleAE2I2SSwitch5 + AppleAE2AOPI2SSwitch1) (root, iPhone).
# Field format of both switches: one register per target, three 5-bit fields (4:0, 12:8, 20:16) = source index,
# 0x18 = free. AP switch 0x20a004000: pinN = index N, audN = 5+N; sources audN = N, pinN = 8+N;
# pin enable index 15+N (bit 4 / bit 0). AOP switch 0x210540000: pinN = N, mcaN = 2+N;
# sources mcaN = N, pinN = 8+N; enable index 15+N. ADT: mca0 i2s_route = ('aud0','pin4',0x30303),
# i2s_route_aop = ('mca1','pin0',0x30303) -> both directions.
P=/tmp
show() { python3 $P/mmio_peek.en.py $1 24 | grep -v ": 0x00181818$" | grep -v ": 0x00000000$"; }
echo "== AP switch before";  show 0x20a004000
echo "== AOP switch before"; show 0x210540000; python3 $P/mmio_peek.en.py 0x210000600 1
[ "${1:-}" = "show" ] && exit 0
# AP: pin4 <- aud0, aud0 <- pin4, enable pin 4
python3 $P/peek.en.py 0x20a004010 0x000000
python3 $P/peek.en.py 0x20a004014 0x0c0c0c
v=$(python3 $P/peek.en.py 0x20a00404c | awk '{print $3}'); python3 $P/peek.en.py 0x20a00404c $(( v | 0x11 ))
# AOP: defaults (reg-defaults), output enable 8, pin0 <- mca1, mca1 <- pin0, enable pin 0
v=$(python3 $P/peek.en.py 0x210000600 | awk '{print $3}'); python3 $P/peek.en.py 0x210000600 $(( v | 0x8 ))
python3 $P/peek.en.py 0x210540008 0x080808
python3 $P/peek.en.py 0x210540000 0x010101
python3 $P/peek.en.py 0x21054000c 0x080808
v=$(python3 $P/peek.en.py 0x21054003c | awk '{print $3}'); python3 $P/peek.en.py 0x21054003c $(( v | 0x11 ))
echo "== after"; show 0x20a004000; show 0x210540000

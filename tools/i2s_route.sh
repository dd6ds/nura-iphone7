#!/bin/bash
# I2S-Signalweg mca0 -> Codec wie iOS (AppleAE2I2SSwitch5 + AppleAE2AOPI2SSwitch1) setzen (root, iPhone).
# Feldformat beider Schalter: Register je Ziel, drei 5-bit-Felder (4:0, 12:8, 20:16) = Quellindex,
# 0x18 = frei. AP-Schalter 0x20a004000: pinN = Index N, audN = 5+N; Quellen audN = N, pinN = 8+N;
# Pin-Freigabe Index 15+N (Bit 4 / Bit 0). AOP-Schalter 0x210540000: pinN = N, mcaN = 2+N;
# Quellen mcaN = N, pinN = 8+N; Freigabe Index 15+N. ADT: mca0 i2s_route = ('aud0','pin4',0x30303),
# i2s_route_aop = ('mca1','pin0',0x30303) -> beide Richtungen.
P=/tmp
show() { python3 $P/mmio_peek.py $1 24 | grep -v ": 0x00181818$" | grep -v ": 0x00000000$"; }
echo "== AP-Schalter vorher";  show 0x20a004000
echo "== AOP-Schalter vorher"; show 0x210540000; python3 $P/mmio_peek.py 0x210000600 1
[ "${1:-}" = "show" ] && exit 0
# AP: pin4 <- aud0, aud0 <- pin4, Pin 4 freigeben
python3 $P/peek.py 0x20a004010 0x000000
python3 $P/peek.py 0x20a004014 0x0c0c0c
v=$(python3 $P/peek.py 0x20a00404c | awk '{print $3}'); python3 $P/peek.py 0x20a00404c $(( v | 0x11 ))
# AOP: Vorgaben (reg-defaults), Ausgangsfreigabe 8, pin0 <- mca1, mca1 <- pin0, Pin 0 freigeben
v=$(python3 $P/peek.py 0x210000600 | awk '{print $3}'); python3 $P/peek.py 0x210000600 $(( v | 0x8 ))
python3 $P/peek.py 0x210540008 0x080808
python3 $P/peek.py 0x210540000 0x010101
python3 $P/peek.py 0x21054000c 0x080808
v=$(python3 $P/peek.py 0x21054003c | awk '{print $3}'); python3 $P/peek.py 0x21054003c $(( v | 0x11 ))
echo "== nachher"; show 0x20a004000; show 0x210540000

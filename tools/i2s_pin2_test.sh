#!/bin/bash
# Test: Codec-Ports laut ADT (hawk_active/asp_active = i2sA('pin2')) -> AP-Schalter Pin 2 freigeben
# (Index 17 = 0x20a004044) und pin2 <- aud0 (mca0, MCLK 12 MHz) bzw. aud0 <- pin2 routen,
# danach PLL/RCO des CS42L71 prüfen (root, auf dem iPhone).
P=/tmp
python3 $P/peek.py 0x20a004008 0x000000          # pin2 <- aud0
v=$(python3 $P/peek.py 0x20a004044 | awk '{print $3}'); python3 $P/peek.py 0x20a004044 $(( v | 0x11 ))
MCLK=1 bash $P/cs42l71_test.sh $P/cs42l71_pll.py 2>&1 | grep -E "PLL|RCO|Chip"

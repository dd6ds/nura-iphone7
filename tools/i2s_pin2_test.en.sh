#!/bin/bash
# Test: codec ports per ADT (hawk_active/asp_active = i2sA('pin2')) -> enable AP switch pin 2
# (index 17 = 0x20a004044) and route pin2 <- aud0 (mca0, MCLK 12 MHz) or aud0 <- pin2,
# then check the CS42L71 PLL/RCO (root, on the iPhone).
P=/tmp
python3 $P/peek.en.py 0x20a004008 0x000000          # pin2 <- aud0
v=$(python3 $P/peek.en.py 0x20a004044 | awk '{print $3}'); python3 $P/peek.en.py 0x20a004044 $(( v | 0x11 ))
MCLK=1 bash $P/cs42l71_test.en.sh $P/cs42l71_pll.en.py 2>&1 | grep -E "PLL|RCO|Chip"

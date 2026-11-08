#!/bin/bash
# Fully initialise mca0 and mca2 (12 MHz each), set routes, then check the CS42L71 PLL/RCO (root, iPhone).
P=/tmp
python3 $P/mca_init.en.py 0
python3 $P/mca_init.en.py 2
bash $P/i2s_route.en.sh >/dev/null
python3 $P/peek.en.py 0x20a004008 0x020202                        # pin2 <- aud2 (mca2)
v=$(python3 $P/peek.en.py 0x20a004044 | awk '{print $3}'); python3 $P/peek.en.py 0x20a004044 $(( v | 0x11 ))
MCLK=1 bash $P/cs42l71_test.en.sh $P/cs42l71_pll.en.py 2>&1 | grep -E "PLL|RCO|Chip"

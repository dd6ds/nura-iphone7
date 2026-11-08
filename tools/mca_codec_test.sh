#!/bin/bash
# mca0 und mca2 voll initialisieren (je 12 MHz), Routen setzen, dann PLL/RCO des CS42L71 prüfen (root, iPhone).
P=/tmp
python3 $P/mca_init.py 0
python3 $P/mca_init.py 2
bash $P/i2s_route.sh >/dev/null
python3 $P/peek.py 0x20a004008 0x020202                        # pin2 <- aud2 (mca2)
v=$(python3 $P/peek.py 0x20a004044 | awk '{print $3}'); python3 $P/peek.py 0x20a004044 $(( v | 0x11 ))
MCLK=1 bash $P/cs42l71_test.sh $P/cs42l71_pll.py 2>&1 | grep -E "PLL|RCO|Chip"

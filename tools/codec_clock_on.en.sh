#!/bin/bash
# Switch on the codec clock (12 MHz MCLK) like iOS and test the CS42L71 RCO (root, on the iPhone).
# Steps: PMGR mca0 on -> NCO0 12 MHz -> MCA0 MCLK control 0x50 (nclk==f: 0x10, output: 0x40)
#        -> i2s-switch aud0 -> pin4 (fields = source index 0, output enable in reg 19) -> check RCO
set -e
P=/tmp
echo "== switch before"; python3 $P/mmio_peek.en.py 0x20a004000 24 | grep -v ": 0x00181818$" || true
python3 $P/pmgr_ps.en.py 0x80178 on
python3 $P/nco_set.en.py 0 12000000 | head -1
python3 $P/peek.en.py 0x20a002000 0x50
python3 $P/peek.en.py 0x20a004010 0x0
v=$(python3 $P/peek.en.py 0x20a00404c | awk '{print $3}')
python3 $P/peek.en.py 0x20a00404c $(( v | 0x11 ))
MCLK=1 bash $P/cs42l71_test.en.sh $P/cs42l71_rco.en.py 2>&1 | grep -E "RCO|Seite 3"

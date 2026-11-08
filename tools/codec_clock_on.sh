#!/bin/bash
# Codec-Takt (12 MHz MCLK) wie iOS einschalten und RCO des CS42L71 testen (root, auf dem iPhone).
# Schritte: PMGR mca0 an -> NCO0 12 MHz -> MCA0 MCLK-Steuerung 0x50 (nclk==f: 0x10, Ausgang: 0x40)
#           -> i2s-switch aud0 -> pin4 (Felder = Quellindex 0, Ausgang frei in Reg 19) -> RCO prüfen
set -e
P=/tmp
echo "== switch vorher"; python3 $P/mmio_peek.py 0x20a004000 24 | grep -v ": 0x00181818$" || true
python3 $P/pmgr_ps.py 0x80178 on
python3 $P/nco_set.py 0 12000000 | head -1
python3 $P/peek.py 0x20a002000 0x50
python3 $P/peek.py 0x20a004010 0x0
v=$(python3 $P/peek.py 0x20a00404c | awk '{print $3}')
python3 $P/peek.py 0x20a00404c $(( v | 0x11 ))
MCLK=1 bash $P/cs42l71_test.sh $P/cs42l71_rco.py 2>&1 | grep -E "RCO|Seite 3"

#!/bin/sh
# Query I2C bus 2/3 without a Linux driver (root, on the iPhone) – READ ONLY.
# Bus 2: ALS ct821 0x29, Taptic AD81006 0x21, speaker amp cs35l26 0x40; bus 3: ica60 0x54/0x56
cd /tmp
python3 pmgr_ps.en.py 0x801b8 on | tail -1
python3 pmgr_ps.en.py 0x801c0 on | tail -1
echo "== Bus 2";  python3 i2c_poll.en.py 2 --scan
for a in 0x29 0x21; do python3 i2c_poll.en.py 2 $a 0 32; done
python3 i2c_poll.en.py 2 0x40 0 16 --w16
echo "== Bus 3";  python3 i2c_poll.en.py 3 --scan
for a in 0x54 0x56; do python3 i2c_poll.en.py 3 $a 0 16; done

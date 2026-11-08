#!/bin/bash
# Maggie load test with AOP power/clock (MAGGIE_AOP=1); output to /tmp/maggie_aop.log on the laptop
K="-i $HOME/.ssh/id_ed25519_nura_iphone -o BatchMode=yes -o IdentitiesOnly=yes"
D="$(dirname "$0")"
scp -q $K "$D/maggie_load.en.py" "$D/peek.en.py" user@172.16.42.1:/tmp/
ssh $K user@172.16.42.1 'pkill -f "[g]pioset.*interactive" ; echo 147147 | sudo -S -p "" env MAGGIE_AOP=1 MAGGIE_CS=${MAGGIE_CS:-1} timeout 20 python3 /tmp/maggie_load.en.py ~user/audio/maggie_d10.bin; echo 147147 | sudo -S -p "" pkill -f "[g]pioset.*interactive"; gpioinfo -c gpiochip0 26 2>/dev/null | tail -1' 2>&1 | grep -v Pseudo

#!/bin/bash
# Reads Maggie-related registers (read-only): AOP MCLK, AOP pin 20, AP pins CRESET(0x16) CDONE(0x1a) CS1(0xb1) CS0(0x83)
K="-i $HOME/.ssh/id_ed25519_nura_iphone -o BatchMode=yes -o IdentitiesOnly=yes"
scp -q $K "$(dirname "$0")/peek.en.py" user@172.16.42.1:/tmp/peek.en.py
ssh $K user@172.16.42.1 'for a in 0x210c02000 0x2100f0050 0x20f100058 0x20f100068 0x20f1002c4 0x20f10020c; do echo 147147 | sudo -S -p "" python3 /tmp/peek.en.py $a; done' 2>&1 | grep -v Pseudo

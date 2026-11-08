#!/bin/bash
# nura-autobright auf das laufende iPhone kopieren und starten (vom Laptop aus, ohne Neubau).
set -e
cd "$(dirname "$0")/.."
KEY="${KEY:-$HOME/.ssh/id_ed25519_nura_iphone}"; IP="${IP:-172.16.42.1}"; PW="${PW:-147147}"
O=(-i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=8)
scp -q "${O[@]}" tools/nura-autobright.py tools/i2c_poll.py tools/nura-autobright.service "user@$IP:/tmp/"
ssh "${O[@]}" "user@$IP" "echo $PW | sudo -S -p '' sh -c '
  install -Dm755 /tmp/nura-autobright.py /usr/local/sbin/nura-autobright
  install -Dm644 /tmp/i2c_poll.py /usr/local/sbin/nura_i2c.py
  install -Dm644 /tmp/nura-autobright.service /etc/systemd/system/nura-autobright.service
  systemctl daemon-reload && systemctl enable --now nura-autobright && systemctl restart nura-autobright
  sleep 4; systemctl is-active nura-autobright; journalctl -u nura-autobright -b --no-pager -o cat | tail -5'"

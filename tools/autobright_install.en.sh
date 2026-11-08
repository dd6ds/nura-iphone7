#!/bin/bash
# Copy nura-autobright to the running iPhone and start it (from the laptop, without a rebuild).
set -e
cd "$(dirname "$0")/.."
KEY="${KEY:-$HOME/.ssh/id_ed25519_nura_iphone}"; IP="${IP:-172.16.42.1}"; PW="${PW:-147147}"
O=(-i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=8)
scp -q "${O[@]}" tools/nura-autobright.en.py tools/i2c_poll.en.py tools/nura-autobright.service "user@$IP:/tmp/"
ssh "${O[@]}" "user@$IP" "echo $PW | sudo -S -p '' sh -c '
  install -Dm755 /tmp/nura-autobright.en.py /usr/local/sbin/nura-autobright
  install -Dm644 /tmp/i2c_poll.en.py /usr/local/sbin/nura_i2c.py
  install -Dm644 /tmp/nura-autobright.service /etc/systemd/system/nura-autobright.service
  systemctl daemon-reload && systemctl enable --now nura-autobright && systemctl restart nura-autobright
  sleep 4; systemctl is-active nura-autobright; journalctl -u nura-autobright -b --no-pager -o cat | tail -5'"

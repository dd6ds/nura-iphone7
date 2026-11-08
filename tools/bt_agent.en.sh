#!/bin/sh
# Bluetooth pairing agent on the iPhone (as user) for N seconds: discoverable + pairable,
# confirms pairing requests automatically with "yes" (use only with your own devices!).
# Usage: bt_agent.en.sh [seconds]
T="${1:-120}"
bluetoothctl power on >/dev/null
bluetoothctl pairable on >/dev/null
bluetoothctl discoverable on >/dev/null
{ echo "agent DisplayYesNo"; echo "default-agent"
  i=0; while [ $i -lt "$T" ]; do sleep 2; echo yes; i=$((i + 2)); done
  echo "discoverable off"; echo quit; } \
  | bluetoothctl 2>&1 | tr '\r' '\n' | grep -E -i 'passkey|paired|bonded|authoriz|Connected: yes' | tail -20

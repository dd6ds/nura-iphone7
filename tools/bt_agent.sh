#!/bin/sh
# Bluetooth-Kopplungs-Agent auf dem iPhone (als user) für N Sekunden: sichtbar + koppelbar,
# bestätigt Kopplungsanfragen automatisch mit "yes" (nur für eigene Geräte verwenden!).
# Aufruf: bt_agent.sh [sekunden]
T="${1:-120}"
bluetoothctl power on >/dev/null
bluetoothctl pairable on >/dev/null
bluetoothctl discoverable on >/dev/null
{ echo "agent DisplayYesNo"; echo "default-agent"
  i=0; while [ $i -lt "$T" ]; do sleep 2; echo yes; i=$((i + 2)); done
  echo "discoverable off"; echo quit; } \
  | bluetoothctl 2>&1 | tr '\r' '\n' | grep -E -i 'passkey|paired|bonded|authoriz|Connected: yes' | tail -20

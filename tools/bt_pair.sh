#!/bin/sh
# Bluetooth-Gerät suchen, koppeln, vertrauen, verbinden (auf dem iPhone, als user).
# Aufruf: bt_pair.sh <MAC> [Suchdauer s]   – das Gerät muss sichtbar bzw. im Kopplungsmodus sein.
MAC="$1"; T="${2:-20}"
[ -n "$MAC" ] || { echo "Aufruf: $0 <MAC> [sekunden]"; exit 1; }
bluetoothctl power on >/dev/null
bluetoothctl pairable on >/dev/null
echo "-- Suche ${T} s …"
bluetoothctl --timeout "$T" scan on >/dev/null 2>&1
bluetoothctl devices | grep -i "$MAC" || echo "(nicht gefunden – trotzdem Kopplung versuchen)"
echo "-- Koppeln"
bluetoothctl --agent NoInputNoOutput --timeout 30 pair "$MAC" 2>&1 | grep -v -E '^\[|Agent' | tail -5
bluetoothctl trust "$MAC" | tail -1
echo "-- Verbinden"
bluetoothctl --timeout 15 connect "$MAC" 2>&1 | tail -3
bluetoothctl info "$MAC" | grep -E 'Name|Paired|Trusted|Connected|UUID' | head -20

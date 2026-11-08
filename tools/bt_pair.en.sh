#!/bin/sh
# Find, pair, trust and connect a Bluetooth device (on the iPhone, as user).
# Usage: bt_pair.en.sh <MAC> [scan time s]   – the device must be discoverable / in pairing mode.
MAC="$1"; T="${2:-20}"
[ -n "$MAC" ] || { echo "Usage: $0 <MAC> [seconds]"; exit 1; }
bluetoothctl power on >/dev/null
bluetoothctl pairable on >/dev/null
echo "-- Scanning ${T} s …"
bluetoothctl --timeout "$T" scan on >/dev/null 2>&1
bluetoothctl devices | grep -i "$MAC" || echo "(not found – trying to pair anyway)"
echo "-- Pairing"
bluetoothctl --agent NoInputNoOutput --timeout 30 pair "$MAC" 2>&1 | grep -v -E '^\[|Agent' | tail -5
bluetoothctl trust "$MAC" | tail -1
echo "-- Connecting"
bluetoothctl --timeout 15 connect "$MAC" 2>&1 | tail -3
bluetoothctl info "$MAC" | grep -E 'Name|Paired|Trusted|Connected|UUID' | head -20

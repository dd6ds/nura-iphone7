#!/bin/sh
# Bluetooth-Audio-Test (auf dem iPhone, als user): mit gekoppeltem Gerät verbinden, A2DP-Sink suchen,
# 2 s Testton (440 Hz) abspielen. Aufruf: bt_audio_test.sh <MAC>
MAC="$1"
[ -n "$MAC" ] || { echo "Aufruf: $0 <MAC>"; exit 1; }
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
bluetoothctl trust "$MAC" >/dev/null
bluetoothctl --timeout 15 connect "$MAC" 2>&1 | tail -1
sleep 3
SINK=$(pactl list short sinks | awk '/bluez/{print $2; exit}')
echo "Bluetooth-Sink: ${SINK:-keiner}"
pactl list short cards | grep bluez
[ -n "$SINK" ] || exit 1
python3 - <<'PY'
import math, struct, wave
with wave.open("/tmp/ton440.wav", "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
    w.writeframes(b"".join(struct.pack("<hh", v, v) for v in
                  (int(8000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(88200))))
PY
paplay -d "$SINK" /tmp/ton440.wav && echo "Testton gespielt"

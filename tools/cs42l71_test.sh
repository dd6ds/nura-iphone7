#!/bin/bash
# CS42L71 abfragen, Maggie dabei im Reset (root, auf dem iPhone)
#   cs42l71_test.sh [skript.py args…]   Standard: SPIv2-Probe
#   MCLK=1 cs42l71_test.sh …            vorher AOP-MCLK (0x48) + AOP-GPIO 20 einschalten (wie maggie_load)
#   MAGGIE=1 cs42l71_test.sh …          Maggie NICHT im Reset halten, sondern laden (MISO dann geteilt!)
pkill -f "[g]pioset -c gpiochip0" 2>/dev/null; sleep 0.2
if [ "${MAGGIE:-0}" = 1 ]; then
  timeout 20 python3 /tmp/maggie_load.py /home/user/audio/maggie_d10.bin | grep -E "CDONE nachher"; G=
else
  gpioset -c gpiochip0 22=0 >/dev/null 2>&1 & G=$!; sleep 0.3
fi
if [ "${MCLK:-0}" = 1 ]; then
  python3 /tmp/peek.py 0x210c02000 0x48
  v=$(python3 /tmp/peek.py 0x2100f0050 | awk '{print $3}'); python3 /tmp/peek.py 0x2100f0050 $(( v | 1 ))
  sleep 0.05
fi
if [ $# -gt 0 ]; then python3 "$@"; else python3 /tmp/cs42l71_v2probe.py; fi
[ -n "$G" ] && kill $G 2>/dev/null

#!/bin/bash
# Taschenlampen-Test (root, auf dem iPhone): ADT isp function-torch_enable = GPIO 0xb0 (AP-Pin 176).
# Nach 5 s Vorlauf dreimal 2 s an / 1 s aus; danach sicher aus.
sleep 5
for i in 1 2 3; do
  echo "an ($i)"; timeout 2 gpioset -c gpiochip0 176=1 2>/dev/null
  echo "aus";     timeout 1 gpioset -c gpiochip0 176=0 2>/dev/null
done
gpioset -c gpiochip0 176=0 >/dev/null 2>&1 & p=$!; sleep 0.2; kill $p 2>/dev/null
python3 /tmp/pin_dump.py 0x20f100000 0xb0 0xb0

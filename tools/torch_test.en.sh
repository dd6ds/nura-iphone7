#!/bin/bash
# Torch test (root, on the iPhone): ADT isp function-torch_enable = GPIO 0xb0 (AP pin 176).
# After a 5 s lead-in: three times 2 s on / 1 s off; then safely off.
sleep 5
for i in 1 2 3; do
  echo "an ($i)"; timeout 2 gpioset -c gpiochip0 176=1 2>/dev/null
  echo "off";     timeout 1 gpioset -c gpiochip0 176=0 2>/dev/null
done
gpioset -c gpiochip0 176=0 >/dev/null 2>&1 & p=$!; sleep 0.2; kill $p 2>/dev/null
python3 /tmp/pin_dump.en.py 0x20f100000 0xb0 0xb0

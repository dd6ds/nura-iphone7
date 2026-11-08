#!/bin/bash
# PMU-GPIOs anzeigen (root, auf dem iPhone): Chip-Liste + Leitungen des PMU-GPIO-Controllers
gpiodetect
c=$(gpiodetect | grep -iE "pmic|900" | head -1 | cut -d' ' -f1)
[ -n "$c" ] && gpioinfo -c "$c"
# Rohregister lesen: PMU 0x74 auf i2c-1, GPIO-Konfig ab 0x900 (Offsets laut DT apple,gpio-offsets)
for o in 0x00 0x02 0x04 0x06 0x08 0x0a 0x0c 0x0e 0x10 0x12 0x14 0x16 0x18; do
  python3 /tmp/i2c_peek.py 1 0x74 $((0x900 + o)) 2 16
done

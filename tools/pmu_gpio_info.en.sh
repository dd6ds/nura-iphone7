#!/bin/bash
# Show PMU GPIOs (root, on the iPhone): chip list + lines of the PMU GPIO controller
gpiodetect
c=$(gpiodetect | grep -iE "pmic|900" | head -1 | cut -d' ' -f1)
[ -n "$c" ] && gpioinfo -c "$c"
# Read raw registers: PMU 0x74 on i2c-1, GPIO config from 0x900 (offsets per DT apple,gpio-offsets)
for o in 0x00 0x02 0x04 0x06 0x08 0x0a 0x0c 0x0e 0x10 0x12 0x14 0x16 0x18; do
  python3 /tmp/i2c_peek.en.py 1 0x74 $((0x900 + o)) 2 16
done

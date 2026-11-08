#!/bin/bash
# Compare codec queries with and without an active Maggie (root, on the iPhone): MISO is shared.
pkill -f "[g]pioset -c gpiochip0 --interactive" 2>/dev/null; sleep 0.2
echo "== Maggie in reset (CRESET=0)"
gpioset -c gpiochip0 22=0 >/dev/null 2>&1 & G=$!; sleep 0.3
python3 /tmp/codec_probe.en.py
kill $G 2>/dev/null; sleep 0.2
echo "== Maggie configured"
timeout 20 python3 /tmp/maggie_load.en.py /home/user/audio/maggie_d10.bin | grep CDONE
python3 /tmp/codec_probe.en.py

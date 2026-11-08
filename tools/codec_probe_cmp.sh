#!/bin/bash
# Codec-Abfrage mit und ohne aktive Maggie vergleichen (root, auf dem iPhone): MISO wird geteilt.
pkill -f "[g]pioset -c gpiochip0 --interactive" 2>/dev/null; sleep 0.2
echo "== Maggie im Reset (CRESET=0)"
gpioset -c gpiochip0 22=0 >/dev/null 2>&1 & G=$!; sleep 0.3
python3 /tmp/codec_probe.py
kill $G 2>/dev/null; sleep 0.2
echo "== Maggie konfiguriert"
timeout 20 python3 /tmp/maggie_load.py /home/user/audio/maggie_d10.bin | grep CDONE
python3 /tmp/codec_probe.py

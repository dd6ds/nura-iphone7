#!/bin/sh
# Suche nach Maggies Strom-/Freigabeleitung unter den AOP-GPIO-Ausgängen, die gerade low sind:
# je Leitung kurz high, Maggie laden, CDONE prüfen, Leitung wieder low. (root)
LINES="${LINES:-3 5 7 20 25 38 39 40 41}"
L=/home/user/audio/maggie_load.py
pkill gpioset 2>/dev/null; sleep 0.2
for n in $LINES; do
  gpioset -c gpiochip1 $n=1 > /dev/null 2>&1 &       # hält die Leitung high, bis beendet
  gs=$!
  sleep 0.3
  out=$(python3 $L 2>&1 | grep -E "CDONE nachher")
  echo "AOP-GPIO $n high: $out"
  pkill -f "gpioset -c gpiochip0" 2>/dev/null       # CRESET-Halter von maggie_load
  kill $gs 2>/dev/null; wait $gs 2>/dev/null
  case "$out" in *"= 1 "*) echo "TREFFER: AOP-GPIO $n (bleibt high)"; gpioset -c gpiochip1 $n=1 >/dev/null 2>&1 & exit 0;; esac
  gpioset -c gpiochip1 $n=0 > /dev/null 2>&1 & r=$!; sleep 0.2; kill $r 2>/dev/null   # zurück auf low
done
echo "kein Treffer"

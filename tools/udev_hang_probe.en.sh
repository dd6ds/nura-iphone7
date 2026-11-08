#!/bin/sh
# restart systemd-udevd and, if it hangs, show what it is waiting for (root, on the iPhone)
systemctl restart --no-block systemd-udevd
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    sleep 2
    st=$(systemctl is-active systemd-udevd)
    echo "t=$((i*2))s udevd: $st"
    [ "$st" = active ] && break
done
for p in $(pgrep -x systemd-udevd) $(pgrep -f "udevd-worker|\(udev-worker\)"); do
    echo "== PID $p $(cat /proc/$p/comm) state=$(awk '/^State/{print $2}' /proc/$p/status) wchan=$(cat /proc/$p/wchan 2>/dev/null)"
    cat /proc/$p/stack 2>/dev/null | head -12
done
ps -eo pid,stat,wchan:32,args | awk '$2 ~ /D/' | head -10

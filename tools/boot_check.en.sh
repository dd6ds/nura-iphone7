#!/bin/sh
# Quick check after booting (on the iPhone as root)
echo "== $(uname -v) | up $(cut -d. -f1 /proc/uptime) s"
echo "-- Kernel-Kommandozeile: $(cat /proc/cmdline)"
echo "-- PCIe/WLAN"
dmesg | grep -E "port2: link|brcmf_c_preinit_dcmds|Falling back" | cut -c1-120
ip -br link show wlan0 2>/dev/null || echo "wlan0 missing"
echo "-- udevd"
journalctl -b -o short-monotonic --no-pager | grep -E "systemd-udevd.service: (start operation timed out|State|Failed)" | cut -c1-120 || true
echo "-- Dienste"
for s in hx-touchd tigris-charge NetworkManager; do printf '  %-16s %s\n' "$s" "$(systemctl is-active $s)"; done
journalctl -u tigris-charge -b --no-pager -o cat | tail -2
echo "-- Touch-IRQs: $(grep hx-touch /proc/interrupts | awk '{print $2+$3}')"

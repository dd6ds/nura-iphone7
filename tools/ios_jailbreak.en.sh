#!/bin/bash
# Boot iOS (not Nura) with palera1n in rootless mode – for research under iOS (e.g. the AOP IORegistry).
# Changes neither Nura nor the iOS system permanently (rootless = files only under /var/jb).
# First: put the iPhone into DFU mode (power + volume down 8 s, release power, volume down 5–10 s).
# Then on the iPhone: open the palera1n app -> install Sileo -> install "OpenSSH" in Sileo.
# SSH via USB:  iproxy 2222 22 &   ssh -p 2222 mobile@127.0.0.1   (password set in Sileo)
# As in boot.en.sh: run palera1n as root and re-enumerate the DFU device first (USB controller reset),
# otherwise palera1n waits forever for "DFU mode devices".
set -e
P1N="${P1N:-$HOME/.local/bin/palera1n}"
sudo -v
pkill -f '[/]palera1n ' 2>/dev/null && sleep 1 || true
echo "-- re-enable usbmuxd (tools/cleanup.en.sh blocks it for the Nura boot)"
sudo systemctl unmask usbmuxd.service usbmuxd.socket 2>/dev/null || true
sudo systemctl start usbmuxd.socket 2>/dev/null || sudo systemctl start usbmuxd 2>/dev/null || true
command -v iproxy >/dev/null || { echo "-- iproxy fehlt: installiere libusbmuxd-tools"; sudo apt-get install -y libusbmuxd-tools; }

dfu_dev() { for d in /sys/bus/usb/devices/*; do
    [[ "$(cat "$d/idVendor" 2>/dev/null):$(cat "$d/idProduct" 2>/dev/null)" == "05ac:1227" ]] && { echo "$d"; return 0; }
done; return 1; }
if ! dfu_dev >/dev/null; then
    echo "-- No iPhone in DFU mode – please enter DFU now, waiting up to 90 s …"
    for _ in $(seq 1 90); do dfu_dev >/dev/null && break; sleep 1; done
fi
if dev="$(dfu_dev)"; then
    pci="$(basename "$(readlink -f "$dev/../..")" 2>/dev/null)"
    [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]] || pci="$(basename "$(readlink -f "$(readlink -f "$dev")/../../..")")"
    if [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]]; then
        echo "-- Re-enumerating the DFU device (resetting USB controller $pci) …"
        echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind >/dev/null
        sleep 2
        echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind >/dev/null
        for _ in $(seq 1 20); do dfu_dev >/dev/null && break; sleep 0.5; done
        sleep 5
    fi
fi
echo "-- palera1n rootless (iOS with jailbreak)"
sudo "$P1N" --cli -l      # --cli: the text UI (TUI) does not find DFU devices reliably
echo "Done. For Nura later again: tools/cleanup.en.sh && ./boot.en.sh"

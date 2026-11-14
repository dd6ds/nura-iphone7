#!/bin/bash
# iOS (nicht Nura) mit palera1n im rootless-Modus starten – für Forschung unter iOS (z. B. IORegistry des AOP).
# Verändert weder Nura noch das iOS-System dauerhaft (rootless = Dateien nur unter /var/jb).
# Vorher: iPhone in den DFU-Modus bringen (Power + Leiser 8 s, Power los, Leiser 5–10 s).
# Danach am iPhone: palera1n-App öffnen -> Sileo installieren -> in Sileo "OpenSSH" installieren.
# SSH dann über USB:  iproxy 2222 22 &   ssh -p 2222 mobile@127.0.0.1   (Passwort in Sileo festgelegt)
# Wie boot.sh: palera1n als root starten und das DFU-Gerät vorher frisch anmelden (USB-Controller-Reset),
# sonst wartet palera1n endlos auf "DFU mode devices".
set -e
P1N="${P1N:-$HOME/.local/bin/palera1n}"
sudo -v
pkill -f '[/]palera1n ' 2>/dev/null && sleep 1 || true
echo "-- usbmuxd wieder freigeben (tools/cleanup.sh sperrt ihn für den Nura-Start)"
sudo systemctl unmask --runtime usbmuxd.service 2>/dev/null || true   # cleanup.sh sperrt mit --runtime
sudo systemctl unmask usbmuxd.service usbmuxd.socket 2>/dev/null || true
sudo systemctl start usbmuxd.socket 2>/dev/null || sudo systemctl start usbmuxd 2>/dev/null || true
command -v iproxy >/dev/null || { echo "-- iproxy fehlt: installiere libusbmuxd-tools"; sudo apt-get install -y libusbmuxd-tools; }

dfu_dev() { for d in /sys/bus/usb/devices/*; do
    [[ "$(cat "$d/idVendor" 2>/dev/null):$(cat "$d/idProduct" 2>/dev/null)" == "05ac:1227" ]] && { echo "$d"; return 0; }
done; return 1; }
if ! dfu_dev >/dev/null; then
    echo "-- Kein iPhone im DFU-Modus – bitte jetzt DFU herstellen, warte bis zu 90 s …"
    for _ in $(seq 1 90); do dfu_dev >/dev/null && break; sleep 1; done
fi
if dev="$(dfu_dev)"; then
    pci="$(basename "$(readlink -f "$dev/../..")" 2>/dev/null)"
    [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]] || pci="$(basename "$(readlink -f "$(readlink -f "$dev")/../../..")")"
    if [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]]; then
        echo "-- Melde das DFU-Gerät frisch an (USB-Controller $pci zurücksetzen) …"
        echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind >/dev/null
        sleep 2
        echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind >/dev/null
        for _ in $(seq 1 20); do dfu_dev >/dev/null && break; sleep 0.5; done
        sleep 5
    fi
fi
echo "-- palera1n rootless (iOS mit Jailbreak)"
sudo "$P1N" --cli -l      # --cli: die Text-Oberfläche (TUI) findet DFU-Geräte nicht zuverlässig
echo "Fertig. Für Nura später wieder: tools/cleanup.sh && ./boot.sh"

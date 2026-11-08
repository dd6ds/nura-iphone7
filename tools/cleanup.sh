#!/usr/bin/env bash
# =============================================================================
#  cleanup.sh – Laptop zwischen zwei iPhone-Bootversuchen zurücksetzen
#               (ersetzt den Laptop-Neustart)
#
#  1. alte Prozesse beenden (palera1n/checkra1n, Proxy-Tools, Netboot, boot.sh)
#  2. pmbootstrap-Chroots aushängen (pmbootstrap shutdown)
#  3. störende Dienste aus (usbmuxd gesperrt, fwupd, ModemManager)
#     + Kernelmodul apple_mfi_fastcharge entladen/sperren
#  4. USB-Controller (xHCI), an dem das iPhone hängt, neu initialisieren
#     -> behebt den "checkm8 klappt nur direkt nach dem Booten"-Effekt
#
#  Optionen:  --no-usb-reset   Schritt 4 auslassen
#             --all-usb        alle xHCI-Controller zurücksetzen
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PMB="${PMB:-$SCRIPT_DIR/.venv/bin/pmbootstrap}"
USB_RESET=1; ALL_USB=0
for a in "$@"; do
    case "$a" in
        --no-usb-reset) USB_RESET=0 ;;
        --all-usb)      ALL_USB=1 ;;
        -h|--help)      sed -n '2,16p' "$0"; exit 0 ;;
    esac
done

c_info() { printf '\e[1;34m[*]\e[0m %s\n' "$*"; }
c_ok()   { printf '\e[1;32m[+]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m[!]\e[0m %s\n' "$*"; }

sudo -v || exit 1

# --------------------------------------------------------- 1. Prozesse ---
c_info "Beende alte Prozesse …"
PATTERNS=( '/palera1n ' '/checkra1n' 'checkra1n\.' 'pongo_send\.py' 'live_probe\.py'
           'touch_wake_probe\.py' 'vnc_probe\.py' 'nbd-server' 'pmbootstrap netboot'
           '/boot\.sh( |$)' )
# PIDs per pgrep ermitteln und gezielt beenden. Nicht 'sudo pkill -f MUSTER':
# das trifft den eigenen sudo-Prozess (Muster steht in dessen Kommandozeile),
# sudo stirbt per SIGKILL und hinterlässt das Terminal im Raw-Modus.
kill_matching() {   # signal
    local pat pids=""
    for pat in "${PATTERNS[@]}"; do
        pids+=" $(pgrep -f "$pat" 2>/dev/null | tr '\n' ' ')"
    done
    pids="$(tr ' ' '\n' <<<"$pids" | grep -vxE "|$$|$PPID" | sort -u | tr '\n' ' ')"
    [[ -n "${pids// /}" ]] && sudo kill "-$1" $pids 2>/dev/null
    return 0
}
kill_matching TERM
sleep 1
kill_matching KILL
# Prozesse, die noch eine ttyACM (m1n1-Proxy) offen halten
for t in /dev/ttyACM*; do
    [[ -e "$t" ]] && sudo fuser -k "$t" >/dev/null 2>&1 || true
done
c_ok "Prozesse bereinigt."

# ------------------------------------------------------ 2. pmbootstrap ---
if [[ -x "$PMB" ]]; then
    c_info "pmbootstrap shutdown (Chroots/Loop-Devices aushängen) …"
    "$PMB" shutdown >/dev/null 2>&1 && c_ok "Chroots ausgehängt." || c_warn "pmbootstrap shutdown meldete einen Fehler (meist harmlos)."
fi
# Verwaiste Loop-Geräte auf (gelöschte) Nura-Images – sonst scheitert 'pmbootstrap install'
# mit "losetup -d /dev/loopN (lost)"
for dev in $(sudo losetup -a 2>/dev/null | grep -E 'apple-idevice\.img|pmbootstrap' | cut -d: -f1); do
    for part in "$dev"p*; do
        [[ -b "$part" ]] && grep -q "^$part " /proc/mounts && sudo umount -l "$part" 2>/dev/null
    done
    grep -q "^$dev " /proc/mounts && sudo umount -l "$dev" 2>/dev/null
    sudo losetup -d "$dev" 2>/dev/null && c_ok "Loop-Gerät $dev freigegeben." \
        || c_warn "Loop-Gerät $dev ließ sich nicht freigeben (noch in Benutzung?)."
done

# --------------------------------------------------------- 3. Dienste ---
c_info "Störende Dienste anhalten …"
sudo systemctl mask --runtime usbmuxd.service >/dev/null 2>&1 || true
sudo systemctl stop usbmuxd.service usbmuxd.socket >/dev/null 2>&1 || true
sudo pkill -x usbmuxd 2>/dev/null || true
for s in fwupd ModemManager; do
    systemctl is-active --quiet "$s" 2>/dev/null && sudo systemctl stop "$s" >/dev/null 2>&1 || true
done
echo 'install apple_mfi_fastcharge /bin/true' | sudo tee /run/modprobe.d/iphone-nura.conf >/dev/null 2>&1 \
  || { sudo mkdir -p /run/modprobe.d; echo 'install apple_mfi_fastcharge /bin/true' | sudo tee /run/modprobe.d/iphone-nura.conf >/dev/null; }
grep -q '^apple_mfi_fastcharge ' /proc/modules && sudo rmmod apple_mfi_fastcharge 2>/dev/null || true
c_ok "usbmuxd gesperrt, fwupd/ModemManager aus, apple_mfi_fastcharge entladen."

# ------------------------------------------------------ 4. USB-Reset ---
if [[ "$USB_RESET" == "1" ]]; then
    declare -a CTRL=()
    if [[ "$ALL_USB" == "1" ]]; then
        for d in /sys/bus/pci/drivers/xhci_hcd/0000:*; do CTRL+=("$(basename "$d")"); done
    else
        # Controller, an dem ein Apple-Gerät hängt; sonst der des Busses 1
        for dev in /sys/bus/usb/devices/*; do
            [[ "$(cat "$dev/idVendor" 2>/dev/null)" == "05ac" ]] || continue
            pci="$(basename "$(readlink -f "$dev/../..")")"
            [[ "$pci" == 0000:* ]] || pci="$(readlink -f "$dev" | grep -oE '0000:[0-9a-f:.]+' | tail -n1)"
            [[ -n "$pci" ]] && CTRL+=("$pci")
        done
        [[ ${#CTRL[@]} -eq 0 ]] && CTRL+=("$(basename "$(readlink -f /sys/bus/usb/devices/usb1/..)")")
    fi
    mapfile -t CTRL < <(printf '%s\n' "${CTRL[@]}" | sort -u)
    for pci in "${CTRL[@]}"; do
        [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]] || continue
        c_info "Setze USB-Controller $pci zurück (Kamera/BT/Touchscreen des Laptops kurz weg) …"
        echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind >/dev/null
        sleep 2
        echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind >/dev/null
        sleep 3
        c_ok "USB-Controller $pci neu initialisiert."
    done
fi

# --------------------------------------------------------- Status ---
echo
c_info "Status:"
echo "  Apple-Geräte am USB : $(lsusb | grep -ci '05ac:') ($(lsusb | grep -i '05ac:' | sed 's/.*ID 05ac:\([0-9a-f]*\).*/\1/' | tr '\n' ' '))"
echo "  usbmuxd             : $(systemctl is-active usbmuxd 2>/dev/null)"
echo "  palera1n-Prozesse   : $(pgrep -fc '/palera1n ' 2>/dev/null || true)"
echo "  nbd-server          : $(pgrep -fc nbd-server 2>/dev/null || true)"
echo "  apple_mfi_fastcharge: $(grep -q "^apple_mfi_fastcharge " /proc/modules && echo GELADEN \(stört!\) || echo entladen)"
echo "  fwupd / ModemManager: $(systemctl is-active fwupd 2>/dev/null) / $(systemctl is-active ModemManager 2>/dev/null)"
echo
[[ -t 0 ]] && stty sane 2>/dev/null   # falls ein beendeter Prozess das Terminal verstellt hat
c_ok "Fertig – jetzt iPhone in DFU bringen und ./boot.sh (bzw. M1N1_PROXY=1 ./boot.sh) starten."

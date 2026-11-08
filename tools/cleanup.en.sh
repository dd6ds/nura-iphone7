#!/usr/bin/env bash
# =============================================================================
#  cleanup.en.sh – reset the laptop between two iPhone boot attempts
#               (replaces rebooting the laptop)
#
#  1. stop old processes (palera1n/checkra1n, proxy tools, netboot, boot.en.sh)
#  2. unmount pmbootstrap chroots (pmbootstrap shutdown)
#  3. stop interfering services (usbmuxd blocked, fwupd, ModemManager)
#     + unload/block kernel module apple_mfi_fastcharge
#  4. reinitialise the USB controller (xHCI) the iPhone is attached to
#     -> fixes the "checkm8 only works right after booting" effect
#
#  Options:   --no-usb-reset   skip step 4
#             --all-usb        reset all xHCI controllers
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
c_info "Stopping old processes …"
PATTERNS=( '/palera1n ' '/checkra1n' 'checkra1n\.' 'pongo_send\.py' 'live_probe\.py'
           'touch_wake_probe\.py' 'vnc_probe\.py' 'nbd-server' 'pmbootstrap netboot'
           '/boot\.sh( |$)' )
# Find PIDs with pgrep and stop them specifically. Not 'sudo pkill -f PATTERN':
# that hits its own sudo process (the pattern is in its command line),
# sudo dies via SIGKILL and leaves the terminal in raw mode.
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
# Processes that still hold a ttyACM (m1n1 proxy) open
for t in /dev/ttyACM*; do
    [[ -e "$t" ]] && sudo fuser -k "$t" >/dev/null 2>&1 || true
done
c_ok "Processes cleaned up."

# ------------------------------------------------------ 2. pmbootstrap ---
if [[ -x "$PMB" ]]; then
    c_info "pmbootstrap shutdown (unmounting chroots/loop devices) …"
    "$PMB" shutdown >/dev/null 2>&1 && c_ok "Chroots unmounted." || c_warn "pmbootstrap shutdown reported an error (usually harmless)."
fi
# Orphaned loop devices on (deleted) Nura images – otherwise 'pmbootstrap install' fails
# with "losetup -d /dev/loopN (lost)"
for dev in $(sudo losetup -a 2>/dev/null | grep -E 'apple-idevice\.img|pmbootstrap' | cut -d: -f1); do
    for part in "$dev"p*; do
        [[ -b "$part" ]] && grep -q "^$part " /proc/mounts && sudo umount -l "$part" 2>/dev/null
    done
    grep -q "^$dev " /proc/mounts && sudo umount -l "$dev" 2>/dev/null
    sudo losetup -d "$dev" 2>/dev/null && c_ok "Loop device $dev released." \
        || c_warn "Loop device $dev could not be released (still in use?)."
done

# --------------------------------------------------------- 3. Dienste ---
c_info "Stopping interfering services …"
sudo systemctl mask --runtime usbmuxd.service >/dev/null 2>&1 || true
sudo systemctl stop usbmuxd.service usbmuxd.socket >/dev/null 2>&1 || true
sudo pkill -x usbmuxd 2>/dev/null || true
for s in fwupd ModemManager; do
    systemctl is-active --quiet "$s" 2>/dev/null && sudo systemctl stop "$s" >/dev/null 2>&1 || true
done
echo 'install apple_mfi_fastcharge /bin/true' | sudo tee /run/modprobe.d/iphone-nura.conf >/dev/null 2>&1 \
  || { sudo mkdir -p /run/modprobe.d; echo 'install apple_mfi_fastcharge /bin/true' | sudo tee /run/modprobe.d/iphone-nura.conf >/dev/null; }
grep -q '^apple_mfi_fastcharge ' /proc/modules && sudo rmmod apple_mfi_fastcharge 2>/dev/null || true
c_ok "usbmuxd blocked, fwupd/ModemManager off, apple_mfi_fastcharge unloaded."

# ------------------------------------------------------ 4. USB-Reset ---
if [[ "$USB_RESET" == "1" ]]; then
    declare -a CTRL=()
    if [[ "$ALL_USB" == "1" ]]; then
        for d in /sys/bus/pci/drivers/xhci_hcd/0000:*; do CTRL+=("$(basename "$d")"); done
    else
        # Controller with an Apple device attached; otherwise that of bus 1
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
        c_info "Resetting USB controller $pci (laptop camera/BT/touchscreen briefly gone) …"
        echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind >/dev/null
        sleep 2
        echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind >/dev/null
        sleep 3
        c_ok "USB controller $pci reinitialised."
    done
fi

# --------------------------------------------------------- Status ---
echo
c_info "Status:"
echo "  Apple devices on USB: $(lsusb | grep -ci '05ac:') ($(lsusb | grep -i '05ac:' | sed 's/.*ID 05ac:\([0-9a-f]*\).*/\1/' | tr '\n' ' '))"
echo "  usbmuxd             : $(systemctl is-active usbmuxd 2>/dev/null)"
echo "  palera1n-Prozesse   : $(pgrep -fc '/palera1n ' 2>/dev/null || true)"
echo "  nbd-server          : $(pgrep -fc nbd-server 2>/dev/null || true)"
echo "  apple_mfi_fastcharge: $(grep -q "^apple_mfi_fastcharge " /proc/modules && echo LOADED \(interferes!\) || echo unloaded)"
echo "  fwupd / ModemManager: $(systemctl is-active fwupd 2>/dev/null) / $(systemctl is-active ModemManager 2>/dev/null)"
echo
[[ -t 0 ]] && stty sane 2>/dev/null   # in case a terminated process messed up the terminal
c_ok "Done – now put the iPhone into DFU and start ./boot.en.sh (or M1N1_PROXY=1 ./boot.en.sh)."

#!/usr/bin/env bash
# =============================================================================
#  iPhone (A9/A10) – boot Nura via checkm8 / PongoOS / m1n1 + netboot
#
#  Procedure (Hoolock "pongoOS method"):
#   1. palera1n puts the iPhone into the PongoOS shell via checkm8
#      (with Hoolock's Pongo.bin)
#   2. m1n1-linux.bin is sent to PongoOS and started with 'bootm'
#   3. m1n1 starts kernel + initramfs, the initramfs waits for netboot
#   4. 'pmbootstrap netboot serve' serves the rootfs via NBD over USB
#   5. ssh user@172.16.42.1
#
#  Must be repeated on EVERY start – iOS stays untouched.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/out"
VENV="${VENV:-$SCRIPT_DIR/.venv}"
PMB="${PMB:-$VENV/bin/pmbootstrap}"
PY="${PY:-$VENV/bin/python}"
M1N1_PROXY="${M1N1_PROXY:-0}"               # 1 = boot only m1n1 (USB proxy) instead of Linux
# ROOT=internal: rootfs from internal storage (partition "Nura"), no NBD server needed
# ROOT=netboot : rootfs via NBD from the laptop (previous method, fallback)
if [[ -z "${ROOT:-}" ]]; then
    [[ -f "$OUT/m1n1-linux-internal.bin" ]] && ROOT=internal || ROOT=netboot
fi
if [[ "$M1N1_PROXY" == "1" ]]; then
    PAYLOAD="${PAYLOAD:-$OUT/m1n1.bin}"
elif [[ "$ROOT" == "internal" ]]; then
    PAYLOAD="${PAYLOAD:-$OUT/m1n1-linux-internal.bin}"
else
    PAYLOAD="${PAYLOAD:-$OUT/m1n1-linux.bin}"
fi
PONGO_BIN="${PONGO_BIN:-$OUT/Pongo.bin}"
PONGO_BOOT_CMD="${PONGO_BOOT_CMD:-bootm}"
SKIP_PALERA1N="${SKIP_PALERA1N:-0}"         # 1 = PongoOS is already running
# USB network (CDC-NCM) laptop->iPhone: large NTB blocks overwhelm the iPhone's dwc2
# gadget controller -> packet loss, NBD hangs. 2048 = 1 packet/block.
NCM_TX_MAX="${NCM_TX_MAX:-2048}"
NCM_TX_TIMER="${NCM_TX_TIMER:-0}"
PALERA1N_ARGS="${PALERA1N_ARGS:-}"          # empty = automatic depending on the palera1n version

c_info() { printf '\e[1;34m[*]\e[0m %s\n' "$*"; }
c_ok()   { printf '\e[1;32m[+]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m[!]\e[0m %s\n' "$*"; }
die()    { printf '\e[1;31m[x]\e[0m %s\n' "$*" >&2; exit 1; }

[[ -x "$PMB" && -x "$PY" ]] || die "venv missing – run ./build.en.sh deps first."
[[ -f "$PAYLOAD" ]]   || die "Payload missing: $PAYLOAD – run ./build.en.sh first."
[[ -f "$PONGO_BIN" ]] || die "Pongo.bin missing – run ./build.en.sh bootloader first."

pongo_present() { lsusb -d 05ac:4141 >/dev/null 2>&1; }

sudo -v   # ask for the password once up front

# ------------------------------------------- switch off USB troublemakers ---
# fwupd queries new USB devices and apple-mfi-fastcharge binds to the
# iPhone – both break the checkm8 timing ("did not enter DFU mode").
FWUPD_WAS_ACTIVE=0
if systemctl is-active --quiet fwupd 2>/dev/null; then
    FWUPD_WAS_ACTIVE=1
    c_info "Stopping fwupd during the exploit …"
    sudo systemctl stop fwupd
    sudo systemctl mask --runtime fwupd >/dev/null 2>&1 || true
fi
# Block until the next reboot (otherwise udev reloads it on reconnect):
echo 'install apple_mfi_fastcharge /bin/true' | sudo tee /run/modprobe.d/iphone-nura.conf >/dev/null 2>&1 \
  || { sudo mkdir -p /run/modprobe.d && echo 'install apple_mfi_fastcharge /bin/true' | sudo tee /run/modprobe.d/iphone-nura.conf >/dev/null; }
if grep -q '^apple_mfi_fastcharge ' /proc/modules; then
    c_info "Unloading kernel module apple_mfi_fastcharge …"
    sudo modprobe -r apple_mfi_fastcharge 2>/dev/null || sudo rmmod apple_mfi_fastcharge 2>/dev/null \
      || c_warn "apple_mfi_fastcharge is still attached to the iPhone – briefly unplug the cable and restart the script."
fi
restore_usb() {
    if [[ "$FWUPD_WAS_ACTIVE" == "1" ]]; then
        sudo systemctl unmask --runtime fwupd >/dev/null 2>&1 || true
        sudo systemctl start fwupd >/dev/null 2>&1 || true
    fi
}
trap restore_usb EXIT

# ---------------------------------------------------------- 1. PongoOS ---
if [[ "$SKIP_PALERA1N" != "1" ]] && ! pongo_present; then
    P1N="$(command -v palera1n || true)"
    [[ -z "$P1N" && -x "$HOME/.local/bin/palera1n" ]] && P1N="$HOME/.local/bin/palera1n"
    [[ -n "$P1N" ]] || die "palera1n missing – './build.en.sh deps' installs it."
    c_info "palera1n: $P1N ($("$P1N" --version 2>&1 | grep -m1 -iE 'palera1n|[0-9]+\.[0-9]' || true))"
    if [[ -z "$PALERA1N_ARGS" ]]; then
        P1N_HELP="$("$P1N" --help 2>&1 || true)"   # collect first (pipefail + grep -q = SIGPIPE)
        if [[ "$P1N_HELP" == *--early-exit* ]]; then
            PALERA1N_ARGS="-p"          # v3 (beta): -p = exit after the Pongo upload
        else
            PALERA1N_ARGS="-l -p"       # v2.x: rootless + PongoOS-Shell
        fi
    fi
    # Stop leftovers of earlier runs – two palera1n instances interfere with each other
    if pgrep -f '/palera1n |/checkra1n' >/dev/null; then
        c_warn "Stopping old palera1n/checkra1n processes …"
        pids="$(pgrep -f '/palera1n |/checkra1n' | tr '\n' ' ')"
        [[ -n "${pids// /}" ]] && sudo kill $pids 2>/dev/null || true
        sleep 1
    fi
    # usbmuxd disturbs the checkm8 timing (especially with more iPhones on the bus) –
    # it is not needed for manual DFU entry.
    # udev restarts usbmuxd on every iOS boot -> block it until the next laptop reboot
    sudo systemctl mask --runtime usbmuxd.service >/dev/null 2>&1 || true
    sudo systemctl stop usbmuxd usbmuxd.socket >/dev/null 2>&1 || true
    cat <<'EOF'

  Proven procedure (only ONE iPhone on the laptop!):
    1. Put the iPhone into DFU mode (before or after Enter – the script waits):
       iPhone 7 / 7 Plus : hold power + volume down for 8 s, then release power,
                           keep holding volume down for another 5–10 s
       iPhone SE / 6s    : power + home 8 s, then release power, home 5–10 s
       -> screen stays BLACK; check: lsusb | grep 1227
    2. Enter: the DFU device is freshly re-enumerated, then palera1n starts immediately.
  After "Checkmate" do not touch the iPhone. If no "download mode" appears:
  enter DFU again and restart the script (checkm8 is flaky on A10).

EOF
    read -rp "  Bereit? [Enter] " _

    # Proven (comparing successful/failed runs in the kernel log): checkm8 works
    # when the DFU device is freshly enumerated right before palera1n. Hence: wait for DFU,
    # reset the iPhone's xHCI controller, start palera1n immediately.
    dfu_dev() { for d in /sys/bus/usb/devices/*; do
        [[ "$(cat "$d/idVendor" 2>/dev/null):$(cat "$d/idProduct" 2>/dev/null)" == "05ac:1227" ]] && { echo "$d"; return 0; }
    done; return 1; }
    if [[ "${DFU_REFRESH:-1}" == "1" ]]; then
        if ! dfu_dev >/dev/null; then
            c_warn "No iPhone in DFU mode (05ac:1227) – please enter DFU now, waiting up to 90 s …"
            for _ in $(seq 1 90); do dfu_dev >/dev/null && break; sleep 1; done
        fi
        if dev="$(dfu_dev)"; then
            pci="$(basename "$(readlink -f "$dev/../..")" 2>/dev/null)"
            [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]] || pci="$(basename "$(readlink -f "$(readlink -f "$dev")/../../..")")"
            if [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]]; then
                c_info "Re-enumerating the DFU device (resetting USB controller $pci) …"
                echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind >/dev/null
                sleep 2
                echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind >/dev/null
                for _ in $(seq 1 20); do dfu_dev >/dev/null && break; sleep 0.5; done
                dfu_dev >/dev/null && c_ok "DFU device freshly enumerated." \
                    || c_warn "DFU device did not come back after the reset – enter DFU again."
                # The laptop's camera/touchscreen/BT/fingerprint reader re-enumerate on the same controller
                # re-enumerate – start palera1n only once the bus is quiet (successful run: +4 s)
                c_info "Waiting for the other USB devices to enumerate …"
                sleep "${DFU_SETTLE:-5}"
            fi
        fi
    fi
    # shellcheck disable=SC2086
    c_info "Starte: palera1n $PALERA1N_ARGS -k $(basename "$PONGO_BIN")"
    sudo env PALERA1N_BYPASS_PASSCODE_CHECK=1 "$P1N" $PALERA1N_ARGS -k "$PONGO_BIN" &
    P1N_PID=$!
    c_info "Waiting for PongoOS (USB 05ac:4141) …"
    until pongo_present; do
        if ! kill -0 "$P1N_PID" 2>/dev/null; then
            wait "$P1N_PID" || true
            c_info "palera1n finished – waiting up to 30 s for PongoOS to show up …"
            for _ in $(seq 1 30); do pongo_present && break; sleep 1; done
            pongo_present || die "palera1n finished, but no PongoOS found – start again."
            break
        fi
        sleep 1
    done
    sleep 2
    # stop the whole process chain (sudo -> palera1n -> checkra1n), not just the wrapper
    sudo pkill -f '/palera1n |/checkra1n' 2>/dev/null || true
    wait "$P1N_PID" 2>/dev/null || true
fi
pongo_present || die "PongoOS not found."
c_ok "PongoOS is running."

# ------------------------------------------------------- 2. send m1n1 ---
c_info "Sending m1n1 payload to PongoOS and starting it with '$PONGO_BOOT_CMD' …"
sudo "$PY" "$SCRIPT_DIR/pongo_send.en.py" --file "$PAYLOAD" --cmd "$PONGO_BOOT_CMD"
c_ok "m1n1 started – Linux should now be booting on the iPhone."

# ------------------------------------------------- Proxy-Modus (Analyse) ---
if [[ "$M1N1_PROXY" == "1" ]]; then
    systemctl is-active --quiet ModemManager 2>/dev/null && { c_info "Stopping ModemManager (would grab ttyACM) …"; sudo systemctl stop ModemManager; }
    c_info "Proxy mode: waiting for m1n1 USB serial (/dev/ttyACM*) …"
    DEV=""
    for _ in $(seq 1 60); do
        DEV="$(ls /dev/ttyACM* 2>/dev/null | head -n1 || true)"
        [[ -n "$DEV" ]] && break
        sleep 1
    done
    [[ -n "$DEV" ]] || die "No /dev/ttyACM* – m1n1 proxy not reachable (check dmesg)."
    c_ok "m1n1 proxy on $DEV"
    sleep 2
    M1N1DEVICE="$DEV" "$PY" "$SCRIPT_DIR/research/tools/live_probe.py" \
        || c_warn "live_probe.py ended with an error – log: research/live/probe.log"
    if [[ "${SKIP_PMU_READ:-0}" != "1" ]]; then
        c_info "Reading PMU registers of the touch supply (read-only) …"
        M1N1DEVICE="$DEV" "$PY" "$SCRIPT_DIR/research/tools/pmu_read.py" 2>&1 | grep -v '^TTY>' \
            || c_warn "pmu_read.py ended with an error"
    fi
    if [[ "${SKIP_TOUCH_WAKE:-0}" != "1" ]]; then
        c_info "Touch wake test (release reset, watch IRQ) …"
        M1N1DEVICE="$DEV" "$PY" "$SCRIPT_DIR/research/tools/touch_wake_probe.py" 2>&1 \
            | grep -v '^TTY>' | tee "$SCRIPT_DIR/research/live/touch-wake.log" \
            || c_warn "touch_wake_probe.py ended with an error"
    fi
    c_info "Fertig. Interaktive Shell (sicher):  M1N1DEVICE=$DEV $PY research/tools/safe_shell.py"
    exit 0
fi

# ------------------------------------------------------- 3. Netboot ---
c_info "Waiting for USB networking from the iPhone (172.16.42.x) …"
IFACE=""
for _ in $(seq 1 90); do
    IFACE="$(ip -br -4 a 2>/dev/null | awk '/172\.16\.42\./{print $1; exit}')"
    [[ -n "$IFACE" ]] && break
    sleep 2
done
if [[ -n "$IFACE" ]]; then
    c_ok "USB network on interface $IFACE."
    N="/sys/class/net/$IFACE/cdc_ncm"
    if [[ -d "$N" ]]; then
        echo "$NCM_TX_MAX"   | sudo tee "$N/tx_max" >/dev/null 2>&1 || c_warn "tx_max cannot be set"
        echo "$NCM_TX_TIMER" | sudo tee "$N/tx_timer_usecs" >/dev/null 2>&1 || true
        c_ok "NCM-Tuning: tx_max=$(cat "$N/tx_max") tx_timer_usecs=$(cat "$N/tx_timer_usecs") rx_max=$(cat "$N/rx_max")"
    fi
    sudo ip link set dev "$IFACE" txqueuelen 2000 2>/dev/null || true
    # Record connection statistics (for debugging)
    mkdir -p "$OUT/diag"
    LINKLOG="$OUT/diag/link-$(date +%Y%m%d-%H%M%S).log"
    (
        while ip link show "$IFACE" >/dev/null 2>&1; do
            {
                echo "=== $(date +%T)"
                ip -s link show "$IFACE" | sed -n '3,6p'
                nstat -az TcpRetransSegs TcpExtTCPTimeouts 2>/dev/null | tail -n +2
                ss -tin '( sport = :9999 )' 2>/dev/null | tail -n +2 | tr -s ' ' | cut -c1-200
            } >> "$LINKLOG"
            sleep 10
        done
    ) &
    c_info "Link-Statistik -> $LINKLOG"
    if command -v firewall-cmd >/dev/null && sudo firewall-cmd --state >/dev/null 2>&1; then
        c_warn "firewalld active – putting $IFACE (temporarily) into zone 'trusted'."
        sudo firewall-cmd --zone=trusted --change-interface="$IFACE" >/dev/null || true
    fi
    if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q 'Status: active'; then
        c_warn "ufw active – allowing traffic on $IFACE."
        sudo ufw allow in on "$IFACE" >/dev/null || true
    fi
else
    c_warn "No 172.16.42.x interface seen (the PC may get its IP later)."
    c_warn "Netboot server starts anyway. Check 'dmesg | tail' / 'ip -br a'."
fi

if [[ "$ROOT" == "internal" && "$M1N1_PROXY" != "1" ]]; then
    cat <<EOF

  Nura boots from internal storage (no netboot server needed, this window may be closed).
  SSH over USB:  ssh -i ~/.ssh/id_ed25519_nura_iphone $("$PMB" config user 2>/dev/null || echo user)@172.16.42.1
  Fallback to netboot:  ROOT=netboot ./boot.en.sh

EOF
    exit 0
fi

cat <<EOF

  Netboot server is starting now (keep this window open!).
  As soon as the iPhone has mounted the rootfs, in a second terminal:

      ssh -i ~/.ssh/id_ed25519_nura_iphone $("$PMB" config user 2>/dev/null || echo user)@172.16.42.1
        (without key: password, default 147147)

  Phosh image: operate via VNC (no touchscreen), about 1 min after boot:
      xtigervncviewer 172.16.42.1:5900   (Remmina times out with wayvnc)

  Stop with Ctrl+C (the iPhone then loses its rootfs).

EOF
exec "$PMB" netboot serve

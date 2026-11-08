#!/usr/bin/env bash
# =============================================================================
#  iPhone (A9/A10) – Nura per checkm8 / PongoOS / m1n1 booten + Netboot
#
#  Ablauf (Hoolock-"pongoOS-Methode"):
#   1. palera1n bringt das iPhone per checkm8 in die PongoOS-Shell
#      (mit Hoolocks Pongo.bin)
#   2. m1n1-linux.bin wird an PongoOS geschickt und mit 'bootm' gestartet
#   3. m1n1 startet Kernel + initramfs, initramfs wartet auf Netboot
#   4. 'pmbootstrap netboot serve' liefert das Rootfs per NBD über USB
#   5. ssh user@172.16.42.1
#
#  Muss bei JEDEM Start wiederholt werden – iOS bleibt unangetastet.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/out"
VENV="${VENV:-$SCRIPT_DIR/.venv}"
PMB="${PMB:-$VENV/bin/pmbootstrap}"
PY="${PY:-$VENV/bin/python}"
M1N1_PROXY="${M1N1_PROXY:-0}"               # 1 = nur m1n1 (USB-Proxy) statt Linux booten
# ROOT=internal: Rootfs vom internen Speicher (Partition "Nura"), kein NBD-Server nötig
# ROOT=netboot : Rootfs per NBD vom Laptop (bisheriger Weg, Rückfall)
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
SKIP_PALERA1N="${SKIP_PALERA1N:-0}"         # 1 = PongoOS läuft schon
# USB-Netz (CDC-NCM) Laptop->iPhone: große NTB-Blöcke überfordern den dwc2-
# Gadget-Controller des iPhones -> Paketverluste, NBD hängt. 2048 = 1 Paket/Block.
NCM_TX_MAX="${NCM_TX_MAX:-2048}"
NCM_TX_TIMER="${NCM_TX_TIMER:-0}"
PALERA1N_ARGS="${PALERA1N_ARGS:-}"          # leer = automatisch je nach palera1n-Version

c_info() { printf '\e[1;34m[*]\e[0m %s\n' "$*"; }
c_ok()   { printf '\e[1;32m[+]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m[!]\e[0m %s\n' "$*"; }
die()    { printf '\e[1;31m[x]\e[0m %s\n' "$*" >&2; exit 1; }

[[ -x "$PMB" && -x "$PY" ]] || die "venv fehlt – erst ./build.sh deps ausführen."
[[ -f "$PAYLOAD" ]]   || die "Payload fehlt: $PAYLOAD – erst ./build.sh ausführen."
[[ -f "$PONGO_BIN" ]] || die "Pongo.bin fehlt – erst ./build.sh bootloader ausführen."

pongo_present() { lsusb -d 05ac:4141 >/dev/null 2>&1; }

sudo -v   # Passwort einmal vorab abfragen

# ------------------------------------------- USB-Störenfriede abschalten ---
# fwupd fragt neue USB-Geräte ab und apple-mfi-fastcharge bindet sich an das
# iPhone – beides zerschießt das checkm8-Timing ("did not enter DFU mode").
FWUPD_WAS_ACTIVE=0
if systemctl is-active --quiet fwupd 2>/dev/null; then
    FWUPD_WAS_ACTIVE=1
    c_info "Stoppe fwupd während des Exploits …"
    sudo systemctl stop fwupd
    sudo systemctl mask --runtime fwupd >/dev/null 2>&1 || true
fi
# Bis zum nächsten Neustart sperren (sonst lädt udev es beim Reconnect neu):
echo 'install apple_mfi_fastcharge /bin/true' | sudo tee /run/modprobe.d/iphone-nura.conf >/dev/null 2>&1 \
  || { sudo mkdir -p /run/modprobe.d && echo 'install apple_mfi_fastcharge /bin/true' | sudo tee /run/modprobe.d/iphone-nura.conf >/dev/null; }
if grep -q '^apple_mfi_fastcharge ' /proc/modules; then
    c_info "Entlade Kernel-Modul apple_mfi_fastcharge …"
    sudo modprobe -r apple_mfi_fastcharge 2>/dev/null || sudo rmmod apple_mfi_fastcharge 2>/dev/null \
      || c_warn "apple_mfi_fastcharge hängt noch am iPhone – Kabel kurz abziehen und Script neu starten."
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
    [[ -n "$P1N" ]] || die "palera1n fehlt – './build.sh deps' installiert es."
    c_info "palera1n: $P1N ($("$P1N" --version 2>&1 | grep -m1 -iE 'palera1n|[0-9]+\.[0-9]' || true))"
    if [[ -z "$PALERA1N_ARGS" ]]; then
        P1N_HELP="$("$P1N" --help 2>&1 || true)"   # erst einsammeln (pipefail + grep -q = SIGPIPE)
        if [[ "$P1N_HELP" == *--early-exit* ]]; then
            PALERA1N_ARGS="-p"          # v3 (Beta): -p = nach Pongo-Upload beenden
        else
            PALERA1N_ARGS="-l -p"       # v2.x: rootless + PongoOS-Shell
        fi
    fi
    # Reste früherer Läufe beenden – zwei palera1n-Instanzen stören sich gegenseitig
    if pgrep -f '/palera1n |/checkra1n' >/dev/null; then
        c_warn "Beende alte palera1n/checkra1n-Prozesse …"
        pids="$(pgrep -f '/palera1n |/checkra1n' | tr '\n' ' ')"
        [[ -n "${pids// /}" ]] && sudo kill $pids 2>/dev/null || true
        sleep 1
    fi
    # usbmuxd stört das checkm8-Timing (vor allem mit weiteren iPhones am Bus) –
    # beim manuellen DFU-Einstieg wird er nicht gebraucht.
    # udev startet usbmuxd bei jedem iOS-Boot neu -> bis zum nächsten Laptop-Neustart sperren
    sudo systemctl mask --runtime usbmuxd.service >/dev/null 2>&1 || true
    sudo systemctl stop usbmuxd usbmuxd.socket >/dev/null 2>&1 || true
    cat <<'EOF'

  Bewährter Ablauf (nur EIN iPhone am Laptop!):
    1. iPhone in den DFU-Modus bringen (vor oder nach Enter – das Script wartet):
       iPhone 7 / 7 Plus : Power + Leiser 8 s halten, dann Power los,
                           Leiser noch 5–10 s halten
       iPhone SE / 6s    : Power + Home 8 s, dann Power los, Home 5–10 s
       -> Bildschirm bleibt SCHWARZ; Kontrolle: lsusb | grep 1227
    2. Enter: das DFU-Gerät wird frisch angemeldet, dann startet palera1n sofort.
  Nach "Checkmate" iPhone nicht anfassen. Kommt kein "download mode":
  DFU neu herstellen und Script erneut starten (checkm8 ist auf A10 wackelig).

EOF
    read -rp "  Bereit? [Enter] " _

    # Bewährt (Vergleich erfolgreicher/fehlgeschlagener Läufe im Kernel-Log): checkm8 klappt,
    # wenn das DFU-Gerät direkt vor palera1n frisch angemeldet wird. Daher: auf DFU warten,
    # den xHCI-Controller des iPhones zurücksetzen, sofort palera1n starten.
    dfu_dev() { for d in /sys/bus/usb/devices/*; do
        [[ "$(cat "$d/idVendor" 2>/dev/null):$(cat "$d/idProduct" 2>/dev/null)" == "05ac:1227" ]] && { echo "$d"; return 0; }
    done; return 1; }
    if [[ "${DFU_REFRESH:-1}" == "1" ]]; then
        if ! dfu_dev >/dev/null; then
            c_warn "Kein iPhone im DFU-Modus (05ac:1227) – bitte jetzt DFU herstellen, warte bis zu 90 s …"
            for _ in $(seq 1 90); do dfu_dev >/dev/null && break; sleep 1; done
        fi
        if dev="$(dfu_dev)"; then
            pci="$(basename "$(readlink -f "$dev/../..")" 2>/dev/null)"
            [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]] || pci="$(basename "$(readlink -f "$(readlink -f "$dev")/../../..")")"
            if [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]]; then
                c_info "Melde das DFU-Gerät frisch an (USB-Controller $pci zurücksetzen) …"
                echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind >/dev/null
                sleep 2
                echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind >/dev/null
                for _ in $(seq 1 20); do dfu_dev >/dev/null && break; sleep 0.5; done
                dfu_dev >/dev/null && c_ok "DFU-Gerät frisch angemeldet." \
                    || c_warn "DFU-Gerät nach dem Reset nicht wieder da – DFU neu herstellen."
                # Kamera/Touchscreen/BT/Fingerprint des Laptops melden sich am selben Controller
                # neu an – erst wenn der Bus ruhig ist, palera1n starten (erfolgreicher Lauf: +4 s)
                c_info "Warte, bis sich die übrigen USB-Geräte angemeldet haben …"
                sleep "${DFU_SETTLE:-5}"
            fi
        fi
    fi
    # shellcheck disable=SC2086
    c_info "Starte: palera1n $PALERA1N_ARGS -k $(basename "$PONGO_BIN")"
    sudo env PALERA1N_BYPASS_PASSCODE_CHECK=1 "$P1N" $PALERA1N_ARGS -k "$PONGO_BIN" &
    P1N_PID=$!
    c_info "Warte auf PongoOS (USB 05ac:4141) …"
    until pongo_present; do
        if ! kill -0 "$P1N_PID" 2>/dev/null; then
            wait "$P1N_PID" || true
            c_info "palera1n beendet – warte bis zu 30 s, bis sich PongoOS meldet …"
            for _ in $(seq 1 30); do pongo_present && break; sleep 1; done
            pongo_present || die "palera1n beendet, aber kein PongoOS gefunden – nochmal starten."
            break
        fi
        sleep 1
    done
    sleep 2
    # komplette Prozesskette beenden (sudo -> palera1n -> checkra1n), nicht nur den Wrapper
    sudo pkill -f '/palera1n |/checkra1n' 2>/dev/null || true
    wait "$P1N_PID" 2>/dev/null || true
fi
pongo_present || die "PongoOS nicht gefunden."
c_ok "PongoOS läuft."

# ---------------------------------------------------- 2. m1n1 schicken ---
c_info "Schicke m1n1-Payload an PongoOS und starte mit '$PONGO_BOOT_CMD' …"
sudo "$PY" "$SCRIPT_DIR/pongo_send.py" --file "$PAYLOAD" --cmd "$PONGO_BOOT_CMD"
c_ok "m1n1 gestartet – auf dem iPhone sollte jetzt Linux booten."

# ------------------------------------------------- Proxy-Modus (Analyse) ---
if [[ "$M1N1_PROXY" == "1" ]]; then
    systemctl is-active --quiet ModemManager 2>/dev/null && { c_info "Stoppe ModemManager (würde ttyACM belegen) …"; sudo systemctl stop ModemManager; }
    c_info "Proxy-Modus: warte auf m1n1-USB-Seriell (/dev/ttyACM*) …"
    DEV=""
    for _ in $(seq 1 60); do
        DEV="$(ls /dev/ttyACM* 2>/dev/null | head -n1 || true)"
        [[ -n "$DEV" ]] && break
        sleep 1
    done
    [[ -n "$DEV" ]] || die "Kein /dev/ttyACM* – m1n1-Proxy nicht erreichbar (dmesg prüfen)."
    c_ok "m1n1-Proxy auf $DEV"
    sleep 2
    M1N1DEVICE="$DEV" "$PY" "$SCRIPT_DIR/research/tools/live_probe.py" \
        || c_warn "live_probe.py endete mit Fehler – Log: research/live/probe.log"
    if [[ "${SKIP_PMU_READ:-0}" != "1" ]]; then
        c_info "PMU-Register der Touch-Versorgung lesen (nur lesend) …"
        M1N1DEVICE="$DEV" "$PY" "$SCRIPT_DIR/research/tools/pmu_read.py" 2>&1 | grep -v '^TTY>' \
            || c_warn "pmu_read.py endete mit Fehler"
    fi
    if [[ "${SKIP_TOUCH_WAKE:-0}" != "1" ]]; then
        c_info "Touch-Aufwachtest (Reset freigeben, IRQ beobachten) …"
        M1N1DEVICE="$DEV" "$PY" "$SCRIPT_DIR/research/tools/touch_wake_probe.py" 2>&1 \
            | grep -v '^TTY>' | tee "$SCRIPT_DIR/research/live/touch-wake.log" \
            || c_warn "touch_wake_probe.py endete mit Fehler"
    fi
    c_info "Fertig. Interaktive Shell (sicher):  M1N1DEVICE=$DEV $PY research/tools/safe_shell.py"
    exit 0
fi

# ------------------------------------------------------- 3. Netboot ---
c_info "Warte auf USB-Netzwerk vom iPhone (172.16.42.x) …"
IFACE=""
for _ in $(seq 1 90); do
    IFACE="$(ip -br -4 a 2>/dev/null | awk '/172\.16\.42\./{print $1; exit}')"
    [[ -n "$IFACE" ]] && break
    sleep 2
done
if [[ -n "$IFACE" ]]; then
    c_ok "USB-Netz auf Interface $IFACE."
    N="/sys/class/net/$IFACE/cdc_ncm"
    if [[ -d "$N" ]]; then
        echo "$NCM_TX_MAX"   | sudo tee "$N/tx_max" >/dev/null 2>&1 || c_warn "tx_max nicht setzbar"
        echo "$NCM_TX_TIMER" | sudo tee "$N/tx_timer_usecs" >/dev/null 2>&1 || true
        c_ok "NCM-Tuning: tx_max=$(cat "$N/tx_max") tx_timer_usecs=$(cat "$N/tx_timer_usecs") rx_max=$(cat "$N/rx_max")"
    fi
    sudo ip link set dev "$IFACE" txqueuelen 2000 2>/dev/null || true
    # Verbindungsstatistik mitschreiben (für die Fehlersuche)
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
        c_warn "firewalld aktiv – setze $IFACE (temporär) in Zone 'trusted'."
        sudo firewall-cmd --zone=trusted --change-interface="$IFACE" >/dev/null || true
    fi
    if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q 'Status: active'; then
        c_warn "ufw aktiv – erlaube Verkehr auf $IFACE."
        sudo ufw allow in on "$IFACE" >/dev/null || true
    fi
else
    c_warn "Kein 172.16.42.x-Interface gesehen (evtl. bekommt der PC die IP erst später)."
    c_warn "Netboot-Server startet trotzdem. 'dmesg | tail' / 'ip -br a' prüfen."
fi

if [[ "$ROOT" == "internal" && "$M1N1_PROXY" != "1" ]]; then
    cat <<EOF

  Nura startet vom internen Speicher (kein Netboot-Server nötig, Fenster darf zu).
  SSH über USB:  ssh -i ~/.ssh/id_ed25519_nura_iphone $("$PMB" config user 2>/dev/null || echo user)@172.16.42.1
  Rückfall auf Netboot:  ROOT=netboot ./boot.sh

EOF
    exit 0
fi

cat <<EOF

  Netboot-Server startet jetzt (Fenster offen lassen!).
  Sobald das iPhone das Rootfs gemountet hat, in einem zweiten Terminal:

      ssh -i ~/.ssh/id_ed25519_nura_iphone $("$PMB" config user 2>/dev/null || echo user)@172.16.42.1
        (ohne Schlüssel: Passwort, Standard 147147)

  Phosh-Image: Bedienung per VNC (kein Touchscreen), ca. 1 Min nach dem Boot:
      xtigervncviewer 172.16.42.1:5900   (Remmina macht mit wayvnc Timeouts)

  Beenden mit Strg+C (das iPhone verliert dann sein Rootfs).

EOF
exec "$PMB" netboot serve

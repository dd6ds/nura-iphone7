#!/usr/bin/env bash
# iPhone 7: iOS-APFS-Container EINMALIG verkleinern, damit Platz für Linux entsteht.
# Läuft komplett vom Laptop aus über ein SSH-Ramdisk (SSHRD_Script) – kein iOS-Code, keine
# Bedienung am iPhone nötig. Es wird NUR der APFS-Container verkleinert; die Partitionstabelle
# ändern wir danach unter Linux (erst Schreibtest im frei gewordenen Bereich, dann GPT).
#
#   tools/ios_resize.sh            -> verkleinert auf 20 GB (Linux bekommt ~12 GB)
#   NEW_BYTES=16000000000 tools/ios_resize.sh   (andere Größe, Vielfaches von 4096)
#   RD_VER=15.7 tools/ios_resize.sh             (andere Ramdisk-Version, Standard 15.8)
#   tools/ios_resize.sh ssh                     (Ramdisk läuft schon -> nur noch verbinden + verkleinern)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
NEW_BYTES="${NEW_BYTES:-19999997952}"     # 20 GB, auf 4096 abgerundet
RD_VER="${RD_VER:-15.8}"                   # iPhone hat iOS 15.6–15.8 (iBoot-7459.140.15)
USED_BYTES="${USED_BYTES:-9200000000}"     # belegt laut tools/apfs_info.py (erstes iPhone 9,17 GB; anderes Gerät: messen!)
SRD="$ROOT/src/SSHRD_Script"
c_info() { printf '\e[1;34m[*]\e[0m %s\n' "$*"; }
c_ok()   { printf '\e[1;32m[+]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m[!]\e[0m %s\n' "$*"; }
die()    { printf '\e[1;31m[x]\e[0m %s\n' "$*"; exit 1; }

(( NEW_BYTES % 4096 == 0 )) || die "NEW_BYTES muss ein Vielfaches von 4096 sein"
(( NEW_BYTES > USED_BYTES + 4000000000 )) || die "zu klein: iOS braucht mind. 4 GB Reserve über den belegten $((USED_BYTES / 1000000)) MB"
[[ -x "$ROOT/tools/ios/resize_apfs" ]] || die "tools/ios/resize_apfs fehlt (HoolockLinux/docs, iphoneos-Build)"
[[ -d "$SRD" ]] || git clone --depth 1 https://github.com/verygenericname/SSHRD_Script.git "$SRD"

cat <<EOF

  iOS-Container verkleinern auf $((NEW_BYTES / 1000000)) MB (jetzt 32000 MB, belegt ~$((USED_BYTES / 1000000)) MB)
  ------------------------------------------------------------------------------
  * Vorher BACKUP des iPhones (Finder/iTunes), falls irgend möglich.
  * iPhone am Ladegerät/USB lassen, während des Verkleinerns NICHT abziehen.
  * Ablauf: DFU -> SSH-Ramdisk (Download ~100 MB beim ersten Mal) -> resize_apfs -> Neustart in iOS.

EOF
read -rp "  Weiter? [j/N] " a; [[ "$a" == [jJ] ]] || exit 1
sudo -v
MODE="${1:-full}"
if [[ "$MODE" != ssh ]]; then

# --- DFU frisch anmelden (wie boot.sh: checkm8 ist auf A10 wackelig) -------------------------
dfu_dev() { for d in /sys/bus/usb/devices/*; do
    [[ "$(cat "$d/idVendor" 2>/dev/null):$(cat "$d/idProduct" 2>/dev/null)" == "05ac:1227" ]] && { echo "$d"; return 0; }
done; return 1; }
sudo systemctl stop usbmuxd usbmuxd.socket >/dev/null 2>&1 || true
c_info "iPhone in den DFU-Modus bringen (Power + Leiser 8 s, Power los, Leiser 5–10 s) …"
for _ in $(seq 1 120); do dfu_dev >/dev/null && break; sleep 1; done
dev="$(dfu_dev)" || die "kein DFU-Gerät (05ac:1227)"
pci="$(basename "$(readlink -f "$dev/../..")" 2>/dev/null)"
[[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]] || pci="$(basename "$(readlink -f "$(readlink -f "$dev")/../../..")")"
if [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]]; then
    c_info "DFU-Gerät frisch anmelden …"
    echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind >/dev/null; sleep 2
    echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind >/dev/null
    for _ in $(seq 1 20); do dfu_dev >/dev/null && break; sleep 0.5; done
    sleep 5
fi

# --- Ramdisk bauen (einmalig) und booten ----------------------------------------------------
cd "$SRD"
if [[ ! -d sshramdisk ]]; then
    c_info "Baue SSH-Ramdisk für iOS $RD_VER (lädt Teile der IPSW) …"
    sudo ./sshrd.sh "$RD_VER"
fi
c_info "Boote SSH-Ramdisk …"
sudo ./sshrd.sh boot
fi
cd "$SRD"
c_info "Warte auf das Ramdisk; usbmuxd ohne Pairing starten (SSHRD-Vorgabe für Linux) …"
sudo systemctl stop usbmuxd.socket usbmuxd.service >/dev/null 2>&1 || true
sudo systemctl mask --runtime usbmuxd.socket usbmuxd.service >/dev/null 2>&1 || true
sudo pkill -x usbmuxd 2>/dev/null || true; sleep 1
sudo sh -c 'nohup usbmuxd -p -f > /tmp/usbmuxd-sshrd.log 2>&1 &'
PORT=2224
trap 'sudo pkill -x usbmuxd 2>/dev/null; pkill -f "iproxy $PORT" 2>/dev/null; sudo systemctl unmask --runtime usbmuxd.socket usbmuxd.service >/dev/null 2>&1 || true' EXIT
sleep 10
pkill -f "iproxy $PORT" 2>/dev/null || true
Linux/iproxy $PORT 22 >/dev/null 2>&1 &
S() { Linux/sshpass -p alpine ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o LogLevel=ERROR -p$PORT root@localhost "$@"; }
for i in $(seq 1 60); do S true 2>/dev/null && break; sleep 2; done
S true || die "keine SSH-Verbindung zum Ramdisk"
c_ok "SSH-Ramdisk erreichbar."

# --- Dateisysteme einhängen, Werkzeug kopieren, verkleinern --------------------------------
S 'mount_filesystems' || c_warn "mount_filesystems meldete Fehler (bei gesperrtem Datenvolume normal)"
S 'mount | grep -q " /mnt5 " || { mkdir -p /mnt5; mount_tmpfs /mnt5; } 2>/dev/null; true'
# beschreibbares Verzeichnis wirklich durch Schreiben einer Datei ermitteln
W=$(S 'for d in /mnt5 /mnt2/tmp /mnt6/tmp /var/tmp /tmp; do mkdir -p $d 2>/dev/null; if echo x > $d/.w 2>/dev/null; then rm -f $d/.w; echo $d; break; fi; done')
[[ -n "$W" ]] || { S 'mount' || true; die "kein beschreibbares Verzeichnis im Ramdisk"; }
c_info "Arbeitsverzeichnis im Ramdisk: $W"
S "cat > $W/resize_apfs && chmod 755 $W/resize_apfs" < "$ROOT/tools/ios/resize_apfs"
c_info "Partitionen im Ramdisk:"; S 'ls /dev/disk0*' || true
c_info "Verkleinere disk0s1 auf $NEW_BYTES Bytes (iOS friert dabei kurz ein) …"
if S "$W/resize_apfs disk0s1 $NEW_BYTES"; then
    c_ok "resize_apfs erfolgreich."
else
    c_warn "resize_apfs meldete einen Fehler – NICHTS weiter ändern, Ausgabe an Claude geben."
    exit 1
fi
c_info "Neustart in iOS …"
S '/sbin/reboot' || true
cat <<EOF

  Fertig. iOS startet normal (gleicher Inhalt, kleinerer Container).
  Danach wie gewohnt Nura booten:  tools/cleanup.sh && ./boot.sh
  Dann prüft Claude unter Linux die neue Größe (tools/apfs_info.py), testet das Schreiben
  im frei gewordenen Bereich und legt erst dann die Linux-Partition an.
EOF

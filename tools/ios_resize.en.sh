#!/usr/bin/env bash
# iPhone 7: shrink the iOS APFS container ONCE to make room for Linux.
# Runs entirely from the laptop via an SSH ramdisk (SSHRD_Script) – no iOS code, no
# interaction on the iPhone needed. ONLY the APFS container is shrunk; the partition table
# is changed afterwards under Linux (first a write test in the freed area, then the GPT).
#
#   tools/ios_resize.en.sh            -> shrinks to 20 GB (Linux gets ~12 GB)
#   NEW_BYTES=16000000000 tools/ios_resize.en.sh   (different size, multiple of 4096)
#   RD_VER=15.7 tools/ios_resize.en.sh             (different ramdisk version, default 15.8)
#   tools/ios_resize.en.sh ssh                     (ramdisk already running -> just connect + shrink)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
NEW_BYTES="${NEW_BYTES:-19999997952}"     # 20 GB, rounded down to 4096
RD_VER="${RD_VER:-15.8}"                   # the iPhone runs iOS 15.6–15.8 (iBoot-7459.140.15)
USED_BYTES="${USED_BYTES:-9200000000}"     # used according to tools/apfs_info.en.py (first iPhone 9.17 GB; other device: measure!)
SRD="$ROOT/src/SSHRD_Script"
c_info() { printf '\e[1;34m[*]\e[0m %s\n' "$*"; }
c_ok()   { printf '\e[1;32m[+]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m[!]\e[0m %s\n' "$*"; }
die()    { printf '\e[1;31m[x]\e[0m %s\n' "$*"; exit 1; }

(( NEW_BYTES % 4096 == 0 )) || die "NEW_BYTES must be a multiple of 4096"
(( NEW_BYTES > USED_BYTES + 4000000000 )) || die "too small: iOS needs at least 4 GB headroom above the used $((USED_BYTES / 1000000)) MB"
[[ -x "$ROOT/tools/ios/resize_apfs" ]] || die "tools/ios/resize_apfs missing (HoolockLinux/docs, iphoneos build)"
[[ -d "$SRD" ]] || git clone --depth 1 https://github.com/verygenericname/SSHRD_Script.git "$SRD"

cat <<EOF

  Shrink iOS container to $((NEW_BYTES / 1000000)) MB (now 32000 MB, used ~$((USED_BYTES / 1000000)) MB)
  ------------------------------------------------------------------------------
  * BACK UP the iPhone first (Finder/iTunes) if at all possible.
  * Keep the iPhone on the charger/USB, do NOT unplug it while shrinking.
  * Procedure: DFU -> SSH ramdisk (~100 MB download the first time) -> resize_apfs -> reboot into iOS.

EOF
read -rp "  Weiter? [j/N] " a; [[ "$a" == [jJ] ]] || exit 1
sudo -v
MODE="${1:-full}"
if [[ "$MODE" != ssh ]]; then

# --- Re-enumerate DFU (like boot.en.sh: checkm8 is flaky on A10) -------------------------
dfu_dev() { for d in /sys/bus/usb/devices/*; do
    [[ "$(cat "$d/idVendor" 2>/dev/null):$(cat "$d/idProduct" 2>/dev/null)" == "05ac:1227" ]] && { echo "$d"; return 0; }
done; return 1; }
sudo systemctl stop usbmuxd usbmuxd.socket >/dev/null 2>&1 || true
c_info "Put the iPhone into DFU mode (power + volume down 8 s, release power, volume down 5–10 s) …"
for _ in $(seq 1 120); do dfu_dev >/dev/null && break; sleep 1; done
dev="$(dfu_dev)" || die "no DFU device (05ac:1227)"
pci="$(basename "$(readlink -f "$dev/../..")" 2>/dev/null)"
[[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]] || pci="$(basename "$(readlink -f "$(readlink -f "$dev")/../../..")")"
if [[ -e "/sys/bus/pci/drivers/xhci_hcd/$pci" ]]; then
    c_info "Re-enumerating the DFU device …"
    echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind >/dev/null; sleep 2
    echo "$pci" | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind >/dev/null
    for _ in $(seq 1 20); do dfu_dev >/dev/null && break; sleep 0.5; done
    sleep 5
fi

# --- Build the ramdisk (once) and boot it ----------------------------------------------------
cd "$SRD"
if [[ ! -d sshramdisk ]]; then
    c_info "Building SSH ramdisk for iOS $RD_VER (downloads parts of the IPSW) …"
    sudo ./sshrd.sh "$RD_VER"
fi
c_info "Booting SSH ramdisk …"
sudo ./sshrd.sh boot
fi
cd "$SRD"
c_info "Waiting for the ramdisk; starting usbmuxd without pairing (SSHRD default for Linux) …"
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
S true || die "no SSH connection to the ramdisk"
c_ok "SSH ramdisk reachable."

# --- Mount file systems, copy the tool, shrink --------------------------------
S 'mount_filesystems' || c_warn "mount_filesystems reported errors (normal with a locked data volume)"
S 'mount | grep -q " /mnt5 " || { mkdir -p /mnt5; mount_tmpfs /mnt5; } 2>/dev/null; true'
# find a writable directory by actually writing a file
W=$(S 'for d in /mnt5 /mnt2/tmp /mnt6/tmp /var/tmp /tmp; do mkdir -p $d 2>/dev/null; if echo x > $d/.w 2>/dev/null; then rm -f $d/.w; echo $d; break; fi; done')
[[ -n "$W" ]] || { S 'mount' || true; die "no writable directory in the ramdisk"; }
c_info "Working directory in the ramdisk: $W"
S "cat > $W/resize_apfs && chmod 755 $W/resize_apfs" < "$ROOT/tools/ios/resize_apfs"
c_info "Partitions in the ramdisk:"; S 'ls /dev/disk0*' || true
c_info "Shrinking disk0s1 to $NEW_BYTES bytes (iOS freezes briefly) …"
if S "$W/resize_apfs disk0s1 $NEW_BYTES"; then
    c_ok "resize_apfs succeeded."
else
    c_warn "resize_apfs reported an error – do NOT change anything else, pass the output to Claude."
    exit 1
fi
c_info "Neustart in iOS …"
S '/sbin/reboot' || true
cat <<EOF

  Fertig. iOS startet normal (gleicher Inhalt, kleinerer Container).
  Then boot Nura as usual:  tools/cleanup.en.sh && ./boot.en.sh
  Then Claude checks the new size under Linux (tools/apfs_info.en.py), tests writing
  in the freed area and only then creates the Linux partition.
EOF

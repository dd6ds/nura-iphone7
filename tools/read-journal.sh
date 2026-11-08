#!/usr/bin/env bash
# Liest das systemd-Journal (und ein paar Konfig-Dateien) aus dem Netboot-Image,
# nachdem das iPhone abgestürzt/eingefroren ist. Netboot-Server vorher beenden!
# Ergebnis: out/diag/  (für die Auswertung)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:-$HOME/.local/var/pmbootstrap/images_netboot/apple-idevice.img}"
OUT="$SCRIPT_DIR/out/diag"
mkdir -p "$OUT"
pgrep -f nbd-server >/dev/null && { echo "Netboot-Server läuft noch – erst mit Strg+C beenden."; exit 1; }

loop="$(sudo losetup -b 4096 -rfP --show "$IMG")"
trap 'sudo umount "$mnt" 2>/dev/null; rmdir "$mnt" 2>/dev/null; sudo losetup -d "$loop"' EXIT
sleep 1
[[ -b "${loop}p2" ]] || { echo "Partition nicht gefunden"; exit 1; }
mnt="$(mktemp -d)"
sudo mount -o ro,noload "${loop}p2" "$mnt"

J="$mnt/var/log/journal"
if sudo test -d "$J"; then
    sudo journalctl -D "$J" --no-pager -b -1 -o short-monotonic > "$OUT/journal-last.txt" 2>&1 || true
    sudo journalctl -D "$J" --no-pager -b 0  -o short-monotonic > "$OUT/journal-current.txt" 2>&1 || true
    sudo journalctl -D "$J" --no-pager --list-boots > "$OUT/boots.txt" 2>&1 || true
    sudo journalctl -D "$J" --no-pager -k -b 0 -o short-monotonic > "$OUT/kernel-current.txt" 2>&1 || true
else
    echo "Kein persistentes Journal im Image ($J fehlt)." | tee "$OUT/journal-current.txt"
fi
for f in etc/phrog/greetd-config-autologin.toml etc/systemd/system/greetd.service.d/zz-iphone-autologin.conf \
         etc/phosh/phoc.ini etc/fstab etc/NetworkManager/conf.d/90-netboot-usb0.conf; do
    echo "=== /$f"; sudo cat "$mnt/$f" 2>&1 || true
done > "$OUT/config.txt"
sudo ls -la "$mnt/var/lib/iphone-nura" > "$OUT/state.txt" 2>&1 || true
sudo chown -R "$(id -u):$(id -g)" "$OUT"
echo "Fertig: $(ls "$OUT")  ->  $OUT"

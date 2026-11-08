#!/usr/bin/env bash
# After a new build (kernel/drivers/firmware) sync the internal Nura installation.
# The iPhone runs from internal storage (ROOT=internal) and is reachable via SSH.
# ONLY system parts from the freshly built image are transferred – user data,
# settings and packages installed on the iPhone stay untouched:
#   /lib/modules  /lib/firmware  /usr/local  plus our config snippets in /etc
set -euo pipefail
cd "$(dirname "$0")/.."
PMB="${PMB:-.venv/bin/pmbootstrap}"
DEVICE="${DEVICE:-apple-idevice}"
KEY="$HOME/.ssh/id_ed25519_nura_iphone"
SSHU="${SSHU:-user}"; IP=172.16.42.1; PW="${PW:-147147}"
W="$("$PMB" config work)"
IMG="$W/images_netboot/$DEVICE.img"
sudo test -f "$IMG" || IMG="$W/chroot_native/home/pmos/rootfs/$DEVICE.img"
sudo test -f "$IMG" || { echo "Image not found – run ./build.en.sh first"; exit 1; }
ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=10 "$SSHU@$IP" 'grep -q nura.internal /proc/cmdline' \
    || { echo "iPhone is not running from internal storage (or not reachable) – aborted."; exit 1; }

loop="$(sudo losetup -b 4096 -rfP --show "$IMG")"; sleep 1
[[ -b "${loop}p2" ]] || { sudo losetup -d "$loop"; loop="$(sudo losetup -rfP --show "$IMG")"; sleep 1; }
mnt="$(mktemp -d)"
trap 'sudo umount "$mnt" 2>/dev/null; sudo losetup -d "$loop" 2>/dev/null; rmdir "$mnt"' EXIT
sudo mount -o ro "${loop}p2" "$mnt"
PARTS=(lib/modules lib/firmware usr/local
       etc/udev/rules.d etc/modules-load.d etc/modprobe.d etc/tmpfiles.d
       etc/systemd/system)
echo "Transferring: ${PARTS[*]}"
# first as a file onto the iPhone (otherwise sudo's stdin is the password, not the archive)
sudo tar -C "$mnt" -cf - "${PARTS[@]}" 2>/dev/null | gzip -1 \
  | ssh -i "$KEY" "$SSHU@$IP" 'cat > /var/tmp/nura-sync.tgz'
ssh -i "$KEY" "$SSHU@$IP" "echo $PW | sudo -S -p '' sh -c 'rm -rf /lib/modules.alt && mv /lib/modules /lib/modules.alt && if tar -C / -xzpf /var/tmp/nura-sync.tgz; then rm -rf /lib/modules.alt; else rm -rf /lib/modules; mv /lib/modules.alt /lib/modules; echo ERROR; exit 1; fi; rm -f /var/tmp/nura-sync.tgz; depmod -a 2>/dev/null; systemctl daemon-reload; sync'"
echo "Done. New drivers take effect after the next start:  tools/cleanup.en.sh && ./boot.en.sh"

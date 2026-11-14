#!/usr/bin/env bash
# =============================================================================
#  iPhone SE (2016) – build the Nura (formerly postmarketOS) netboot image
#
#  Device:   Apple iPhone SE 1st gen. (iPhone8,4 / n69, SoC Apple A9)
#  Port:    Nura "Apple Generic iDevice" (apple-idevice, Hoolock-Linux-Kernel)
#  Result:   out/m1n1-linux.bin  -> booted via PongoOS (see boot.en.sh)
#
#  Important: A9 has no NVMe driver -> the rootfs ALWAYS comes via netboot
#  (USB networking + NBD from the PC). Nothing is flashed to the iPhone.
# =============================================================================
set -euo pipefail

# ----------------------------------------------------------------- config ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VENV:-$SCRIPT_DIR/.venv}"
PMB_GIT="${PMB_GIT:-https://gitlab.nura.eco/postmarketOS/pmbootstrap.git}"
PMB_REF="${PMB_REF:-}"               # Branch/Tag von pmbootstrap (leer = Default-Branch)
PMB="${PMB:-$VENV/bin/pmbootstrap}"  # Nura tool (still called pmbootstrap for now)
DEVICE="apple-idevice"
KERNEL="${KERNEL:-16k}"               # A9 = 16K pages (4k only for A7/A8)
UI="${UI:-phosh}"                    # phosh | console | sxmo-de-sway | ...
# Read from the iPhone 7 (d101, A10) under Hoolock 7.0:
#   Display  : simpledrm 750x1334 (no GPU driver -> Mesa llvmpipe)
#   Input    : only gpio-keys (power/volume) – NO touchscreen
#   Network  : only USB gadget usb0 (no Wi-Fi/BT/modem), no NVMe, no audio
# => Phosh is operated via VNC (wayvnc over USB) from the laptop.
EXTRA_SPACE="${EXTRA_SPACE:-}"       # MB of extra space in the rootfs (empty = automatic)
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_nura_iphone}"   # copied into the image
VNC_LISTEN="${VNC_LISTEN:-172.16.42.1}"
HOSTNAME_PH="${HOSTNAME_PH:-iphone-se}"
DTB_FILTER="${DTB_FILTER:-all}"      # all = all Apple DTBs (m1n1 picks the right one) | n69 = iPhone SE only
# PCIe/Wi-Fi starts at boot. Emergency switch in case the iPhone hangs there:
#   PCIE_BOOT=0 ./build.en.sh payload   (driver can then be started via SSH:
#   echo 0 > /sys/module/pcie_apple_t8010/parameters/disable;
#   echo 610000000.pcie > /sys/bus/platform/drivers/pcie-apple-t8010/bind)
PCIE_BOOT="${PCIE_BOOT:-1}"   # 0 = emergency switch (PCIe/Wi-Fi off, can be started via SSH)
# ext4 UUID of the internal partition "Nura" (nvme0n1p2, created with tools/nura_partition.en.sh)
NURA_ROOT_UUID="${NURA_ROOT_UUID:-663e8742-8b87-4502-9304-ee983b927a67}"
NVME_BOOT="${NVME_BOOT:-1}"   # 0 = skip PCIe port 0 (internal storage) at boot
NVME_AUTOLOAD="${NVME_AUTOLOAD:-1}"   # 0 = nvme module blocked (manual modprobe only)
# spidev.bufsiz: load the Maggie FPGA bitstream (71 KB) in one SPI transfer (audio tests)
CMDLINE="${CMDLINE:-console=tty0 earlycon=tty0 fbcon=rotate:0 spidev.bufsiz=262144$([[ "$PCIE_BOOT" == 1 ]] || echo ' pcie_apple_t8010.disable=1')$([[ "$NVME_BOOT" == 1 ]] || echo ' pcie_apple_t8010.skip_ports=0x1')}"
EXTRA_PKGS="${EXTRA_PKGS:-openssh,htop,nano},postmarketos-mkinitfs-hook-netboot,bluez,libgpiod"
if [[ "$UI" == "phosh" ]]; then
    EXTRA_PKGS="${EXTRA_PKGS},wayvnc,mesa-dri-gallium,gnome-console"
    : "${EXTRA_SPACE:=1536}"
else
    : "${EXTRA_SPACE:=512}"
fi

OUT="${SCRIPT_DIR}/out"
SRC="${SCRIPT_DIR}/src"
HL_M1N1_GIT="${HL_M1N1_GIT:-https://github.com/HoolockLinux/m1n1}"
HL_DOCS_GIT="${HL_DOCS_GIT:-https://github.com/HoolockLinux/docs}"
EXPORT_DIR="${OUT}/export"

c_info() { printf '\e[1;34m[*]\e[0m %s\n' "$*"; }
c_ok()   { printf '\e[1;32m[+]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m[!]\e[0m %s\n' "$*"; }
die()    { printf '\e[1;31m[x]\e[0m %s\n' "$*" >&2; exit 1; }

usage() {
cat <<EOF
Usage: $0 [step]

Steps (without argument: all of them in order):
  deps      check/install dependencies (venv, pmbootstrap, pyusb, palera1n, ...)
  init      configure Nura for apple-idevice
  install   build rootfs + kernel (pmbootstrap install) incl. netboot hook
  fixup     Netboot-Image patchen (/boot nofail, NetworkManager ignoriert usb0)
  export    export kernel/initramfs/DTBs to out/
  bootloader build m1n1.bin (Hoolock) + fetch Pongo.bin
  payload   m1n1-linux.bin zusammensetzen
  all       everything (default)

Umgebungsvariablen:
  UI=$UI  DTB_FILTER=$DTB_FILTER  EXTRA_PKGS=$EXTRA_PKGS
  CMDLINE="$CMDLINE"
EOF
}

# ---------------------------------------------------------------- steps ---
step_deps() {
    c_info "Checking dependencies …"
    local missing=()
    for b in git python3 sudo openssl curl make clang ld.lld zstd gzip; do command -v "$b" >/dev/null || missing+=("$b"); done
    ((${#missing[@]})) && die "Missing: ${missing[*]}"

    # --- Python venv (all PyPI releases of pmbootstrap have been yanked) ---
    if [[ ! -x "$VENV/bin/python" ]]; then
        c_info "Lege venv an: $VENV"
        python3 -m venv "$VENV" \
          || die "venv failed – run 'sudo apt install python3-venv' and start again."
    fi
    "$VENV/bin/python" -m pip install -q --upgrade pip

    if [[ ! -x "$PMB" || "${PMB_UPDATE:-0}" == "1" ]]; then
        c_info "Installing pmbootstrap from Git ($PMB_GIT ${PMB_REF:-default}) into the venv …"
        "$VENV/bin/pip" install -q --upgrade "git+${PMB_GIT}${PMB_REF:+@$PMB_REF}" \
          || die "Installing pmbootstrap from Git failed."
    fi
    c_ok "pmbootstrap: $("$PMB" --version 2>/dev/null || echo '?')  ($PMB)"

    "$VENV/bin/python" -c 'import usb.core' 2>/dev/null || {
        c_info "Installing pyusb into the venv (for pongo_send.en.py) …"
        "$VENV/bin/pip" install -q pyusb
    }
    if ! "$VENV/bin/python" -c 'import usb.backend.libusb1 as b; assert b.get_backend()' 2>/dev/null; then
        c_warn "libusb-1.0 may be missing – if so 'sudo apt install libusb-1.0-0'."
    fi
    if ! command -v cargo >/dev/null && [[ -x "$HOME/.cargo/bin/cargo" ]]; then export PATH="$HOME/.cargo/bin:$PATH"; fi
    command -v cargo >/dev/null || die "Rust (cargo/rustup) missing – needed for m1n1: https://rustup.rs"
    if ! command -v palera1n >/dev/null; then
        c_info "Installing palera1n (official script, asks for sudo itself) …"
        /bin/sh -c "$(curl -fsSL https://static.palera.in/scripts/install.sh)" \
          || die "Installing palera1n failed – manually: https://github.com/palera1n/palera1n/releases"
    fi
    c_ok "palera1n: $( { palera1n --version 2>&1 || true; } | grep -m1 -iE 'palera1n|[0-9]+\.[0-9]' || echo vorhanden)"
    c_ok "Dependencies ok."
}

step_init() {
    # First init only if no pmbootstrap configuration exists at all.
    if ! "$PMB" config work >/dev/null 2>&1 || [[ ! -d "$("$PMB" config aports 2>/dev/null)" ]]; then
        c_info "First-time setup – 'pmbootstrap init' (just confirm the questions with Enter,"
        c_info "device/kernel are set to apple-idevice/16k automatically afterwards)."
        "$PMB" init
    fi
    # Set device, kernel & co. NOT interactively but to fixed values:
    "$PMB" config device "$DEVICE"
    "$PMB" config kernel "$KERNEL"
    "$PMB" config ui "$UI"
    "$PMB" config hostname "$HOSTNAME_PH"
    "$PMB" config extra_packages "$EXTRA_PKGS"
    "$PMB" config extra_space "$EXTRA_SPACE"
    if [[ ! -f "$SSH_KEY" ]]; then
        c_info "Generating SSH key for the iPhone: $SSH_KEY"
        mkdir -p "$(dirname "$SSH_KEY")"
        ssh-keygen -q -t ed25519 -N '' -C nura-iphone -f "$SSH_KEY"
    fi
    "$PMB" config ssh_keys True
    "$PMB" config ssh_key_glob "${SSH_KEY}.pub"
    c_ok "Konfiguration: device=$("$PMB" config device) kernel=$("$PMB" config kernel) ui=$("$PMB" config ui)"
}

check_device() {
    local d k; d="$("$PMB" config device)"; k="$("$PMB" config kernel)"
    [[ "$d" == "$DEVICE" && "$k" == "$KERNEL" ]] \
        || die "Wrong configuration (device=$d kernel=$k) – run '$0 init' first."
}

# If the netboot from the last iPhone start is still running, it keeps the image mounted and
# pmbootstrap fails with "umount … netboot" (exit 32) -> clean up first.
stop_old_netboot() {
    if pgrep -f 'nbd-server|pmbootstrap netboot' >/dev/null 2>&1; then
        c_warn "Netboot from the last iPhone start is still running – stopping it (the iPhone loses its rootfs)."
        "$SCRIPT_DIR/tools/cleanup.en.sh" --no-usb-reset >/dev/null 2>&1 || true
        pgrep -f 'nbd-server|pmbootstrap netboot' >/dev/null 2>&1 \
            && die "Netboot is still running – please stop the boot.en.sh window with Ctrl+C and start again."
        c_ok "Old netboot stopped."
    fi
}

step_install() {
    stop_old_netboot
    check_device
    # Clean up leftovers of earlier runs (loop devices, bind mounts) – otherwise
    # mkfs fails with "No such device or address" on /dev/installp2.
    "$PMB" shutdown >/dev/null 2>&1 || true
    c_info "Building rootfs (pmbootstrap install) – this takes a while the first time …"
    # The generated rootfs image is later served via NBD by 'pmbootstrap netboot serve'.
    "$PMB" -y install --password "${PMOS_PASSWORD:-147147}"
    "$PMB" shutdown >/dev/null 2>&1 || true
    c_ok "Rootfs built. Default password for user '$("$PMB" config user 2>/dev/null || echo user)': ${PMOS_PASSWORD:-147147}"
}

workdir() { "$PMB" config work; }

# Fix up the netboot image:
#  - /boot is not available during netboot -> 'nofail', otherwise emergency mode
#  - NetworkManager must NOT manage usb0, otherwise 172.16.42.1 disappears
#    and the NBD connection (= the whole rootfs) drops
patch_image() {
    local img="$1" loop part mnt
    [[ -f "$img" ]] || return 0
    c_info "Patche $(basename "$(dirname "$img")")/$(basename "$img") …"
    loop="$(sudo losetup -b 4096 -fP --show "$img")"
    sudo partprobe "$loop" 2>/dev/null || true; sleep 1
    if [[ ! -b "${loop}p2" ]]; then
        sudo losetup -d "$loop"
        loop="$(sudo losetup -fP --show "$img")"; sleep 1
    fi
    part="${loop}p2"
    [[ -b "$part" ]] || { sudo losetup -d "$loop"; die "Root partition not found in $img."; }
    mnt="$(mktemp -d)"
    sudo mount -o init_itable=0 "$part" "$mnt"
    # /boot -> nofail + short timeout
    sudo sed -i -E '/[[:space:]]\/boot[[:space:]]/{/nofail/!s/(ext[234]|vfat)[[:space:]]+([^[:space:]]+)/\1 \2,nofail,x-systemd.device-timeout=5s/}' "$mnt/etc/fstab"
    # NetworkManager: do not touch usb0
    sudo mkdir -p "$mnt/etc/NetworkManager/conf.d"
    printf '[keyfile]\nunmanaged-devices=interface-name:usb0\n' \
        | sudo tee "$mnt/etc/NetworkManager/conf.d/90-netboot-usb0.conf" >/dev/null
    [[ "$UI" == "phosh" ]] && patch_phosh "$mnt"
    patch_touch "$mnt"
    patch_wifi "$mnt"
    patch_bt "$mnt"
    patch_nvme "$mnt"
    patch_charge "$mnt"
    c_ok "fstab: $(grep -E '[[:space:]]/boot[[:space:]]' "$mnt/etc/fstab" | tr -s ' ')"
    # First-boot tasks that are extremely slow over NBD are done locally here
    if command -v systemd-hwdb >/dev/null; then
        sudo systemd-hwdb --root="$mnt" update 2>/dev/null && c_ok "hwdb lokal erzeugt."
    fi
    # ConditionNeedsUpdate= satisfied -> no hwdb/ldconfig/catalog update at boot
    sudo touch -r "$mnt/usr" "$mnt/etc/.updated" "$mnt/var/.updated" 2>/dev/null || true

    # Wait for ext4 lazy init (zeroing inode tables) locally instead of over USB
    c_info "Waiting for ext4 initialisation (locally, a few seconds) …"
    local dev st prev="" same=0
    dev="$(basename "$part")"
    for _ in $(seq 1 180); do
        sync
        st="$(awk '{print $7}' "/sys/class/block/$dev/stat" 2>/dev/null || echo x)"
        if [[ "$st" == "$prev" ]]; then same=$((same+1)); else same=0; fi
        (( same >= 3 )) && break
        prev="$st"; sleep 1
    done
    sudo umount "$mnt"; rmdir "$mnt"
    sudo losetup -d "$loop"
}

# Adapt Phosh to the iPhone (A9/A10) – without touch & GPU
# Touch (iPhone 7): hx-touchd + firmware + calibration + panel re-init before start.
# Prerequisite: tools/kernel-custom.en.sh (touch driver) and tools/hx-touchd/build.en.sh.
patch_touch() {
    local m="$1" h="$SCRIPT_DIR/out/hx-touch"
    [[ -x "$h/hx-touchd" && -f "$h/syscfg.bin" && -f "$h/D10.mtprops" ]] || {
        c_warn "Touch: out/hx-touch missing – run tools/hx-touchd/build.en.sh first (touch stays off)."; return 0; }
    c_info "Touch: installing hx-touchd + firmware + panel re-init …"
    sudo install -Dm755 "$h/hx-touchd" "$m/usr/local/sbin/hx-touchd"
    sudo install -Dm755 "$SCRIPT_DIR/tools/dsi_reinit.en.py" "$m/usr/local/sbin/dsi-reinit"
    sudo install -Dm644 "$h/D10.mtprops" "$m/usr/local/share/hx-touch/D10.mtprops"
    sudo install -Dm644 "$h/syscfg.bin" "$m/usr/local/share/hx-touch/syscfg.bin"
    sudo tee "$m/etc/systemd/system/hx-touchd.service" >/dev/null <<'UNIT'
[Unit]
Description=Apple multitouch firmware loader (hx-touchd, Project Sandcastle)
ConditionPathExists=/dev/hx-touch
After=systemd-modules-load.service
Before=greetd.service

[Service]
# In-cell touch: start the panel once from the reset default, otherwise the controller does not scan
ExecStartPre=-/usr/bin/python3 /usr/local/sbin/dsi-reinit
ExecStart=/usr/local/sbin/hx-touchd C1F5D,2 /usr/local/share/hx-touch/D10.mtprops /usr/local/share/hx-touch/syscfg.bin
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT
    sudo mkdir -p "$m/etc/systemd/system/multi-user.target.wants"
    sudo ln -sf ../hx-touchd.service "$m/etc/systemd/system/multi-user.target.wants/hx-touchd.service"
    c_ok "Touch service set up."
}

# Wi-Fi (iPhone 7, BCM4355 "elsa"): firmware from the iOS rootfs for brcmfmac
# (generated by tools/wifi-fw.en.py into out/wifi-fw/brcm)
patch_wifi() {
    local m="$1" w="$SCRIPT_DIR/out/wifi-fw/brcm"
    if ! ls "$w"/*.bin >/dev/null 2>&1 && [[ -d "$SCRIPT_DIR/research/firmware/wifi" ]]; then
        "$VENV/bin/python" "$SCRIPT_DIR/tools/wifi-fw.en.py" >/dev/null || true
    fi
    ls "$w"/*.bin >/dev/null 2>&1 || { c_warn "Wi-Fi: no firmware in out/wifi-fw – Wi-Fi stays off."; return 0; }
    sudo mkdir -p "$m/lib/firmware/brcm"
    sudo cp "$w"/* "$m/lib/firmware/brcm/"
    # Load brcmfmac early via systemd-modules-load instead of via udev (udevd hung for
    # ~190 s on first boot, so Wi-Fi only came up after ~4 min)
    sudo mkdir -p "$m/etc/modules-load.d"
    echo brcmfmac | sudo tee "$m/etc/modules-load.d/wlan.conf" >/dev/null
    # Firmware loader: do not wait 60 s per missing file for a userspace helper
    sudo mkdir -p "$m/etc/tmpfiles.d"
    echo 'w /sys/class/firmware/timeout - - - - 1' | sudo tee "$m/etc/tmpfiles.d/firmware-timeout.conf" >/dev/null
    c_ok "Wi-Fi firmware installed ($(ls "$w" | wc -l) files)."
}

# Bluetooth (iPhone 7): BCM4355C0 on UART1, firmware patch from iOS BlueTool (tools/bt-fw.en.sh)
patch_bt() {
    local m="$1" b="$SCRIPT_DIR/out/bt-fw/brcm"
    [[ -f "$b/BCM.hcd" ]] || "$SCRIPT_DIR/tools/bt-fw.en.sh" >/dev/null 2>&1 || true
    [[ -f "$b/BCM.hcd" ]] || { c_warn "Bluetooth: no firmware in out/bt-fw – chip runs with ROM firmware."; }
    [[ -f "$b/BCM.hcd" ]] && { sudo mkdir -p "$m/lib/firmware/brcm"; sudo cp "$b"/*.hcd "$m/lib/firmware/brcm/"; }
    # Load hci_uart early (udevd hangs at boot because of NBD, see Wi-Fi)
    sudo mkdir -p "$m/etc/modules-load.d"
    echo hci_uart | sudo tee "$m/etc/modules-load.d/bluetooth.conf" >/dev/null
    # the image masks bluetooth.service (-> /dev/null) – remove the mask
    [[ -L "$m/etc/systemd/system/bluetooth.service" ]] && sudo rm -f "$m/etc/systemd/system/bluetooth.service"
    sudo mkdir -p "$m/etc/systemd/system/multi-user.target.wants"
    [[ -f "$m/usr/lib/systemd/system/bluetooth.service" ]] && \
        sudo ln -sf /usr/lib/systemd/system/bluetooth.service "$m/etc/systemd/system/multi-user.target.wants/bluetooth.service"
    c_ok "Bluetooth eingerichtet."
}

# Internal storage (iPhone 7): do NOT load the nvme module automatically during testing –
# only via SSH: modprobe nvme (if the controller hangs, the system stays usable)
patch_nvme() {
    local m="$1"
    sudo mkdir -p "$m/etc/modprobe.d"
    # Protect iOS data: APFS container (nvme0n1p1) and system namespaces 2..7 always read-only
    sudo mkdir -p "$m/etc/udev/rules.d"
    printf '%s\n' '# iPhone 7: never write to the iOS areas of internal storage' \
        'ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="nvme0n1p1|nvme0n[2-9]", RUN+="/sbin/blockdev --setro /dev/%k"' \
        | sudo tee "$m/etc/udev/rules.d/60-ios-readonly.rules" >/dev/null
    if [[ "$NVME_AUTOLOAD" == 1 ]]; then
        sudo rm -f "$m/etc/modprobe.d/nvme-test.conf"
        echo nvme | sudo tee "$m/etc/modules-load.d/nvme.conf" >/dev/null
        c_ok "NVMe: loaded at startup (iOS areas read-only)."
    else
        sudo rm -f "$m/etc/modules-load.d/nvme.conf"
        echo 'blacklist nvme' | sudo tee "$m/etc/modprobe.d/nvme-test.conf" >/dev/null
        c_info "NVMe: module blocked (test: via SSH 'modprobe nvme'; NVME_AUTOLOAD=1 lifts this)"
    fi
}

# Charging (iPhone 7): without the iOS driver the Tigris charger chip sits at a 90 mA USB input limit –
# the battery drains despite the cable. tigris-charge raises the limit (up to 900 mA, with
# voltage-droop control) and sets it again after replugging.
patch_charge() {
    local m="$1"
    c_info "Charging: installing the tigris-charge service …"
    sudo install -Dm755 "$SCRIPT_DIR/tools/tigris-charge.en.py" "$m/usr/local/sbin/tigris-charge"
    sudo install -Dm644 "$SCRIPT_DIR/tools/tigris-charge.service" "$m/etc/systemd/system/tigris-charge.service"
    sudo mkdir -p "$m/etc/systemd/system/multi-user.target.wants"
    sudo ln -sf ../tigris-charge.service "$m/etc/systemd/system/multi-user.target.wants/tigris-charge.service"
    c_ok "tigris-charge eingerichtet."
    # Automatic brightness from the light sensor CT821 (I2C2 via /dev/mem, see research/SENSOR-ANALYSE.md)
    c_info "Brightness: installing the nura-autobright service …"
    sudo install -Dm755 "$SCRIPT_DIR/tools/nura-autobright.en.py" "$m/usr/local/sbin/nura-autobright"
    sudo install -Dm644 "$SCRIPT_DIR/tools/i2c_poll.en.py" "$m/usr/local/sbin/nura_i2c.py"
    sudo install -Dm644 "$SCRIPT_DIR/tools/nura-autobright.service" "$m/etc/systemd/system/nura-autobright.service"
    sudo ln -sf ../nura-autobright.service "$m/etc/systemd/system/multi-user.target.wants/nura-autobright.service"
    c_ok "nura-autobright set up."
}

patch_phosh() {
    local m="$1"
    c_info "Phosh tweaks: scaling, software rendering, no lock screen, wayvnc …"

    # 1) Display 750x1334 @ 326 dpi -> scale 2
    sudo mkdir -p "$m/etc/phosh"
    sudo tee "$m/etc/phosh/phoc.ini" >/dev/null <<'INI'
[core]
xwayland=false

[output:Unknown-1]
scale = 2
INI

    # 2) Optimise software rendering (no GPU driver)
    sudo mkdir -p "$m/etc/environment.d" "$m/etc/profile.d"
    # WLR_RENDERER=pixman: phoc renders directly on the CPU instead of GLES2/llvmpipe –
    # measured (tools/gfx_bench.en.py): phoc CPU 76 % -> 8 %, 28 -> 37 frames/s, scrolling 37 -> 55.
    # wayvnc still delivers images with it (zwlr_screencopy via the shim below).
    printf 'GSK_RENDERER=cairo\nLIBGL_ALWAYS_SOFTWARE=1\nGALLIUM_DRIVER=llvmpipe\nWLR_RENDERER_ALLOW_SOFTWARE=1\nWLR_RENDERER=pixman\n' \
        | sudo tee "$m/etc/environment.d/50-iphone-nura.conf" >/dev/null
    printf 'export GSK_RENDERER=cairo\nexport LIBGL_ALWAYS_SOFTWARE=1\nexport GALLIUM_DRIVER=llvmpipe\nexport WLR_RENDERER_ALLOW_SOFTWARE=1\nexport WLR_RENDERER=pixman\n' \
        | sudo tee "$m/etc/profile.d/50-iphone-nura.sh" >/dev/null
    sudo grep -q WLR_RENDERER_ALLOW_SOFTWARE "$m/etc/environment" 2>/dev/null \
        || echo 'WLR_RENDERER_ALLOW_SOFTWARE=1' | sudo tee -a "$m/etc/environment" >/dev/null
    sudo grep -q '^WLR_RENDERER=' "$m/etc/environment" 2>/dev/null \
        || echo 'WLR_RENDERER=pixman' | sudo tee -a "$m/etc/environment" >/dev/null

    # 3) Without touch there is no PIN unlock on the device -> disable lock/blanking
    sudo mkdir -p "$m/usr/share/glib-2.0/schemas"
    sudo tee "$m/usr/share/glib-2.0/schemas/90_iphone-nura.gschema.override" >/dev/null <<'GSO'
[org.gnome.desktop.screensaver]
lock-enabled=false

[org.gnome.desktop.session]
idle-delay=uint32 0

[org.gnome.settings-daemon.plugins.power]
sleep-inactive-ac-type='nothing'
sleep-inactive-battery-type='nothing'
idle-dim=false

[org.gnome.desktop.interface]
enable-animations=false

[mobi.phosh.osk]
scaling=['auto-landscape']
GSO
    # Compile schemas on the device at first boot (the host cannot execute aarch64)
    sudo tee "$m/etc/systemd/system/iphone-nura-schemas.service" >/dev/null <<'UNIT'
[Unit]
Description=Compile GSettings schema overrides (iPhone Nura)
Before=display-manager.service greetd.service
ConditionPathExists=!/var/lib/iphone-nura/schemas-done

[Service]
Type=oneshot
ExecStart=/usr/bin/glib-compile-schemas /usr/share/glib-2.0/schemas
ExecStartPost=/bin/sh -c 'mkdir -p /var/lib/iphone-nura && touch /var/lib/iphone-nura/schemas-done'

[Install]
WantedBy=multi-user.target
UNIT
    sudo mkdir -p "$m/etc/systemd/system/multi-user.target.wants"
    sudo ln -sf ../iphone-nura-schemas.service \
        "$m/etc/systemd/system/multi-user.target.wants/iphone-nura-schemas.service"

    # 4) Autologin: phrog (login greeter) cannot be used without touch
    local user sess_exec
    user="$("$PMB" config user 2>/dev/null || echo user)"
    sess_exec="$(sed -n 's/^Exec=//p' "$m/usr/share/wayland-sessions/phosh.desktop" 2>/dev/null | head -n1)"
    [[ -n "$sess_exec" ]] || sess_exec="phosh-session"
    if [[ -f "$m/etc/phrog/greetd-config.toml" ]]; then
        sudo cp "$m/etc/phrog/greetd-config.toml" "$m/etc/phrog/greetd-config-autologin.toml"
        sudo sed -i '/^\[initial_session\]/,$d' "$m/etc/phrog/greetd-config-autologin.toml"
        printf '\n[initial_session]\ncommand = "%s"\nuser = "%s"\n' "$sess_exec" "$user" \
            | sudo tee -a "$m/etc/phrog/greetd-config-autologin.toml" >/dev/null
        sudo mkdir -p "$m/etc/systemd/system/greetd.service.d"
        printf '[Service]\nExecStart=\nExecStart=greetd -c /etc/phrog/greetd-config-autologin.toml\n' \
            | sudo tee "$m/etc/systemd/system/greetd.service.d/zz-iphone-autologin.conf" >/dev/null
        c_ok "Autologin: $user -> $sess_exec"
    else
        c_warn "/etc/phrog/greetd-config.toml not in the image – autologin skipped."
    fi

    # Slim down + timeouts (user@.service, Phosh, OSK) – see tools/phosh-slim.en.sh
    sudo sh "$SCRIPT_DIR/tools/phosh-slim.en.sh" "$m" >/dev/null && c_ok "Phosh slimmed down (modem/calls/chatty/VVM/Evolution off)."

    # Raise the start timeout (software rendering + netboot = slow)
    sudo mkdir -p "$m/etc/systemd/user/mobi.phosh.Shell.service.d"
    printf '[Service]\nTimeoutStartSec=600\n' \
        | sudo tee "$m/etc/systemd/user/mobi.phosh.Shell.service.d/timeout.conf" >/dev/null
    # Switch off services without matching hardware (saves RAM/CPU/IO)
    for svc in ModemManager.service eg25-manager.service; do   # bluetooth stays on (BT works, r118)
        sudo ln -sf /dev/null "$m/etc/systemd/system/$svc"
    done
    for ad in udiskie.desktop org.gnome.SettingsDaemon.Smartcard.desktop \
              org.gnome.SettingsDaemon.PrintNotifications.desktop \
              org.gnome.SettingsDaemon.Wwan.desktop org.gnome.SettingsDaemon.UsbProtection.desktop; do
        printf '[Desktop Entry]\nType=Application\nName=disabled\nHidden=true\n' \
            | sudo tee "$m/etc/xdg/autostart/$ad" >/dev/null
    done

    # wayvnc shim: hides ext-image-copy-capture (without a GPU it delivers no
    # formats) -> wayvnc uses zwlr_screencopy. Source: tools/wayvnc-hide-ext/
    local shim="$SCRIPT_DIR/tools/wayvnc-hide-ext/hide_ext_capture.so"
    if [[ ! -f "$shim" ]] && command -v aarch64-linux-gnu-gcc >/dev/null; then
        aarch64-linux-gnu-gcc -shared -fPIC -nostdlib -O2 -fno-stack-protector -fno-builtin \
            -o "$shim" "$SCRIPT_DIR/tools/wayvnc-hide-ext/hide_ext_capture.c"
    fi
    if [[ -f "$shim" ]]; then
        sudo install -m755 "$shim" "$m/usr/lib/wayvnc-hide-ext-capture.so"
    else
        c_warn "wayvnc shim missing (aarch64-linux-gnu-gcc not installed) – VNC may show no picture."
    fi

    # 5) wayvnc in the Phosh session start -> operation via VNC from the laptop
    sudo mkdir -p "$m/etc/xdg/autostart"
    sudo tee "$m/etc/xdg/autostart/wayvnc-iphone.desktop" >/dev/null <<DESK
[Desktop Entry]
Type=Application
Name=wayvnc (USB)
Comment=VNC server on ${VNC_LISTEN}:5900 – remote control without touchscreen
Exec=sh -c 'sleep 3; exec env LD_PRELOAD=/usr/lib/wayvnc-hide-ext-capture.so wayvnc --max-fps=15 ${VNC_LISTEN} 5900'
NoDisplay=true
DESK
}

step_fixup() {
    check_device
    local w; w="$(workdir)"
    "$PMB" shutdown >/dev/null 2>&1 || true   # image must not be mounted anymore
    patch_image "$w/chroot_native/home/pmos/rootfs/${DEVICE}.img"
    # pmbootstrap only copies to images_netboot/ if nothing is there yet ->
    # remove the old copy so that 'netboot serve' uses the freshly built image.
    if sudo test -f "$w/images_netboot/${DEVICE}.img"; then
        c_info "Removing old netboot copy (recreated on the next boot.en.sh) …"
        sudo rm -f "$w/images_netboot/${DEVICE}.img"
    fi
    # also store it in the chroot so that future installs bring it along
    sudo mkdir -p "$w/chroot_rootfs_${DEVICE}/etc/NetworkManager/conf.d"
    printf '[keyfile]\nunmanaged-devices=interface-name:usb0\n' \
        | sudo tee "$w/chroot_rootfs_${DEVICE}/etc/NetworkManager/conf.d/90-netboot-usb0.conf" >/dev/null
    c_ok "Netboot image patched."
}

step_export() {
    check_device
    rm -rf "$EXPORT_DIR"; mkdir -p "$EXPORT_DIR" "$OUT/dtbs"
    c_info "Exporting kernel + initramfs …"
    "$PMB" export --no-install "$EXPORT_DIR" 2>/dev/null || "$PMB" export "$EXPORT_DIR"

    local rootfs; rootfs="$(workdir)/chroot_rootfs_${DEVICE}"
    [[ -d "$rootfs" ]] || die "Rootfs chroot not found: $rootfs"

    # (m1n1-idevice.macho from the package is for the iBoot method – we use PongoOS + m1n1.bin)

    # DTBs
    local dtbdir="$rootfs/boot/dtbs/apple"
    sudo test -d "$dtbdir" || dtbdir="$(sudo find "$rootfs/boot" -type d -name apple | head -n1)"
    [[ -n "$dtbdir" ]] || die "No Apple DTBs found in the rootfs."
    if [[ "$DTB_FILTER" == "n69" ]]; then
        sudo find "$dtbdir" -name '*n69*.dtb' -exec cp {} "$OUT/dtbs/" \;
        ls "$OUT"/dtbs/*.dtb >/dev/null 2>&1 || { c_warn "No n69 DTB found – taking all."; sudo cp "$dtbdir"/*.dtb "$OUT/dtbs/"; }
    else
        sudo cp "$dtbdir"/*.dtb "$OUT/dtbs/"
    fi
    sudo chown -R "$(id -u):$(id -g)" "$OUT"
    c_ok "Export done: $(ls "$OUT"/dtbs | wc -l) DTBs, m1n1, vmlinuz, initramfs."
}

step_bootloader() {
    mkdir -p "$SRC" "$OUT"
    if ! command -v cargo >/dev/null && [[ -x "$HOME/.cargo/bin/cargo" ]]; then export PATH="$HOME/.cargo/bin:$PATH"; fi

    c_info "Fetching/updating Hoolock m1n1 …"
    if [[ -d "$SRC/m1n1/.git" ]]; then
        git -C "$SRC/m1n1" checkout -q -- .      # revert our own patches, otherwise pull fails
        git -C "$SRC/m1n1" pull -q --ff-only
    else
        git clone -q --depth 1 "$HL_M1N1_GIT" "$SRC/m1n1"
    fi
    git -C "$SRC/m1n1" submodule update -q --init --depth 1
    # our own m1n1 patches (e.g. Wi-Fi data from the ADT for the iPhone 7)
    for p in "$SCRIPT_DIR"/tools/m1n1-patches/*.patch; do
        [[ -f "$p" ]] || continue
        git -C "$SRC/m1n1" apply --check "$p" 2>/dev/null \
            && git -C "$SRC/m1n1" apply "$p" && c_ok "m1n1-Patch: $(basename "$p")" \
            || c_warn "m1n1 patch does not apply (anymore): $(basename "$p")"
    done
    rustup target add aarch64-unknown-none-softfloat >/dev/null
    c_info "Building m1n1.bin (PongoOS variant) …"
    make -C "$SRC/m1n1" -j"$(nproc)" >"$OUT/m1n1-build.log" 2>&1 \
      || { tail -20 "$OUT/m1n1-build.log"; die "m1n1 build failed (log: out/m1n1-build.log)."; }
    cp "$SRC/m1n1/build/m1n1.bin" "$OUT/m1n1.bin"

    c_info "Fetching Hoolock Pongo.bin …"
    if [[ -d "$SRC/hl-docs/.git" ]]; then
        git -C "$SRC/hl-docs" pull -q --ff-only
    else
        git clone -q --depth 1 "$HL_DOCS_GIT" "$SRC/hl-docs"
    fi
    cp "$SRC/hl-docs/binaries/Pongo.bin" "$OUT/Pongo.bin"
    c_ok "Bootloader: out/m1n1.bin ($(du -h "$OUT/m1n1.bin" | cut -f1)), out/Pongo.bin"
}

step_payload() {
    local kernel initfs
    kernel="$(readlink -f "$EXPORT_DIR/vmlinuz")"
    initfs="$(readlink -f "$EXPORT_DIR/initramfs")"
    [[ -f "$kernel" && -f "$initfs" ]] || die "Export incomplete – run '$0 export' first."
    [[ -f "$OUT/m1n1.bin" ]] || die "out/m1n1.bin missing – run '$0 bootloader' first."
    ls "$OUT"/dtbs/*.dtb >/dev/null 2>&1 || die "No DTBs in out/dtbs."
    # Our own DTBs (e.g. iPhone 7 with Wi-Fi node) replace those from the kernel package,
    # so that DT changes do not need a new kernel build.
    if ls "$OUT"/dtbs-override/*.dtb >/dev/null 2>&1; then
        cp "$OUT"/dtbs-override/*.dtb "$OUT/dtbs/"
        c_ok "DTB-Override: $(cd "$OUT/dtbs-override" && ls *.dtb | tr '\n' ' ')"
    fi

    # m1n1 only understands gzip/xz/cpio – Nura builds the initramfs with zstd.
    c_info "Repacking initramfs as gzip …"
    case "$(head -c4 "$initfs" | od -An -tx1 | tr -d ' ')" in
        1f8b*)    cp "$initfs" "$OUT/initramfs.gz" ;;
        28b52ffd) zstd -dcq "$initfs" | gzip -9 > "$OUT/initramfs.gz" ;;
        fd377a58) xz -dc "$initfs" | gzip -9 > "$OUT/initramfs.gz" ;;
        3037303*) gzip -9c "$initfs" > "$OUT/initramfs.gz" ;;
        *) die "Unknown initramfs format: $(file -b "$initfs")" ;;
    esac
    head -c2 "$kernel" | od -An -tx1 | grep -q '1f 8b' \
        || c_warn "Kernel is not gzip – m1n1 may not read it correctly inline."

    # Overlay for the initramfs: skip the netboot hook when "nura.internal" is on the
    # command line (root then comes from internal storage via pmos.root_uuid).
    # Second cpio archive in the same gzip stream – the kernel unpacks both one after the other.
    local ov; ov="$(mktemp -d)"
    mkdir -p "$ov/hooks"
    zcat "$OUT/initramfs.gz" | (cd "$ov" && cpio -i --quiet hooks/netboot.sh 2>/dev/null) || true
    if [[ -f "$ov/hooks/netboot.sh" ]]; then
        { printf '#!/bin/sh\n# Nura: internal storage instead of netboot\n'
          printf 'if grep -qw nura.internal /proc/cmdline; then echo "Netboot skipped (nura.internal)"; exit 0; fi\n'
          tail -n +2 "$ov/hooks/netboot.sh"; } > "$ov/netboot.new"
        mv "$ov/netboot.new" "$ov/hooks/netboot.sh"; chmod 755 "$ov/hooks/netboot.sh"
        { zcat "$OUT/initramfs.gz"; (cd "$ov" && echo hooks/netboot.sh | cpio -o -H newc -R 0:0 --quiet); } \
            | gzip -9 > "$OUT/initramfs-nura.gz"
        mv "$OUT/initramfs-nura.gz" "$OUT/initramfs.gz"
        c_ok "initramfs: netboot hook can be skipped (nura.internal)."
    else
        c_warn "initramfs without hooks/netboot.sh – no overlay needed."
    fi
    rm -rf "$ov"

    mkpayload() {  # $1 = output, $2 = command line
        {
            cat "$OUT/m1n1.bin"
            printf 'chosen.bootargs=%s\n' "$2"
            cat "$OUT"/dtbs/*.dtb
            cat "$kernel"
            cat "$OUT/initramfs.gz"
        } > "$1"
    }
    c_info "Assembling m1n1 payloads (m1n1.bin + bootargs + DTBs + kernel + initramfs) …"
    mkpayload "$OUT/m1n1-linux.bin" "$CMDLINE"
    mkpayload "$OUT/m1n1-linux-internal.bin" "$CMDLINE pmos.root_uuid=$NURA_ROOT_UUID nura.internal"
    c_ok "Interne Payload: $OUT/m1n1-linux-internal.bin (Root UUID $NURA_ROOT_UUID)"
    c_ok "Fertig: $OUT/m1n1-linux.bin ($(du -h "$OUT/m1n1-linux.bin" | cut -f1)), DTBs: $(ls "$OUT"/dtbs | tr '\n' ' ')"
    echo
    echo "  Next:  ./boot.en.sh"
}

# ------------------------------------------------------------------ main ---
case "${1:-all}" in
    deps)    step_deps ;;
    init)    step_init ;;
    install) step_install ;;
    fixup)   step_fixup ;;
    export)  step_export ;;
    bootloader) step_bootloader ;;
    payload) step_payload ;;
    all)     step_deps; step_init; step_install; step_fixup; step_export; step_bootloader; step_payload ;;
    -h|--help|help) usage ;;
    *) usage; exit 1 ;;
esac

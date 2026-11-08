#!/usr/bin/env bash
# =============================================================================
#  iPhone SE (2016) – Nura (ehem. postmarketOS) Netboot-Image bauen
#
#  Gerät:   Apple iPhone SE 1. Gen. (iPhone8,4 / n69, SoC Apple A9)
#  Port:    Nura "Apple Generic iDevice" (apple-idevice, Hoolock-Linux-Kernel)
#  Ergebnis: out/m1n1-linux.bin  -> wird per PongoOS gebootet (siehe boot.sh)
#
#  Wichtig: A9 hat keine NVMe-Treiber -> Rootfs kommt IMMER per Netboot
#  (USB-Netzwerk + NBD vom PC). Auf das iPhone wird nichts geflasht.
# =============================================================================
set -euo pipefail

# ----------------------------------------------------------------- Konfig ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VENV:-$SCRIPT_DIR/.venv}"
PMB_GIT="${PMB_GIT:-https://gitlab.nura.eco/postmarketOS/pmbootstrap.git}"
PMB_REF="${PMB_REF:-}"               # Branch/Tag von pmbootstrap (leer = Default-Branch)
PMB="${PMB:-$VENV/bin/pmbootstrap}"  # Nura-Tool (heißt derzeit noch pmbootstrap)
DEVICE="apple-idevice"
KERNEL="${KERNEL:-16k}"               # A9 = 16K-Pages (4k nur für A7/A8)
UI="${UI:-phosh}"                    # phosh | console | sxmo-de-sway | ...
# Ausgelesen vom iPhone 7 (d101, A10) unter Hoolock 7.0:
#   Display  : simpledrm 750x1334 (kein GPU-Treiber -> Mesa llvmpipe)
#   Eingabe  : nur gpio-keys (Power/Lautstärke) – KEIN Touchscreen
#   Netz     : nur USB-Gadget usb0 (kein WLAN/BT/Modem), kein NVMe, kein Audio
# => Phosh wird per VNC (wayvnc über USB) vom Laptop aus bedient.
EXTRA_SPACE="${EXTRA_SPACE:-}"       # MB Zusatzplatz im Rootfs (leer = automatisch)
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_nura_iphone}"   # wird ins Image übernommen
VNC_LISTEN="${VNC_LISTEN:-172.16.42.1}"
HOSTNAME_PH="${HOSTNAME_PH:-iphone-se}"
DTB_FILTER="${DTB_FILTER:-all}"      # all = alle Apple-DTBs (m1n1 wählt passend) | n69 = nur iPhone SE
# PCIe/WLAN startet beim Booten. Notschalter, falls das iPhone dabei hängt:
#   PCIE_BOOT=0 ./build.sh payload   (Treiber dann per SSH startbar:
#   echo 0 > /sys/module/pcie_apple_t8010/parameters/disable;
#   echo 610000000.pcie > /sys/bus/platform/drivers/pcie-apple-t8010/bind)
PCIE_BOOT="${PCIE_BOOT:-1}"   # 0 = Notschalter (PCIe/WLAN aus, per SSH startbar)
# ext4-UUID der internen Partition "Nura" (nvme0n1p2, angelegt mit tools/nura_partition.sh)
NURA_ROOT_UUID="${NURA_ROOT_UUID:-663e8742-8b87-4502-9304-ee983b927a67}"
NVME_BOOT="${NVME_BOOT:-1}"   # 0 = PCIe-Port 0 (interner Speicher) beim Boot auslassen
NVME_AUTOLOAD="${NVME_AUTOLOAD:-1}"   # 0 = nvme-Modul gesperrt (nur manuell per modprobe)
# spidev.bufsiz: Maggie-FPGA-Bitstream (71 KB) in einem SPI-Durchgang laden (Audio-Tests)
CMDLINE="${CMDLINE:-console=tty0 earlycon=tty0 fbcon=rotate:0 spidev.bufsiz=262144$([[ "$PCIE_BOOT" == 1 ]] || echo ' pcie_apple_t8010.disable=1')$([[ "$NVME_BOOT" == 1 ]] || echo ' pcie_apple_t8010.skip_ports=0x1')}"
EXTRA_PKGS="${EXTRA_PKGS:-openssh,htop,nano},postmarketos-mkinitfs-hook-netboot,bluez"
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
Aufruf: $0 [Schritt]

Schritte (ohne Argument: alle der Reihe nach):
  deps      Abhängigkeiten prüfen/installieren (venv, pmbootstrap, pyusb, palera1n, ...)
  init      Nura für apple-idevice konfigurieren
  install   Rootfs + Kernel bauen (pmbootstrap install) inkl. Netboot-Hook
  fixup     Netboot-Image patchen (/boot nofail, NetworkManager ignoriert usb0)
  export    Kernel/initramfs/DTBs nach out/ exportieren
  bootloader m1n1.bin (Hoolock) bauen + Pongo.bin holen
  payload   m1n1-linux.bin zusammensetzen
  all       alles (Standard)

Umgebungsvariablen:
  UI=$UI  DTB_FILTER=$DTB_FILTER  EXTRA_PKGS=$EXTRA_PKGS
  CMDLINE="$CMDLINE"
EOF
}

# ------------------------------------------------------------- Schritte ---
step_deps() {
    c_info "Prüfe Abhängigkeiten …"
    local missing=()
    for b in git python3 sudo openssl curl make clang ld.lld zstd gzip; do command -v "$b" >/dev/null || missing+=("$b"); done
    ((${#missing[@]})) && die "Fehlt: ${missing[*]}"

    # --- Python-venv (PyPI-Versionen von pmbootstrap sind alle zurückgezogen) ---
    if [[ ! -x "$VENV/bin/python" ]]; then
        c_info "Lege venv an: $VENV"
        python3 -m venv "$VENV" \
          || die "venv fehlgeschlagen – 'sudo apt install python3-venv' und erneut starten."
    fi
    "$VENV/bin/python" -m pip install -q --upgrade pip

    if [[ ! -x "$PMB" || "${PMB_UPDATE:-0}" == "1" ]]; then
        c_info "Installiere pmbootstrap aus Git ($PMB_GIT ${PMB_REF:-default}) ins venv …"
        "$VENV/bin/pip" install -q --upgrade "git+${PMB_GIT}${PMB_REF:+@$PMB_REF}" \
          || die "pmbootstrap-Installation aus Git fehlgeschlagen."
    fi
    c_ok "pmbootstrap: $("$PMB" --version 2>/dev/null || echo '?')  ($PMB)"

    "$VENV/bin/python" -c 'import usb.core' 2>/dev/null || {
        c_info "Installiere pyusb ins venv (für pongo_send.py) …"
        "$VENV/bin/pip" install -q pyusb
    }
    if ! "$VENV/bin/python" -c 'import usb.backend.libusb1 as b; assert b.get_backend()' 2>/dev/null; then
        c_warn "libusb-1.0 fehlt evtl. – ggf. 'sudo apt install libusb-1.0-0'."
    fi
    if ! command -v cargo >/dev/null && [[ -x "$HOME/.cargo/bin/cargo" ]]; then export PATH="$HOME/.cargo/bin:$PATH"; fi
    command -v cargo >/dev/null || die "Rust (cargo/rustup) fehlt – für m1n1 nötig: https://rustup.rs"
    if ! command -v palera1n >/dev/null; then
        c_info "Installiere palera1n (offizielles Script, fragt selbst nach sudo) …"
        /bin/sh -c "$(curl -fsSL https://static.palera.in/scripts/install.sh)" \
          || die "palera1n-Installation fehlgeschlagen – manuell: https://github.com/palera1n/palera1n/releases"
    fi
    c_ok "palera1n: $( { palera1n --version 2>&1 || true; } | grep -m1 -iE 'palera1n|[0-9]+\.[0-9]' || echo vorhanden)"
    c_ok "Abhängigkeiten ok."
}

step_init() {
    # Erst-Init nur, wenn noch gar keine pmbootstrap-Konfiguration existiert.
    if ! "$PMB" config work >/dev/null 2>&1 || [[ ! -d "$("$PMB" config aports 2>/dev/null)" ]]; then
        c_info "Erste Einrichtung – 'pmbootstrap init' (Fragen einfach mit Enter bestätigen,"
        c_info "Gerät/Kernel werden danach automatisch auf apple-idevice/16k gesetzt)."
        "$PMB" init
    fi
    # Gerät, Kernel & Co. NICHT interaktiv, sondern fest setzen:
    "$PMB" config device "$DEVICE"
    "$PMB" config kernel "$KERNEL"
    "$PMB" config ui "$UI"
    "$PMB" config hostname "$HOSTNAME_PH"
    "$PMB" config extra_packages "$EXTRA_PKGS"
    "$PMB" config extra_space "$EXTRA_SPACE"
    if [[ ! -f "$SSH_KEY" ]]; then
        c_info "Erzeuge SSH-Schlüssel für das iPhone: $SSH_KEY"
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
        || die "Falsche Konfiguration (device=$d kernel=$k) – erst '$0 init'."
}

# Läuft noch der Netboot vom letzten iPhone-Start, hält er das Image eingehängt und
# pmbootstrap scheitert mit "umount … netboot" (Exit 32) -> vorher aufräumen.
stop_old_netboot() {
    if pgrep -f 'nbd-server|pmbootstrap netboot' >/dev/null 2>&1; then
        c_warn "Netboot vom letzten iPhone-Start läuft noch – wird beendet (das iPhone verliert sein Rootfs)."
        "$SCRIPT_DIR/tools/cleanup.sh" --no-usb-reset >/dev/null 2>&1 || true
        pgrep -f 'nbd-server|pmbootstrap netboot' >/dev/null 2>&1 \
            && die "Netboot läuft immer noch – bitte das boot.sh-Fenster mit Strg+C beenden und erneut starten."
        c_ok "Alter Netboot beendet."
    fi
}

step_install() {
    stop_old_netboot
    check_device
    # Reste früherer Läufe (Loop-Devices, Bind-Mounts) aufräumen – sonst
    # schlägt mkfs mit "No such device or address" auf /dev/installp2 fehl.
    "$PMB" shutdown >/dev/null 2>&1 || true
    c_info "Baue Rootfs (pmbootstrap install) – das dauert beim ersten Mal …"
    # Das erzeugte Rootfs-Image wird später von 'pmbootstrap netboot serve' per NBD ausgeliefert.
    "$PMB" -y install --password "${PMOS_PASSWORD:-147147}"
    "$PMB" shutdown >/dev/null 2>&1 || true
    c_ok "Rootfs gebaut. Standard-Passwort für Benutzer '$("$PMB" config user 2>/dev/null || echo user)': ${PMOS_PASSWORD:-147147}"
}

workdir() { "$PMB" config work; }

# Netboot-Image nachbessern:
#  - /boot ist beim Netboot nicht verfügbar -> 'nofail', sonst Emergency Mode
#  - NetworkManager darf usb0 NICHT verwalten, sonst fliegt 172.16.42.1 weg
#    und die NBD-Verbindung (= das komplette Rootfs) reißt ab
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
    [[ -b "$part" ]] || { sudo losetup -d "$loop"; die "Root-Partition in $img nicht gefunden."; }
    mnt="$(mktemp -d)"
    sudo mount -o init_itable=0 "$part" "$mnt"
    # /boot -> nofail + kurzer Timeout
    sudo sed -i -E '/[[:space:]]\/boot[[:space:]]/{/nofail/!s/(ext[234]|vfat)[[:space:]]+([^[:space:]]+)/\1 \2,nofail,x-systemd.device-timeout=5s/}' "$mnt/etc/fstab"
    # NetworkManager: usb0 nicht anfassen
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
    # Erstboot-Aufgaben, die über NBD extrem langsam sind, hier lokal erledigen
    if command -v systemd-hwdb >/dev/null; then
        sudo systemd-hwdb --root="$mnt" update 2>/dev/null && c_ok "hwdb lokal erzeugt."
    fi
    # ConditionNeedsUpdate= erfüllt -> kein hwdb/ldconfig/catalog-Update beim Boot
    sudo touch -r "$mnt/usr" "$mnt/etc/.updated" "$mnt/var/.updated" 2>/dev/null || true

    # ext4-Lazy-Init (Inode-Tabellen nullen) lokal abwarten statt über USB
    c_info "Warte auf ext4-Initialisierung (lokal, wenige Sekunden) …"
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

# Phosh an iPhone (A9/A10) anpassen – ohne Touch & GPU
# Touch (iPhone 7): hx-touchd + Firmware + Kalibrierung + Panel-Neuinit vor dem Start.
# Voraussetzung: tools/kernel-custom.sh (Touch-Treiber) und tools/hx-touchd/build.sh.
patch_touch() {
    local m="$1" h="$SCRIPT_DIR/out/hx-touch"
    [[ -x "$h/hx-touchd" && -f "$h/syscfg.bin" && -f "$h/D10.mtprops" ]] || {
        c_warn "Touch: out/hx-touch fehlt – erst tools/hx-touchd/build.sh (Touch bleibt aus)."; return 0; }
    c_info "Touch: hx-touchd + Firmware + Panel-Neuinit installieren …"
    sudo install -Dm755 "$h/hx-touchd" "$m/usr/local/sbin/hx-touchd"
    sudo install -Dm755 "$SCRIPT_DIR/tools/dsi_reinit.py" "$m/usr/local/sbin/dsi-reinit"
    sudo install -Dm644 "$h/D10.mtprops" "$m/usr/local/share/hx-touch/D10.mtprops"
    sudo install -Dm644 "$h/syscfg.bin" "$m/usr/local/share/hx-touch/syscfg.bin"
    sudo tee "$m/etc/systemd/system/hx-touchd.service" >/dev/null <<'UNIT'
[Unit]
Description=Apple multitouch firmware loader (hx-touchd, Project Sandcastle)
ConditionPathExists=/dev/hx-touch
After=systemd-modules-load.service
Before=greetd.service

[Service]
# In-cell-Touch: Panel einmal aus dem Reset-Default starten, sonst scannt der Controller nicht
ExecStartPre=-/usr/bin/python3 /usr/local/sbin/dsi-reinit
ExecStart=/usr/local/sbin/hx-touchd C1F5D,2 /usr/local/share/hx-touch/D10.mtprops /usr/local/share/hx-touch/syscfg.bin
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT
    sudo mkdir -p "$m/etc/systemd/system/multi-user.target.wants"
    sudo ln -sf ../hx-touchd.service "$m/etc/systemd/system/multi-user.target.wants/hx-touchd.service"
    c_ok "Touch-Dienst eingerichtet."
}

# WLAN (iPhone 7, BCM4355 "elsa"): Firmware aus der iOS-Rootfs für brcmfmac
# (erzeugt von tools/wifi-fw.py nach out/wifi-fw/brcm)
patch_wifi() {
    local m="$1" w="$SCRIPT_DIR/out/wifi-fw/brcm"
    if ! ls "$w"/*.bin >/dev/null 2>&1 && [[ -d "$SCRIPT_DIR/research/firmware/wifi" ]]; then
        "$VENV/bin/python" "$SCRIPT_DIR/tools/wifi-fw.py" >/dev/null || true
    fi
    ls "$w"/*.bin >/dev/null 2>&1 || { c_warn "WLAN: keine Firmware in out/wifi-fw – WLAN bleibt aus."; return 0; }
    sudo mkdir -p "$m/lib/firmware/brcm"
    sudo cp "$w"/* "$m/lib/firmware/brcm/"
    # brcmfmac früh per systemd-modules-load laden statt erst über udev (udevd hing beim
    # ersten Boot ~190 s, WLAN kam dadurch erst nach ~4 min)
    sudo mkdir -p "$m/etc/modules-load.d"
    echo brcmfmac | sudo tee "$m/etc/modules-load.d/wlan.conf" >/dev/null
    # Firmware-Loader: nicht 60 s je fehlender Datei auf einen Userspace-Helfer warten
    sudo mkdir -p "$m/etc/tmpfiles.d"
    echo 'w /sys/class/firmware/timeout - - - - 1' | sudo tee "$m/etc/tmpfiles.d/firmware-timeout.conf" >/dev/null
    c_ok "WLAN-Firmware installiert ($(ls "$w" | wc -l) Dateien)."
}

# Bluetooth (iPhone 7): BCM4355C0 an UART1, Firmware-Patch aus iOS-BlueTool (tools/bt-fw.sh)
patch_bt() {
    local m="$1" b="$SCRIPT_DIR/out/bt-fw/brcm"
    [[ -f "$b/BCM.hcd" ]] || "$SCRIPT_DIR/tools/bt-fw.sh" >/dev/null 2>&1 || true
    [[ -f "$b/BCM.hcd" ]] || { c_warn "Bluetooth: keine Firmware in out/bt-fw – Chip läuft mit ROM-Firmware."; }
    [[ -f "$b/BCM.hcd" ]] && { sudo mkdir -p "$m/lib/firmware/brcm"; sudo cp "$b"/*.hcd "$m/lib/firmware/brcm/"; }
    # hci_uart früh laden (udevd hängt beim Boot wegen NBD, s. WLAN)
    sudo mkdir -p "$m/etc/modules-load.d"
    echo hci_uart | sudo tee "$m/etc/modules-load.d/bluetooth.conf" >/dev/null
    # das Image maskiert bluetooth.service (-> /dev/null) – Maske entfernen
    [[ -L "$m/etc/systemd/system/bluetooth.service" ]] && sudo rm -f "$m/etc/systemd/system/bluetooth.service"
    sudo mkdir -p "$m/etc/systemd/system/multi-user.target.wants"
    [[ -f "$m/usr/lib/systemd/system/bluetooth.service" ]] && \
        sudo ln -sf /usr/lib/systemd/system/bluetooth.service "$m/etc/systemd/system/multi-user.target.wants/bluetooth.service"
    c_ok "Bluetooth eingerichtet."
}

# Interner Speicher (iPhone 7): nvme-Modul in der Testphase NICHT automatisch laden –
# erst per SSH: modprobe nvme (hängt der Controller, bleibt das System bedienbar)
patch_nvme() {
    local m="$1"
    sudo mkdir -p "$m/etc/modprobe.d"
    # iOS-Daten schützen: APFS-Container (nvme0n1p1) und die System-Namespaces 2..7 immer schreibgeschützt
    sudo mkdir -p "$m/etc/udev/rules.d"
    printf '%s\n' '# iPhone 7: iOS-Bereiche des internen Speichers nie beschreiben' \
        'ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="nvme0n1p1|nvme0n[2-9]", RUN+="/sbin/blockdev --setro /dev/%k"' \
        | sudo tee "$m/etc/udev/rules.d/60-ios-readonly.rules" >/dev/null
    if [[ "$NVME_AUTOLOAD" == 1 ]]; then
        sudo rm -f "$m/etc/modprobe.d/nvme-test.conf"
        echo nvme | sudo tee "$m/etc/modules-load.d/nvme.conf" >/dev/null
        c_ok "NVMe: wird beim Start geladen (iOS-Bereiche schreibgeschützt)."
    else
        sudo rm -f "$m/etc/modules-load.d/nvme.conf"
        echo 'blacklist nvme' | sudo tee "$m/etc/modprobe.d/nvme-test.conf" >/dev/null
        c_info "NVMe: Modul gesperrt (Test: per SSH 'modprobe nvme'; NVME_AUTOLOAD=1 hebt das auf)"
    fi
}

# Laden (iPhone 7): Ladechip Tigris steht ohne iOS-Treiber auf 90 mA USB-Eingangslimit –
# der Akku entlädt sich trotz Kabel. tigris-charge hebt das Limit (bis 900 mA, mit
# Spannungseinbruch-Kontrolle) und setzt es nach erneutem Anstecken wieder.
patch_charge() {
    local m="$1"
    c_info "Laden: tigris-charge-Dienst installieren …"
    sudo install -Dm755 "$SCRIPT_DIR/tools/tigris-charge.py" "$m/usr/local/sbin/tigris-charge"
    sudo install -Dm644 "$SCRIPT_DIR/tools/tigris-charge.service" "$m/etc/systemd/system/tigris-charge.service"
    sudo mkdir -p "$m/etc/systemd/system/multi-user.target.wants"
    sudo ln -sf ../tigris-charge.service "$m/etc/systemd/system/multi-user.target.wants/tigris-charge.service"
    c_ok "tigris-charge eingerichtet."
    # Automatische Helligkeit über den Lichtsensor CT821 (I2C2 per /dev/mem, siehe research/SENSOR-ANALYSE.md)
    c_info "Helligkeit: nura-autobright-Dienst installieren …"
    sudo install -Dm755 "$SCRIPT_DIR/tools/nura-autobright.py" "$m/usr/local/sbin/nura-autobright"
    sudo install -Dm644 "$SCRIPT_DIR/tools/i2c_poll.py" "$m/usr/local/sbin/nura_i2c.py"
    sudo install -Dm644 "$SCRIPT_DIR/tools/nura-autobright.service" "$m/etc/systemd/system/nura-autobright.service"
    sudo ln -sf ../nura-autobright.service "$m/etc/systemd/system/multi-user.target.wants/nura-autobright.service"
    c_ok "nura-autobright eingerichtet."
}

patch_phosh() {
    local m="$1"
    c_info "Phosh-Anpassungen: Skalierung, Software-Rendering, kein Sperrbildschirm, wayvnc …"

    # 1) Display 750x1334 @ 326 dpi -> Skalierung 2
    sudo mkdir -p "$m/etc/phosh"
    sudo tee "$m/etc/phosh/phoc.ini" >/dev/null <<'INI'
[core]
xwayland=false

[output:Unknown-1]
scale = 2
INI

    # 2) Software-Rendering optimieren (kein GPU-Treiber)
    sudo mkdir -p "$m/etc/environment.d" "$m/etc/profile.d"
    # WLR_RENDERER_ALLOW_SOFTWARE=1: phoc nutzt GLES2/llvmpipe statt pixman –
    # nötig, damit wayvnc (ext-image-copy-capture) Bildformate bekommt.
    printf 'GSK_RENDERER=cairo\nLIBGL_ALWAYS_SOFTWARE=1\nGALLIUM_DRIVER=llvmpipe\nWLR_RENDERER_ALLOW_SOFTWARE=1\n' \
        | sudo tee "$m/etc/environment.d/50-iphone-nura.conf" >/dev/null
    printf 'export GSK_RENDERER=cairo\nexport LIBGL_ALWAYS_SOFTWARE=1\nexport GALLIUM_DRIVER=llvmpipe\nexport WLR_RENDERER_ALLOW_SOFTWARE=1\n' \
        | sudo tee "$m/etc/profile.d/50-iphone-nura.sh" >/dev/null
    sudo grep -q WLR_RENDERER_ALLOW_SOFTWARE "$m/etc/environment" 2>/dev/null \
        || echo 'WLR_RENDERER_ALLOW_SOFTWARE=1' | sudo tee -a "$m/etc/environment" >/dev/null

    # 3) Ohne Touch kein PIN-Entsperren am Gerät -> Sperre/Blanking aus
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
GSO
    # Schemas beim ersten Boot auf dem Gerät kompilieren (Host kann aarch64 nicht ausführen)
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

    # 4) Autologin: phrog (Login-Greeter) ist ohne Touch nicht bedienbar
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
        c_warn "/etc/phrog/greetd-config.toml nicht im Image – Autologin übersprungen."
    fi

    # Entschlacken + Timeouts (user@.service, Phosh, OSK) – siehe tools/phosh-slim.sh
    sudo sh "$SCRIPT_DIR/tools/phosh-slim.sh" "$m" >/dev/null && c_ok "Phosh entschlackt (Modem/Calls/Chatty/VVM/Evolution aus)."

    # Start-Timeout hoch (Software-Rendering + Netboot = langsam)
    sudo mkdir -p "$m/etc/systemd/user/mobi.phosh.Shell.service.d"
    printf '[Service]\nTimeoutStartSec=600\n' \
        | sudo tee "$m/etc/systemd/user/mobi.phosh.Shell.service.d/timeout.conf" >/dev/null
    # Dienste ohne passende Hardware abschalten (spart RAM/CPU/IO)
    for svc in ModemManager.service bluetooth.service eg25-manager.service; do
        sudo ln -sf /dev/null "$m/etc/systemd/system/$svc"
    done
    for ad in udiskie.desktop org.gnome.SettingsDaemon.Smartcard.desktop \
              org.gnome.SettingsDaemon.PrintNotifications.desktop \
              org.gnome.SettingsDaemon.Wwan.desktop org.gnome.SettingsDaemon.UsbProtection.desktop; do
        printf '[Desktop Entry]\nType=Application\nName=disabled\nHidden=true\n' \
            | sudo tee "$m/etc/xdg/autostart/$ad" >/dev/null
    done

    # wayvnc-Shim: blendet ext-image-copy-capture aus (liefert ohne GPU keine
    # Formate) -> wayvnc nutzt zwlr_screencopy. Quelle: tools/wayvnc-hide-ext/
    local shim="$SCRIPT_DIR/tools/wayvnc-hide-ext/hide_ext_capture.so"
    if [[ ! -f "$shim" ]] && command -v aarch64-linux-gnu-gcc >/dev/null; then
        aarch64-linux-gnu-gcc -shared -fPIC -nostdlib -O2 -fno-stack-protector -fno-builtin \
            -o "$shim" "$SCRIPT_DIR/tools/wayvnc-hide-ext/hide_ext_capture.c"
    fi
    if [[ -f "$shim" ]]; then
        sudo install -m755 "$shim" "$m/usr/lib/wayvnc-hide-ext-capture.so"
    else
        c_warn "wayvnc-Shim fehlt (aarch64-linux-gnu-gcc nicht installiert) – VNC zeigt evtl. kein Bild."
    fi

    # 5) wayvnc im Phosh-Session-Start -> Bedienung per VNC vom Laptop
    sudo mkdir -p "$m/etc/xdg/autostart"
    sudo tee "$m/etc/xdg/autostart/wayvnc-iphone.desktop" >/dev/null <<DESK
[Desktop Entry]
Type=Application
Name=wayvnc (USB)
Comment=VNC-Server auf ${VNC_LISTEN}:5900 – Fernbedienung ohne Touchscreen
Exec=sh -c 'sleep 3; exec env LD_PRELOAD=/usr/lib/wayvnc-hide-ext-capture.so wayvnc --max-fps=15 ${VNC_LISTEN} 5900'
NoDisplay=true
DESK
}

step_fixup() {
    check_device
    local w; w="$(workdir)"
    "$PMB" shutdown >/dev/null 2>&1 || true   # Image darf nicht mehr eingehängt sein
    patch_image "$w/chroot_native/home/pmos/rootfs/${DEVICE}.img"
    # pmbootstrap kopiert nach images_netboot/ nur, wenn dort noch nichts liegt ->
    # alte Kopie entfernen, damit 'netboot serve' das frisch gebaute Image nimmt.
    if sudo test -f "$w/images_netboot/${DEVICE}.img"; then
        c_info "Entferne alte Netboot-Kopie (wird beim nächsten boot.sh neu angelegt) …"
        sudo rm -f "$w/images_netboot/${DEVICE}.img"
    fi
    # auch im Chroot hinterlegen, damit künftige Installs es mitbringen
    sudo mkdir -p "$w/chroot_rootfs_${DEVICE}/etc/NetworkManager/conf.d"
    printf '[keyfile]\nunmanaged-devices=interface-name:usb0\n' \
        | sudo tee "$w/chroot_rootfs_${DEVICE}/etc/NetworkManager/conf.d/90-netboot-usb0.conf" >/dev/null
    c_ok "Netboot-Image gepatcht."
}

step_export() {
    check_device
    rm -rf "$EXPORT_DIR"; mkdir -p "$EXPORT_DIR" "$OUT/dtbs"
    c_info "Exportiere Kernel + initramfs …"
    "$PMB" export --no-install "$EXPORT_DIR" 2>/dev/null || "$PMB" export "$EXPORT_DIR"

    local rootfs; rootfs="$(workdir)/chroot_rootfs_${DEVICE}"
    [[ -d "$rootfs" ]] || die "Rootfs-Chroot nicht gefunden: $rootfs"

    # (m1n1-idevice.macho aus dem Paket ist für die iBoot-Methode – wir nutzen PongoOS + m1n1.bin)

    # DTBs
    local dtbdir="$rootfs/boot/dtbs/apple"
    sudo test -d "$dtbdir" || dtbdir="$(sudo find "$rootfs/boot" -type d -name apple | head -n1)"
    [[ -n "$dtbdir" ]] || die "Keine Apple-DTBs im Rootfs gefunden."
    if [[ "$DTB_FILTER" == "n69" ]]; then
        sudo find "$dtbdir" -name '*n69*.dtb' -exec cp {} "$OUT/dtbs/" \;
        ls "$OUT"/dtbs/*.dtb >/dev/null 2>&1 || { c_warn "Keine n69-DTB gefunden – nehme alle."; sudo cp "$dtbdir"/*.dtb "$OUT/dtbs/"; }
    else
        sudo cp "$dtbdir"/*.dtb "$OUT/dtbs/"
    fi
    sudo chown -R "$(id -u):$(id -g)" "$OUT"
    c_ok "Export fertig: $(ls "$OUT"/dtbs | wc -l) DTBs, m1n1, vmlinuz, initramfs."
}

step_bootloader() {
    mkdir -p "$SRC" "$OUT"
    if ! command -v cargo >/dev/null && [[ -x "$HOME/.cargo/bin/cargo" ]]; then export PATH="$HOME/.cargo/bin:$PATH"; fi

    c_info "Hole/aktualisiere Hoolock-m1n1 …"
    if [[ -d "$SRC/m1n1/.git" ]]; then
        git -C "$SRC/m1n1" checkout -q -- .      # eigene Patches zurücknehmen, sonst scheitert pull
        git -C "$SRC/m1n1" pull -q --ff-only
    else
        git clone -q --depth 1 "$HL_M1N1_GIT" "$SRC/m1n1"
    fi
    git -C "$SRC/m1n1" submodule update -q --init --depth 1
    # eigene m1n1-Patches (z. B. WLAN-Daten aus der ADT für das iPhone 7)
    for p in "$SCRIPT_DIR"/tools/m1n1-patches/*.patch; do
        [[ -f "$p" ]] || continue
        git -C "$SRC/m1n1" apply --check "$p" 2>/dev/null \
            && git -C "$SRC/m1n1" apply "$p" && c_ok "m1n1-Patch: $(basename "$p")" \
            || c_warn "m1n1-Patch passt nicht (mehr): $(basename "$p")"
    done
    rustup target add aarch64-unknown-none-softfloat >/dev/null
    c_info "Baue m1n1.bin (PongoOS-Variante) …"
    make -C "$SRC/m1n1" -j"$(nproc)" >"$OUT/m1n1-build.log" 2>&1 \
      || { tail -20 "$OUT/m1n1-build.log"; die "m1n1-Build fehlgeschlagen (Log: out/m1n1-build.log)."; }
    cp "$SRC/m1n1/build/m1n1.bin" "$OUT/m1n1.bin"

    c_info "Hole Hoolock-Pongo.bin …"
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
    [[ -f "$kernel" && -f "$initfs" ]] || die "Export unvollständig – erst '$0 export'."
    [[ -f "$OUT/m1n1.bin" ]] || die "out/m1n1.bin fehlt – erst '$0 bootloader'."
    ls "$OUT"/dtbs/*.dtb >/dev/null 2>&1 || die "Keine DTBs in out/dtbs."
    # Eigene DTBs (z. B. iPhone 7 mit WLAN-Knoten) ersetzen die aus dem Kernelpaket,
    # damit DT-Änderungen keinen neuen Kernel-Build brauchen.
    if ls "$OUT"/dtbs-override/*.dtb >/dev/null 2>&1; then
        cp "$OUT"/dtbs-override/*.dtb "$OUT/dtbs/"
        c_ok "DTB-Override: $(cd "$OUT/dtbs-override" && ls *.dtb | tr '\n' ' ')"
    fi

    # m1n1 versteht nur gzip/xz/cpio – Nura baut das initramfs mit zstd.
    c_info "Packe initramfs nach gzip um …"
    case "$(head -c4 "$initfs" | od -An -tx1 | tr -d ' ')" in
        1f8b*)    cp "$initfs" "$OUT/initramfs.gz" ;;
        28b52ffd) zstd -dcq "$initfs" | gzip -9 > "$OUT/initramfs.gz" ;;
        fd377a58) xz -dc "$initfs" | gzip -9 > "$OUT/initramfs.gz" ;;
        3037303*) gzip -9c "$initfs" > "$OUT/initramfs.gz" ;;
        *) die "Unbekanntes initramfs-Format: $(file -b "$initfs")" ;;
    esac
    head -c2 "$kernel" | od -An -tx1 | grep -q '1f 8b' \
        || c_warn "Kernel ist nicht gzip – m1n1 kann ihn inline evtl. nicht korrekt einlesen."

    # Überlagerung fürs initramfs: Netboot-Hook überspringen, wenn "nura.internal" auf der
    # Kommandozeile steht (Root kommt dann per pmos.root_uuid vom internen Speicher).
    # Zweites cpio-Archiv im selben gzip-Strom – der Kernel entpackt beide nacheinander.
    local ov; ov="$(mktemp -d)"
    mkdir -p "$ov/hooks"
    zcat "$OUT/initramfs.gz" | (cd "$ov" && cpio -i --quiet hooks/netboot.sh 2>/dev/null) || true
    if [[ -f "$ov/hooks/netboot.sh" ]]; then
        { printf '#!/bin/sh\n# Nura: interner Speicher statt Netboot\n'
          printf 'if grep -qw nura.internal /proc/cmdline; then echo "Netboot übersprungen (nura.internal)"; exit 0; fi\n'
          tail -n +2 "$ov/hooks/netboot.sh"; } > "$ov/netboot.new"
        mv "$ov/netboot.new" "$ov/hooks/netboot.sh"; chmod 755 "$ov/hooks/netboot.sh"
        { zcat "$OUT/initramfs.gz"; (cd "$ov" && echo hooks/netboot.sh | cpio -o -H newc -R 0:0 --quiet); } \
            | gzip -9 > "$OUT/initramfs-nura.gz"
        mv "$OUT/initramfs-nura.gz" "$OUT/initramfs.gz"
        c_ok "initramfs: Netboot-Hook überspringbar (nura.internal)."
    else
        c_warn "initramfs ohne hooks/netboot.sh – keine Überlagerung nötig."
    fi
    rm -rf "$ov"

    mkpayload() {  # $1 = Ausgabe, $2 = Kommandozeile
        {
            cat "$OUT/m1n1.bin"
            printf 'chosen.bootargs=%s\n' "$2"
            cat "$OUT"/dtbs/*.dtb
            cat "$kernel"
            cat "$OUT/initramfs.gz"
        } > "$1"
    }
    c_info "Setze m1n1-Payloads zusammen (m1n1.bin + bootargs + DTBs + Kernel + initramfs) …"
    mkpayload "$OUT/m1n1-linux.bin" "$CMDLINE"
    mkpayload "$OUT/m1n1-linux-internal.bin" "$CMDLINE pmos.root_uuid=$NURA_ROOT_UUID nura.internal"
    c_ok "Interne Payload: $OUT/m1n1-linux-internal.bin (Root UUID $NURA_ROOT_UUID)"
    c_ok "Fertig: $OUT/m1n1-linux.bin ($(du -h "$OUT/m1n1-linux.bin" | cut -f1)), DTBs: $(ls "$OUT"/dtbs | tr '\n' ' ')"
    echo
    echo "  Weiter mit:  ./boot.sh"
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

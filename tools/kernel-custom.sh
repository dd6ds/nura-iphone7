#!/usr/bin/env bash
# =============================================================================
#  kernel-custom.sh – eigenen Nura-Kernel (linux-postmarketos-apple-16k) bauen
#
#  - setzt Zusatzoptionen in der Kernel-Konfiguration (KCONFIG unten)
#  - hängt Patches aus tools/kernel-patches/*.patch an (z. B. Device-Tree für Touch)
#  - erhöht pkgrel, damit das lokale Paket Vorrang vor dem Nura-Repo hat
#  - baut per pmbootstrap (Cross-Compile auf dem Laptop, ca. 30–60 min)
#
#  Danach:  ./build.sh   (installiert den eigenen Kernel ins Image, fixup, payload)
#
#  Hinweis: Die Änderungen liegen im pmaports-Clone von pmbootstrap.
#  'pmbootstrap pull' kann daran scheitern -> vorher: tools/kernel-custom.sh --reset
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PMB="${PMB:-$SCRIPT_DIR/.venv/bin/pmbootstrap}"
PKG="linux-postmarketos-apple-16k"
PKGREL_BUMP="${PKGREL_BUMP:-118}"   # r100 i2c/spidev, r101 Touch, r102 PCIe (ohne CONFIG_PCI), r103 PCIe/WLAN, r104 PCIe zur Laufzeit startbar + Schrittmeldungen, r105 PD-Liste-Fix, r106 Akku (Tigris + HDQ-Gauge), r107 Tigris-I2C Einzelbyte-Fix, r108 IBUSLIMIT-Reset abfangen, r109 Bluetooth (hci_bcm Apple/UART1), r110 Tigris-Rundung, r111 NVMe-Port 0 + Akku-Feinschliff, r112 NVMe ohne SGL + CID-Quirk, r113 NVMMU, r114 NVMe-Tags < 36, r115 nvme eingebaut (Root intern), r116 spi-s5l CS-Polarität (Maggie lädt), r117 spi-s5l SPI-Modus je Gerät (Codec Mode 0), r118 Bluetooth RFCOMM/BNEP/HIDP (Kopfhörer-HFP)
PATCHDIR="$SCRIPT_DIR/tools/kernel-patches"

# Zusätzliche Kernel-Optionen (Name=Wert)
KCONFIG=(
    "CONFIG_I2C_CHARDEV=y"       # /dev/i2c-* -> PMU-Register lesen (i2ctransfer / Python)
    "CONFIG_SPI_SPIDEV=y"        # /dev/spidev* -> Touch-Controller aus dem Userspace testen
    # --- Touch (Patches 0001-0006) ---
    "CONFIG_REGULATOR=y"                    # war im Nura-Kernel aus
    "CONFIG_MFD_SIMPLE_MFD_I2C=y"           # chestnut Display-PMU (i2c0 @0x27)
    "CONFIG_SPI_APPLE_S5L=y"                # A10-SPI (Port von Sandcastle spi-hx)
    "CONFIG_COMMON_CLK_APPLE_TOUCH=y"       # 32,768-kHz-Touch-Takt aus PMGR
    "CONFIG_REGULATOR_APPLE_PMIC_SWITCH=y"  # touch-core (D2333) / touch-hv (chestnut)
    "CONFIG_TOUCHSCREEN_HX=y"               # /dev/hx-touch für hx-touchd
    # --- PCIe + WLAN (Patches 0007-0009) ---
    "CONFIG_PCI=y"                          # war im Nura-Kernel aus!
    "CONFIG_PCI_MSI=y"
    "CONFIG_GPIO_APPLE_PMIC=y"              # D2333-GPIOs (WLAN reg_on)
    "CONFIG_PCIE_APPLE_T8010=y"             # A10-PCIe (Port von Sandcastle pcie-hx)
    "CONFIG_WIRELESS=y"
    "CONFIG_CFG80211=m"
    "CONFIG_WLAN=y"
    "CONFIG_WLAN_VENDOR_BROADCOM=y"
    "CONFIG_BRCMUTIL=m"
    "CONFIG_BRCMFMAC=m"                     # BCM4355 (als Modul: rmmod/modprobe zum Testen)
    "CONFIG_BRCMFMAC_PCIE=y"
    "CONFIG_SERIAL_SAMSUNG_UARTS=8"
    "CONFIG_CHARGER_APPLE_TIGRIS=y"
    "CONFIG_BT=m"
    "CONFIG_BT_HCIUART=m"
    "CONFIG_BT_HCIUART_SERDEV=y"
    "CONFIG_BT_HCIUART_BCM=y"
    "CONFIG_BT_RFCOMM=m"                   # HFP/HSP: Kopfhörer bauen zuerst RFCOMM auf, sonst trennt BlueZ
    "CONFIG_BT_RFCOMM_TTY=y"
    "CONFIG_BT_BNEP=m"                     # Bluetooth-Tethering (PAN)
    "CONFIG_BT_BNEP_MC_FILTER=y"
    "CONFIG_BT_BNEP_PROTO_FILTER=y"
    "CONFIG_BT_HIDP=m"                     # Bluetooth-Tastaturen/-Mäuse (classic)
    "CONFIG_UHID=m"                        # Bluetooth-LE-Eingabegeräte (HoG über BlueZ)
    "CONFIG_BLK_DEV_NVME=y"
)

c_info() { printf '\e[1;34m[*]\e[0m %s\n' "$*"; }
c_ok()   { printf '\e[1;32m[+]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m[!]\e[0m %s\n' "$*"; }
die()    { printf '\e[1;31m[x]\e[0m %s\n' "$*" >&2; exit 1; }

APORTS="$("$PMB" config aports)"
APORT="$(find "$APORTS/device" -maxdepth 2 -type d -name "$PKG" | head -n1)"
[[ -d "$APORT" ]] || die "Aport $PKG nicht gefunden in $APORTS"
CFG="$(ls "$APORT"/config-*.aarch64 | head -n1)"

if [[ "${1:-}" == "--reset" ]]; then
    c_info "Setze $PKG im pmaports-Clone zurück …"
    git -C "$APORTS" checkout -- "$APORT"
    git -C "$APORTS" clean -fdq -- "$APORT"
    c_ok "Zurückgesetzt. Nächstes ./build.sh nutzt wieder den Standard-Kernel (ggf. 'pmbootstrap zap -p')."
    exit 0
fi

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

stop_old_netboot

# 1) Kernel-Optionen setzen (idempotent)
c_info "Kernel-Optionen setzen in $(basename "$CFG") …"
for kv in "${KCONFIG[@]}"; do
    key="${kv%%=*}"
    sed -i -E "/^(# )?${key}( is not set|=.*)$/d" "$CFG"
    echo "$kv" >> "$CFG"
    echo "    $kv"
done

# 1b) Vorab-Prüfung: überlebt jede Option 'make olddefconfig'? (fehlende Abhängigkeiten
#     werden sonst beim Build stillschweigend entfernt – so war CONFIG_PCI verloren)
KSRC="${KSRC:-$SCRIPT_DIR/src/kpatch/linux-hoolock-7.0.12}"
if [[ -f "$KSRC/Makefile" ]]; then
    tmpcfg="$(mktemp)"; cp "$CFG" "$tmpcfg"
    if make -s -C "$KSRC" ARCH=arm64 LLVM=1 KCONFIG_CONFIG="$tmpcfg" olddefconfig >/dev/null 2>&1; then
        lost=()
        for kv in "${KCONFIG[@]}"; do grep -qx "$kv" "$tmpcfg" || lost+=("$kv"); done
        rm -f "$tmpcfg" "$tmpcfg.old"
        ((${#lost[@]})) && die "Diese Optionen würden beim Build verloren gehen (Abhängigkeit fehlt): ${lost[*]}"
        c_ok "Alle ${#KCONFIG[@]} Kernel-Optionen überleben olddefconfig."
    else
        rm -f "$tmpcfg"; c_warn "olddefconfig-Prüfung nicht möglich (Quellbaum $KSRC) – übersprungen."
    fi
else
    c_warn "Kein lokaler Kernel-Quellbaum ($KSRC) – Optionsprüfung übersprungen."
fi

# 2) Patches einbinden
mkdir -p "$PATCHDIR"
shopt -s nullglob
PATCHES=("$PATCHDIR"/*.patch)
shopt -u nullglob
# alte eigene Patches aus dem Aport entfernen
find "$APORT" -maxdepth 1 -name 'nura-iphone-*.patch' -delete
sed -i '/nura-iphone-.*\.patch/d' "$APORT/APKBUILD"
# rückwärts einfügen, damit sie in source= in der richtigen Reihenfolge stehen
for ((i=${#PATCHES[@]}-1; i>=0; i--)); do
    p="${PATCHES[$i]}"
    dst="nura-iphone-$(basename "$p")"
    cp "$p" "$APORT/$dst"
    # in source= hinter die config-Zeile einfügen
    sed -i "/^\tconfig-\$_flavor.\$arch$/a \\\t$dst" "$APORT/APKBUILD"
    echo "    Patch: $dst"
done

# 3) pkgrel erhöhen (einmalig relativ zum Original im Git)
orig_rel="$(git -C "$APORTS" show "HEAD:${APORT#$APORTS/}/APKBUILD" | sed -n 's/^pkgrel=//p')"
new_rel=$((orig_rel + PKGREL_BUMP))
sed -i "s/^pkgrel=.*/pkgrel=$new_rel/" "$APORT/APKBUILD"
c_ok "pkgrel $orig_rel -> $new_rel"

# 4) Prüfsummen + Bauen
c_info "pmbootstrap checksum $PKG …"
"$PMB" checksum "$PKG"
c_info "Baue $PKG (Cross-Compile, dauert) – Log: pmbootstrap log"
"$PMB" build --force "$PKG"
c_ok "Kernel gebaut: $PKG pkgrel $new_rel"

echo
echo "  Weiter mit:  ./build.sh      (Rootfs mit eigenem Kernel neu bauen + fixup + payload)"

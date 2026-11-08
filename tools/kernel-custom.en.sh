#!/usr/bin/env bash
# =============================================================================
#  kernel-custom.en.sh – build our own Nura kernel (linux-postmarketos-apple-16k)
#
#  - sets additional options in the kernel configuration (KCONFIG below)
#  - adds patches from tools/kernel-patches/*.patch (e.g. device tree for touch)
#  - bumps pkgrel so that the local package takes precedence over the Nura repo
#  - builds via pmbootstrap (cross-compile on the laptop, about 30–60 min)
#
#  Afterwards:  ./build.en.sh   (installs the custom kernel into the image, fixup, payload)
#
#  Note: the changes live in pmbootstrap's pmaports clone.
#  'pmbootstrap pull' may fail because of that -> first: tools/kernel-custom.en.sh --reset
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PMB="${PMB:-$SCRIPT_DIR/.venv/bin/pmbootstrap}"
PKG="linux-postmarketos-apple-16k"
PKGREL_BUMP="${PKGREL_BUMP:-117}"   # r100 i2c/spidev, r101 touch, r102 PCIe (without CONFIG_PCI), r103 PCIe/Wi-Fi, r104 PCIe startable at runtime + step messages, r105 PD list fix, r106 battery (Tigris + HDQ gauge), r107 Tigris I2C single-byte fix, r108 catch IBUSLIMIT reset, r109 Bluetooth (hci_bcm Apple/UART1), r110 Tigris rounding, r111 NVMe port 0 + battery polish, r112 NVMe without SGL + CID quirk, r113 NVMMU, r114 NVMe tags < 36, r115 nvme built-in (internal root), r116 spi-s5l CS polarity (Maggie loads), r117 spi-s5l SPI mode per device (codec mode 0)
PATCHDIR="$SCRIPT_DIR/tools/kernel-patches"

# Additional kernel options (name=value)
KCONFIG=(
    "CONFIG_I2C_CHARDEV=y"       # /dev/i2c-* -> read PMU registers (i2ctransfer / Python)
    "CONFIG_SPI_SPIDEV=y"        # /dev/spidev* -> test the touch controller from userspace
    # --- Touch (Patches 0001-0006) ---
    "CONFIG_REGULATOR=y"                    # was off in the Nura kernel
    "CONFIG_MFD_SIMPLE_MFD_I2C=y"           # chestnut Display-PMU (i2c0 @0x27)
    "CONFIG_SPI_APPLE_S5L=y"                # A10-SPI (Port von Sandcastle spi-hx)
    "CONFIG_COMMON_CLK_APPLE_TOUCH=y"       # 32.768 kHz touch clock from PMGR
    "CONFIG_REGULATOR_APPLE_PMIC_SWITCH=y"  # touch-core (D2333) / touch-hv (chestnut)
    "CONFIG_TOUCHSCREEN_HX=y"               # /dev/hx-touch for hx-touchd
    # --- PCIe + WLAN (Patches 0007-0009) ---
    "CONFIG_PCI=y"                          # was off in the Nura kernel!
    "CONFIG_PCI_MSI=y"
    "CONFIG_GPIO_APPLE_PMIC=y"              # D2333-GPIOs (WLAN reg_on)
    "CONFIG_PCIE_APPLE_T8010=y"             # A10 PCIe (port of Sandcastle pcie-hx)
    "CONFIG_WIRELESS=y"
    "CONFIG_CFG80211=m"
    "CONFIG_WLAN=y"
    "CONFIG_WLAN_VENDOR_BROADCOM=y"
    "CONFIG_BRCMUTIL=m"
    "CONFIG_BRCMFMAC=m"                     # BCM4355 (as a module: rmmod/modprobe for testing)
    "CONFIG_BRCMFMAC_PCIE=y"
    "CONFIG_SERIAL_SAMSUNG_UARTS=8"
    "CONFIG_CHARGER_APPLE_TIGRIS=y"
    "CONFIG_BT=m"
    "CONFIG_BT_HCIUART=m"
    "CONFIG_BT_HCIUART_SERDEV=y"
    "CONFIG_BT_HCIUART_BCM=y"
    "CONFIG_BLK_DEV_NVME=y"
)

c_info() { printf '\e[1;34m[*]\e[0m %s\n' "$*"; }
c_ok()   { printf '\e[1;32m[+]\e[0m %s\n' "$*"; }
c_warn() { printf '\e[1;33m[!]\e[0m %s\n' "$*"; }
die()    { printf '\e[1;31m[x]\e[0m %s\n' "$*" >&2; exit 1; }

APORTS="$("$PMB" config aports)"
APORT="$(find "$APORTS/device" -maxdepth 2 -type d -name "$PKG" | head -n1)"
[[ -d "$APORT" ]] || die "Aport $PKG not found in $APORTS"
CFG="$(ls "$APORT"/config-*.aarch64 | head -n1)"

if [[ "${1:-}" == "--reset" ]]; then
    c_info "Resetting $PKG in the pmaports clone …"
    git -C "$APORTS" checkout -- "$APORT"
    git -C "$APORTS" clean -fdq -- "$APORT"
    c_ok "Reset done. The next ./build.en.sh uses the standard kernel again (maybe 'pmbootstrap zap -p')."
    exit 0
fi

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

stop_old_netboot

# 1) set kernel options (idempotent)
c_info "Setting kernel options in $(basename "$CFG") …"
for kv in "${KCONFIG[@]}"; do
    key="${kv%%=*}"
    sed -i -E "/^(# )?${key}( is not set|=.*)$/d" "$CFG"
    echo "$kv" >> "$CFG"
    echo "    $kv"
done

# 1b) Pre-check: does every option survive 'make olddefconfig'? (options with missing dependencies
#     are otherwise silently dropped during the build – that is how CONFIG_PCI got lost)
KSRC="${KSRC:-$SCRIPT_DIR/src/kpatch/linux-hoolock-7.0.12}"
if [[ -f "$KSRC/Makefile" ]]; then
    tmpcfg="$(mktemp)"; cp "$CFG" "$tmpcfg"
    if make -s -C "$KSRC" ARCH=arm64 LLVM=1 KCONFIG_CONFIG="$tmpcfg" olddefconfig >/dev/null 2>&1; then
        lost=()
        for kv in "${KCONFIG[@]}"; do grep -qx "$kv" "$tmpcfg" || lost+=("$kv"); done
        rm -f "$tmpcfg" "$tmpcfg.old"
        ((${#lost[@]})) && die "These options would be lost during the build (missing dependency): ${lost[*]}"
        c_ok "All ${#KCONFIG[@]} kernel options survive olddefconfig."
    else
        rm -f "$tmpcfg"; c_warn "olddefconfig check not possible (source tree $KSRC) – skipped."
    fi
else
    c_warn "No local kernel source tree ($KSRC) – option check skipped."
fi

# 2) Patches einbinden
mkdir -p "$PATCHDIR"
shopt -s nullglob
PATCHES=("$PATCHDIR"/*.patch)
shopt -u nullglob
# remove our old patches from the aport
find "$APORT" -maxdepth 1 -name 'nura-iphone-*.patch' -delete
sed -i '/nura-iphone-.*\.patch/d' "$APORT/APKBUILD"
# insert in reverse so that they end up in the right order in source=
for ((i=${#PATCHES[@]}-1; i>=0; i--)); do
    p="${PATCHES[$i]}"
    dst="nura-iphone-$(basename "$p")"
    cp "$p" "$APORT/$dst"
    # insert into source= after the config line
    sed -i "/^\tconfig-\$_flavor.\$arch$/a \\\t$dst" "$APORT/APKBUILD"
    echo "    Patch: $dst"
done

# 3) bump pkgrel (once, relative to the original in Git)
orig_rel="$(git -C "$APORTS" show "HEAD:${APORT#$APORTS/}/APKBUILD" | sed -n 's/^pkgrel=//p')"
new_rel=$((orig_rel + PKGREL_BUMP))
sed -i "s/^pkgrel=.*/pkgrel=$new_rel/" "$APORT/APKBUILD"
c_ok "pkgrel $orig_rel -> $new_rel"

# 4) checksums + build
c_info "pmbootstrap checksum $PKG …"
"$PMB" checksum "$PKG"
c_info "Baue $PKG (Cross-Compile, dauert) – Log: pmbootstrap log"
"$PMB" build --force "$PKG"
c_ok "Kernel gebaut: $PKG pkgrel $new_rel"

echo
echo "  Next:  ./build.en.sh      (rebuild the rootfs with the custom kernel + fixup + payload)"

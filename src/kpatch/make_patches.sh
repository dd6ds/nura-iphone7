#!/usr/bin/env bash
# Erzeugt tools/kernel-patches/*.patch aus dem Testbaum (a/ b/ Pfade)
#   orig/        = unveränderter Hoolock-Kernel (nur betroffene Dateien)
#   stage-touch/ = DT-Stand nach den Touch-Patches (Basis für 0009)
#   stage-wlan/  = DT-Stand nach PCIe/WLAN (Basis für 0012)
#   stage-batt/  = DT-Stand nach Akku (Basis für 0014)
#   stage-bt/    = DT-Stand nach Bluetooth (Basis für 0017)
#   stage-pcie-wlan/ = PCIe-Treiber vor NVMe-Port (Basis für 0015)
set -euo pipefail
cd "$(dirname "$0")"
T=linux-hoolock-7.0.12
O=orig
S=stage-touch
W=stage-wlan
B=stage-batt
N=stage-bt
Q=stage-pcie-wlan
P=../../tools/kernel-patches
mkdir -p "$P"; rm -f "$P"/*.patch
mk() {  # name, basis, ziel, dateien...
    local name=$1 base=$2 tgt=$3; shift 3; local out="$P/$name.patch"; : > "$out"
    for f in "$@"; do
        local a="$base/$f"
        [[ -f "$a" ]] || a=/dev/null
        diff -Nu --label "a/$f" --label "b/$f" "$a" "$tgt/$f" >> "$out" || true
    done
    echo "$out: $(grep -c '^+' "$out") Zeilen +"
}
DTS=arch/arm64/boot/dts/apple
mk 0001-spi-apple-s5l               $O $T drivers/spi/spi-apple-s5l.c drivers/spi/Kconfig drivers/spi/Makefile
mk 0002-clk-apple-touch             $O $T drivers/clk/clk-apple-touch.c drivers/clk/Kconfig drivers/clk/Makefile
mk 0003-regulator-apple-pmic-switch $O $T drivers/regulator/apple-pmic-switch.c drivers/regulator/Kconfig drivers/regulator/Makefile
mk 0004-mfd-simple-mfd-i2c-chestnut $O $T drivers/mfd/simple-mfd-i2c.c
mk 0005-input-hx-touch              $O $T drivers/input/touchscreen/hx-touch.c drivers/input/touchscreen/Kconfig drivers/input/touchscreen/Makefile
mk 0006-dts-t8010-touch             $O $S $DTS/t8010.dtsi $DTS/t8010-7.dtsi
mk 0007-gpio-apple-pmic             $O $T drivers/gpio/gpio-apple-pmic.c drivers/gpio/Kconfig drivers/gpio/Makefile
mk 0008-pci-apple-t8010             $O $Q drivers/pci/controller/pcie-apple-t8010.c drivers/pci/controller/Kconfig drivers/pci/controller/Makefile
mk 0009-dts-t8010-pcie-wlan         $S $W $DTS/t8010.dtsi $DTS/t8010-7.dtsi
mk 0010-serdev-set-stopbits         $O $T include/linux/serdev.h drivers/tty/serdev/core.c drivers/tty/serdev/serdev-ttyport.c
mk 0011-power-apple-tigris          $O $T drivers/power/supply/apple-tigris.c drivers/power/supply/Kconfig drivers/power/supply/Makefile drivers/tty/serial/Kconfig
mk 0012-dts-t8010-battery           $W $B $DTS/t8010.dtsi $DTS/t8010-7.dtsi
mk 0013-bluetooth-hci-bcm-apple     $O $T drivers/bluetooth/hci_bcm.c
mk 0014-dts-t8010-bluetooth         $B $N $DTS/t8010.dtsi $DTS/t8010-7.dtsi
mk 0015-pci-apple-t8010-nvme-port   $Q $T drivers/pci/controller/pcie-apple-t8010.c include/linux/pcie-apple-t8010.h
mk 0016-nvme-apple-embedded         $O $T drivers/nvme/host/pci.c drivers/nvme/host/nvme.h drivers/nvme/host/core.c
mk 0017-dts-t8010-nvme-spi1         $N $T $DTS/t8010.dtsi $DTS/t8010-7.dtsi

# Gegenprobe: alle Patches der Reihe nach auf die Originale anwenden
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
(cd $O && find . -type f -exec cp --parents {} "$tmp" \;)
for p in "$P"/*.patch; do
    patch -d "$tmp" -p1 -s --dry-run < "$p" >/dev/null || { echo "FEHLER: $p"; exit 1; }
    patch -d "$tmp" -p1 -s < "$p"
done
fail=0
for f in drivers/spi/spi-apple-s5l.c drivers/pci/controller/pcie-apple-t8010.c drivers/gpio/gpio-apple-pmic.c \
         drivers/gpio/Kconfig drivers/pci/controller/Makefile $DTS/t8010.dtsi $DTS/t8010-7.dtsi \
         drivers/power/supply/apple-tigris.c drivers/tty/serdev/core.c drivers/tty/serial/Kconfig include/linux/serdev.h drivers/bluetooth/hci_bcm.c drivers/nvme/host/pci.c; do
    cmp -s "$tmp/$f" "$T/$f" && echo "OK $f" || { echo "ABWEICHUNG $f"; fail=1; }
done
exit $fail

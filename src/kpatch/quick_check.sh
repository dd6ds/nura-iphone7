#!/bin/bash
# Schnellprüfung wie in der CI: frischer Hoolock-Tarball + tools/kernel-patches, dann einzelne Objekte
# und t8010-DTBs cross-kompilieren (Arbeitsverzeichnis /tmp/kcheck).
#   quick_check.sh [objekt.o …]   Standard: spi-apple-s5l.o
set -e
P="$(cd "$(dirname "$0")/../../tools/kernel-patches" && pwd)"
TAR=~/.local/var/pmbootstrap/cache_distfiles/hoolock-7.0.12.tar.gz
W=/tmp/kcheck
rm -rf $W && mkdir -p $W && tar -xzf $TAR -C $W --strip-components=1 && cd $W
for p in "$P"/*.patch; do patch -p1 -s --forward --batch < "$p"; done
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
make -s defconfig
scripts/config -e ARCH_APPLE -e SPI -e SPI_APPLE_S5L -e PCI -e PCIE_APPLE_T8010
make -s olddefconfig
make -s -j"$(nproc)" prepare >/dev/null 2>&1
objs=${*:-drivers/spi/spi-apple-s5l.o}
set +e
make -j"$(nproc)" W=1 $objs 2>&1 | grep -E "warning|error" ; echo "OBJ-EXIT=${PIPESTATUS[0]}"
make -s apple/t8010-d10.dtb apple/t8010-d101.dtb apple/t8010-d11.dtb apple/t8010-d111.dtb 2>&1 | tail -3
echo "DTB-EXIT=${PIPESTATUS[0]}"
# UPDATE_OVERRIDE=1: frische DTBs nach out/dtbs-override (die Payload nimmt sonst die alten!)
if [ "${UPDATE_OVERRIDE:-0}" = 1 ]; then
  cp arch/arm64/boot/dts/apple/t8010-d1{0,01,1,11}.dtb "$P/../../out/dtbs-override/"
  echo "out/dtbs-override aktualisiert – jetzt ./build.sh payload"
fi

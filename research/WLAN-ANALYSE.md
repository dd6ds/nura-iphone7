# WLAN iPhone 7 (d101) – Stand 2026-11-07

## Hardware (Live-ADT + Sandcastle hx-h9p-d101.dts)
- WLAN: Broadcom BCM4355 ("wlan-pcie,bcm4350"), Modul "elsa", an PCIe-Port 2 (Gen1)
- BT: BCM4345C5-kompatibel an UART (später)
- PCIe-RC `apcie,t8010`: ECAM 0x610000000 (16 Busse), PHY 0x600000000/0x600008000/0x60a000000,
  Glue 0x600010000, Ports 0x60[1-4]000000, SART 0x60[1-4]004000, DART 0x60[1-4]008000
- IRQs: Port 270/273/276/279, MSI 288–319 (8 je Port, Port 2 = 304–311), DART2 277
- MSI-Doorbell 0xBFFFF000, MEM-Fenster 0x7C0000000 -> Bus 0xC0000000 (1 GiB)
- Port 2: PERST# GPIO 14, CLKREQ# GPIO 18 (Pinmux 1), device_wake GPIO 88, reg_on = D2333-GPIO 10
  (Reg 0x914 Bit 0, iBoot hinterlässt 0x80 = Ausgang/aus)
- DART2: vm-offset 0x80000000, vm-size ~1 GiB, fetch-config 0xE0303, diag-config 0x100

## Umsetzung (Patches 0007–0009)
- `gpio-apple-pmic.c`: GPIOs des D2333 (Regmap des PMIC-MFD)
- `pcie-apple-t8010.c`: PHY/Port-Init aus Sandcastle `pcie-hx.c`, MSI wie `pcie-apple.c`,
  **statische DART** (Bus 0x80000000 -> RAM 0x800000000, 512 MiB) statt IOMMU-Treiber,
  passend dazu `dma-ranges` -> Geräte-DMA läuft über ZONE_DMA/swiotlb.
- Notschalter: `pcie_apple_t8010.disable=1` (Kernel-Kommandozeile, z. B. via `CMDLINE=` in build.sh)

## Nächste Schritte
1. Boot r102: `dmesg | grep -i pcie`, `lspci -nn` -> erwartet 14e4:4355 auf 0000:01:00.0
2. Firmware aus iOS-Rootfs (`usr/share/firmware/wifi/…`) + NVRAM/CLM, MAC aus ADT
3. brcmfmac: Board-Typ/OTP-Auswahl für Apple-Module prüfen

## Ergebnis 2026-11-07 20:35 – WLAN funktioniert
- Absturzursache beim Booten: `devm_pm_domain_attach_list(dev, …, NULL)` – Kernel 7.0 schreibt
  immer nach `*list` -> NULL-Deref. Behoben in r105 (Patch 0008).
- Debug-Methode: Treiber per sysfs-bind zur Laufzeit gestartet + `dmesg -W` per SSH; Schrittmeldungen `[step]`.
- PCIe: Port 2 Link Gen1 (LTSSM 0x11), `0000:01:00.0 [14e4:43dc] class 0x0280`, BAR0/2 aus 0x7c0000000.
- brcmfmac: Chip `BCM4355/10` -> Präfix `brcmfmac4355-pcie`; OTP: Modul PRNL, Hersteller u, Version 5.9
  -> NVRAM `P-elsa_M-PRNL_V-u__m-5.9`; Firmware 9.120.2.0.3.50.34 (iOS 13.3.1), TxCap + Cal-Blob geladen.
- m1n1-Patch `tools/m1n1-patches/0001-kboot-wifi-iphone.patch`: WLAN-Knoten unter `/arm-io/uartN/wlan`,
  fehlende `wifi-antenna-sku-info` tolerieren, `brcm,board-type` aus `module-instance`.
  MAC kommt aus `/chosen/mac-address-wifi0` (Alias `wifi0`).
- DT: `apple,antenna-sku = "X0"` als Platzhalter -> Apple-Firmwareauswahl über OTP aktiv.
- Scan ok: 2,4 GHz (Kanal 6/11/13) und 5 GHz (Kanal 44).
- Offen: p2p-dev (Wi-Fi Direct) meldet -52 (harmlos); Bluetooth (BCM4345C5 an UART4) noch nicht angefangen.

## Boot mit PCIe aktiv (2026-11-07 21:00)
- PCIe-Probe beim Booten ok (Link bei 0,54 s), kein Hänger mehr.
- WLAN kam erst nach ~254 s: systemd-udevd hing beim Start (start timeout 90 s, stop-sigterm
  timeout, SIGKILL bei 251 s); erst der neu gestartete udevd lud brcmfmac. Manueller udevd-Restart
  danach in 2 s ok -> nur beim Boot. Gegenmaßnahme: /etc/modules-load.d/wlan.conf (brcmfmac).
  Beim nächsten Boot prüfen, ob der udevd-Hänger bleibt (dann Ursache suchen).

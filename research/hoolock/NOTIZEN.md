# HoolockLinux – was davon für das iPhone 7 (t8010) nützt (Stand 2026-11-07)

Quellen: github.com/HoolockLinux/docs (geklont nach ./docs), github.com/HoolockLinux/linux (Branches).

## Direkt nützlich
- **Bluetooth** (Branch `tests/bluetooth`, Commit 83cfde7b90 „bluetooth blah“ → bt-83cfde7b90.patch):
  hci_bcm-Erweiterung für Apple-BCM-Chips (A11/BCM4349): eigene compatible `brcm,bcm4349-bt-apple`,
  sendet vor dem Firmware-Download einen „Taurus“-Kalibrierblob (DT-Property `brcm,taurus-cal-blob`,
  HCI-Vendor-Befehl 0xfd97, 0xe6-Byte-Blöcke). DT-Muster: serdev-Kind unter der UART mit
  device-wakeup/host-wakeup/shutdown-GPIOs, max-speed 1500000, uart-pinmux per pinctrl.
  → Vorlage für unseren BT auf UART4 (Sandcastle: wake GPIO 87, host-wake pmu_gpio 11, shutdown pmu_gpio 8).
  Prüfen: hat die ADT von bluetooth@uart4 einen Taurus-/Kalibrierblob? (m1n1 müsste ihn ins DT kopieren)
- bt-6d756fb65f.patch: btbcm – Default-BD-Adresse des BCM4349B1 als ungültig markieren (Muster, falls
  unser Chip eine Default-Adresse meldet → dann `local-bd-address` aus ADT setzen).
- **DART A7–A10** (`iommu: apple-dart: add S5L8960X DART support` + dma-range-Property, dart-*.patch):
  echter IOMMU-Treiber für die A10-DARTs. Könnte unser statisches DART-Mapping bei PCIe (WLAN, später NVMe)
  ersetzen. In unserem 7.0.12-Baum noch nicht enthalten (Snapshot-Branch `snapshot/hoolock-7.1-dart`).
- **Interner Speicher**: docs/tools (resize_apfs, gdisk unter palera1n-iOS). Weg: APFS-Container in iOS
  verkleinern, mit gdisk eigene Linux-Partition anlegen → in Linux /dev/nvme0n1pN, kein APFS-Treiber nötig.
  Hinweis docs: resize braucht SEP-Firmware; auf A10 mit iOS ≥16 nicht möglich (iPhone 7 max. iOS 15 → ok).
  Hoolock unterstützt internen Speicher bisher nur auf A11; A10-NVMe (über PCIe) müssen wir selbst machen.
- hw/DART.md: Registerbeschreibung dart,s5l8960x (TCR, TTBR, STREAM_COMMAND …).

## Nicht nützlich für A10
- Branch `ans1`: Speichertreiber für A7/A8 (ANS1, nicht PCIe-NVMe).
- `tests/macsmc-power`/`pmp`: Akku über SMC nur A11 – A10 hat kein SMC, dort Tigris + bq27545 (unser Treiber).
- Akku/Laden, Touch, WLAN: in Hoolock für A10 nicht vorhanden (FEATURES/A10.md: nur DT, Display, Helligkeit, Tasten).

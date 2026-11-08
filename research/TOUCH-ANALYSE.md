# Touchscreen iPhone 7 (d101 / T8010) – Bestandsaufnahme

Quelle: offizielles IPSW iOS 15.8.8 (19H422) für iPhone9,1/9,3,
`Firmware/all_flash/DeviceTree.d101ap.im4p` (Apple Device Tree, Vorlage) und
`kernelcache.release.iphone9`. Gezielt per `remotezip` geladen, entpackt mit
`research/tools/im4p_extract.py` (IM4P + LZFSE), geparst mit m1n1 `proxyclient/m1n1/adt.py`.
Vollständiger ADT-Dump: `research/d101ap-adt.txt`.

## Hardware-Pfad

```
SoC T8010 ── spi2 (Samsung-SPI "spi-1,samsung", spi-version 1)
               reg 0xA088000 (+0x4000), IRQ 216, clock-gate 76, DMA vorhanden
               └── multi-touch   compatible = "hid-transport,k1"
                     Interrupt : GPIO-Controller (phandle 33) Pin 166
                     Reset     : GPIO 0xa1 (AP-GPIO, phandle 33)
                     CS/Enable : GPIO 0x51
                     Strom     : PMU-LDO 0x21e (pmuL), dpLE 0x302, Takt TCLK
                     Bootloader: hbpp-version = 259  (HBPP -> Firmware-Upload nötig)
                     Kalibrier.: syscfg/MtCl, OrbG, SFCl, … (aus NOR-syscfg, nicht im IPSW)
```

## iOS-Treiberstack (aus dem Kernelcache)

- `AppleHIDTransportDeviceSPI` matcht **`hid-transport,k1`** UND **`hid-transport,spi`**
  -> dasselbe "Apple HID over SPI"-Transportprotokoll wie die Tastatur/Trackpads
  der Apple-Silicon-MacBooks (`hid-transport,spi`).
- `AppleHIDTransportBootloaderHBPP`: Firmware wird beim Start per HBPP in den
  Touch-Controller geladen ("Firmware image successfully sent. Resetting MCU").
- `AppleHIDTransportProtocolZ2`, `AppleMultitouchZ2SPI`: Z2-Protokoll wie bei der
  Touch Bar (Linux: `drivers/input/touchscreen/apple_z2.c`, seit 6.15).
- Die Touch-Firmware selbst steckt NICHT im Kernelcache -> liegt im iOS-Rootfs
  (vermutlich `/usr/share/firmware/multitouch/…`), 5 GB-Rootfs-DMG im IPSW.

## Was für Linux fehlt

| Baustein | Stand | Ansatz |
|---|---|---|
| SPI-Controller T8010 (Samsung-Erbe) | kein Treiber (Hoolock A10: nicht gelistet) | `spi-s3c64xx` anpassen oder neuer Treiber |
| DT-Knoten spi2 + Touch | fehlt im Hoolock-DT d101 | aus ADT übertragen (Adressen/GPIOs oben) |
| Strom (PMU-LDO 0x21e, dpLE) | unklar, ob schon an | PMU-Treiber prüfen / testen ob Rail aktiv |
| HBPP-Firmware-Upload | Logik ähnlich `apple_z2` | an `apple_z2`/Asahi `spi-hid-apple` anlehnen |
| Touch-Firmware | im iOS-Rootfs | Rootfs-DMG holen, mit apfs-fuse extrahieren |
| Kalibrierung (syscfg) | im NOR des Geräts | über m1n1 aus dem Live-ADT lesen |

## Nächste Schritte (Vorschlag)

1. Touch-Firmware aus dem iOS-Rootfs extrahieren (Download ~5 GB oder Restore-Ramdisk prüfen).
2. Mit m1n1 im Proxy-Modus den **Live**-ADT (inkl. syscfg-Kalibrierung) und
   SPI-/GPIO-Register testen – ohne Linux-Kernel-Neubau.
3. SPI-Treiber für T8010 (spi2) zum Laufen bringen – Grundvoraussetzung.
4. Touch-Treiber (HBPP-Upload + Z2/HID) – Prototyp als Userspace-Tool über spidev,
   danach als Kernel-Treiber.
5. Bei Hoolock (Matrix "The Apple Basement") nachfragen, ob SPI/Touch für A10 in Arbeit ist.

## Touch-Firmware (extrahiert 2026-11-06)

Quelle: iOS-Rootfs `098-68844-067.dmg` (DMG -> APFS, gelesen mit 7-Zip 23.01),
Pfad laut mtree: `/usr/share/firmware/multitouch/D10.mtprops` (gilt für D10 und D101).
Ablage: `research/firmware/`.

`D10.mtprops` ist eine XML-Plist mit genau einer Personality **`C1F5D,2`**
(= `hid-merge-personality` im ADT-Knoten `multi-touch`):

| Schlüssel | Inhalt |
|---|---|
| `Constructed Firmware` | 2 fertige Bootload-Pakete (59 248 B + 17 076 B) -> `C1F5D_2_Constructed_Firmware_{0,1}.bin` |
| `Constructed Firmware Version` | `0x0741.mihu` |
| `PreconstructedBootloadPacketType` | **`Z2`** (wie Touch Bar / Linux `apple_z2`) |
| `Firmware Config` | 4 413 B Plist: `Calibration Sequence` (Adresse, Max Size, Provider = ADT-Property wie `multi-touch-calibration`) -> `C1F5D_2_Firmware_Config.plist` |
| `Firmware Config Version` | `0x0016.conf` |
| `ResetInterval` | 432000 |

Paketaufbau (verifiziert, Header-Prüfsumme stimmt):

```
18 e1 | 30 01 | words(BE16) | addr(BE32) | hdrsum(BE16) | payload (words*4) | checksum(4)
Blob 0: 14808 Wörter -> addr 0x00000000
Blob 1:  4265 Wörter -> addr 0x1ae00040
```

Das entspricht dem Z2-Befehl 0x3001 ("send blob"), den auch Asahis
`asahi_firmware/multitouch.py` (`plist_to_bin_touchbar`) für das Linux-Firmwareformat
`Z2FW` erzeugt – dort jedoch little-endian und ohne das Präfix `18 e1`.
=> Eine Umwandlung nach `Z2FW` für `apple_z2` ist machbar; Byte-Reihenfolge und
Präfix müssen beim ersten Hardwaretest geklärt werden.

Die Kalibrierwerte selbst (`multi-touch-calibration` = syscfg `MtCl` usw.) stehen
nicht im IPSW, sondern im NOR des Geräts -> per m1n1 aus dem Live-ADT lesen.

## Live-Messung über m1n1-Proxy (2026-11-06)

Gerät: iPhone9,3 / D101, Board-ID 0xc, iBoot-7459.140.15, m1n1 d5a10ac (USB-Proxy über dwc2).

**Live-ADT** (`research/live/live.adt`, 174 508 B) – iBoot hat alle syscfg-Kalibrierungen
eingetragen, roh gesichert in `research/live/multi-touch/`:
`multi-touch-calibration` (1024 B), `orb-force-cal` (1474 B), `orb-gap-cal` (992 B),
`shape-dynamic-accel-cal` (208 B), `prox-calibration` (144 B), `sshb-force-cal` (48 B),
`sshb-inverse-filter-cal` (28 B), `orb-offset-cal` (16 B).

**spi2 @ 0x20A088000** – nach `pmgr_adt_power_enable("/arm-io/spi2")` lesbar
(VORHER lesen hängt den Bus auf -> Reset des iPhones!):

| Offset | Wert | Deutung nach Linux `spi-apple.c` (M1-Generation) |
|---|---|---|
| 0x00 CTRL | 0x0 | gestoppt |
| 0x04 CFG | 0x8 | Bit 3 – in spi-apple nicht belegt (Altlast/S5L) |
| 0x08 STATUS | 0x0 | – |
| 0x0c PIN | 0x3 | KEEP_MOSI + CS (high = inaktiv) ✔ passt |
| 0x30 CLKDIV | 0x1 | plausibel ✔ |

=> Registerlayout passt zu **`spi-apple`** (`apple,spi`) – der T8010-SPI ist der Vorfahr.
   Erster Versuch: Hoolock-Kernel mit `spi-apple` + DT-Knoten für spi2.
   Offen: FIFOSTAT 0x10c / IE 0x130+ prüfen, Bedeutung CFG Bit 3, Taktquelle für CLKDIV.

**GPIOs** (AP-GPIO @ 0x20F100000, Layout `pinctrl-apple-gpio`):

| Signal | Pin | cfg | Deutung |
|---|---|---|---|
| Reset | 0xa1 (161) | 0x00078a02 | Ausgang, LOW -> Controller im Reset (iBoot-Zustand) |
| CS/Enable | 0x51 (81) | 0x00078a21 | Peripherie-Funktion 1 (SPI-CS gemuxt) |
| IRQ | 166 | 0x0007cb80 | Eingang, Pull-up, IRQ noch nicht konfiguriert |

**Linux `apple_z2`** (Hoolock-Baum `drivers/input/touchscreen/apple_z2.c`):
- Boot: Reset freigeben, innerhalb 20 ms IRQ vom HBPP-Bootloader erwarten, dann Upload.
- Blob-Upload: Daten + Ack `1a a1`; Init-Payload 8-Bit-Wörter, Blobs **16-Bit-Wörter**
  -> erklärt die Byte-Reihenfolge: Z2FW speichert LE16, iPhone-mtprops ist Leitungsreihenfolge.
- Präfix der iPhone-Pakete `18 e1` vs. Ack `1a a1` – Rolle beim ersten Upload klären.

Nächster Test (automatisch in `M1N1_PROXY=1 ./boot.sh`): `touch_wake_probe.py` –
Reset freigeben und IRQ beobachten. IRQ -> LOW = Controller hat Strom und Bootloader läuft.

## Aufwachtest (2026-11-06, 14:45)

- Vor der Reset-Freigabe: IRQ-Pin 166 liest **0**, obwohl er als Eingang mit Pull-up
  konfiguriert ist (cfg 0x0007cb80). Ein stromversorgter Controller im Reset würde die
  Leitung nicht aktiv nach unten ziehen -> Hinweis: **Controller hat keinen Strom**
  (Leitung wird über Schutzdioden des stromlosen Chips auf GND gezogen).
- Nach dem Hochziehen von Reset (GPIO 0xa1 -> 1) war schon der nächste Proxy-Lesezugriff
  tot; das iPhone verschwand vom USB (Absturz/Reset). Plausibel: Rückspeisung über den
  Reset-Pin in den stromlosen Controller / Spannungseinbruch.
- Folge: `touch_wake_probe.py` bricht jetzt ab, wenn IRQ schon vor der Freigabe LOW ist.

=> **Weg B:** Zuerst die Stromversorgung des Touch-Controllers klären:
   `function-power_ldo = pmuL(0x21e)` (PMU, phandle 88), `function-power_ana = dpLE(0x302)`
   (phandle 84), `function-clock_enable = TCLK(0x8, 0x64, 0x8000)` (phandle 28),
   Reihenfolge laut `power-sequence`-Property. PMU-Anbindung (I2C/SPMI) des A10 ermitteln.

## Durchbruch: Project Sandcastle (Corellium, 2020) als Vorlage (2026-11-06 abends)

Quellen (geklont nach `src/sandcastle`, `src/psc`):
- github.com/corellium/linux-sandcastle – `arch/arm64/boot/dts/hx/hx-h9p-d101.dts`,
  `drivers/input/touchscreen/hx-touch.c`, `drivers/regulator/hx-pmu-i2c-pwrsw.c`,
  `drivers/platform/hx/hx-pmu-i2c.c`, `drivers/spi/spi-hx.c`
- github.com/corellium/projectsandcastle – `hx-touchd/` (Userspace-Firmware-Loader, nutzt `mtfw/` + D10.mtprops)

### Stromversorgung laut Sandcastle-DT (d101)
| Rail | PMU | Register | Maske |
|---|---|---|---|
| touch core (`touch_pwrsw`) | D2333 i2c1 @0x74 (16-Bit-Reg) | 0x31f | 0x01 |
| touch hv (`touch_ldo`) | chestnut i2c0 @0x27 (8-Bit-Reg) | 0x05 | 0x10 (Bits 0-3 = LCD-LDO, NICHT anfassen) |
| touchclk | PMGR `0x20e078000` ("hx,pmgr-clk-touch") | – | 32768 Hz aus 24 MHz |

Unter Nura gelesen (`/dev/i2c-0` = i2c1): **0x31f = 0x01 -> Kern-Versorgung ist AN.**
Die ADT-Angabe `pmuL(0x21e)` ist KEINE Registeradresse (Kodierung Typ/Index).

### Touch-Knoten (Sandcastle)
spi2 @0x20a088000, IRQ 216; touch@0: spi-max-frequency 3 MHz, reset-gpios <gpio 161>,
cs-gpios <gpio 81>, irq-gpios <gpio 166 ACTIVE_LOW>, hv-supply, core-supply, clocks touchclk.

### Software-Architektur Sandcastle
- Kernel `hx-touch`: Strom/Reset/CS/IRQ + rohes SPI über Misc-Device `/dev/hx-touch`
  (ioctls SET_CS, RESET, READY, SETUP_IRQ, WAIT_IRQ, METRICS), danach Report-Parser -> Input-Device.
- Userspace `hx-touchd <personality> <D10.mtprops> <syscfg-Blockdevice>`: lädt Firmware +
  Kalibrierung (aus syscfg) per HBPP/Z2 hoch, setzt Metriken, dann `HXT_IOC_READY`.
- Auf dem A10 gibt es keinen NVMe-Treiber -> syscfg-Partition nicht lesbar. Ersatz:
  Kalibrierung aus dem Live-ADT (`research/live/multi-touch/`) in eine syscfg-ähnliche Datei packen.

### Port-Plan
1. Kernel-Patches (`tools/kernel-patches/`): hx-touch.c portieren; Regulator für PMU-Schalter
   (regmap-basiert über simple-mfd-i2c); chestnut auf i2c0 aktivieren; touchclk-Treiber;
   SPI: zuerst spi-apple testen, sonst spi-hx portieren; DT-Patch für t8010-d101 (+d10/d11/d111).
2. Userspace: hx-touchd für aarch64/musl bauen, syscfg-Ersatz aus ADT-Kalibrierung.
3. systemd-Dienst: hx-touchd beim Boot -> Input-Gerät -> Phosh.

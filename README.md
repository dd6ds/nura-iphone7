# Nura auf dem iPhone 7 (d101, Apple A10 / T8010)

*[English version: README.en.md](README.en.md)*

Build- und Boot-Kit für **Nura** (ehemals postmarketOS) mit **Phosh** auf dem **iPhone 7**.
Boot-Kette: **checkm8 (palera1n) → PongoOS → m1n1 → Hoolock-Linux 7.0.12**.
Das Rootfs liegt wahlweise auf einer eigenen Partition im **internen Speicher**
(neben dem verkleinerten iOS) oder kommt per **Netboot (NBD über USB)** vom PC.

> **Experimentell.** Der Boot muss bei jedem Kaltstart per checkm8 wiederholt werden
> (tethered). iOS bleibt bootfähig, wird für den internen Modus aber verkleinert –
> vorher unbedingt ein Backup machen.

## Stand

| Komponente | Status | Umsetzung |
|---|---|---|
| Display / Backlight | ✅ | simpledrm 750×1334, Phosh (llvmpipe) |
| Touchscreen | ✅ | eigener `hx-touch`-Treiber + `hx-touchd` (Kernel-Patches) |
| Tasten | ✅ | gpio-keys |
| USB-Netzwerk / SSH | ✅ | USB-Gadget NCM, `172.16.42.1` |
| WLAN | ✅ | BCM4355 über PCIe (eigener t8010-PCIe-Treiber) |
| Bluetooth | ✅ | BCM4355C0 an UART1, `hci_bcm` + Taurus-Kalibrierung |
| Akku-Anzeige / Laden | ✅ | Tigris-Lader (I²C) + bq27545-Gauge (HDQ über UART5) |
| Interner Speicher (NVMe) | ✅ | ANS2 über PCIe-Port 0 mit NVMMU-Unterstützung |
| Boot vom internen Speicher | ✅ | Partition „Nura“ (ext4), ca. 8 s bis Userspace |
| Audio | 🚧 in Arbeit | Audio-FPGA „Maggie“ lädt, Codec CS42L71 per SPI lesbar; Initialisierung/Verstärker folgen (`research/AUDIO-ANALYSE.md`) |
| GPU, Kamera, Modem | ❌ | – |

Details zur Hardware: [`HARDWARE-iPhone7.md`](HARDWARE-iPhone7.md), Analysen unter `research/`.

## Voraussetzungen

- Linux-PC, möglichst **Intel** mit USB-A (checkm8 ist auf AMD-/USB-C-Hosts zickig)
- `python3-venv` – `./build.sh deps` legt `.venv/` an (pmbootstrap aus Git, pyusb)
- [palera1n](https://palera.in), `libusb-1.0-0`
- Für den Kernel-Build: Abhängigkeiten von pmbootstrap (läuft im chroot)
- Lightning-Kabel, ca. 15 GB freier Platz

## Schnellstart

```bash
./build.sh                 # deps, init, install, fixup, export, bootloader, payload
tools/kernel-custom.sh     # Kernel mit den Patches aus tools/kernel-patches/ bauen
./build.sh payload         # m1n1-Payload neu zusammensetzen

./boot.sh                  # Standard: ROOT=internal (Rootfs im internen Speicher)
ROOT=netboot ./boot.sh     # Rückfall: Rootfs per NBD vom PC
ssh user@172.16.42.1
```

### Einzelne Build-Schritte

| Befehl | Zweck |
|---|---|
| `./build.sh deps` | Abhängigkeiten prüfen/installieren |
| `./build.sh init` | Gerät/UI für pmbootstrap konfigurieren |
| `./build.sh install` | Rootfs bauen (inkl. Netboot-Hook) |
| `./build.sh fixup` | Image anpassen (Firmware, Dienste, udev-Regeln, SSH-Schlüssel …) |
| `./build.sh export` | Kernel, initramfs, DTBs nach `out/` |
| `./build.sh bootloader` | m1n1/PongoOS holen und patchen |
| `./build.sh payload` | `out/m1n1-linux*.bin` zusammensetzen |

### Wichtige Variablen

| Variable | Standard | Bedeutung |
|---|---|---|
| `UI` | `phosh` | Oberfläche (`console`, `sxmo-de-sway`, …) |
| `ROOT` (boot.sh) | `internal` | `netboot` = Rootfs per NBD |
| `NURA_ROOT_UUID` | UUID der Nura-Partition | ext4-UUID für den internen Boot |
| `NVME_BOOT` / `NVME_AUTOLOAD` | `1` | interner Speicher beim Boot / nvme-Modul automatisch |
| `PCIE_BOOT` | `1` | `0` = PCIe/WLAN beim Boot aus (Notschalter) |
| `PMOS_PASSWORD` | `147147` | Benutzerpasswort – **für eigene Installationen ändern** |
| `SSH_KEY` | `~/.ssh/id_ed25519_nura_iphone` | Öffentlicher Schlüssel wird ins Image übernommen |
| `PONGO_BOOT_CMD` | `bootm` | PongoOS-Befehl zum Starten von m1n1 |

## Interner Speicher (einmalig)

1. **iOS-Container verkleinern:** `tools/ios_resize.sh` (SSHRD-Ramdisk + `resize_apfs`).
2. **Partition anlegen:** `tools/nura_partition.sh check|writetest|gpt|mkfs`
   (sichert vorher die GPT).
3. **Rootfs kopieren:** `tools/nura_copy_root.sh`, später Updates mit `tools/nura_sync.sh`.

Die iOS-Partitionen werden per udev-Regel nur lesbar eingebunden.

## Weitere Werkzeuge (`tools/`)

| Skript | Zweck |
|---|---|
| `kernel-custom.sh` | pmaports-Kernel mit eigenen Patches bauen |
| `bt-fw.sh`, `wifi-fw.py` | BT-/WLAN-Firmware aus eigenen iOS-Dateien bereitstellen |
| `tigris-charge.py`, `tigris_read.py`, `tigris_set.py` | Lader/Akku auslesen und einstellen |
| `apfs_info.py`, `gpt_info.py` | APFS-Container und GPT anzeigen |
| `maggie_load.py`, `maggie_*.sh`, `peek.py` | Audio-FPGA-Experimente |
| `read-journal.sh`, `boot_check.sh`, `cleanup.sh` | Fehlersuche und Aufräumen |
| `make_en.py` | englische Skriptfassungen neu erzeugen |

Zu den Skripten gibt es englische Fassungen mit der Endung `.en.sh` / `.en.py`
(`build.en.sh`, `boot.en.sh`, `tools/*.en.*`). Sie werden mit `tools/make_en.py` aus den
deutschen Originalen und der Übersetzungstabelle `tools/i18n/en.json` erzeugt –
nach Änderungen an einem Skript einfach neu laufen lassen.

## Was nicht im Repository liegt

Apple-Firmware, iOS-Images, Kernelcaches, ADT-Dumps und gerätespezifische Daten
(Seriennummern, MAC-Adressen, Kalibrierdaten, GPT-Backups) werden **nicht** veröffentlicht.
Die Skripte extrahieren alles Nötige aus einem IPSW bzw. vom eigenen Gerät.

## Fehlersuche

- **palera1n hängt bei „Right before trigger“:** iPhone ab- und wieder anstecken, anderen USB-Port nehmen.
- **PongoOS nicht gefunden:** `lsusb | grep 05ac:4141`, sonst palera1n-Schritt wiederholen.
- **Netboot kommt nicht an:** Firewall auf dem USB-Interface (172.16.42.x) öffnen.
- **SSH hängt bei Netboot:** lange Jobs auf dem Telefon mit `systemd-run` starten (NBD-Stalls).

## Danksagungen

Dieses Projekt steht auf den Schultern vieler anderer. Herzlichen Dank an:

- **[Hoolock Linux](https://github.com/HoolockLinux)** – Linux-Kernel für A7–A11
  ([linux](https://github.com/HoolockLinux/linux)), angepasstes [m1n1](https://github.com/HoolockLinux/m1n1),
  PongoOS-Build, [Dokumentation](https://github.com/HoolockLinux/docs) sowie `resize_apfs`/`gdisk` für iOS.
- **[Asahi Linux](https://asahilinux.org)** – das ursprüngliche [m1n1](https://github.com/AsahiLinux/m1n1),
  zahlreiche Apple-Treiber (Pinctrl, NVMe, SPI, DART …), der [asahi-installer](https://github.com/AsahiLinux/asahi-installer)
  und die Reverse-Engineering-Dokumentation.
- **[postmarketOS](https://postmarketos.org) / Nura** – Distribution, `pmbootstrap`, pmaports und der
  Port *Apple Generic iDevice* (`apple-idevice`).
- **[palera1n](https://palera.in)** – checkm8-Bootkette; **axi0mX** für den checkm8-Exploit;
  das **checkra1n-Team** für [PongoOS](https://github.com/checkra1n/PongoOS).
- **[verygenericname/SSHRD_Script](https://github.com/verygenericname/SSHRD_Script)** – SSH-Ramdisk zum
  Verkleinern des iOS-Containers.
- **[Corellium – Project Sandcastle](https://github.com/corellium/projectsandcastle)** und
  [linux-sandcastle](https://github.com/corellium/linux-sandcastle) – wertvolle Referenz für A10-Hardware
  (NVMe/ANS, Peripherie).
- **[libimobiledevice](https://libimobiledevice.org) / usbmuxd** – USB-Kommunikation mit iOS-Geräten.
- **Linux-Kernel-Community** – u. a. `bq27xxx` (HDQ), `hci_bcm`/`btbcm` (Bluetooth), `brcmfmac` (WLAN),
  NVMe- und serdev-Subsystem.
- **[Phosh](https://phosh.mobi)** und **[wayvnc](https://github.com/any1/wayvnc)** – Oberfläche und Fernzugriff.
- **[Ghidra](https://github.com/NationalSecurityAgency/ghidra)** (NSA) und
  **[Capstone](https://www.capstone-engine.org)** – Analyse der AOP-Firmware.
- **Lattice Semiconductor** (iCE40-Konfigurationsdokumentation) und
  **[Project IceStorm](https://github.com/YosysHQ/icestorm)**.
- **Apple** – für die Hardware; Firmware und iOS-Bestandteile werden hier nicht weitergegeben.

Fehlt jemand? Bitte ein Issue aufmachen – ergänze ich gern.

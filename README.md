# iPhone SE (2016) – Nura Netboot-Kit

Baut und bootet **Nura** (ehemals postmarketOS) auf dem **iPhone SE 1. Gen.**
(iPhone8,4 / n69, Apple A9) über den generischen Port `apple-idevice`
(Hoolock-Linux-Kernel + m1n1).

> **Erwartungen:** Experimentell. Auf dem A9 gibt es keine NVMe-Treiber, daher
> wird das Rootfs bei jedem Start per USB-Netzwerk (NBD) vom PC geliefert.
> Keine GPU-Beschleunigung, kein Touch, kein WLAN/Modem. Sinnvoll nutzbar ist
> die Konsole bzw. SSH über USB. iOS bleibt komplett unangetastet.

## Voraussetzungen

- Linux-PC, möglichst **Intel** mit USB-A (checkm8 ist auf AMD-/USB-C-Hosts zickig)
- `python3-venv` – `build.sh deps` legt `.venv/` an und installiert dort pmbootstrap (aus Git, gitlab.nura.eco) und pyusb
- [palera1n](https://palera.in) für den checkm8-Exploit / PongoOS
- `libusb-1.0-0` für den Upload an PongoOS
- `PMB_UPDATE=1 ./build.sh deps` aktualisiert pmbootstrap im venv
- Lightning-Kabel, ~10 GB Platz für den Nura-Workdir

## Ablauf

```bash
chmod +x build.sh boot.sh pongo_send.py

# 1) Image bauen (einmalig bzw. nach Änderungen)
./build.sh            # = deps, init, install, export, payload

# 2) Booten (bei jedem Start)
./boot.sh
# in zweitem Terminal, sobald gebootet:
ssh user@172.16.42.1
```

Bei `pmbootstrap init` (läuft beim ersten Mal interaktiv):
**Vendor `apple`, Codename `idevice`, Kernel-Variante mit 16K-Pages**, UI `console`.

## Einzelne Schritte / Optionen

| Befehl | Zweck |
|---|---|
| `./build.sh deps` | Abhängigkeiten prüfen/installieren |
| `./build.sh init` | Gerät/UI konfigurieren |
| `./build.sh install` | Rootfs bauen + Netboot-Hook |
| `./build.sh export` | Kernel, initramfs, DTBs, m1n1 nach `out/` |
| `./build.sh payload` | `out/m1n1-linux.bin` zusammensetzen |

| Variable | Standard | Bedeutung |
|---|---|---|
| `UI` | `console` | z. B. `sxmo-de-sway` zum Experimentieren |
| `DTB_FILTER` | `all` | `n69` = nur iPhone-SE-DTBs anhängen |
| `CMDLINE` | `console=tty0 …` | Kernel-Kommandozeile (via `chosen.bootargs`) |
| `PMOS_PASSWORD` | `147147` | Benutzerpasswort |
| `PONGO_BOOT_CMD` | `bootm` | PongoOS-Befehl zum Starten von m1n1 |
| `SKIP_PALERA1N` | `0` | `1`, wenn PongoOS schon läuft |

## Fehlersuche

- **palera1n hängt bei „Right before trigger"**: iPhone ab- und wieder anstecken,
  bis „Booting…" erscheint; ggf. anderen USB-Port/Hub nehmen.
- **PongoOS nicht gefunden**: `lsusb | grep 05ac:4141` – erscheint das Gerät nicht,
  den palera1n-Schritt wiederholen.
- **`bootm` startet nichts**: in PongoOS mit `sudo .venv/bin/python pongo_send.py --cmd help`
  die verfügbaren Befehle prüfen und `PONGO_BOOT_CMD` anpassen.
- **Netboot kommt nicht an**: Firewall auf dem USB-Interface (172.16.42.x) öffnen.
- **Falsche Page-Size**: Kernel ohne 16K-Variante bootet auf A9 nicht → `pmbootstrap init` neu.

## Quellen

- Nura-Wiki: *Apple Generic iDevice (apple-idevice)*
- [Hoolock Linux](https://github.com/HoolockLinux) (Kernel, m1n1)
- [palera1n](https://palera.in) / PongoOS

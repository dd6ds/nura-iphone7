# iPhone 7 (d101, Apple A10 / T8010) unter Nura – ausgelesener Stand

Ausgelesen am 2026-11-06 per SSH über den Netboot (Kernel 7.0.12, Hoolock, 16K-Pages).

| Bereich        | Befund                                                        | Folge für das Image |
|----------------|---------------------------------------------------------------|---------------------|
| Modell / DT    | `Apple iPhone 7 (Intel)`, compatible `apple,d101 apple,t8010` | m1n1 wählt t8010-d101.dtb |
| CPU / RAM      | 2 Kerne aktiv, 1,9 GB RAM, 16K-Pages                          | zram-Swap aktiv |
| Display        | `simpledrm` 750×1334, `/dev/dri/card0`, Connector `Unknown-1` | phoc-Skalierung 2 |
| Backlight      | `20e200080.backlight` (max 2047) – funktioniert                | Helligkeit in Phosh nutzbar |
| GPU            | kein Treiber (Hoolock: TBA)                                   | Mesa llvmpipe, GSK_RENDERER=cairo |
| Eingabe        | nur `gpio-keys` (Power, Lautstärke) – **kein Touchscreen**    | Autologin, keine Sperre, **wayvnc** |
| Speicher       | kein NVMe-Treiber                                             | Rootfs nur per Netboot (NBD) |
| Netz           | nur USB-Gadget `usb0` (NCM), kein WLAN/BT/Modem               | NetworkManager darf usb0 nicht verwalten |
| Audio / Akku   | kein ALSA, kein power_supply                                  | – |
| Firmware       | `/lib/firmware/apple/pmp-t8010.bin` vorhanden                 | – |

Quelle Feature-Stand: HoolockLinux/docs `features/A10.md` (Display Pipe, GPU: TBA;
Main Display, Brightness, Buttons: upstream; USB2 Device Mode: linux-apple).

# Bluetooth iPhone 7 (d101) – Befunde 2026-11-07

- Chip: BCM4355C0 (BT-Teil des WLAN/BT-Kombimoduls "Elsa", Hersteller USI).
- Anschluss laut ADT: **uart1** (0x20a0c4000, IRQ 219) – nicht uart4 (dort hängt nur der wlan-ADT-Knoten).
  - function-tx GPIO 0x60 (96), function-rts GPIO 0x62 (98) → Pinmux Funktion 1
  - function-bt_wake AP-GPIO 0x57 (87), function-power_enable PMU-GPIO 8
  - transport-speed 3000000 (Samsung-UART bei 24 MHz kann max. 1,5 Mbaud → max-speed 1500000, wie Sandcastle)
  - bluetooth-taurus-calibration = syscfg/BCAL, tx/rx-calibration syscfg/BTTx, BTRx
  - BD-Adresse: /chosen mac-address-bluetooth0 (m1n1 setzt local-bd-address über Alias bluetooth0)
- Firmware: iOS bettet die .hcd-Patches ins BlueTool-Binary ein (usr/sbin/BlueTool, iOS 13.3.1).
  research/tools/hcd_scan.py findet 80+ Blobs; "BCM4355C0 Elsa USI MCC" = 90495 Byte → tools/bt-fw.sh.
- Kernel: hci_bcm + compatible brcm,bcm4355c0-bt-apple (Patch 0013), Taurus-Kalibrierung nach
  HoolockLinux tests/bluetooth (HCI 0xfd97, 0xe6-Blöcke), hier nicht fatal. DT Patch 0014.
- m1n1: Patch 0002 sucht /arm-io/uartN/bluetooth (für brcm,taurus-cal-blob).
- Offen: btbcm kennt die Subversion des 4355C0 nicht → Firmware heißt BCM.hcd (+BCM4355C0.hcd);
  nach dem ersten Lauf Subversion aus dmesg ablesen und ggf. in btbcm-Tabelle eintragen.

## Stand 2026-11-08: Koppeln + Audio funktionieren
- Scan, Koppeln (Numeric Comparison, beide Seiten bestätigen) und Verbinden mit dem Laptop T490s: ok.
- Audio-Server auf dem iPhone ist PulseAudio 17 (module-bluez5-discover); PipeWire läuft ohne BlueZ-SPA mit.
- A2DP-Ausgabe: `bluez_sink.<MAC>.a2dp_sink` entsteht beim Verbinden, Testton kam am Laptop an
  → erster funktionierender Tonausgang (interner Lautsprecher noch nicht, siehe AUDIO-ANALYSE.md).
- Werkzeuge: tools/bt_pair.sh (vom iPhone aus koppeln), tools/bt_agent.sh (iPhone sichtbar +
  automatisch bestätigen, nur eigene Geräte), tools/bt_audio_test.sh (verbinden + Testton).
- r118 (Kernel #119): CONFIG_BT_RFCOMM/BNEP/HIDP + UHID. Vorher scheiterte das Verbinden mit Kopfhörern
  ("socket(STREAM, RFCOMM): Protocol not supported" → BlueZ trennt). Jetzt: soundcore Space Q45 verbindet
  normal, Profile a2dp_sink + handsfree_head_unit (HFP mit Mikrofon), Testton im Kopfhörer.
- Offen (2026-11-08): Antippen der Q45 im Phosh-Schnellmenü (Phosh 0.58) löst keinen Verbindungsversuch
  aus (bluetoothd-Log bleibt leer). gnome-control-center 51 startet nur mit XDG_CURRENT_DESKTOP=Phosh:GNOME
  ("bluetooth"-Panel), dort noch ungetestet. Workaround: bluetoothctl connect <MAC> bzw. tools/bt_audio_test.sh.

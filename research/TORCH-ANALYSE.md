# Taschenlampe / Blitz-LED (iPhone 7, d101) – Stand 2026-11-08

## Ergebnis
**Nicht nutzbar ohne Kamera-Stack.** Den Blitz steuert unter iOS die ISP-Firmware, kein eigener Treiber.

## Befunde
- ADT `isp`: `function-torch_enable = GPIO(0xb0, 0x101)` → AP-Pin 176.
  `tools/torch_test.sh` schaltet ihn auf dem iPhone 3× 2 s an: **LED bleibt dunkel**.
  Der Pin ist nur ein Freigabesignal für den ISP.
- ADT `i2c0/boost`: `reg 0xEA` (7-Bit 0x75), nur `device_type = boost`, **kein compatible**.
  Im Kernelcache passt keine IOKitPersonality darauf (`research/tools/kc_match.py … 'boost|torch|strobe'`
  findet nur AppleLVBOOST (AOP/SPU-Nub) und AppleLMBacklight).
  Nur gelesen, Register 0x00–0x0f: `06 08 0b 0b 1e 20 00 00 00 00 22 00 00 00 00 00`.
  Baustein unbekannt → **nicht beschreiben** (Überstromgefahr für die LED).
- `lm3539` (Backlight, i2c0 0x31) trägt `strobeTimeoutOverride` / `pre-strobe-*`.
  Gemeint ist das Abdimmen des Displays beim Blitz, nicht der Blitz selbst.

## Was nötig wäre
1. ISP-Treiber mit Apple-ISP-Firmware (großes Projekt, wie bei der Kamera), oder
2. den Chip auf der Platine identifizieren (Beschriftung/Schaltplan), dann gezielt nach Datenblatt ansteuern.

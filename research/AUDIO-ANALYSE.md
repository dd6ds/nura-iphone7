# Ton iPhone 7 (d101) – Bestandsaufnahme 2026-11-08

## Hardware laut Live-ADT
- **Maggie** (AppleMaggieARCAudio): FPGA/Audio-Router + Taptic-Treiber ("maggie-arc", spi1 CS1).
  Firmware im IPSW: Firmware/Maggie/AppleMaggieFirmwareImage.im4p (71 KB; ADT nennt MaggieBitstream_D10.bin).
  maggie_reset = GPIO 0x16, maggie_done = GPIO 0x1a, codec_asp_dout GPIO 9. Alle anderen Audio-Teile
  hängen von Maggie ab (dependency-name AppleMaggie, MCLK per "mckE", Enable "magE").
- **CS42L71** Codec (Hörmuschel, Mikrofone; kein Klinkenanschluss beim iPhone 7) an **spi1 CS0**
  (0x20a084000, IRQ 215), IRQ über GPIO-Controller 52 (Pin 24), hawk_pwr = PMU-LDO 0x308.
- **CS35L26** Lautsprecher-Verstärker ("speaker-top") an **spi2** (0x20a088000), reset GPIO 0x8c,
  Kalibrierdaten in der ADT (speaker-calib, speaker-config: amp_gain, rx/vsense/isense slots).
- **AD81006** "audio-convoy" an spi2.
- I2S: **MCA0..4** (compatible mca,t8010 / mca,s5l8950x, mca-version 5) @0x20a0a0000 + 0x4000*n,
  IRQ 227..; i2s-switch @0x20a004000 (Routing aud0..aud2 -> pin), aop-i2s-switch.
  mca0 -> cs42l71, mca1 (virtuell, TDM) -> cs35l26 + maggie, mca2 -> hawking/reference, mca3 -> Baseband,
  mca4 -> mikeybus.
- **DMA**: dma-parent = sio-dma (SIO-Koprozessor, RTKit-Firmware) – kein passender Linux-Treiber im Baum
  (nur apple-admac). Alternative: CPU füttert die MCA-FIFOs (PIO, per IRQ).

## Linux-Stand
- sound/soc/apple/mca.c nur für t8103 ("apple,mca") – A10-MCA (s5l8950x-Familie, Version 5) vermutlich anders.
- Keine Treiber für CS42L71, CS35L26, Maggie; weder Hoolock noch Sandcastle haben Ton.
- iOS-Kexts im kernelcache vorhanden: AppleCS42L71Audio, AppleCS35L26Amp, AppleMaggieARCAudio,
  AppleEmbeddedAudio(Libs) -> Registerfolgen per Reverse Engineering.

## Plan (Stufen, jede einzeln prüfbar)
1. Maggie: Firmware aus IPSW holen, Format bestimmen (iCE40-Bitstream?), per SPI laden, DONE-GPIO prüfen.
2. SPI-Kommunikation: CS42L71- und CS35L26-ID-Register lesen (Userspace per spidev).
3. MCA/I2S: Register aus iOS-Kext ableiten, Testton per PIO auf mca1 -> CS35L26 (Lautsprecher).
4. ASoC-Treiber (MCA-PIO oder SIO-DMA, Codec, Amp) -> ALSA-Karte, PipeWire.

## Stufe 1 – Ergebnis 2026-11-08
- Maggie-Bitstream: IPSW Firmware/Maggie/AppleMaggieFirmwareImage.im4p, unverschlüsselt, Lattice
  iCE5LP4K (iCEcube2, Aug 2016), 71339 B, Sync 7EAA997E bei Offset 83 -> research/maggie/maggie_d10.bin.
- DT: spi1 + spidev (CS0 Codec, CS1 Maggie); cmdline spidev.bufsiz=262144. tools/maggie_load.py.
- Laden läuft technisch (SS low, CRESET_B nach 11 ms frei, 235 KB in 0,36 s), CDONE bleibt 0.
- Verdacht: Maggie ohne Strom/Takt. Laut ADT schaltet das der AOP (SPUApp, Funktionen magE/mckE);
  AOP-Firmware (IPSW Firmware/AOP/aopfw-t8010aop.im4p, ARM32) enthält "enableMaggie=%s"/"enableMCLK=%s".
- AOP-GPIO (gpiochip1, 0x2100f0000): Ausgänge low: 3,5,7,20,25,38,39,40,41; high: 11,17,22.
- Hinweis: cs-gpios-Quirk ("spidev@0 enforce active low") -> CS0 ruht low (invertiert); CS1 korrekt.
- Suchlauf (tools/maggie_scan.sh): AOP-GPIO 3,5,7,20,25,38–41 jeweils high + Laden -> CDONE immer 0.
  Alle Leitungen danach wieder Ausgang low (Registerwerte wie vorher). Achtung: gpioget schaltet
  Leitungen auf Eingang um – nur für echte Eingänge verwenden.
- Nächster Ansatz: AOP-Firmware zerlegen (enableMaggie/enableMCLK), Kandidaten auch PMU (D2333) GPIO/LDO.

## AOP-Firmware (Stand 2026-11-08)
- research/maggie/aopfw.bin (aus aopfw-t8010aop.im4p), Thumb-2, Text-Basis: Dateioffset + 0xFFFFD0
  (Vektortabelle Datei 0x30 = 0x01000000). Hinterer Abschnitt (Init-Code, ~Datei 0xa8000) hat eine
  ANDERE Ladeadresse (bl-Ziele passen erst mit +0x347DC) – noch nicht sauber zugeordnet.
- Disassembly: research/maggie/aop.dis (arm-none-eabi-objdump, force-thumb, adjust-vma 0xffffd0).
- Modul "Button.cpp" (Haptik/Maggie): Befehlsverteiler ~0x100c330; enableMaggie -> 0x100c940,
  enableMCLK -> 0x100caf4. enableMaggie zählt Nutzer (this+0x6b0/0x6b4) und ruft beim Übergang
  0<->1: obj=[this+0x698]; obj->vtbl[+0x10](obj, pin=(u16)[this+0x6a0], 1/0)  => GPIO-Setzen
  über ein Treiberobjekt. Wer 0x698/0x6a0 setzt, ist noch offen (kein direkter Store gefunden).
- Button::start ~0x100b57c sucht Dienste per Namen: "accel", "aop-audio", "mux", "arc", "btmspk",
  "ampworker" (vgl. ADT SPUApp spkamp-config_arc / _btmspk).
- Hinweise "I2C Power", "Amp Power", "mux Power": AOP schaltet evtl. PMU-Anschlüsse per eigenem I2C.
- Empfehlung: Ghidra (headless) mit zwei Speicherblöcken für die weitere Datenflussanalyse.


## Ghidra-Sitzung 2026-11-08 (AOP-Firmware, Ghidra 12.2 headless, tools: ~/tools/aop_ghidra.sh)

- Basis 0x00FFFFD0 für Text **und** .data; der Init-Teil am Ende (ab ~0x10a3000) ruft Ziele mit +0x347DC
  (z. B. blx 0xfcc3ec -> memcpy 0x1000bc8).
- Button-Konstruktor (0x10a863c): `this+0x6a0 = 20` (Pin), `this+0x698 = 0x1090600`, `this+0x69c = 0x1090c08`,
  `this+0x6c2 = 1` (immer Pin-Pfad).
- 0x1090600 = GPIO-Controller-Objekt, MMIO phys **0x2_100f0000** (AOP-GPIO); vtbl+0x10 = set(pin,v):
  Bit0 von `base + pin*4`.  -> **enableMaggie = AOP-GPIO 20 Bit0** (Register 0x2100f0050, Ruhe 0x78a02).
- 0x1090c08 = MMIO-Fenster phys **0x2_10c02000**; enableMCLK schreibt dort **0x48 (an) / 0x08 (aus)**.
- Maggie-Service (0x1010c10) Kommando 0x1d = Bitstream laden: MCLK an -> Maggie an -> SPI-Write -> beide aus.
  Kein CRESET-Toggle in der AOP (macht der AP über GPIO 0x16).
- AOP-MMIO-Liste enthält kein AP-spi1; Bitstream-SPI läuft laut ADT (maggie-arc auf spi1, reg CS1) über den AP.
- Test: MCLK=0x48 + Pin20=1 gesetzt (Readback ok), CRESET/CS-Timing korrigiert (ctypes-ioctl statt
  fcntl.ioctl, das die GIL hielt – frühere Brute-Force-Tests waren deshalb ungültig) -> **CDONE weiter 0**.
- CDONE-Pin 0x1a: 0x7cb8e = Eingang, Pull-up an -> Lesung echt. CS1 (0xb1) idle high. s5l-SPI CONFIG 0x1E
  enthält bereits CPOL|CPHA (Mode 3).
- Offen: spi1-Pinmux (SCK/MOSI) prüfen, CS42L71-ID über CS0 als Gegenprobe; AppleMaggie-kext (AP-Seite)
  im Kernelcache auf zusätzliche Schritte untersuchen.

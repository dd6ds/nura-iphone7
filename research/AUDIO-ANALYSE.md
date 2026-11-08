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

### Durchbruch 2026-11-08: Maggie konfiguriert (CDONE = 1)

- Ursache: **CS-Polarität auf spi1 invertiert.** Die `cs-gpios` stehen am Controller-Knoten; gpiolib erzwingt
  dafür active-low („enforce active low“), der s5l-Treiber schrieb zusätzlich `!enable` -> beide CS-Leitungen
  idle LOW (ausgewählt) und HIGH während der Übertragung. Gemessen mit `tools/spi_cs_probe.py`.
- spi1-Pinmux ok (`tools/pin_dump.py`): 0x80/0x81/0x82 = Funktion 1 (SCK/MOSI/MISO), 0x83/0xb1 = GPIO-CS.
- Workaround-Test (alter Kernel): Bitstream über spidev1.0 senden (CS0 geht high, CS1 bleibt low) mit
  AOP-Sequenz (MCLK 0x48 + AOP-GPIO 20) -> **CDONE = 1**.
- Fix: `s5l_spi_set_cs()` setzt jetzt den logischen Wert `enable` (Patch 0001, Kernel r116).
  Danach reicht `sudo python3 tools/maggie_load.py` (MAGGIE_AOP ist jetzt Standard).
- Nächste Schritte: Codec CS42L71 (CS0) ansprechen (ID lesen), MCA/I2S-Takt, Verstärker CS35L26 (spi2),
  Datenpfad AP -> Maggie -> Lautsprecher.

### Stand r116 (2026-11-08 abends)

- CS-Polarität korrekt (CS low nur während der Übertragung); Restpunkt: beim Probe startet CS „ausgewählt“
  (GPIOD_OUT_HIGH) -> in Patch 0001 auf GPIOD_OUT_LOW geändert (nächster Kernel-Build).
- `maggie_load.py` zuverlässig (6/6): s5l nutzt für die ganze Nachricht die kleinste Taktrate und bricht
  jeden Teiltransfer nach 1 s ab (TIMEOUT_MS) -> jetzt 64 KiB Vorlauf + Bitstream bei 1 MHz (~0,5 s Puffer
  für den CRESET-Zeitpunkt), bis zu 3 Versuche.
- Codec CS42L71 (CS0): PMU-Versorgung `hawk_pwr` = PMU 0x308 ist bereits an (01). Antworten auf MISO
  hängen davon ab, ob Maggie konfiguriert ist -> MISO ist geteilt, Codec-Tests mit Maggie im Reset.
  Mit Maggie im Reset kommt konstant `00 90 …` – SPI-Protokoll des Codecs noch unbekannt.
- iOS-Treiber: `com.apple.driver.AppleCS42L71Audio` (Kernelcache, prelinked, Fat-Hülle +0x1c).
  `research/tools/kc_kext.py` / `kc_kext_segs.py` extrahieren Kext-Sections (nach research/maggie/cs42l71/,
  nicht im Repo). Register-/SPI-Zugriffe liegen vermutlich in der Basisklasse (AppleCSCodec… in
  AppleEmbeddedAudio) – als Nächstes dort das Leseformat suchen.

### CS42L71: SPI-Protokoll aus iOS (AppleEmbeddedAudio.kext)

- Treiberkette: `AppleCS42L71Audio` erbt von **AppleCSSPIv2Audio** (Metaklasse 0x…7a400a0 im GOT des Kexts),
  diese von AppleCSSPIAudio (v1). Code in `com.apple.driver.AppleEmbeddedAudio` (Kernelcache-Datei-Offset 0xae7f00).
- v1 (zum Vergleich): lesen `6d, a>>8, a&0x7f, 00, 00` (Wert im 5. Byte), schreiben `6c, a>>8, a&0x7f, 00, v`.
- v2: 2-Byte-Kommandos `[cmd, wert]`. Block lesen (`_readDataBlock`):
  `80, A0, A1, A2 (24-bit LE, Wortadresse bei Wortzugriff), 81, N0, N1 (Anzahl), C4|C6, 00, 00…, C4|C6, 00`,
  letztes Empfangsbyte muss **0x50** sein (Status bereit), sonst erneut pollen; danach Datenphase.
  Vorher/hinterher `[A1, ctrl]` bzw. `[A1, ctrl|0x40]` (Steuerregister 0x21).
  Basisadressen im Code: 0x14000 (Wortmodus) bzw. 0x5000.
- Test (r116): Codec antwortet mit Statusbyte 0x4c/0x48 bzw. 0x98/0x90 (= um 1 Bit verschoben) ->
  **falscher SPI-Modus**. ADT: Codec `00 00 01 08` (Mode 0), Maggie `01 01 01 08` (Mode 3); der s5l-Treiber
  war fest auf CONFIG 0x1E = CPOL|CPHA.
- Fix r117: `apple,honor-spi-mode` am spi1-Knoten -> CPOL/CPHA je Gerät (Touch auf spi2 unverändert),
  maggie@1 mit `spi-cpol; spi-cpha;`. Driver kompiliert mit W=1 ohne Warnungen (`src/kpatch/quick_check.sh`).
- Werkzeuge: `tools/cs42l71.py` (v1-Format), `tools/cs42l71_v2probe.py`, `tools/cs42l71_test.sh` (hält Maggie im Reset).

- Falle: `./build.sh payload` ersetzt die DTBs aus dem Kernelpaket durch `out/dtbs-override/*.dtb`.
  Nach DT-Änderungen daher `UPDATE_OVERRIDE=1 src/kpatch/quick_check.sh && ./build.sh payload`.
  (r117 lief zunächst mit dem alten DT ohne `apple,honor-spi-mode`.)

### CS42L71 antwortet (r117, 2026-11-08 17:45)

- SPI-Modus jetzt korrekt je Gerät (gemessen mit `tools/spi_cfg_probe.py`): CS0 CONFIG 0x1041b8 (Mode 0),
  CS1 0x1041be (Mode 3). Touch läuft unverändert.
- **Lesen per SPIv2 funktioniert** (`tools/cs42l71_v2.py`, `tools/cs42l71_dump.py`): Kopf, Status und Daten
  in EINER CS-Phase (iOS: keepCSAsserted=1). Daten kommen direkt nach einem Status mit (st & 0x50)==0x50;
  der Status wechselt d0/90, daher ohne Zusatz-Polls lesen. Ohne Auto-Inkrement (n Bytes = derselbe Wert);
  Anzahl 8 anfordern (mit n=1 nur Nullen).
- Adressen = Seite<<16 | Register.
- **Chip-ID: Seite 0 = `42 a7 10` -> 0x42A71 (CS42L71), Revision `a1`.**
  ```
  0x000000: 42 a7 10 00 a1 0a a4 0e 08 00 …
  0x010000: 0f 7f ff fb 03 03 03 c5 8f 77 00 a6 00 00 14 50
  0x010010: 01 80 00 00 00 ee ff ff ff 08 00 …
  0x020000: 00 01 01 00 f9 00 80 01 01 00 f9 00 80 01 01 00
  0x020010: f9 00 80 44 44 00 03 00 00 00 00 00 78 00 78 b4
  ```
- iOS-Hochfahren (AppleCS42L71Audio, um 0x…6bc5b68): maskWrite (vtbl+0xb18) auf 0x200003/0x200004
  (0x7f/0x40), 0x300000/0x300002 (0x3f), 0x10006 (1), 0x10001 (0x0e, 0x20), danach Warten auf
  0x3000c Bit 3 (RCO hochgelaufen, Timeout 100×10 ms). Nächster Schritt: Schreiben (`_writeDataBlock`)
  nachbauen und diese Sequenz ausführen.

### CS42L71: Schreiben funktioniert (2026-11-08 18:00)

- `_writeDataBlock` (AppleCSSPIv2Audio, 0x…5f70dbc) nachgebaut in `tools/cs42l71_v2.py` (`wr`, `update`):
  `[A1,ctrl]`, dann in EINER CS-Phase `80 A0 A1 A2 81 N0 N1` + 10×`[90 00]` (Status, bereit wenn
  (st & 0x90) == 0x90), danach `B5` (Byte; `B2` = Wort) + Daten + 10×`[90 00]`, zum Schluss `[A1, ctrl|0x40]`.
- Test 0x200003: 0x40 -> 0x41 geschrieben, zurückgelesen 0x41, wiederhergestellt 0x40. ✔
- Stand der iOS-Hochfahrregister nach iBoot: 0x200003/04 = 0x40, 0x300000/02 = 0x3f, 0x10001 = 0x7f,
  0x10007 = 0xc5, 0x1000a = 0x00.
- `tools/cs42l71_powerup.py` (Sequenz aus iOS): 0x1000a |= 4, 0x10001 &= ~0x40 -> Werte kommen an, aber
  **RCO läuft nicht hoch** (0x3000c Bit 3 bleibt 0), auch mit AOP-MCLK (0x48) + AOP-GPIO 20.
  Seite 3 liest sich komplett 0 (byte- und wortweise).
- Offene Spuren: iOS ruft vor der Sequenz `c6130` (Takt-/Ratenkonfiguration, Konstante 1 000 000 = 0xf4240)
  sowie vtbl+0x430(0xe3ff8103) und vtbl+0x710(0x185) auf; nach dem RCO-Hochlauf folgen 0x20000 (mask 3),
  0x10000 (mask 1 / 0xc0), 0x50000. Möglicherweise braucht der RCO den I2S/MCA-Takt (MCLK vom AP) statt
  nur des AOP-MCLK.

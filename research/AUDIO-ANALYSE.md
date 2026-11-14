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

### RCO-Suche (2026-11-08 18:15)

- vtable AppleCS42L71Audio = 0x…6fcad38 (361 Einträge). Aufgelöst: +0x430 = messageClients() (nur
  IOKit-Benachrichtigung), +0x710 = Controls-Verwaltung (Software), +0xad8 = `_readReg` (fragt per +0xb40,
  ob 32-bit-Register, dann `_readDataBlock`), +0xb18 = maskWrite. `c6130` wartet nur auf einen
  Software-Zustand (this+0xba2 == 7, 19×100 ms). -> Die Register-Sequenz aus iOS ist vollständig nachgebaut.
- Wortlesen (C4) bestätigt: liefert dieselben Werte wie Bytelesen (Seite 0/1), Seite 4 = 0xff, Seite 3 = 0.
- Versucht ohne Erfolg (0x3000c Bit 3 bleibt 0, Seite 3 komplett 0):
  0x10000 Bit 1 = 0 (c3f04, Taktwahl), Flanke 0x10001 Bit 6 (1 -> 0), mit AOP-MCLK 0x48 + AOP-GPIO 20.
- PMU-GPIO 12 (`digitalldo_pulldown`) = Ausgang 0 (Pulldown inaktiv), `hawk_pwr` PMU 0x308 = 1.
- Vermutung: Der Codec braucht den Audio-Takt vom AP (MCA/I2S, ADT `hawk_master = AUD1('ap2h')`,
  Pins 0x00–0x04 auf Funktion 1) oder eine weitere Versorgung über die AOP (`external-power-provider = 47`).
  Nächster Schritt: MCA-Block (0x20a0a0000…) und den AUD1/ap2h-Takt untersuchen.

### Audio-Takt: NCO läuft, Weg zum Codec noch offen (2026-11-08 18:40)

- ADT: `mca0` (0x20a0a0000, IRQ 227, clock-gate 64, zweites Register 0x20a002000) bedient den Codec;
  `function-mclk_frequency = NCOf(0)`, `function-i2s_route = i2s-switch i2sR('aud0','pin4',0x30303)`,
  audio-data reg enthält `00 1b b7 00` = **MCLK 12 MHz**. mca1 -> Lautsprecher/Maggie (virtual-mca1a/1b),
  weitere MCAs für hawking/reference/voice.
- **NCO** `nco,s5l8960x` @ 0x2_0e044000, 5 Seiten à 0x4000 (Kanal = Seite). iOS-Treiber
  `AppleS5L8960XNCO::setFrequency` (0x…657453c) entschlüsselt und in `tools/nco_set.py` nachgebaut:
  fin = 2,4 GHz/7; div = 2·2,4G/(7f); DIV = LFSR(0x7ff, 0xa01, div/4−3 Schritte)<<2 | div&3;
  INC1 = Rest, INC2 = Rest−7f, ACCINIT = (Rest^0x80000000)−7f, CTRL = 0x80001000 (Bit 30 = busy).
  Kanal 0 auf 12 MHz gesetzt: INC1 = 0x00b71b00, CTRL liest 0x80309000. ✔
- i2s-switch @ 0x20a004000: alle Pin-Gruppen 0x00181818 (unbelegt). Pin 4 (0x20a004010) testweise 0x030303.
  0x20a002000..c = 0.
- RCO des Codecs startet trotzdem nicht. Fehlend vermutlich: MCA0 selbst (Takt-Gate 64 einschalten,
  MCLK-Ausgang aktivieren; Register 0x20a002000) und die richtige Kodierung des i2s-switch.
  `AppleARMIISSwitch` (AppleIISController.kext) berechnet nur Masken; die Register schreibt eine
  SoC-spezifische Unterklasse (vtbl+0x588) – noch nicht gefunden. setMCLKFrequency ebenfalls dort.
- Vorsicht: MCA-Register (0x20a0a0000) noch nicht gelesen – bei abgeschaltetem Takt-Gate kann ein Zugriff
  das System anhalten. Zuerst Gate 64 im PMGR finden/einschalten (Linux: power-domain ps_mca0?).

### MCA/i2s-switch entschlüsselt (AppleAE2Audio.kext, 2026-11-08 19:00)

- Echte Treiber: `com.apple.driver.AppleAE2Audio` (Kernelcache-Datei-Offset 0xc386c0) mit `AppleAE2MCA`,
  `AppleAE2I2SSwitch5`, `AppleAE2AOPI2SSwitch1`. Werkzeuge: `research/tools/kc_kext*.py`.
- **PMGR**: mca0 = Power-State 0x2_0e080178 (Linux `ps_mca0`, unter `ps_sio_p`); war aus (0xa00).
  `tools/pmgr_ps.py 0x80178 on` -> 0xff, danach sind MCA0-Register lesbar (0x20a0a0000 = 0x5 = mca-version,
  +4 = 0x00100010, Blöcke bei +0x60/+0x80 …).
- **MCLK-Steuerung** (`AppleAE2MCA::_getMCLKClkCon`): Wert in `mcaMCLKControl` = zweites MCA-Register
  (mca0: 0x20a002000): Quelle nclk==f -> 0x10, ==2f -> 0x18, ==4f -> 0x20 (Teiler-Modus: 8),
  `| 0x40` = MCLK-Ausgang an. Für 12 MHz aus NCO0 = 12 MHz: **0x50**.
- **i2s-switch** (`AppleAE2I2SSwitch5`, 0x20a004000): Register-Index N = Ziel `pinN` (0..4), `audN` = 5+N;
  je drei 5-bit-Felder (Bits 4:0, 12:8, 20:16) mit Quellindex: `audN` = N, `pinN` = 8+N, 0x18 = frei.
  Ausgangsfreigabe für Pins in Index 19 (0x20a00404c): Bit 4 (Signaltyp 0) / Bit 0 (Typ 1) bzw. Index 15+N.
  Route mca0: `aud0 -> pin4` => 0x20a004010 = 0x000000, 0x20a00404c |= 0x11.
- Alles zusammen in `tools/codec_clock_on.sh` (PMGR an, NCO0 12 MHz, ClkCon 0x50, Route). Ergebnis:
  **RCO startet weiterhin nicht** (0x3000c = 0, Seite 3 = 0).
- Offen: `function-pclk_gate` der MCA (Takt-Gate 64 noch nicht geschaltet), MCA-Grundinitialisierung
  („cannot init IES“, FIFO), ob MCLK physisch am Codec ankommt (Pins 0x00–0x04 Funktion 1 = I2S-Gruppe?),
  bzw. ob der RCO überhaupt vom MCLK abhängt. Nicht ausgeschlossen: Seite 3 ist anders adressiert.

### SPIv2-Steuerregister 0x21 (`[A1, ctrl]`) – 2026-11-08 19:20

- `AppleAE2MCA::start`: Version/FIFO prüfen, IES/DMA-Ereignisquellen (Software), dann `function-*`
  einlesen; MCLK-Register schreibt nur `setMCLKEnabled` (ClkCon, s. o.). Die iOS-Hochfahrfunktion des
  Codecs ruft vor dem RCO-Schritt KEINE MCLK-Funktion (die Aufrufe auf this+0xc08 gehen in
  AppleCSEmbeddedAudio = Headset/Mikey). -> MCLK als RCO-Voraussetzung eher unwahrscheinlich.
- `_initializeCodecRegisters` (0x…5f72d9c): `[A1, ctrl|0x50]`, 1 ms, Status `[90 00]` pollen bis
  (st & 0x90) == 0x90 (max. 49×), dann `[A1, ctrl|0x40]` (`tools/cs42l71_v2.py: init()`).
- Test: erster Lauf Status 0xd0 (ok), danach meldet die Brücke dauerhaft 0x80/0xc0 (nicht bereit) –
  Lesen unmöglich. **`[A1, 0x01]` holt sie zurück** (Chip-ID 0x42 wieder lesbar,
  `tools/cs42l71_recover.py`). Bedeutung der Steuerbits noch offen; iOS ändert sie in 0x…5f73780
  (Bit 2 u. a.) – als Nächstes entschlüsseln.
- `tools/cs42l71_v2.py: read_poll()` liest robust mit mehreren Status-/Datenfenstern in einer CS-Phase.

### Steuerregister der SPIv2-Brücke entschlüsselt (2026-11-08 19:40)

- Hilfsfunktion 0x…5f733c4: `[90 00]` = Status (2 Bytes, Wert im 2.), `[91 00 00]` = Steuerregister
  lesen (3 Bytes, Wert im 3.), `[A1 x]` = Steuerregister schreiben.
- Steuerbits (aus AppleCSSPIv2Audio): Bit 0 = Brücke wecken (holt sie aus „nicht bereit“),
  Bit 2 = `_enableControlI2C`, **Bit 5 = `_enableControlPLL`** (danach Status Bit 3 = PLL eingerastet,
  max. 51 ms), Bit 6 = Abschluss nach Zugriffen, Bit 4 (mit 0x50 in `_initializeCodecRegisters`)
  lässt die Brücke ohne laufenden Takt hängen.
- `tools/cs42l71_pll.py`: Steuerregister 0x01 -> 0x21 gesetzt, **PLL rastet nicht ein** (Status-Bit 3
  bleibt 0) – mit AOP-MCLK, NCO0 12 MHz, MCA0-ClkCon 0x50, Route aud0->pin4, mca0 an, und auch mit
  geladener Maggie (`MAGGIE=1 tools/cs42l71_test.sh`; Codec bleibt dabei lesbar).
- Schluss: Der Codec bekommt **keinen Referenztakt** (die Brücken-PLL braucht ihn, der RCO/Kern
  vermutlich ebenso). Der MCLK-Pfad SoC -> Codec ist noch nicht vollständig. Kandidaten: falscher
  Ziel-Pin im i2s-switch (pin4 laut ADT, aber Signaltyp/Feld?), MCA0 muss selbst laufen (Serialisierer
  an), oder der Codec-MCLK kommt aus einer anderen Quelle (Maggie/AOP `mckE`, AOP-i2s-switch
  0x210540000 mit `aop_i2s_oe_reg_val = 8`).

### AOP-i2s-switch (2026-11-08 19:55)

- `AppleAE2AOPI2SSwitch1` (gleiche Kext): Basis 0x2_10540000, Version bei +0xffc, zweites Register
  0x2_10000600 = `aop_i2s_oe_reg_val` (ADT 8; iBoot-Stand 0x0c). `reg-defaults` = Paare (Index, Wert):
  (0, 0), (2, 0x080808); übrige 0x181818. Geschrieben werden Index 0–3, +0x3c, +0x40.
- Gleiches Feldformat wie der AP-Schalter: Ziel `pinN` = Index N (Freigabe Index 15+N), `mcaN` = 2+N;
  Quellen `mcaN` = N, `pinN` = 8+N. Route-Flags 0x30303 = beide Richtungen.
- `tools/i2s_route.sh`: AP pin4<-aud0 (0x000000), aud0<-pin4 (0x0c0c0c), Freigabe 0x20a00404c |= 0x11;
  AOP pin0<-mca1 (0x010101), mca1<-pin0 (0x080808), Vorgabe Index 2 = 0x080808, Freigabe
  0x21054003c |= 0x11, 0x210000600 |= 8. Alle Werte zurückgelesen ✔.
- Ergebnis: **PLL der Codec-Brücke rastet weiterhin nicht ein**, RCO bleibt aus.
- Stand des MCLK-Pfads: NCO0 12 MHz ✔, mca0 Power ✔, MCA0 ClkCon 0x50 ✔, AP- und AOP-Schalter ✔.
  Offen: MCA0 selbst (Serialisierer/Taktausgang erst bei laufendem Stream?), Pinmux der AOP-I2S-Pins
  (AOP-GPIO-Funktion), oder MCLK kommt über einen ganz anderen Weg. Ohne Messgerät nicht prüfbar.

### MCA-Konfiguration und Codec-Ports (2026-11-08 20:15)

- MCA-Registerzugriff in AppleAE2MCA: `base + idx*4` (Lesen 0x…644e6b4, Schreiben 0x…644e734).
  Konfiguration (0x…644c140): ClkCon -> mcaMCLKControl; bei mca-version != 0 Reset `0x11=3`,
  `0x12=1` (warten bis Bit 0 = 0) bzw. `0x11=0x301`; dann `4=0`, `7=0xd`, `0xc=0xd`,
  `2=(0x2000-(rxbits<<8))|(0x20-txbits)`, 8/0xd = Teiler, 5, 9/0xe = Slot-Masken, 6/0xb = Takt-/
  Sync-Quelle, `4 = 1|3` (Freigabe), `0x10 = 0xb0003000`, `3` = Rahmen/Sync. Start: `3 = 1/2`.
- ADT-Codec-Ports: `hawk_active`/`asp_active` = `i2sA('pin2')`, `msp_active` = `i2sA('pin0')`;
  Takt-Master `AUD1('ap2h')` = audio-codec-hawking unter **mca2** (NCO2, Route aud2->pin2),
  `ap2x` = reference (mca2b), `ap2v` = voice/mikeybus (mca4, NCO4, 12 MHz).
  mca0-`audio-data,cs42l71` (12 MHz, NCO0, aud0->pin4) ist ein weiterer Port.
- Test `tools/i2s_pin2_test.sh`: Pin 2 freigegeben (0x20a004044 = 0x11), pin2 <- aud0 -> PLL rastet
  weiterhin nicht ein.
- Fazit für jetzt: ohne Messung am MCLK-Pin nicht weiter eingrenzbar. Nächste sinnvolle Schritte wären
  die vollständige MCA-Initialisierung (Reset 0x11/0x12, Freigabe 4, 0x10) für mca0 **und** mca2
  sowie NCO2 auf 12 MHz, oder ein Logikanalysator.

### Option 1: volle MCA-Initialisierung (2026-11-08 20:35) – ohne Erfolg

- `tools/mca_init.py N` (PMGR an, NCO N 12 MHz, ClkCon 0x50, Reset 0x11/0x12, Registerfolge wie
  AppleAE2MCA, Freigabe 4/0x10/3) für **mca0 und mca2**; `tools/mca_codec_test.sh` zusätzlich Routen
  (i2s_route.sh, pin2 <- aud2, Pin-2-Freigabe).
- MCA-Register: Version 0x5, Reg1 0x00100010, Reg7 liest 0x80000400 (Status?). Nach dem Schreiben
  lesen sich nur 4 (=1), 0xb (=8), 0xe (=3) zurück; 2/3/5/6/8/9/0xc/0xd/0x10 lesen 0 (nur schreibbar
  oder nur bei laufendem Stream gültig).
- PMGR mca2 = 0x80188 (war aus, 0xa00).
- **Ergebnis: PLL der Codec-Brücke rastet nicht ein, RCO bleibt aus.**
- Audio vorerst pausiert. Wiederaufnahme am besten mit Messung (Logikanalysator am Codec-MCLK) oder
  mit einem echten Linux-MCA-Treiber, der einen Stream inkl. DMA startet (MCLK evtl. nur bei laufendem
  Serialisierer).

## AOP-Coprozessor starten – Vorarbeit (2026-11-14, nach dem GPU-Erfolg)
Gleiche Treiberfamilie wie die GPU (AppleA7IOP, AKF V2, RTKit 1827.140.2) → siehe research/GPU-ANALYSE.md.
- `tools/aop_peek.py` (nur lesend): AKF 0x2_10800000: CPU_CTRL +0x44 = 0 (steht), INBOX/OUTBOX 0x20001
  (leer), IDLE 0x79. Fenster-Register (von iBoot gesetzt): +0x08 = 0x10e00000, +0x10 = 2 (phys. 0x2_10e00000
  = AOP-SRAM), +0x18/+0x20 = 0, +0x28 = 0x1ff000, +0x38 = 1; außerdem +0x0c = 0x40000000, +0x14 = 1,
  +0x1c = 0xc0000000, +0x2c = 0xfffff000, +0x3c = 1 (zweites Fenster?). 0x2_10000408 = 0x1ddeae2.
  SRAM-Anfang: 00030201 00050220 000d0000 000d0000 00080000 000c0000 (keine ARM-Vektoren → keine Firmware geladen).
- `research/tools/osbin.py`: aopfw.bin ist OSSerializeBinary (0xd3):
  firmware[0] AOP „AppleSPUFirmwareBuilder-373.100.9~11772“, 669 568 Byte (Code ab IOP 0x0100_0000);
  firmware[1] AOP_ext, Segment `__ETEXT`, 26 976 Byte, Adresse 0x010d_8000, Tag 0x454330.
  Teile nach research/maggie/aopfw-teile/ (gitignored).
- Offen: Speicheraufteilung (Hauptteil > 640 KB SRAM → zweites Fenster/DRAM), `segment-ranges` im ADT,
  Start wie GPU (Fenster, CPU-Start, RTKit-Handshake mit tools/gpu_rtkit.py-Logik auf Basis 0x2_10800000).

### AOP-Startversuche (2026-11-14, tools/aop_fw_boot.py)
- iBoot lädt die AOP-Firmware bei unserem Boot-Weg (checkm8/PongoOS/m1n1) **nicht**: AOP-SRAM
  0x2_10e00000 enthält nur zufälliges SRAM-Rauschen (163 804 von 163 840 Wörtern != 0).
- Firmware-Basis bestätigt: 6829 Zeiger 0x010x_xxxx → Hauptteil ab IOP 0x0100_0000, AOP_ext ab 0x010d_8000.
- DT `reserved-memory/aop-fw@840400000` (1 MB, no-map); Hauptteil an +0, AOP_ext an +0xd8000.
- **Start braucht zusätzlich das Auto-Boot-Register:** AppleA7IOP bildet bei „auto-boot“ Register-Index 2
  ab (ADT aop reg[2] = **0x2_10000500**) und schreibt beim Start 1, beim Anhalten 0 hinein
  (zusätzlich zu akf+0x44 Bit 4). Ohne das: RUN-Bit gesetzt, aber keine Ausführung.
  0x2_10000408 ist dagegen ein 32-kHz-Zähler (läuft hoch), kein Steuerregister.
- Der AOP startet an IOP-Adresse 0: Fenster nur auf 0x0100_0000 → keine Ausführung; Fenster 0 auf IOP 0
  → Ausführung. Zweiter Fenstersatz (+0x0c/+0x14/+0x1c/+0x24/+0x2c/+0x34/+0x3c; iBoot: IOP 0xc000_0000 →
  phys 0x1_4000_0000, Länge 0xfffff000) als Alias IOP 0x0100_0000 → derselbe RAM (FENSTER2=1).
- Ergebnis (IOP_BASIS=0 FENSTER2=1): Firmware läuft und baut **MMU-Seitentabellen ab RAM +0x78000**
  (4-KB-Einträge 0x…483, fortlaufend +0x1000), insgesamt 819 Wörter geschrieben, IDLE 0x79 → 0x78.
  AOP-SRAM bleibt unberührt. **Kein RTKit-HELLO** – die Firmware bleibt vorher stehen.
- Nächster Schritt: Boot-Pfad der AOP-Firmware nach dem MMU-Aufbau statisch verfolgen (Ghidra-Projekt vom
  2026-11-08): welche Speicherbereiche/Peripherie sie erwartet (SRAM-Adresse aus Sicht des AOP, iBoot-
  Übergabedaten, Fenster 1 = Peripherie-Zugang?).

### AOP-Startcode statisch + dynamisch (2026-11-14)
- Reset (ARM, IOP 0x0100_0068): Modus/VBAR/FPU, berechnet den **Slide** aus dem PC (Ladeadresse − 0x0100_0000)
  und baut eine LPAE-Seitentabelle bei Ladeadresse + 0x78000 (Zeiger 0x0100_0058 = 0 → Standard 0x0107_8000),
  die VA 0x0100_0000 auf die echte Ladeadresse abbildet → **Fenster 0 auf IOP 0 genügt**, FENSTER2 unnötig.
- Kennwort 0x0100_a36fc: im Bild 0xFEED1B00 → Kaltstart; danach 0xCAFE4B0B (Warmstart-Marke), 0xBAADF1AC = Fehlerpfad.
- Laufzeitbereich laut Literalen: 0x0100_0000–0x010d_7028 (+ AOP_ext bis 0x010d_e960) → passt in 1 MB.
- Lauf mit IOP_BASIS=0: 819 Wörter geschrieben – Seitentabelle (780), RTKit-Task-Stack bei 0x0108_e7xx
  (Füllung „RTKSTACK“), Marke 0x010a_36fc, Stack 0x010d_6fxx. Aufrufkette auf dem Stack:
  0x0100_0394 (Start) → 0x0105_91e7 (Modus-Stacks, VBAR 0x0100_0580, dann bl 0x0105_a248) → 0x0105_a261.
- 0x0105_a248 kopiert (memmove 0x0100_0bc8) einen **Block von Konfigurations-Einträgen** aus 0x010a_3290:
  Kennungen (im Speicher rückwärts) `LCSD`, `SZSD`, `LZSD`, `SNUT`, `ZNUT`, `OTTR`, `ARcM` …, Werte im Bild alle 0
  → **werden normalerweise von iBoot ausgefüllt** (Boot-Parameter/Tunables).
- Auf dem Stack stehen außerdem 0x011f_8000 (Länge 0x1000) und 0x011f_8f80 – **außerhalb** unseres Fensters
  (endet 0x0110_0000). Vermutung: AOP-SRAM (0xa0000) wird bei IOP 0x0116_0000–0x0120_0000 erwartet.
- Nächste Schritte: (1) Fenster 1 auf IOP 0x0116_0000 → AOP-SRAM 0x2_10e00000 (0xa0000) testen;
  (2) Bedeutung/Werte der Konfigurations-Einträge klären (iBoot setzt sie; ggf. aus einem iOS-Speicherabzug
  oder dem iBoot-Code); (3) PC des hängenden AOP über Debug-/PC-Sample-Register ermitteln.

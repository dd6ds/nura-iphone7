# GPU iPhone 7 (A10 / T8010) – Stand 2026-11-14

## Hardware (ADT, Kernelcache)
- ADT `sgx`: compatible `gpu,t8010`, device_type `sgx`, IRQs 185–188 + 193, clock-gates/power-gates 148, 150,
  clock-ids 265, `metal-standard = 256`, `opengl-standard = 768`, 2 Leistungsstufen.
- Darunter ein eigener Steuer-Coprozessor: compatible `iop-gfx,t8010`, device_type `gfx-kf`, role GFX,
  IRQs 189–192, power-gate 149, Kind `iop-gfx-nub` (RTBuddy) – wie der AOP.
- iOS-Kexts: `com.apple.AGXG9P` (Treiber), `com.apple.AGXFirmwareKextG9PRTBuddy` / `…RTBuddy` (Firmware).
- Also: PowerVR-Series-7XT-Abkömmling, aber mit Apple-Firmware und Apple-Schnittstelle („AGX G9P").
  Der Linux-Treiber `powervr` (Imagination-Firmware) passt nicht; Asahi-AGX zielt auf G13+ (M1).

## Weg 1 (Forschung): GPU-Coprozessor starten
1. Power-Domains 148/149/150 einschalten, Register des `gfx-kf`-IOP lesen (nur lesen).
2. Firmware aus `AGXFirmwareKextG9PRTBuddy` extrahieren (nicht veröffentlichen!), RTKit-Start wie beim AOP.
3. Antwort des Coprozessors (RTKit-Hello/Version) = erster Meilenstein. Derselbe RTKit-Start wird auch
   für den AOP gebraucht (Audio, Vibration, Bewegungssensoren).

### Ergebnisse 2026-11-14 (tools/gpu_peek.py, nur lesend)
- PMGR-Domain `gfx` (0x2_0e080328): aus = 0x0f000b00 (Bit 11 PARENT_OFF ist nur ein alter Merker,
  GFX hat laut ADT keine Eltern-Domain). Einschalten → 0x0f0001ff (ist=0xf), stabil.
- Unter-Domains GFX-SGX (148), GFX-KF (149), GFX-BUSY (150) haben **kein** PMGR-Register (psreg 0);
  SGX/KF hängen unter GFX (124). Sie werden GPU-intern geschaltet.
- gfx-kf-IOP 0x2_01d20000 (+0x000…+0x0ff) lesbar: +0x00 = 1, +0x38 = 1, +0x3c = 1, +0x40 = 0x00030000,
  +0x48 = 0x79, Rest 0. +0x44 (bei M1-ASC: CPU_CONTROL, Bit 4 = RUN) = 0 → Coprozessor steht.
- Gemeinsamer Block 0x2_01d00000 (+0x000…+0x0ff) lesbar, alles 0.
- **GPU-Kern 0x2_01000000: schon 1 Lesezugriff friert das iPhone ein** (zweimal reproduziert) →
  GFX-SGX ist aus. Nächster Schritt offline: im Kext `com.apple.AGXG9P` suchen, wie GFX-SGX/GFX-KF
  eingeschaltet werden (vermutlich Register im gemeinsamen Block 0x2_01d00000) und wie der IOP
  gestartet wird (Firmware-Ladeadresse, CPU-Start über +0x44).

### Treiber-Analyse 2026-11-14 (Kernelcache iOS 15.8, Kexts nur lokal in research/maggie/, gitignored)
- `com.apple.AGXG9P` (Klassen AGXAcceleratorG9P_A0/_B0, match `gpu,t8010`): die GPU-Firmware schaltet den
  GPU-Kern selbst ein/aus („submission while the GPU is powered off“, „GPUIdlePowerOff“). Der AP schaltet
  nur `gfx` ein und startet den Coprozessor → GFX-SGX ist erst nach Firmware-Start erreichbar.
  Weitere Registerbereiche im Treiber: „Fender“ (UV-Warnung), „PMGRScratch“.
- Coprozessor-Start: **nicht** im AGX-Treiber, sondern `com.apple.driver.AppleA7IOP`, Klasse
  `AppleA7IOPV2GFX` (match `iop-gfx,t8010`) – dieselbe Treiberfamilie wie beim AOP.
  AKF-V2-Register (aus der Diagnose-Ausgabe `IDLE_STATUS/MAILBOX_SET/…`, relativ zum gfx-kf-Block):
  | Offset | Register | gelesen (gfx an) |
  |---|---|---|
  | +0x4000 | MAILBOX_SET | 0 |
  | +0x4004 | MAILBOX_CLR | 0 |
  | +0x4008 | INBOX_CTRL (Bit 0 an, Bit 17 leer) | 0x00020001 |
  | +0x4020 | OUTBOX_CTRL (Bit 0 an, Bit 17 leer, 0xc0000 = Über-/Unterlauf) | 0x00020001 |
  | +0x4040 | IDLE_STATUS | 0x59 |
  Außerdem +0x4018 = 0x48001000, +0x401c = 0x12000080, +0x4038 = 0x08003020, +0x403c = 0x0020c000.
  CPU-Steuerung vermutlich +0x44 (wie M1-ASC, RUN = Bit 4) = 0.
- Firmware: `com.apple.AGXFirmwareKextG9PRTBuddy`, Section `__TEXT.__const` (373 545 Byte): Kopf „Release“,
  danach ARM32-Code (Vektortabelle), `RTKit_iOS-1827.140.2.release` → RTKit wie beim AOP.
  Treiberfunktionen: requestFirmwareBinary, getBootConfigOffset, getRuntimeBinSize, getFWResumeFlagOffset.

### Startsequenz aus AppleA7IOPV2 / V2GFX (disassembliert, 2026-11-14)
Basis = gfx-kf-Block 0x2_01d20000 („akf“), GFX-Zusatz = gemeinsamer Block 0x2_01d00000 („agx“).
| Funktion | Zugriffe |
|---|---|
| CPU starten/stoppen | akf+0x44: Bit 4 = RUN (lesen, Bit 4 setzen/löschen, schreiben); optional auto-boot-Register |
| `_mapFirmware` (V2) | akf+0x18/+0x20 = IOP-Adresse (lo/hi), +0x28 = Länge & ~0xfff, +0x30 = 0, +0x08/+0x10 = **physische** Adresse (lo/hi), +0x38 = 1 → Adressfenster statt DART |
| `_mapFirmware` (V2GFX) | dasselbe zusätzlich in agx+0x2014/+0x2018 (IOP-Adr.), +0x201c (Länge), +0x2020 = 0, +0x200c/+0x2010 (phys.), danach Basis-Version |
| GFX-Schalter | agx+0x2048 Bit 0 (setzen/löschen) |
| Interrupt-Init | akf+0xc004 = 0x11, akf+0xc024 = 1 |
| Zeitbasis-Sync | akf+0x80c Bit 1 aus, Zeitstempel → akf+0xc030/+0xc038, Bit 1 wieder an |
| Nachricht senden (AP→IOP) | 64-Bit-Schreiben akf+0x4010; Eingang voll = akf+0x4008 Bit 16, leer = Bit 17 |
| Nachricht holen (IOP→AP) | 64-Bit-Lesen akf+0x4038 (**Lesen entnimmt!**); Ausgang leer = akf+0x4020 Bit 17, 0xc0000 = Fehler |
| Interrupt-Masken | akf+0x4000/+0x4004 (Set/Clr) und +0xc00/+0xc04: 0x1 = Eingang, 0x1000 = Ausgang; 0x1111 = alle |
| Sonstiges | akf+0xb88 Bit 0 = Status (vermutlich idle) |

- Kein fester RAM-Bereich für die GFX-Firmware im ADT (anders als AOP: region-base 0x2_10e00000).
  iOS legt sie zur Laufzeit ab (AGXFirmwareKext → requestFirmwareBinary) und stellt nur das Fenster ein.
### ✅ Erster Start des GPU-Coprozessors (2026-11-14, tools/gpu_fw_boot.py)
- Firmware = `__TEXT.__const` ab Byte 9, Länge 0x5B320 (requestFirmwareBinary, Rev. 3); Kopf davor:
  Build „“ (+0) und Version „Release“ (+1). Erstes Wort 0xEA000006 (ARM32 `b`), Laufzeitbedarf 0x8F000.
- RAM: DT `reserved-memory/gfx-fw@840000000` (1 MB, no-map). /dev/mem bildet ihn als Gerätespeicher ab →
  nur ausgerichtete 32-Bit-Zugriffe (memset/memmove = SIGBUS).
- Fenster: IOP-Adresse 0 → phys. 0x8_4000_0000, Länge 0x100000 (akf und agx, s. Tabelle oben).
- **Ohne agx+0x2048 Bit 0 läuft die CPU nicht** (RUN-Bit gesetzt, aber RAM bleibt unverändert).
  agx+0x2048 vorher = 0x6, danach 0x1 (Wert gelesen nach dem Setzen).
- Mit Bit 0: nach **2 ms erste Nachricht `0x00100000000c000c`** = RTKit-HELLO (Typ 1 in Bit 52–59,
  Version min = max = 12). Firmware beschreibt Daten (70 Wörter ab +0x31ec0) und Variablen/Stack
  (107 Wörter ab +0x890c0). IDLE_STATUS 0x61 → 0x6f, OUTBOX_CTRL danach 0x21101. iPhone bleibt stabil.
- Nächster Schritt: RTKit-Handshake (HELLO_ACK Typ 2 mit Version 12 senden, dann Endpunkt-Karte EPMAP
  lesen) – wie Asahi `rtkit.c`, aber älteres Nachrichtenformat (Endpunkt-Feld noch klären).

- Ursprünglicher Plan (umgesetzt):
  1. Im DT einen `reserved-memory`-Bereich (z. B. 1 MB, 16-KB-ausgerichtet) für die Firmware anlegen.
  2. gfx einschalten, Firmware per /dev/mem dorthin kopieren, Fenster (IOP-Adresse 0) setzen.
  3. Interrupt-Masken setzen, CPU starten (akf+0x44 Bit 4), Ausgang auf die erste RTKit-Nachricht pollen.
  Offen: Boot-Konfiguration der Firmware (getBootConfigOffset), RTKit-Protokoll der Version 1827.

## Weg 2: Software-Rendering beschleunigen (erledigt)
Messung mit `tools/gfx_bench.py` (GTK4, Vollbild, braucht `py3-cairo`; iPhone muss entsperrt sein):

| phoc-Renderer | Test | Bilder/s | CPU phoc | CPU App |
|---|---|---|---|---|
| GLES2/llvmpipe (alt) | kleines Quadrat | 27,8 | 76 % | 103 % |
| GLES2/llvmpipe (alt) | Vollbild-Farben | 27,9 | 76 % | 103 % |
| GLES2/llvmpipe (alt) | Liste scrollen | 36,5 | 72 % | 97 % |
| **pixman (neu)** | kleines Quadrat | **36,6** | **8 %** | 141 % |
| **pixman (neu)** | Vollbild-Farben | **36,7** | **8 %** | 141 % |
| **pixman (neu)** | Liste scrollen | **54,8** | **12 %** | 138 % |

- 100 % = ein Kern; Linux nutzt 2 Kerne (Hurricane, 2,24 GHz, schedutil).
- `WLR_RENDERER=pixman` in /etc/environment (build.sh). wayvnc liefert weiter echte Bilder.
- GTK: `GSK_RENDERER=ngl/gl` bringt nichts (fällt ohne GPU auf Cairo zurück) → `cairo` bleibt.
- Jetzt begrenzt die App-Seite (Cairo-Zeichnen auf der CPU), nicht mehr der Compositor.

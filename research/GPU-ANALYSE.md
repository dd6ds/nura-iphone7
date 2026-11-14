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

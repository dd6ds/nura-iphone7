# Sensoren + Vibration (iPhone 7, d101) – Stand 2026-11-08

## Wo hängt was (ADT)
| Teil | Bus | iOS-Treiber | Linux-Zugriff |
|---|---|---|---|
| Beschleunigung, Gyro, Kompass, Luftdruck, Annäherung | AOP (Coprozessor, Firmware t8010aop) | AppleSPU* | keiner (AOP-Firmware nötig) |
| Helligkeit CT821 | AP-I2C2 0x29, INT GPIO 0x8d | AppleCT821 | per Polling, siehe unten |
| Taptic-Verstärker „Convoy“ AD81006 | AP-I2C2 0x21 | AppleAD81006 | lesbar |
| Lautsprecher-Verstärker cs35l26 | AP-I2C2 0x40 (Reset GPIO 0x8c) | – | NACK (im Reset) |
| Mikrofon-Temperatur ica60 | AP-I2C3 0x54/0x56 | AppleICA60 | NACK; Scan findet 0x51 |

## I2C2/I2C3 unter Linux
- `status = "okay"` für i2c2/i2c3 (Pins 132/133 bzw. 41/42, IRQ 234/235 laut ADT korrekt) →
  beim Boot RCU-Stalls + NVMe-Timeouts („completion polled“), System hängt. Ursache offen; zurückgenommen.
- PMGR i2c2/3 (0x801b8/0x801c0) stehen auf 0xa00 (aus). Von Hand einschalten (`pmgr_ps.py 0x801b8 on`) geht problemlos.
- `tools/i2c_poll.py`: PA-Semi-Controller per /dev/mem ohne IRQ. **Wichtig:** echte 32-Bit-Zugriffe
  (ctypes), sonst schiebt Python byteweise in den TX-FIFO. Blocklesen > 1 Byte liefert Müll → Register einzeln.
  Gegenprobe Bus 0: Scan 0x1a 0x27 0x62 0x75, 0x75 = `06 08 0b 0b 1e 20 …` wie unter Linux.

## Helligkeitssensor CT821
- TSL257x-artig: Befehlsbyte 0x80|reg (0xa0|reg = Auto-Increment). ID (0x92) = 0x9b.
- iOS-Einschaltfolge: 0x8C=(cfg|0x40)&0xF0, 0x8C=cfg|0x40, 0x81=ATIME, 0x8F=Gain, 0x80|=0x13, 0x81, 0x8C.
- iOS liest Daten aus 0x94/0x95 (CH0) und 0x96/0x97 (CH1).
- Ergebnis: ENABLE=0x13, STATUS=0x31 (gültig), **Daten bleiben 0** – auch bei Gain 3, Licht/abgedeckt. Offen.

## Taptic / AD81006
- POR-Status Reg 0x14 Bit 4 = 1 (ok), ID Reg 0x01 = 0xcd.
- iOS `enableGated`: 00=02 05=0e 06=01 07=03 08=09 09=09 0a=32 0b=01 0c=09 0d=64 a0=b2 [a1=01] a4=0c a0=00 00=00.
- Die Wellenform kommt per I2S vom AOP (AppleSPUHapticsAudioDriver, `aop-mca`) – gleiche Takt-Baustelle
  wie Audio (siehe AUDIO-ANALYSE.md). Ohne I2S-Takt kein Vibrieren; nicht ohne Not einschalten.

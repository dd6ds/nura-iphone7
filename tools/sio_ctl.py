#!/usr/bin/env python3
"""sio_ctl.py – EXPERIMENT: mit der laufenden SIO (nach tools/sio_boot.py) sprechen (root, iPhone 7).
Nachbau der AP-Seite aus AppleSmartIO (iOS-Kext com.apple.driver.AppleT8010SmartIO):
  Nachricht 64 Bit: Byte 0 = Endpunkt, 1 = Tag, 2 = Opcode, 3 = Parameter, Bit 63:32 = Daten.
  setParam = Opcode 3 (Parameter = Kennung, Daten = Wert), Antwort Opcode 0x65 = ACK.
  Control-Endpunkt 0, Parameter: 0x0f/0x10 Panic-Puffer (Seite/Größe 0x4000), 0x1a/0x1b Coredump (0x2000),
  0x01/0x02 Segmentspeicher (Seite, 0xaaa Einträge à 12 Byte), 0x0b/0x0c Antwortspeicher (Seite, 0x1040).
Die Puffer liegen im SIO-RAM-MB (0x8_4070_0000) ab 0x90000, Seitennummer = physische Adresse >> 12.
  sio_ctl.py init        Puffer anmelden (je setParam, Antworten ausgeben), Panic-Text anzeigen
  sio_ctl.py panic       nur den Panic-Puffer lesen
  sio_ctl.py config [KANAL [XFER TIMEOUT FIFO TRIGGER LIMIT CFG5 RAHMEN CFG6]]   Shim einrichten (Opcode 5)
  sio_ctl.py start [KANAL]   Sinus-Puffer per DMA übergeben (Opcode 6; LAENGE, AMPLITUDE, RICHTUNG, HANDLE)
  sio_ctl.py hoeren [SEK]    nur Nachrichten der SIO mitlesen
  sio_ctl.py ton [SEK]       Dauerton (FREQ, AMPLITUDE, KANAL): zwei Puffer im Wechsel, Fertigmeldung Opcode 0x68
  sio_ctl.py send HEX    eine Rohnachricht senden und Antworten 1 s lang ausgeben"""
import ctypes, mmap, os, sys, time

AKF, RAM = 0x20ae00000, 0x840700000
SEG, ANT, PANIC, CORE = 0x90000, 0xa0000, 0xb4000, 0xb8000     # Versätze im SIO-RAM-MB
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
am = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
ava = ctypes.addressof(ctypes.c_char.from_buffer(am))
rm = mmap.mmap(fd, 0x100000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=RAM)
rva = ctypes.addressof(ctypes.c_char.from_buffer(rm))
r32 = lambda o: ctypes.c_uint32.from_address(ava + o).value


def zeige(m):
    ep, tag, op, par, dat = m & 0xff, m >> 8 & 0xff, m >> 16 & 0xff, m >> 24 & 0xff, m >> 32
    name = {0x65: "ACK", 0x6d: "bereit", 0x6a: "PANIC"}.get(op, "")
    return f"{m:#018x}  EP {ep} TAG {tag} OP {op:#x} {name} PARAM {par:#x} DATA {dat:#x}"


def senden(m):
    for _ in range(1000):
        st = r32(0x4008)
        if st & 0xc0000:
            sys.exit(f"Eingang-Fehler {st:#x}")
        if not st & (1 << 16):
            break
        time.sleep(0.001)
    ctypes.c_uint64.from_address(ava + 0x4010).value = m
    print("  ->", zeige(m))


def holen(dauer=1.0):
    raus, t0 = [], time.time()
    while time.time() - t0 < dauer:
        st = r32(0x4020)
        if st & 0xc0000:
            sys.exit(f"Ausgang-Fehler {st:#x}")
        if st & (1 << 17):                         # leer -> NICHT lesen (sonst Fehlerbits/Panic)
            time.sleep(0.002); continue
        m = ctypes.c_uint64.from_address(ava + 0x4038).value
        print("  <-", zeige(m)); raus.append(m)
        if (m >> 16 & 0xff) in (0x65, 0x6a):
            break
    return raus


def nachricht(ep, tag, op, par, dat):
    return ep | tag << 8 | op << 16 | par << 24 | (dat & 0xffffffff) << 32


def set_param(kennung, wert, tag=1):
    senden(nachricht(0, tag, 3, kennung, wert))
    return holen()


def nullen(off, n):
    for i in range(0, n, 4):
        ctypes.c_uint32.from_address(rva + off + i).value = 0


def panic_text():
    b = bytes(ctypes.c_uint8.from_address(rva + PANIC + i).value for i in range(0x400))
    t = b.split(b"\0")[0].decode(errors="replace")
    print("Panic-Puffer:", repr(t) if t else "(leer)")


cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
print(f"SIO: CPU {r32(0x44):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")
if cmd == "init":
    for off, n in ((SEG, 0x8000), (ANT, 0x10400), (PANIC, 0x4000), (CORE, 0x2000)):
        nullen(off, n)
    for k, v in ((0x0f, (RAM + PANIC) >> 12), (0x10, 0x4000), (0x1a, (RAM + CORE) >> 12), (0x1b, 0x2000),
                 (0x01, (RAM + SEG) >> 12), (0x02, 0xaaa), (0x0b, (RAM + ANT) >> 12), (0x0c, 0x1040)):
        print(f"setParam {k:#x} = {v:#x}")
        if not set_param(k, v):
            print("  (keine Antwort)")
    panic_text()
elif cmd == "panic":
    panic_text()
elif cmd == "config":
    # AppleSmartIODMA::_configureDMA (0x…65b1370): Puffer-Handle im Segmentspeicher (Eintrag = 12 Byte),
    # Struktur: +0 XFER, +4 TIMEOUT, +8 FIFO, +0xc TRIGGER, +0x10 LIMIT, +0x14 cfg[5], +0x18 Rahmengröße,
    # +0x1c cfg[6], +0x38 = 0; Nachricht EP = Kanal, OP 5, DATA = Handle; Antwort ACK (0x65).
    # Werte aus der ADT dma-channels (mca1: 0x2a, 0x21, 0, 0xcc, 0xac, 0, 0, 0).
    kanal = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x2a
    xfer, tout, fifo, trig, limit, c5, rahmen, c6 = (int(x, 0) for x in (sys.argv[3:11] if len(sys.argv) > 10
        else ("0x21", "0", "0xcc", "0xac", "4", "0", "0", "0")))
    handle = int(os.environ.get("HANDLE", "0"), 0)
    nullen(SEG + 12 * handle, 7 * 12)
    for o, v in ((0, xfer), (4, tout), (8, fifo), (0xc, trig), (0x10, limit), (0x14, c5), (0x18, rahmen),
                 (0x1c, c6)):
        ctypes.c_uint32.from_address(rva + SEG + 12 * handle + o).value = v
    senden(nachricht(kanal, 1, 5, 0, handle)); holen(); panic_text()
elif cmd == "start":
    # AppleSmartIODMA::_startDMACommand (0x…65b0b..): Puffer-Handle H im Segmentspeicher; Kopf (6 Einträge):
    # +0x38 = Richtungs-Flag, +0x3c = Anzahl Segmente; Segmente ab Eintrag H+6, je {u64 Adresse, u32 Länge}.
    # Nachricht EP = Kanal, OP 6, DATA = H. Testdaten: Sinus 1 kHz, 48 kHz, 16 Bit Stereo, an RAM+0xc0000.
    import math
    kanal = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x2a
    laenge = int(os.environ.get("LAENGE", "0x10000"), 0)
    richtung = int(os.environ.get("RICHTUNG", "0"), 0)
    handle = int(os.environ.get("HANDLE", "16"), 0)
    PUF = 0xc0000
    amp = int(os.environ.get("AMPLITUDE", "3000"), 0)
    for i in range(laenge // 4):
        s = int(amp * math.sin(2 * math.pi * 1000 * i / 48000)) & 0xffff
        ctypes.c_uint32.from_address(rva + PUF + 4 * i).value = s | s << 16
    nullen(SEG + 12 * handle, 7 * 12)
    kopf = SEG + 12 * handle
    ctypes.c_uint32.from_address(rva + kopf + 0x38).value = richtung
    ctypes.c_uint32.from_address(rva + kopf + 0x3c).value = 1
    seg = SEG + 12 * (handle + 6)
    ctypes.c_uint64.from_address(rva + seg).value = RAM + PUF
    ctypes.c_uint32.from_address(rva + seg + 8).value = laenge
    senden(nachricht(kanal, 2, 6, 0, handle)); holen(2.0); holen(3.0); panic_text()
elif cmd == "ton":
    # Dauerton: Sinus-Puffer (ganze Perioden, 64-Byte-Vielfaches) einmal schreiben, zwei Handles (Tag 2/3)
    # abwechselnd in Umlauf halten; jede Fertigmeldung (Opcode 0x68, Daten = Länge) gibt ihren Puffer neu auf.
    import math
    dauer = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    kanal = int(os.environ.get("KANAL", "0x2a"), 0)
    freq = int(os.environ.get("FREQ", "1000"), 0)
    amp = int(os.environ.get("AMPLITUDE", "3000"), 0)
    # Ein 32-Bit-Wort pro Slot (gemessen: 8 Byte je Rahmen bei 2 TX-Slots); Probe in beiden Hälften.
    slots = int(os.environ.get("SLOTS", "2"), 0)          # Wörter je Rahmen = Bits in der MCA-TX-Slotmaske
    rb = 4 * slots
    perioden = max(1, 0x10000 // (48000 // freq * rb))
    laenge = perioden * (48000 // freq) * rb // 64 * 64
    PUF = 0xc0000
    for i in range(laenge // rb):
        s = int(amp * math.sin(2 * math.pi * freq * i / 48000)) & 0xffff
        for k in range(slots):
            ctypes.c_uint32.from_address(rva + PUF + rb * i + 4 * k).value = s | s << 16
    handles = {2: 16, 3: 32}
    for tag, h in handles.items():
        nullen(SEG + 12 * h, 7 * 12)
        ctypes.c_uint32.from_address(rva + SEG + 12 * h + 0x3c).value = 1
        ctypes.c_uint64.from_address(rva + SEG + 12 * (h + 6)).value = RAM + PUF
        ctypes.c_uint32.from_address(rva + SEG + 12 * (h + 6) + 8).value = laenge
        senden(nachricht(kanal, tag, 6, 0, h))
    fertig, t0, zeiten = 0, time.time(), []
    while time.time() - t0 < dauer:
        st = r32(0x4020)
        if st & 0xc0000:
            sys.exit(f"Ausgang-Fehler {st:#x}")
        if st & (1 << 17):
            time.sleep(0.002); continue
        m = ctypes.c_uint64.from_address(ava + 0x4038).value
        op, tag = m >> 16 & 0xff, m >> 8 & 0xff
        if op == 0x68 and tag in handles and time.time() - t0 < dauer - 0.5:
            fertig += 1
            zeiten.append(time.time())
            senden(nachricht(kanal, tag, 6, 0, handles[tag]))
        elif op not in (0x65, 0x68):
            print("  <-", zeige(m))
            if op == 0x6a: panic_text(); break
    print(f"{fertig} Puffer à {laenge:#x} Byte fertig in {time.time() - t0:.1f} s "
          f"(erwartet {dauer * 48000 * rb / laenge:.0f})")
    stetig = [z for z in zeiten if z - t0 > 1.0]           # Vorlauf (FIFO-/Pufferfüllung) auslassen
    if len(stetig) > 2:
        print(f"Rahmenrate im Dauerbetrieb: {(len(stetig) - 1) * laenge / rb / (stetig[-1] - stetig[0]):.0f} Hz")
elif cmd == "hoeren":
    holen(float(sys.argv[2]) if len(sys.argv) > 2 else 5)
elif cmd == "send":
    senden(int(sys.argv[2], 16)); holen()

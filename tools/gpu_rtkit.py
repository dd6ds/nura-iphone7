#!/usr/bin/env python3
"""gpu_rtkit.py [sekunden] [--start] – EXPERIMENT: RTKit-Handshake mit dem laufenden GPU-Coprozessor (root).
Auch für den AOP: AKF=0x210800000 (HELLO_ACK=12, wenn aop_fw_boot.py das HELLO schon abgeholt hat).
--start: nach der Endpunkt-Karte alle Endpunkte per STARTEP starten (Flag per STARTFLAG, Standard 2).
--puffer: Puffer-Anforderungen der Endpunkte aus dem reservierten RAM (IOP 0x90000..0xfffff) bedienen.
Vorher: gpu_fw_boot.py <fw> 0 --laufen --neu  (startet die Firmware, lässt ihr HELLO im Postfach).
Nachrichtenformat dieser Generation (aus dem ersten HELLO 0x00100000000c000c abgeleitet):
  Bit 63:56 = Endpunkt, Verwaltung (Endpunkt 0): Bit 55:52 = Typ, Rest = Nutzdaten.
Verwaltung nach Asahi rtkit.c: HELLO 1 (min/max-Version Bit 15:0/31:16) -> HELLO_ACK 2;
EPMAP 8 (Basis Bit 34:32, Bitmap 31:0, LAST Bit 51) -> Antwort 8 mit Basis + LAST oder MORE (Bit 0).
Ohne Optionen startet es keine Endpunkte und vergibt keinen Speicher."""
import ctypes, mmap, os, sys, time

AKF = int(os.environ.get("AKF", "0x201D20000"), 0)   # AOP: AKF=0x210800000
dauer = float(sys.argv[1]) if len(sys.argv) > 1 else 5
NAMEN = {0: "Verwaltung", 1: "crashlog", 2: "syslog", 3: "debug", 4: "ioreport", 8: "oslog"}
if os.environ.get("AKF", "").lower() == "0x210800000":      # AOP t8010 (Firmware-Tabelle 0x10a28c0)
    NAMEN.update(dict(zip(range(32, 51), "misc accel gyro compass pressure aggregate1 mca cma devmotion borealis profile prox aop-audio mux aop-button turtle mesa devmotion6 devmotion10".split())))
TYPEN = {1: "HELLO", 2: "HELLO_ACK", 5: "STARTEP", 6: "IOP_PWR", 7: "IOP_PWR_ACK", 8: "EPMAP", 0xb: "AP_PWR"}

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
va = ctypes.addressof(ctypes.c_char.from_buffer(m))
r32 = lambda o: ctypes.c_uint32.from_address(va + o).value


# LOGDATEI=<pfad>: zusätzlich zeilenweise mit fsync in eine Datei schreiben (überlebt ein Einfrieren,
# wenn die Datei auf dem internen Speicher liegt, nicht in /tmp)
_logf = open(os.environ["LOGDATEI"], "a") if "LOGDATEI" in os.environ else None


def log(*a):
    print(*a, flush=True)
    if _logf:
        print(*a, file=_logf, flush=True)
        os.fsync(_logf.fileno())


def senden(msg):
    for _ in range(1000):
        if not r32(0x4008) & (1 << 16):            # Eingang nicht voll
            break
        time.sleep(0.001)
    else:
        raise SystemExit(f"Eingang bleibt voll ({r32(0x4008):#x})")
    ctypes.c_uint64.from_address(va + 0x4010).value = msg
    log(f"  -> {msg:#018x}")


def holen():
    out = r32(0x4020)
    if out & 0xc0000:
        raise SystemExit(f"Ausgang-Fehler {out:#x}")
    if out & (1 << 17):                             # leer
        return None
    return ctypes.c_uint64.from_address(va + 0x4038).value


def verwaltung(typ, daten):
    senden((0 << 56) | (typ << 52) | daten)


if not r32(0x44) & 0x10:
    sys.exit("Coprozessor läuft nicht – erst gpu_fw_boot.py <fw> 0 --laufen --neu (AOP: aop_fw_boot.py)")
endpunkte = []
# nächste freie IOP-Adresse für Puffer; beim AOP ab 0x100000 – darunter liegt die Firmware (0x90000 überschreibt
# sie: syslog bleibt leer, die SPU-Dienste melden sich nie)
_aop = os.environ.get("AKF", "").lower() == "0x210800000"
puffer_frei = int(os.environ.get("PUFFER_AB", "0x100000" if _aop else "0x90000"), 0)
puffer_ende = int(os.environ.get("PUFFER_BIS", "0x100000"), 0)
# RAM_BASIS=<phys>: physische Adresse von IOP 0 (AOP: 0x840400000) -> Puffer lesbar (z. B. syslog-Text)
ram_basis = int(os.environ["RAM_BASIS"], 0) if "RAM_BASIS" in os.environ else None
ram = None
if ram_basis is not None:
    ram_m = mmap.mmap(fd, puffer_ende, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=ram_basis)
    ram_va = ctypes.addressof(ctypes.c_char.from_buffer(ram_m))


def ram_lesen(adr, laenge):
    # Gerätespeicher -> ausgerichtete 32-Bit-Lesezugriffe
    a0 = adr & ~3
    n = (adr + laenge - a0 + 3) // 4
    # Wort für Wort (memcpy über bytes(array) kann auf Gerätespeicher SIGBUS auslösen)
    b = b"".join(ctypes.c_uint32.from_address(ram_va + a0 + 4 * i).value.to_bytes(4, "little") for i in range(n))
    return b[adr - a0:adr - a0 + laenge]


puffer_von = {}                                      # Endpunkt -> IOP-Adresse des vergebenen Puffers
# SPU_PUFFER=32:0x258000,38:0x1c8000:0x50000:0x54000: Puffer schon laufender SPU-Endpunkte übernehmen,
# optional mit den Ring-Versätzen aus 0x8a (AP->IOP) / 0x8b (IOP->AP): Größe = Bit 31:16 << 6, Versatz = Bit 47:32 << 6
ring_ein, ring_aus = {}, {}
for _p in os.environ.get("SPU_PUFFER", "").split(","):
    if _p:
        _e, _a, *_r = _p.split(":")
        puffer_von[int(_e, 0)] = int(_a, 0)
        if _r:
            ring_ein[int(_e, 0)], ring_aus[int(_e, 0)] = int(_r[0], 0), int(_r[1], 0)


def ram_schreiben(adr, daten):
    # nur 32-Bit-ausgerichtet (Gerätespeicher)
    assert adr % 4 == 0 and len(daten) % 4 == 0
    w = (ctypes.c_uint32 * (len(daten) // 4)).from_address(ram_va + adr)
    for i in range(len(daten) // 4):
        w[i] = int.from_bytes(daten[4 * i:4 * i + 4], "little")


# SPU-Ringe (Firmware 0x101a5a0 schreibt, 0x101a2e8 liest; Format 0x70000): Kopf u32 Größe, u32 0x00070006,
# Leseindex +0x40, Schreibindex +0x80, Daten ab +0xc0. Eintrag: 'AOP ', u32 Nutzlänge, u32 Dienst, u32 0,
# dann Nutzdaten; auf 0x40 aufgerundet. Ring AP->IOP = Teilbereich 0x8a (+0), IOP->AP = 0x8b (+RING_AUS).
RING_AUS = int(os.environ.get("RING_AUS", "0x4000"), 0)


def ring_lesen(basis):
    groesse = int.from_bytes(ram_lesen(basis, 4), "little")
    ri = int.from_bytes(ram_lesen(basis + 0x40, 4), "little")
    wi = int.from_bytes(ram_lesen(basis + 0x80, 4), "little")
    if not groesse or groesse > 0x100000:
        return []
    raus = []
    for _ in range(64):
        if ri == wi:
            break
        if ri + 0x10 > groesse:
            ri = 0
        kopf = ram_lesen(basis + 0xc0 + ri, 0x10)
        laenge = int.from_bytes(kopf[4:8], "little")
        gesamt = (laenge + 0x10 + 0x3f) & ~0x3f
        if ri + gesamt > groesse:
            ri = 0
            kopf = ram_lesen(basis + 0xc0, 0x10)
            laenge = int.from_bytes(kopf[4:8], "little")
            gesamt = (laenge + 0x10 + 0x3f) & ~0x3f
        raus.append(ram_lesen(basis + 0xc0 + ri, 0x10 + min(laenge, 0x400)))
        ri = (ri + gesamt) % groesse
    ram_schreiben(basis + 0x40, ri.to_bytes(4, "little"))
    return raus


def ring_schreiben(basis, dienst, nutz):
    groesse = int.from_bytes(ram_lesen(basis, 4), "little")
    wi = int.from_bytes(ram_lesen(basis + 0x80, 4), "little")
    nutz = nutz + b"\0" * (-len(nutz) % 4)
    eintrag = b"AOP " + len(nutz).to_bytes(4, "little") + dienst.to_bytes(4, "little") + bytes(4) + nutz
    gesamt = (len(eintrag) + 0x3f) & ~0x3f
    if wi + gesamt > groesse:
        wi = 0
    ram_schreiben(basis + 0xc0 + wi, eintrag + bytes(gesamt - len(eintrag)))
    ram_schreiben(basis + 0x80, ((wi + gesamt) % groesse).to_bytes(4, "little"))


# SPU_SENDEN=<Sek>:<ep>:<Dienst>:<Typ>:<hex-Daten>[;…]: SPU-Paket in den AP->IOP-Ring legen, Klingel 0xa2.
# Paket wie iOS AppleSPU (Kernel 0xfffffff005c46760): 16 Byte Kopf (02, Folgenr.), dann u32 Datenlänge+4,
# u8 2, u8 0x10, u16 Typ, u16 Folgenr., …, u32 0xe4 (+0x14), u32 Antwortlänge (+0x18), Daten ab +0x1c.
# Typ 4 = setProperty: Daten = u32 Eigenschaft + Wert (mckE = 0xd0, magE = 0xd1, je u32 1/0).
spu_plan = []
for _s in os.environ.get("SPU_SENDEN", "").split(";"):
    if _s:
        _t, _e, _d, _ty, _h, *_a = _s.split(":")       # optional 6. Feld: Antwortlänge (getProperty, Typ 0xa)
        spu_plan.append((float(_t), int(_e, 0), int(_d, 0), int(_ty, 0), bytes.fromhex(_h),
                         int(_a[0], 0) if _a else 0))
spu_folge = 0x100


def spu_paket(typ, daten, antwort=0):
    global spu_folge
    spu_folge += 1
    k = bytes([2]) + spu_folge.to_bytes(2, "little") + bytes(13)
    p = ((len(daten) + 4).to_bytes(4, "little") + bytes([2, 0x10]) + typ.to_bytes(2, "little")
         + spu_folge.to_bytes(2, "little") + bytes(10) + (0xe4).to_bytes(4, "little")
         + antwort.to_bytes(4, "little") + daten)
    return k + p


syslog_n, syslog_groesse = 0, 0
# SPU_EP=48,37: nur diesen SPU-Endpunkten antworten (Standard: allen)
spu_eps = {int(x, 0) for x in os.environ["SPU_EP"].split(",")} if "SPU_EP" in os.environ else set(range(32, 64))
# SYSLOG=<IOP-Adresse>,<Anzahl>,<Textlänge>: syslog-Zustand eines schon laufenden Coprozessors übernehmen
if "SYSLOG" in os.environ:
    a, n, g = (int(x, 0) for x in os.environ["SYSLOG"].split(","))
    puffer_von[2], syslog_n, syslog_groesse = a, n, g
t0 = time.time()
# Nach dem Handshake (0,5 s still) Strom-Anweisungen senden; IOP_PWR_ACK kommt erst nach dem crashlog-Puffer:
# IOP_PWR_STATE (6) = 0x20 (an), dann AP_PWR_STATE (0xb) = 0x20.
nachschub = [(6, 0x20), (0xb, 0x20)]
ack_zeit, letzte_nachricht = None, time.time()
# HELLO_ACK=<version>: das HELLO wurde schon von einem anderen Skript abgeholt -> sofort bestätigen
if "HELLO_ACK" in os.environ:
    v = int(os.environ["HELLO_ACK"], 0)
    log(f"  HELLO schon abgeholt – sende HELLO_ACK Version {v}")
    verwaltung(2, (v << 16) | v)
    ack_zeit = time.time()
while time.time() - t0 < dauer:
    msg = holen()
    if msg is None:
        if ack_zeit and nachschub and time.time() - letzte_nachricht > 0.5:
            typ, wert = nachschub.pop(0)
            log(f"  (0,5 s still) sende {TYPEN[typ]} = {wert:#x}")
            verwaltung(typ, wert)
            letzte_nachricht = time.time()
        if spu_plan and time.time() - t0 >= spu_plan[0][0]:
            _t, _e, _d, _ty, _h, _a = spu_plan.pop(0)
            pk = spu_paket(_ty, _h, _a)
            log(f"  SPU senden ep {_e} Dienst {_d}: Typ {_ty:#x} Daten {_h.hex()} -> {pk.hex()}")
            ring_schreiben(puffer_von[_e] + ring_ein.get(_e, 0), _d, pk)
            senden((_e << 56) | (0xa2 << 48))
            # Die Antwort kommt teils ohne Klingel 0x85 -> den IOP->AP-Ring nach 0,5 s selbst lesen
            time.sleep(0.5)
            for e in ring_lesen(puffer_von[_e] + ring_aus.get(_e, RING_AUS)):
                log(f"  SPU ep {_e} Ring: Dienst {int.from_bytes(e[8:12], 'little'):#x}: {e[0x10:0x80].hex()}")
        time.sleep(0.002)
        continue
    letzte_nachricht = time.time()
    ep, typ = msg >> 56, (msg >> 52) & 0xf
    log(f"{time.time() - t0:6.3f}s <- {msg:#018x}  ep {ep} ({NAMEN.get(ep, '?')})"
        + (f", Typ {typ} ({TYPEN.get(typ, '?')})" if ep == 0 else ""))
    if ep != 0:
        # Puffer-Anforderung (RTKit BUFFER_REQUEST): Typ Bit 55:52 = 1, Größe in Seiten Bit 51:44,
        # Adresse Bit 41:0 = 0 -> Speicher aus dem freien Teil des reservierten RAM vergeben
        # (IOP-Adresse 0x90000.., Firmware selbst braucht 0..0x8f000) und mit Adresse antworten.
        etyp, seiten, adr = (msg >> 52) & 0xf, (msg >> 44) & 0xff, msg & ((1 << 42) - 1)
        if etyp == 1 and adr == 0 and "--puffer" in sys.argv:
            groesse = seiten * 0x4000                      # vorsichtshalber 16-KB-Seiten
            if puffer_frei + groesse > puffer_ende:
                log(f"  Puffer-Anforderung ({seiten} Seiten) passt nicht mehr in den reservierten RAM")
                continue
            log(f"  Puffer-Anforderung: {seiten} Seiten -> IOP-Adresse {puffer_frei:#x} ({groesse:#x} Byte)")
            senden((ep << 56) | (1 << 52) | (seiten << 44) | puffer_frei)
            puffer_von[ep] = puffer_frei
            puffer_frei += groesse
        elif ep == 2 and etyp == 8:
            # syslog-Init: Bit 7:0 Anzahl Einträge, Bit 31:24 Textlänge je Eintrag
            syslog_n, syslog_groesse = msg & 0xff, (msg >> 24) & 0xff
            log(f"  syslog: {syslog_n} Einträge à {syslog_groesse} Byte Text")
        elif ep == 2 and etyp == 5:
            # syslog-Eintrag: Index Bit 7:0. Eintrag = 0x20 Byte Kopf (ab +8 Kontextname) + Text.
            # Jeden Eintrag unverändert zurückschicken, sonst bleibt der Ring (und die Firmware) stehen.
            if ram_basis is not None and 2 in puffer_von and syslog_groesse:
                i = msg & 0xff
                e = ram_lesen(puffer_von[2] + i * (0x20 + syslog_groesse), 0x20 + syslog_groesse)
                ctx = e[8:0x20].split(b"\0")[0].decode(errors="replace")
                text = e[0x20:].split(b"\0")[0].decode(errors="replace").rstrip()
                log(f"  syslog [{ctx}] {text}")
            senden(msg)
        elif ep >= 32 and "--spu" in sys.argv and ep in spu_eps:
            # AOP-SPU-Endpunkte (MailboxSharedMemoryEndpoint, Firmware 0x101c66c): Typ = Bit 55:48.
            # IOP 0x80 -> AP 0xa0; IOP 0x89 (Puffer-Wunsch, Größe Bit 31:10) -> AP 0xa1 mit Adresse;
            # IOP 0x8d/0x8e/… beschreiben den gemeinsamen Speicher; IOP 0x88 -> AP 0xa5 (fertig).
            styp, nutz = (msg >> 48) & 0xff, msg & ((1 << 48) - 1)
            log(f"  SPU ep {ep}: Typ {styp:#x}, Daten {nutz:#x}")
            if styp == 0x80:
                senden((ep << 56) | (0xa0 << 48) | nutz)
            elif styp == 0x89:
                groesse = ((nutz & 0xffffffff) >> 10) or 0x1000
                groesse = (groesse + 0x3fff) & ~0x3fff
                if puffer_frei + groesse <= puffer_ende:
                    log(f"  SPU ep {ep}: Puffer {groesse:#x} Byte -> IOP-Adresse {puffer_frei:#x}")
                    senden((ep << 56) | (0xa1 << 48) | puffer_frei)
                    puffer_von[ep] = puffer_frei
                    puffer_frei += groesse
            elif styp == 0x88:
                senden((ep << 56) | (0xa5 << 48))
            elif styp == 0x85 and ep in puffer_von and ram_basis is not None:
                # Klingel: Einträge im IOP->AP-Ring auslesen (und Leseindex nachziehen)
                for e in ring_lesen(puffer_von[ep] + ring_aus.get(ep, RING_AUS)):
                    d = int.from_bytes(e[8:12], "little")
                    p = e[0x20:]
                    typ = int.from_bytes(p[6:8], "little") if len(p) >= 8 else -1
                    log(f"  SPU ep {ep} Ring: Dienst {d:#x} Pakettyp {typ:#x}: {e[0x10:0x80].hex()}")
        elif ep == 4 and etyp in (8, 0xc):
            # ioreport: Typ 8/0xc werden (wie bei Asahi rtkit.c) unverändert zurückgeschickt
            senden(msg)
        continue
    if typ == 1:                                     # HELLO
        vmin, vmax = msg & 0xffff, (msg >> 16) & 0xffff
        v = vmax
        log(f"  HELLO: Version {vmin}..{vmax} -> antworte mit {v}")
        # ACK-Format per Umgebung: beide (Standard, wie Asahi: min | max << 16) oder nur min
        verwaltung(2, v if os.environ.get("ACK") == "min" else (v << 16) | v)
        ack_zeit = time.time()
    elif typ == 8:                                   # EPMAP
        basis, bitmap, letzte = (msg >> 32) & 7, msg & 0xffffffff, bool(msg >> 51 & 1)
        neu = [basis * 32 + b for b in range(32) if bitmap >> b & 1]
        endpunkte += neu
        log(f"  EPMAP Basis {basis}: Endpunkte {neu}{' (letzte)' if letzte else ''}")
        # Antwort: Basis + LAST/MORE. Diese RTKit-Generation (AOP) schaltet nur die Endpunkte frei, deren Bit
        # die Antwort zurückmeldet (Firmware 0x10630f6) – daher die Bitmap mitschicken (EPMAP_ECHO=0: ohne).
        echo = bitmap & ~1 if os.environ.get("EPMAP_ECHO", "1") == "1" else 0
        # EP_ERLAUBT=1,2,4,48: nur diese Endpunkte freischalten (Rest bleibt aus)
        if "EP_ERLAUBT" in os.environ:
            erlaubt = {int(x, 0) for x in os.environ["EP_ERLAUBT"].split(",")}
            echo &= sum(1 << (e - basis * 32) for e in erlaubt if basis * 32 <= e < basis * 32 + 32)
            log(f"  freigeschaltet: {[basis * 32 + b for b in range(32) if echo >> b & 1]}")
        verwaltung(8, (basis << 32) | echo | ((1 << 51) if letzte else 1))
        if letzte:
            log("Endpunkte der Firmware: " + ", ".join(f"{e} ({NAMEN.get(e, '?')})" for e in endpunkte))
            if "--start" in sys.argv:
                # STARTEP (5): Endpunkt in Bit 47:32, unteres Wort 1 oder 2 (Firmware-Handler IOP 0x2a29c)
                flag = int(os.environ.get("STARTFLAG", "2"))
                for e in endpunkte:
                    if e != 0 and ("EP_ERLAUBT" not in os.environ or e in erlaubt):
                        log(f"  STARTEP Endpunkt {e} (Flag {flag})")
                        verwaltung(5, (e << 32) | flag)
log(f"Ende nach {dauer:.0f}s; IDLE {r32(0x4040):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")

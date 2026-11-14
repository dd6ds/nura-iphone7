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
TYPEN = {1: "HELLO", 2: "HELLO_ACK", 5: "STARTEP", 6: "IOP_PWR", 7: "IOP_PWR_ACK", 8: "EPMAP", 0xb: "AP_PWR"}

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
va = ctypes.addressof(ctypes.c_char.from_buffer(m))
r32 = lambda o: ctypes.c_uint32.from_address(va + o).value


def log(*a):
    print(*a, flush=True)


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
puffer_frei = int(os.environ.get("PUFFER_AB", "0x90000"), 0)   # nächste freie IOP-Adresse für Puffer
puffer_ende = int(os.environ.get("PUFFER_BIS", "0x100000"), 0)
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
            puffer_frei += groesse
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
        verwaltung(8, (basis << 32) | ((1 << 51) if letzte else 1))
        if letzte:
            log("Endpunkte der Firmware: " + ", ".join(f"{e} ({NAMEN.get(e, '?')})" for e in endpunkte))
            if "--start" in sys.argv:
                # STARTEP (5): Endpunkt in Bit 47:32, unteres Wort 1 oder 2 (Firmware-Handler IOP 0x2a29c)
                flag = int(os.environ.get("STARTFLAG", "2"))
                for e in endpunkte:
                    if e != 0:
                        log(f"  STARTEP Endpunkt {e} (Flag {flag})")
                        verwaltung(5, (e << 32) | flag)
log(f"Ende nach {dauer:.0f}s; IDLE {r32(0x4040):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")

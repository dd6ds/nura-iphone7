#!/usr/bin/env python3
"""osbin.py <datei> [ausgabe-ordner] – Apple OSSerializeBinary (Signatur 0x000000d3) lesen und als Baum
ausgeben; Daten-Objekte (z. B. Firmware-Segmente) optional als Dateien ablegen. Format (XNU OSSerializeBinary):
32-Bit-Wörter, Bit 31 = letztes Element der Ebene, Bit 30..24 = Typ, Bit 23..0 = Länge/Anzahl.
Typen: 0x01 Dict, 0x02 Array, 0x03 Set, 0x04 Number (Länge in Bit, 64-Bit-Wert folgt), 0x08 Symbol,
0x09 String, 0x0a Data, 0x0b Boolean (Wert in Länge), 0x0c Objekt-Referenz."""
import os, struct, sys

d = open(sys.argv[1], "rb").read()
aus = sys.argv[2] if len(sys.argv) > 2 else None
assert struct.unpack_from("<I", d, 0)[0] == 0xd3, "keine OSSerializeBinary-Signatur"
pos, objs = 4, []


def wort():
    global pos
    v = struct.unpack_from("<I", d, pos)[0]
    pos += 4
    return v


def lesen(tiefe, pfad):
    global pos
    k = wort()
    ende, typ, ln = k >> 31, (k >> 24) & 0x7f, k & 0xffffff
    if typ in (1, 2, 3):
        o = {} if typ == 1 else []
        objs.append(o)
        for i in range(ln):
            if typ == 1:
                key, _ = lesen(tiefe + 1, pfad)
                val, _ = lesen(tiefe + 1, f"{pfad}/{key}")
                o[key] = val
            else:
                val, _ = lesen(tiefe + 1, f"{pfad}[{i}]")
                o.append(val)
        return o, ende
    if typ == 4:
        v = struct.unpack_from("<Q", d, pos)[0]
        pos += 8
    elif typ in (8, 9):
        v = d[pos:pos + ln].rstrip(b"\0").decode("latin1")
        pos += (ln + 3) & ~3
    elif typ == 0xa:
        v = d[pos:pos + ln]
        if aus:
            os.makedirs(aus, exist_ok=True)
            fn = os.path.join(aus, pfad.strip("/").replace("/", "_").replace("[", "_").replace("]", "") + ".bin")
            open(fn, "wb").write(v)
        v = f"<{ln} Byte @ Datei {pos:#x}>"
        pos += (ln + 3) & ~3
    elif typ == 0xb:
        v = bool(ln)
    elif typ == 0xc:
        v = f"<Ref {ln}>"
    else:
        raise SystemExit(f"unbekannter Typ {typ:#x} @ {pos - 4:#x}")
    objs.append(v)
    return v, ende


baum, _ = lesen(0, "")


def zeigen(o, e=0):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                print("  " * e + f"{k}:")
                zeigen(v, e + 1)
            else:
                print("  " * e + f"{k}: {hex(v) if isinstance(v, int) and not isinstance(v, bool) else v}")
    else:
        for i, v in enumerate(o):
            print("  " * e + f"[{i}]")
            zeigen(v, e + 1) if isinstance(v, (dict, list)) else print("  " * (e + 1) + str(v))


zeigen(baum)

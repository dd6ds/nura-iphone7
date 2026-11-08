#!/usr/bin/env python3
"""make_en.py – erzeugt englische Fassungen der Skripte (X.sh -> X.en.sh, X.py -> X.en.py).

Übersetzt wird zeilenweise über die Tabelle tools/i18n/en.json
({"deutsche Zeile ohne Einrückung": "englische Zeile"}). Einrückung bleibt erhalten,
Code ohne deutschen Text wird unverändert übernommen.

  tools/make_en.py            englische Fassungen erzeugen, fehlende Übersetzungen melden
  tools/make_en.py --missing  nur fehlende Zeilen als JSON-Vorlage ausgeben
"""
import json, os, re, stat, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(ROOT, "tools", "i18n", "en.json")
GERMAN = re.compile(r"[äöüÄÖÜß]|\b(der|die|das|und|nicht|ist|mit|für|wird|werden|kein|keine|nur|auf|bei|wenn|"
                    r"oder|auch|noch|eine?|einen|vom|zum|zur|bitte|aus|nach|über|Fehler|Datei|Gerät|"
                    r"bereits|fertig|gefunden|starten|warten|läuft|vorher|nachher|Standard|lesen|schreiben)\b")


def scripts():
    out = [os.path.join(ROOT, f) for f in ("build.sh", "boot.sh", "pongo_send.py")]
    t = os.path.join(ROOT, "tools")
    for f in sorted(os.listdir(t)):
        if re.search(r"\.(sh|py)$", f) and ".en." not in f and f != "make_en.py":
            out.append(os.path.join(t, f))
    return [p for p in out if os.path.isfile(p)]


def en_name(path):
    base, ext = os.path.splitext(path)
    return base + ".en" + ext


def main():
    table = json.load(open(TABLE, encoding="utf-8")) if os.path.exists(TABLE) else {}
    names = {os.path.basename(p): os.path.basename(en_name(p)) for p in scripts()}
    missing = {}
    for src in scripts():
        lines = open(src, encoding="utf-8").read().split("\n")
        res = []
        for ln in lines:
            key = ln.strip()
            if key in table:
                ln = ln[:len(ln) - len(ln.lstrip())] + table[key]
            elif GERMAN.search(ln):
                missing.setdefault(key, os.path.relpath(src, ROOT))
            # Aufrufe der anderen Skripte auf die englischen Fassungen umbiegen
            for de, en in names.items():
                ln = re.sub(r"(?<![\w.])" + re.escape(de) + r"(?![\w])", en, ln)
            res.append(ln)
        if "--missing" in sys.argv:
            continue
        dst = en_name(src)
        open(dst, "w", encoding="utf-8").write("\n".join(res))
        os.chmod(dst, os.stat(src).st_mode | stat.S_IRUSR)
    if "--missing" in sys.argv:
        json.dump({k: "" for k in missing}, sys.stdout, ensure_ascii=False, indent=1)
        return
    print(f"{len(scripts())} Skripte erzeugt, {len(missing)} Zeilen ohne Übersetzung")
    for k, f in list(missing.items())[:40]:
        print(f"  {f}: {k[:100]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""kc_kext.py <kernelcache.bin> <bundle-id> – Lade-/Dateiadresse eines Kexts im (alten, prelinked)
iOS-Kernelcache aus __PRELINK_INFO bestimmen und Segmente des Kernels zur Adressumrechnung ausgeben."""
import plistlib, re, struct, sys

kc = open(sys.argv[1], "rb").read()
if kc[:4] == b"\xca\xfe\xba\xbe":                     # Fat-Hülle: erste Architektur nehmen
    fo, fs = struct.unpack_from(">II", kc, 16)
    kc = kc[fo:fo + fs]
bid = sys.argv[2]
ncmds = struct.unpack_from("<I", kc, 16)[0]
off, segs = 32, []
for _ in range(ncmds):
    cmd, sz = struct.unpack_from("<II", kc, off)
    if cmd == 0x19:
        name = kc[off + 8:off + 24].rstrip(b"\0").decode()
        vm, vms, fo, fs = struct.unpack_from("<QQQQ", kc, off + 24)
        segs.append((name, vm, vms, fo, fs))
    off += sz
for s in segs:
    print("%-20s vm %#x +%#x  file %#x +%#x" % s)
info = next(s for s in segs if s[0] == "__PRELINK_INFO")
xml = kc[info[3]:info[3] + info[4]].split(b"\0")[0]
# IDREF-Verweise durch den referenzierten Wert ersetzen, Attribute entfernen
ids = {m.group(2): m.group(0) for m in re.finditer(rb'<(\w+) ID="(\d+)"[^>]*>[^<]*</\1>', xml)}
xml = re.sub(rb'<(\w+) IDREF="(\d+)"/>', lambda m: ids.get(m.group(2), b"<string/>"), xml)
xml = re.sub(rb' ID="\d+"', b"", xml)
xml = re.sub(rb'<integer size="\d+">', b"<integer>", xml)
xml = re.sub(rb"<integer>0x([0-9a-fA-F]+)</integer>", lambda m: b"<integer>%d</integer>" % int(m.group(1), 16), xml)
if not xml.lstrip().startswith(b"<?xml"):
    xml = b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0">' + xml + b"</plist>"
pl = plistlib.loads(xml)
for d in pl["_PrelinkInfoDictionary"]:
    if re.search(bid, d.get("CFBundleIdentifier", "")):
        la = d.get("_PrelinkExecutableLoadAddr"); sz = d.get("_PrelinkExecutableSize")
        print(d.get("CFBundleIdentifier"), "load %#x size %#x" % (la, sz))
        for s in segs:
            if s[1] <= la < s[1] + s[2]:
                print("  in", s[0], "file offset %#x" % (la - s[1] + s[3]))

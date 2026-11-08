#!/usr/bin/env python3
"""kc_match.py <kernelcache.bin> <muster> – Kexts finden, deren IOKitPersonalities (IONameMatch,
IOPropertyMatch, IOClass …) das Muster enthalten; gibt Bundle-ID, Ladeadresse und Treffer aus."""
import json, plistlib, re, struct, sys

kc = open(sys.argv[1], "rb").read()
if kc[:4] == b"\xca\xfe\xba\xbe":
    fo, fs = struct.unpack_from(">II", kc, 16)
    kc = kc[fo:fo + fs]
ncmds = struct.unpack_from("<I", kc, 16)[0]
off, segs = 32, []
for _ in range(ncmds):
    cmd, sz = struct.unpack_from("<II", kc, off)
    if cmd == 0x19:
        name = kc[off + 8:off + 24].rstrip(b"\0").decode()
        vm, vms, fo, fs = struct.unpack_from("<QQQQ", kc, off + 24)
        segs.append((name, vm, vms, fo, fs))
        if name == "__PRELINK_INFO":
            xml = kc[fo:fo + fs].split(b"\0")[0]
    off += sz
ids = {m.group(2): m.group(0) for m in re.finditer(rb'<(\w+) ID="(\d+)"[^>]*>[^<]*</\1>', xml)}
xml = re.sub(rb'<(\w+) IDREF="(\d+)"/>', lambda m: ids.get(m.group(2), b"<string/>"), xml)
xml = re.sub(rb' ID="\d+"', b"", xml)
xml = re.sub(rb'<integer size="\d+">', b"<integer>", xml)
xml = re.sub(rb"<integer>0x([0-9a-fA-F]+)</integer>", lambda m: b"<integer>%d</integer>" % int(m.group(1), 16), xml)
pl = plistlib.loads(b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0">' + xml + b"</plist>")
pat = re.compile(sys.argv[2], re.I)
for d in pl["_PrelinkInfoDictionary"]:
    per = d.get("IOKitPersonalities", {})
    s = json.dumps(per, default=str)
    if pat.search(s):
        la = d.get("_PrelinkExecutableLoadAddr", 0)
        fo = next((la - vm + f for n, vm, vms, f, fs in segs if vm <= la < vm + vms), None)
        print(d.get("CFBundleIdentifier"), f"load {la:#x} fileoff {fo:#x}" if fo else "")
        for k, v in per.items():
            if pat.search(json.dumps(v, default=str)):
                print("   ", k, {x: v.get(x) for x in ("IOClass", "IONameMatch", "IOProviderClass") if x in v})

#!/usr/bin/env python3
"""kc_personality.py <kernelcache.bin> <bundle-id> – IOKitPersonalities eines Kexts als JSON ausgeben."""
import json, plistlib, re, struct, sys

kc = open(sys.argv[1], "rb").read()
if kc[:4] == b"\xca\xfe\xba\xbe":
    fo, fs = struct.unpack_from(">II", kc, 16)
    kc = kc[fo:fo + fs]
ncmds = struct.unpack_from("<I", kc, 16)[0]
off = 32
for _ in range(ncmds):
    cmd, sz = struct.unpack_from("<II", kc, off)
    if cmd == 0x19 and kc[off + 8:off + 24].rstrip(b"\0") == b"__PRELINK_INFO":
        fo, fs = struct.unpack_from("<QQ", kc, off + 40)
        xml = kc[fo:fo + fs].split(b"\0")[0]
    off += sz
ids = {m.group(2): m.group(0) for m in re.finditer(rb'<(\w+) ID="(\d+)"[^>]*>[^<]*</\1>', xml)}
xml = re.sub(rb'<(\w+) IDREF="(\d+)"/>', lambda m: ids.get(m.group(2), b"<string/>"), xml)
xml = re.sub(rb' ID="\d+"', b"", xml)
xml = re.sub(rb'<integer size="\d+">', b"<integer>", xml)
xml = re.sub(rb"<integer>0x([0-9a-fA-F]+)</integer>", lambda m: b"<integer>%d</integer>" % int(m.group(1), 16), xml)
xml = b'<?xml version="1.0" encoding="UTF-8"?><plist version="1.0">' + xml + b"</plist>"
pl = plistlib.loads(xml)
for d in pl["_PrelinkInfoDictionary"]:
    if d.get("CFBundleIdentifier") == sys.argv[2]:
        def conv(o):
            if isinstance(o, bytes): return o.hex()
            if isinstance(o, dict): return {k: conv(v) for k, v in o.items()}
            if isinstance(o, list): return [conv(v) for v in o]
            return o
        print(json.dumps(conv(d.get("IOKitPersonalities", {})), indent=1))

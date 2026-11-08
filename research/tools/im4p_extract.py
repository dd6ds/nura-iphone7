#!/usr/bin/env python3
"""IM4P (ASN.1 DER) -> Rohdaten. Unterstützt unkomprimiert und LZSS ('complzss').
Aufruf: im4p_extract.py in.im4p out.bin"""
import sys, struct

def der(buf, pos):
    tag = buf[pos]; pos += 1
    ln = buf[pos]; pos += 1
    if ln & 0x80:
        n = ln & 0x7f
        ln = int.from_bytes(buf[pos:pos + n], "big"); pos += n
    return tag, pos, ln

def lzss(src, dst_len):
    N, F, THRESH = 4096, 18, 2
    text = bytearray(b" " * (N + F - 1)); r = N - F
    out = bytearray(); i = 0; flags = 0
    while i < len(src) and len(out) < dst_len:
        flags >>= 1
        if not flags & 0x100:
            flags = src[i] | 0xff00; i += 1
        if flags & 1:
            c = src[i]; i += 1; out.append(c); text[r] = c; r = (r + 1) & (N - 1)
        else:
            a, b = src[i], src[i + 1]; i += 2
            pos = a | ((b & 0xf0) << 4); ln = (b & 0x0f) + THRESH
            for k in range(ln + 1):
                c = text[(pos + k) & (N - 1)]; out.append(c); text[r] = c; r = (r + 1) & (N - 1)
    return bytes(out)

data = open(sys.argv[1], "rb").read()
tag, pos, ln = der(data, 0)                     # SEQUENCE
items = []
end = pos + ln
while pos < end:
    t, p, l = der(data, pos)
    items.append((t, data[p:p + l])); pos = p + l
kind = items[1][1].decode()
payload = [v for t, v in items if t == 0x04][-1]  # letzter OCTET STRING = Payload
print("IM4P-Typ:", kind, "Payload:", len(payload), "Bytes")
if payload[:8] == b"complzss":
    dlen = struct.unpack(">I", payload[12:16])[0]
    payload = lzss(payload[0x180:], dlen)
    print("LZSS entpackt:", len(payload))
elif payload[:4] == b"bvx2":
    import liblzfse; payload = liblzfse.decompress(payload); print("LZFSE entpackt:", len(payload))
open(sys.argv[2], "wb").write(payload)
print("geschrieben:", sys.argv[2])

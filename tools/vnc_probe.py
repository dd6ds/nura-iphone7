#!/usr/bin/env python3
"""RFB-Test: verbindet, fordert Vollbild an (Raw), liest echte Pixeldaten und speichert out/vnc-probe.png."""
import socket, struct, sys, time, zlib, os
host, port = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5900
s = socket.create_connection((host, port), timeout=60)
def rx(n):
    b = bytearray()
    while len(b) < n:
        c = s.recv(min(1 << 20, n - len(b)))
        if not c:
            raise SystemExit("Verbindung geschlossen")
        b += c
    return bytes(b)
print("Server:", rx(12).strip()); s.sendall(b"RFB 003.008\n")
n = rx(1)[0]; types = list(rx(n))
if 1 not in types: raise SystemExit(f"Security {types} – kein 'None'")
s.sendall(b"\x01"); rx(4); s.sendall(b"\x01")
w, h = struct.unpack(">HH", rx(4)); rx(16); rx(struct.unpack(">I", rx(4))[0])
print(f"Framebuffer {w}x{h}")
# Pixelformat 32bpp, BGRX little endian
s.sendall(struct.pack(">BxxxBBBBHHHBBBxxx", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
s.sendall(struct.pack(">BxH", 2, 1) + struct.pack(">i", 0))  # nur Raw
t0 = time.time()
s.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, w, h))
s.settimeout(40)
fb = bytearray(w * h * 4)
got = 0
while time.time() - t0 < 40:
    t = rx(1)[0]
    if t != 0:
        print("Nachricht Typ", t); continue
    rx(1); nr = struct.unpack(">H", rx(2))[0]
    print(f"Update mit {nr} Rechteck(en) nach {time.time()-t0:.1f}s")
    for _ in range(nr):
        x, y, rw, rh, enc = struct.unpack(">HHHHi", rx(12))
        if enc != 0:
            print("  Pseudo-Encoding", enc, f"{rw}x{rh}")
            if rw and rh and enc == -239:  # Cursor
                rx(rw * rh * 4 + ((rw + 7) // 8) * rh)
            continue
        data = rx(rw * rh * 4)
        for row in range(rh):
            o = ((y + row) * w + x) * 4
            fb[o:o + rw * 4] = data[row * rw * 4:(row + 1) * rw * 4]
        got += rw * rh
    if got >= w * h:
        break
    s.sendall(struct.pack(">BBHHHH", 3, 1, 0, 0, w, h))
print(f"Pixel empfangen: {got}/{w*h}")
if got:
    rows = []
    for r in range(h):
        line = bytearray(b"\x00")
        base = r * w * 4
        for i in range(base, base + w * 4, 4):
            line += bytes((fb[i + 2], fb[i + 1], fb[i]))
        rows.append(bytes(line))
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b"")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "vnc-probe.png")
    open(out, "wb").write(png); print("Gespeichert:", os.path.abspath(out))

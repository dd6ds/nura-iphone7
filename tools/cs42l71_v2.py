#!/usr/bin/env python3
"""cs42l71_v2.py – CS42L71 über das SPIv2-Protokoll lesen (root, Maggie im Reset!).
Nachgebaut aus iOS AppleCSSPIv2Audio::_readDataBlock (AppleEmbeddedAudio.kext). iOS hält CS über
Kopf, Status-Polls und Daten durchgehend low (keepCSAsserted=1) – hier daher EINE Übertragung:
  80 A0 A1 A2  81 N0 N1  C6 00  00…(2k)  C6 00  [Polls: 00…(2k+2) C6 00]  00…(n+2)
  bereit, wenn (Status & 0x50) == 0x50; Daten = die n Bytes nach dem letzten Status.
Adressen: Seite<<16 | Register (z. B. 0x3000c = RCO-Status).
  cs42l71_v2.py ADDR [N] [polls]"""
import sys
sys.path.insert(0, "/tmp")
from cs42l71 import xfer

def read(addr, n, polls=0, cmd=0xC6, ctrl=0, verbose=True):
    k = min(n, 32)
    xfer([0xA1, ctrl])
    tx = [0x80, addr & 0xff, (addr >> 8) & 0xff, (addr >> 16) & 0xff, 0x81, n & 0xff, (n >> 8) & 0xff, cmd, 0]
    tx += [0] * (2 * k) + [cmd, 0]
    st_pos = [len(tx) - 1]
    for _ in range(polls):
        tx += [0] * (2 * k + 2) + [cmd, 0]
        st_pos.append(len(tx) - 1)
    d0 = len(tx)
    tx += [0] * (n + 2)
    rx = xfer(tx)
    xfer([0xA1, ctrl | 0x40])
    sts = [rx[p] for p in st_pos]
    if verbose:
        print("Status:", " ".join(f"{s:02x}" for s in sts))
        print("rx    :", rx.hex(" "))
    return sts, rx[d0:d0 + n]

def init(ctrl=0, verbose=True):
    """Nachbau AppleCSSPIv2Audio::_initializeCodecRegisters (0x…5f72d9c): [A1, ctrl|0x50],
    1 ms warten, Status [90 00] lesen bis (st & 0x90) == 0x90 (max. 49x), dann [A1, ctrl|0x40]."""
    import time
    xfer([0xA1, ctrl | 0x50])
    st = 0
    for i in range(49):
        time.sleep(0.001)
        st = xfer([0x90, 0x00])[1]
        if (st & 0x90) == 0x90:
            break
    xfer([0xA1, ctrl | 0x40])
    if verbose:
        print(f"init: Status {st:#04x} nach {i + 1} Versuchen ->", "ok" if (st & 0x90) == 0x90 else "NICHT bereit")
    return (st & 0x90) == 0x90

def read_poll(addr, n=8, windows=12, cmd=0xC6, ctrl=0):
    """Lesen mit mehreren Status-/Datenfenstern in EINER CS-Phase: Kopf, dann je Fenster
    [cmd 00] + max(n, 2k+2) Nullbytes; Daten = die n Bytes nach dem ersten Status mit (st & 0x50) == 0x50."""
    k = min(n, 32)
    w = max(n, 2 * k + 2)
    xfer([0xA1, ctrl])
    tx = [0x80, addr & 0xff, (addr >> 8) & 0xff, (addr >> 16) & 0xff, 0x81, n & 0xff, (n >> 8) & 0xff, cmd, 0]
    tx += [0] * (2 * k)
    pos = []
    for _ in range(windows):
        tx += [cmd, 0]
        pos.append(len(tx) - 1)
        tx += [0] * w
    rx = xfer(tx)
    xfer([0xA1, ctrl | 0x40])
    for p in pos:
        if (rx[p] & 0x50) == 0x50:
            return rx[p], rx[p + 1:p + 1 + n]
    return rx[pos[-1]], None

def rd(addr):
    """ein Byte-Register lesen (Anzahl 8 anfordern, ohne Auto-Inkrement kommt 8x derselbe Wert)"""
    st, d = read_poll(addr, 8)
    if d is None:
        raise IOError(f"CS42L71 nicht bereit beim Lesen von {addr:#x} (Status {st:#x})")
    return d[0]

def wr(addr, data, cmd=0xB5, ctrl=0, verbose=False):
    """Nachbau AppleCSSPIv2Audio::_writeDataBlock: 80 A0 A1 A2 81 N0 N1 + 10x[90 00] (Status),
    dann B5|B2 + Daten + 10x[90 00]; bereit, wenn (Status & 0x90) == 0x90. Eine CS-Phase."""
    if isinstance(data, int):
        data = [data]
    n = len(data)
    xfer([0xA1, ctrl])
    hdr = [0x80, addr & 0xff, (addr >> 8) & 0xff, (addr >> 16) & 0xff, 0x81, n & 0xff, (n >> 8) & 0xff]
    hdr += [0x90, 0x00] * 10
    body = [cmd] + list(data) + [0x90, 0x00] * 10
    rx = xfer(hdr + body)
    xfer([0xA1, ctrl | 0x40])
    st_h = [rx[8 + 2 * i] for i in range(10)]
    st_d = [rx[len(hdr) + 1 + n + 1 + 2 * i] for i in range(10)]
    ok_h = any((s & 0x90) == 0x90 for s in st_h)
    ok_d = any((s & 0x90) == 0x90 for s in st_d)
    if verbose:
        print("Kopf-Status :", " ".join(f"{s:02x}" for s in st_h), "ok" if ok_h else "NICHT bereit")
        print("Daten-Status:", " ".join(f"{s:02x}" for s in st_d), "ok" if ok_d else "NICHT bestätigt")
    return ok_h and ok_d

def update(addr, mask, val, verbose=True):
    """maskWrite wie im iOS-Treiber (vtbl+0xb18): nur die Bits in mask ändern"""
    old = rd(addr)
    new = (old & ~mask) | (val & mask)
    ok = wr(addr, new, verbose=False)
    back = rd(addr)
    if verbose:
        print(f"{addr:#08x}: {old:#04x} -> {new:#04x}  zurückgelesen {back:#04x}"
              + ("" if ok else "  (Schreibstatus nicht ok)"))
    return back

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "wr":
        a, v = int(sys.argv[2], 0), int(sys.argv[3], 0)
        wr(a, v, verbose=True); print(f"{a:#08x} = {rd(a):#04x}")
        sys.exit()
    a = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x3000c
    n = int(sys.argv[2], 0) if len(sys.argv) > 2 else 4
    p = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
    sts, d = read(a, n, p)
    print(f"{a:#08x}: {d.hex(' ')}")

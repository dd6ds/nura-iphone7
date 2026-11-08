#!/usr/bin/env python3
"""
pongo_send.py – Datei an PongoOS per USB schicken und Befehle ausführen.

Nachbau des Protokolls von checkra1n/pongoOS scripts/pongoterm.c:
  ctrl 0x21/4 wValue=0xffff  -> Konsole freigeben (wie pongoterm nach dem Prompt)
  ctrl 0x21/1 (u32 LE len)   -> Upload-Größe ankündigen    ("/send")
  bulk OUT ep 0x02           -> Daten (in Blöcken)
  ctrl 0x21/3 "cmd\\n"        -> Shell-Befehl ausführen
  ctrl 0xa1/1                -> Konsolenausgabe lesen

Beispiele:
  sudo .venv/bin/python pongo_send.py --file out/m1n1-linux.bin --cmd bootm
  sudo .venv/bin/python pongo_send.py --cmd help
"""
import argparse
import struct
import sys
import time

try:
    import usb.core
    import usb.util
except ImportError:
    sys.exit("pyusb fehlt – './build.sh deps' installiert es ins venv.")

PONGO_VID = 0x05AC
PONGO_PID = 0x4141
CHUNK = 4 * 1024 * 1024
CMD_LEN_MAX = 512


def find_pongo(timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        dev = usb.core.find(idVendor=PONGO_VID, idProduct=PONGO_PID)
        if dev is not None:
            return dev
        time.sleep(0.5)
    return None


def read_console(dev, wait=0.5):
    """Liest gepufferte Konsolenausgabe (best effort)."""
    out = b""
    t0 = time.time()
    while time.time() - t0 < wait:
        try:
            chunk = bytes(dev.ctrl_transfer(0xA1, 1, 0, 0, 0x1000, timeout=1000))
        except usb.core.USBError:
            break
        if chunk:
            out += chunk
        else:
            time.sleep(0.05)
    if out:
        sys.stdout.write(out.decode(errors="replace"))
        sys.stdout.flush()


def cmd(dev, text):
    data = (text.rstrip("\n") + "\n").encode()
    if len(data) > CMD_LEN_MAX:
        sys.exit(f"Befehl zu lang (max {CMD_LEN_MAX} Zeichen)")
    print(f"  > {text}")
    dev.ctrl_transfer(0x21, 3, 0, 0, data)


def send(dev, path):
    with open(path, "rb") as f:
        blob = f.read()
    print(f"  Sende {path} ({len(blob) / 1024 / 1024:.1f} MiB) …")
    dev.ctrl_transfer(0x21, 1, 0, 0, struct.pack("<I", len(blob)))
    chunk = CHUNK
    off = 0
    while off < len(blob):
        part = blob[off:off + chunk]
        try:
            n = dev.write(0x02, part, timeout=30000)
        except usb.core.USBError as e:
            # wie pongoterm: bei ENOMEM kleinere Blöcke probieren
            if e.errno == 12 and chunk > 0x10000:
                chunk //= 2
                continue
            raise
        off += n
        print(f"\r  {off * 100 // len(blob):3d} %", end="", flush=True)
    print("\r  100 % – Upload fertig.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="Datei, die hochgeladen wird")
    ap.add_argument("--cmd", action="append", default=[],
                    help="PongoOS-Befehl (mehrfach möglich), z.B. bootm")
    ap.add_argument("--wait", type=int, default=60,
                    help="Sekunden auf PongoOS warten (Standard 60)")
    a = ap.parse_args()

    print(f"Warte auf PongoOS (USB {PONGO_VID:04x}:{PONGO_PID:04x}) …")
    dev = find_pongo(a.wait)
    if dev is None:
        sys.exit("PongoOS nicht gefunden. Läuft das iPhone in Pongo (palera1n -p)?")
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except (NotImplementedError, usb.core.USBError):
        pass
    try:
        dev.set_configuration()
    except usb.core.USBError:
        pass  # bereits konfiguriert

    read_console(dev)
    dev.ctrl_transfer(0x21, 4, 0xFFFF, 0, b"")

    if a.file:
        send(dev, a.file)
        read_console(dev)
    for c in a.cmd:
        try:
            cmd(dev, c)
            read_console(dev, 1.0)
        except usb.core.USBError:
            # Boot-Befehle trennen USB sofort – das ist normal.
            print("  (USB getrennt – Gerät bootet)")
            break


if __name__ == "__main__":
    main()

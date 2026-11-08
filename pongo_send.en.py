#!/usr/bin/env python3
"""
pongo_send.en.py – send a file to PongoOS over USB and run commands.

Reimplementation of the protocol from checkra1n/pongoOS scripts/pongoterm.c:
  ctrl 0x21/4 wValue=0xffff  -> release the console (like pongoterm after the prompt)
  ctrl 0x21/1 (u32 LE len)   -> announce the upload size    ("/send")
  bulk OUT ep 0x02           -> data (in chunks)
  ctrl 0x21/3 "cmd\\n"        -> run a shell command
  ctrl 0xa1/1                -> read console output

Beispiele:
  sudo .venv/bin/python pongo_send.en.py --file out/m1n1-linux.bin --cmd bootm
  sudo .venv/bin/python pongo_send.en.py --cmd help
"""
import argparse
import struct
import sys
import time

try:
    import usb.core
    import usb.util
except ImportError:
    sys.exit("pyusb missing – './build.en.sh deps' installs it into the venv.")

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
    """Reads buffered console output (best effort)."""
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
        sys.exit(f"Command too long (max {CMD_LEN_MAX} characters)")
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
            # like pongoterm: try smaller chunks on ENOMEM
            if e.errno == 12 and chunk > 0x10000:
                chunk //= 2
                continue
            raise
        off += n
        print(f"\r  {off * 100 // len(blob):3d} %", end="", flush=True)
    print("\r  100 % – upload done.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="file to upload")
    ap.add_argument("--cmd", action="append", default=[],
                    help="PongoOS command (can be given several times), e.g. bootm")
    ap.add_argument("--wait", type=int, default=60,
                    help="seconds to wait for PongoOS (default 60)")
    a = ap.parse_args()

    print(f"Waiting for PongoOS (USB {PONGO_VID:04x}:{PONGO_PID:04x}) …")
    dev = find_pongo(a.wait)
    if dev is None:
        sys.exit("PongoOS not found. Is the iPhone running Pongo (palera1n -p)?")
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except (NotImplementedError, usb.core.USBError):
        pass
    try:
        dev.set_configuration()
    except usb.core.USBError:
        pass  # already configured

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
            # Boot commands disconnect USB immediately – that is normal.
            print("  (USB disconnected – device is booting)")
            break


if __name__ == "__main__":
    main()

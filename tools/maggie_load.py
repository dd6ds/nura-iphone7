#!/usr/bin/env python3
"""Maggie-FPGA (Lattice iCE5LP4K) des iPhone 7 per SPI konfigurieren – Test aus dem Userspace (root).
   maggie_load.py [bitstream]      Standard: ~/audio/maggie_d10.bin (aus IPSW Firmware/Maggie/*.im4p)
Ablauf (iCE40 "SPI slave configuration"): CRESET_B low -> SPI_SS low -> CRESET_B high -> >=1,2 ms
warten -> Bitstream -> >=49 Takte extra -> CDONE muss high werden.
Eine einzige spidev-Nachricht (SS durchgehend low): viele Nullbytes (FPGA im Reset bzw. Löschphase,
ignoriert alles bis zur Sync-Sequenz 7EAA997E) + Bitstream + Nullbytes. CRESET_B wird während der
Nullbytes über ein interaktives gpioset (ohne Neustart des Prozesses) freigegeben."""
import ctypes, fcntl, glob, os, struct, subprocess, sys, threading, time

CHIP, CRESET, CDONE = "gpiochip0", 22, 26          # ADT: maggie_reset GPIO 0x16, maggie_done GPIO 0x1a
SPEED = int(os.environ.get("MAGGIE_HZ", "4000000"))
PRE = int(os.environ.get("MAGGIE_PRE", str(160 * 1024)))
BIT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~user/audio/maggie_d10.bin")

def spidev_for(ctrl="20a084000", cs=int(os.environ.get("MAGGIE_CS", "1"))):
    for d in glob.glob("/sys/bus/spi/devices/spi*.%d" % cs):
        if ctrl in os.path.realpath(d):
            return "/dev/" + os.path.basename(d).replace("spi", "spidev", 1)
    sys.exit("kein spidev für spi1 – DTB mit spi1/maggie@1 gebootet?")

def gpio_get(line):
    return subprocess.run(["gpioget", "-c", CHIP, "--numeric", str(line)],
                          capture_output=True, text=True).stdout.strip()

def spi_message(dev, data, out):
    fd = os.open(dev, os.O_RDWR)
    buf = bytearray(data)
    cbuf = (ctypes.c_char * len(buf)).from_buffer(buf)
    xfer = struct.pack("<QQIIHBBBBBB", ctypes.addressof(cbuf), 0, len(buf), SPEED, 0, 8, 0, 0, 0, 0, 0)
    req = (1 << 30) | (len(xfer) << 16) | (ord('k') << 8) | 0       # SPI_IOC_MESSAGE(1)
    out["start"] = time.monotonic()
    fcntl.ioctl(fd, req, xfer)
    out["end"] = time.monotonic()
    os.close(fd)

bit = open(BIT, "rb").read()
assert b"\x7e\xaa\x99\x7e" in bit[:256], "keine iCE40-Sync-Sequenz – falsche Datei?"
dev = spidev_for()
print(f"Bitstream {len(bit)} B, spidev {dev}, {SPEED/1e6:.1f} MHz, Vorlauf {PRE} B, CDONE vorher = {gpio_get(CDONE)}")

gs = subprocess.Popen(["gpioset", "-c", CHIP, "--interactive", f"{CRESET}=0"],
                      stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, start_new_session=True, text=True)
time.sleep(0.2)                                       # FPGA sicher im Reset
res = {}
th = threading.Thread(target=spi_message, args=(dev, bytes(PRE) + bit + bytes(64), res))
th.start()
while "start" not in res: time.sleep(0.001)
time.sleep(0.01)                                      # SS ist low, Nullbytes laufen
gs.stdin.write(f"set {CRESET}=1\n"); gs.stdin.flush()
t_rel = time.monotonic()
th.join()
time.sleep(0.02)
done = gpio_get(CDONE)
dur = res["end"] - res["start"]
pre_s = PRE * 8 / SPEED
print(f"Transfer {dur:.3f} s (Vorlauf rechnerisch {pre_s:.3f} s), CRESET frei nach {t_rel - res['start']:.3f} s")
if t_rel - res["start"] > pre_s - 0.002:
    print("WARNUNG: CRESET kam zu spät (nach dem Vorlauf) – MAGGIE_PRE erhöhen")
print(f"CDONE nachher = {done}  ->", "Maggie KONFIGURIERT" if done == "1"
      else "nicht konfiguriert (Strom/Takt über AOP 'enableMaggie'?)")
print(f"gpioset (PID {gs.pid}) hält CRESET_B high; beenden mit: kill {gs.pid}")

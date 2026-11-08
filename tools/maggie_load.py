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
SPEED = int(os.environ.get("MAGGIE_HZ", "1000000"))
PRE = int(os.environ.get("MAGGIE_PRE", str(64 * 1024)))   # Vorlauf-Nullbytes (~0,5 s Zeit für CRESET);
PRE_HZ = int(os.environ.get("MAGGIE_PRE_HZ", "1000000"))    # s5l: ganze Nachricht mit kleinster Rate, je Teil max. 1 s
TRIES = int(os.environ.get("MAGGIE_TRIES", "3"))
BIT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~user/audio/maggie_d10.bin")

def spidev_for(ctrl="20a084000", cs=int(os.environ.get("MAGGIE_CS", "1"))):
    for d in glob.glob("/sys/bus/spi/devices/spi*.%d" % cs):
        if ctrl in os.path.realpath(d):
            return "/dev/" + os.path.basename(d).replace("spi", "spidev", 1)
    sys.exit("kein spidev für spi1 – DTB mit spi1/maggie@1 gebootet?")

def gpio_get(line):
    return subprocess.run(["gpioget", "-c", CHIP, "--numeric", str(line)],
                          capture_output=True, text=True).stdout.strip()

def spi_message(dev, parts, out):
    """parts = [(daten, hz), ...] – eine spidev-Nachricht, CS bleibt zwischen den Teilen low."""
    fd = os.open(dev, os.O_RDWR)
    if "MAGGIE_MODE" in os.environ:                       # s5l-Treiber: CONFIG 0x1E = CPOL|CPHA fest
        fcntl.ioctl(fd, 0x40016b01, struct.pack("B", int(os.environ["MAGGIE_MODE"])))
    keep, xfer = [], b""
    for data, hz in parts:
        cbuf = (ctypes.c_char * len(data)).from_buffer_copy(data)
        keep.append(cbuf)
        xfer += struct.pack("<QQIIHBBBBBB", ctypes.addressof(cbuf), 0, len(data), hz, 0, 8, 0, 0, 0, 0, 0)
    req = (1 << 30) | (len(xfer) << 16) | (ord('k') << 8) | 0       # SPI_IOC_MESSAGE(n)
    xb = ctypes.create_string_buffer(xfer, len(xfer))
    libc = ctypes.CDLL(None, use_errno=True)              # ctypes gibt die GIL frei, fcntl.ioctl nicht
    out["start"] = time.monotonic()
    if libc.ioctl(fd, ctypes.c_ulong(req), xb) < 0:
        out["err"] = ctypes.get_errno()
    out["end"] = time.monotonic()
    os.close(fd)

# Aus der AOP-Firmware (Button::enableMCLK / enableMaggie, Ghidra):
#   MCLK an  = *(0x2_10c02000) = 0x48 (aus = 0x08)
#   Maggie an = AOP-GPIO 20 (0x2_100f0000 + 20*4) Bit0 = 1
AOP_MCLK, AOP_PIN20 = 0x210c02000, 0x2100f0000 + 20 * 4

def mem(addr, val=None):
    import mmap
    page = addr & ~0x3fff
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
    o = addr - page
    if val is not None:
        m[o:o + 4] = struct.pack("<I", val)
    r = struct.unpack("<I", m[o:o + 4])[0]
    m.close(); os.close(fd)
    return r

if os.environ.get("MAGGIE_AOP", "1") == "1":
    mem(AOP_MCLK, 0x48)
    mem(AOP_PIN20, (mem(AOP_PIN20) & ~1) | 1)
    time.sleep(0.05)
    print(f"AOP: MCLK=0x{mem(AOP_MCLK):x}  Pin20=0x{mem(AOP_PIN20):x}")

bit = open(BIT, "rb").read()
assert b"\x7e\xaa\x99\x7e" in bit[:256], "keine iCE40-Sync-Sequenz – falsche Datei?"
dev = spidev_for()
print(f"Bitstream {len(bit)} B, spidev {dev}, {SPEED/1e6:.1f} MHz, Vorlauf {PRE} B, CDONE vorher = {gpio_get(CDONE)}")

for attempt in range(1, TRIES + 1):
    gs = subprocess.Popen(["gpioset", "-c", CHIP, "--interactive", f"{CRESET}=0"],
                          stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, start_new_session=True, text=True)
    time.sleep(0.2)                                   # FPGA sicher im Reset
    res = {}
    parts = [(bytes(PRE), PRE_HZ), (bit + bytes(64), SPEED)]
    th = threading.Thread(target=spi_message, args=(dev, parts, res))
    th.start()
    while "start" not in res: time.sleep(0.001)
    time.sleep(0.01)                                  # SS ist low, Nullbytes laufen
    gs.stdin.write(f"set {CRESET}=1\n"); gs.stdin.flush()
    t_rel = time.monotonic()
    th.join()
    time.sleep(0.02)
    done = gpio_get(CDONE)
    dur = res["end"] - res["start"]
    pre_s = PRE * 8 / PRE_HZ
    print(f"[{attempt}] Transfer {dur:.3f} s (Vorlauf rechnerisch {pre_s:.3f} s), "
          f"CRESET frei nach {t_rel - res['start']:.3f} s")
    if t_rel - res["start"] > pre_s - 0.002:
        print("WARNUNG: CRESET kam zu spät (nach dem Vorlauf) – MAGGIE_PRE erhöhen")
    print(f"CDONE nachher = {done}  ->", "Maggie KONFIGURIERT" if done == "1"
          else "nicht konfiguriert (Strom/Takt über AOP 'enableMaggie'?)")
    if done == "1":
        print(f"gpioset (PID {gs.pid}) hält CRESET_B high; beenden mit: kill {gs.pid}")
        break
    gs.kill(); gs.wait()

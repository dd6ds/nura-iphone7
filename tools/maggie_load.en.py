#!/usr/bin/env python3
"""Configure the iPhone 7's Maggie FPGA (Lattice iCE5LP4K) via SPI – test from userspace (root).
   maggie_load.en.py [bitstream]      default: ~/audio/maggie_d10.bin (from IPSW Firmware/Maggie/*.im4p)
Procedure (iCE40 "SPI slave configuration"): CRESET_B low -> SPI_SS low -> CRESET_B high -> >=1.2 ms
wait -> bitstream -> >=49 extra clocks -> CDONE must go high.
A single spidev message (SS low throughout): many zero bytes (FPGA in reset or erase phase,
ignores everything up to the sync sequence 7EAA997E) + bitstream + zero bytes. CRESET_B is
released during the zero bytes via an interactive gpioset (without restarting the process)."""
import ctypes, fcntl, glob, os, struct, subprocess, sys, threading, time

CHIP, CRESET, CDONE = "gpiochip0", 22, 26          # ADT: maggie_reset GPIO 0x16, maggie_done GPIO 0x1a
SPEED = int(os.environ.get("MAGGIE_HZ", "1000000"))
PRE = int(os.environ.get("MAGGIE_PRE", str(64 * 1024)))   # preamble zero bytes (~0.5 s for CRESET);
PRE_HZ = int(os.environ.get("MAGGIE_PRE_HZ", "1000000"))    # s5l: whole message at the lowest rate, max. 1 s per part
TRIES = int(os.environ.get("MAGGIE_TRIES", "3"))
BIT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~user/audio/maggie_d10.bin")

def spidev_for(ctrl="20a084000", cs=int(os.environ.get("MAGGIE_CS", "1"))):
    for d in glob.glob("/sys/bus/spi/devices/spi*.%d" % cs):
        if ctrl in os.path.realpath(d):
            return "/dev/" + os.path.basename(d).replace("spi", "spidev", 1)
    sys.exit("no spidev for spi1 – booted with a DTB containing spi1/maggie@1?")

def gpio_get(line):
    return subprocess.run(["gpioget", "-c", CHIP, "--numeric", str(line)],
                          capture_output=True, text=True).stdout.strip()

def spi_message(dev, parts, out):
    """parts = [(data, hz), ...] – one spidev message, CS stays low between the parts."""
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
    libc = ctypes.CDLL(None, use_errno=True)              # ctypes releases the GIL, fcntl.ioctl does not
    out["start"] = time.monotonic()
    if libc.ioctl(fd, ctypes.c_ulong(req), xb) < 0:
        out["err"] = ctypes.get_errno()
    out["end"] = time.monotonic()
    os.close(fd)

# From the AOP firmware (Button::enableMCLK / enableMaggie, Ghidra):
#   MCLK on  = *(0x2_10c02000) = 0x48 (off = 0x08)
#   Maggie on = AOP GPIO 20 (0x2_100f0000 + 20*4) bit0 = 1
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
assert b"\x7e\xaa\x99\x7e" in bit[:256], "no iCE40 sync sequence – wrong file?"
dev = spidev_for()
print(f"Bitstream {len(bit)} B, spidev {dev}, {SPEED/1e6:.1f} MHz, preamble {PRE} B, CDONE before = {gpio_get(CDONE)}")

for attempt in range(1, TRIES + 1):
    gs = subprocess.Popen(["gpioset", "-c", CHIP, "--interactive", f"{CRESET}=0"],
                          stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, start_new_session=True, text=True)
    time.sleep(0.2)                                   # FPGA safely in reset
    res = {}
    parts = [(bytes(PRE), PRE_HZ), (bit + bytes(64), SPEED)]
    th = threading.Thread(target=spi_message, args=(dev, parts, res))
    th.start()
    while "start" not in res: time.sleep(0.001)
    time.sleep(0.01)                                  # SS is low, zero bytes are running
    gs.stdin.write(f"set {CRESET}=1\n"); gs.stdin.flush()
    t_rel = time.monotonic()
    th.join()
    time.sleep(0.02)
    done = gpio_get(CDONE)
    dur = res["end"] - res["start"]
    pre_s = PRE * 8 / PRE_HZ
    print(f"[{attempt}] Transfer {dur:.3f} s (preamble computed {pre_s:.3f} s), "
          f"CRESET released after {t_rel - res['start']:.3f} s")
    if t_rel - res["start"] > pre_s - 0.002:
        print("WARNING: CRESET came too late (after the preamble) – increase MAGGIE_PRE")
    print(f"CDONE after = {done}  ->", "Maggie CONFIGURED" if done == "1"
          else "not configured (power/clock via AOP 'enableMaggie'?)")
    if done == "1":
        print(f"gpioset (PID {gs.pid}) keeps CRESET_B high; stop with: kill {gs.pid}")
        break
    gs.kill(); gs.wait()

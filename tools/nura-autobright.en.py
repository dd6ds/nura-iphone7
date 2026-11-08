#!/usr/bin/env python3
"""nura-autobright – automatic display brightness from the light sensor CT821 (iPhone 7, root).
The sensor sits on I2C2 (0x29); the Linux driver for i2c2 hangs the boot, so the
controller is driven via /dev/mem without interrupts (tools/i2c_poll.en.py, installed as nura_i2c.py).
- Integration time switches automatically (128 / 16 / 2 cycles), gain fixed at 7 -> no saturation.
- Brightness logarithmic between NURA_BL_MIN and maximum, smoothed, gentle steps.
- If someone changes the brightness by hand (slider), the service pauses for NURA_BL_PAUSE seconds.
Environment: NURA_BL_MIN (default 80), NURA_BL_PAUSE (300), NURA_LUX_MAX (20000 counts = full brightness)."""
import glob, math, mmap, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from nura_i2c import Bus                 # = tools/i2c_poll.en.py, installed as nura_i2c.py

A = 0x29
PMGR_I2C2 = 0x20e0801b8
STUFEN = [(0x80, 128), (0xf0, 16), (0xfe, 2)]        # (ATIME, cycles)
BL = glob.glob("/sys/class/backlight/*/")[0]
BL_MAX = int(open(BL + "max_brightness").read())
BL_MIN = int(os.environ.get("NURA_BL_MIN", "80"))
PAUSE = float(os.environ.get("NURA_BL_PAUSE", "300"))
LUX_MAX = float(os.environ.get("NURA_LUX_MAX", "20000"))


def log(*a):
    print(*a, flush=True)


def domain_an():
    """Switch on the PMGR power domain of i2c2 (target = 0xf) and wait until it is active."""
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
                  offset=PMGR_I2C2 & ~0x3fff)
    o = PMGR_I2C2 & 0x3fff
    v = struct.unpack_from("<I", m, o)[0]
    if (v >> 4) & 0xf != 0xf:
        struct.pack_into("<I", m, o, (v & ~0xf) | 0xf)
        for _ in range(100):
            if (struct.unpack_from("<I", m, o)[0] >> 4) & 0xf == 0xf:
                break
            time.sleep(0.001)
    m.close(); os.close(fd)


class Sensor:
    def __init__(self):
        domain_an()
        self.b = Bus(2)
        self.stufe = 0
        if self.rd(0x12) != 0x9b:
            raise SystemExit("CT821 not found (ID != 0x9b)")
        self.wr(0x00, 0x00)
        self.wr(0x0c, 0x40)
        self.wr(0x0f, 0x07)
        self.setze_stufe(0)
        self.wr(0x00, 0x01); time.sleep(0.003); self.wr(0x00, 0x03)

    def rd(self, r):
        return self.b.read(A, bytes([0x80 | r]), 1)[0]

    def wr(self, r, v):
        self.b.write(A, bytes([0x80 | r, v]))

    def setze_stufe(self, s):
        self.stufe = s
        self.wr(0x01, STUFEN[s][0])

    def messen(self):
        """Value normalised to 128 cycles; switches the integration time when needed."""
        c0 = self.rd(0x14) | self.rd(0x15) << 8
        zyklen = STUFEN[self.stufe][1]
        voll = zyklen * 1024 - 1                       # counter saturation
        if c0 > 0.8 * min(voll, 65535) and self.stufe < len(STUFEN) - 1:
            self.setze_stufe(self.stufe + 1)
        elif c0 < 0.05 * min(voll, 65535) and self.stufe > 0:
            self.setze_stufe(self.stufe - 1)
        return c0 * 128 / zyklen


def bl_lesen():
    return int(open(BL + "brightness").read())


def bl_setzen(v):
    with open(BL + "brightness", "w") as f:
        f.write(str(int(v)))


def ziel(licht):
    x = math.log1p(max(licht, 0)) / math.log1p(LUX_MAX)
    return BL_MIN + (BL_MAX - BL_MIN) * min(1.0, x)


def main():
    while True:
        try:
            s = Sensor()
            break
        except OSError as e:
            log("Sensor not ready:", e); time.sleep(10)
    log(f"nura-autobright: {BL} max {BL_MAX}, min {BL_MIN}")
    glatt = None
    gesetzt = bl_lesen()
    pause_bis = 0.0
    while True:
        time.sleep(0.5)
        try:
            licht = s.messen()
        except OSError as e:
            log("Read error:", e); time.sleep(2)
            try:
                s = Sensor()
            except OSError:
                pass
            continue
        glatt = licht if glatt is None else glatt + 0.25 * (licht - glatt)
        jetzt = bl_lesen()
        if abs(jetzt - gesetzt) > max(8, 0.02 * BL_MAX):   # someone changed it by hand
            pause_bis = time.time() + PAUSE
            gesetzt = jetzt
            log(f"Manual setting {jetzt} -> pause {PAUSE:.0f} s")
        if time.time() < pause_bis or open(BL + "bl_power").read().strip() != "0":
            continue
        z = ziel(glatt)
        if abs(z - jetzt) < max(4, 0.03 * jetzt):
            continue
        neu = jetzt + max(-120, min(120, z - jetzt))       # gentle steps
        bl_setzen(neu)
        gesetzt = bl_lesen()


if __name__ == "__main__":
    main()

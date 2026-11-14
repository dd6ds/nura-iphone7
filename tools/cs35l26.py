#!/usr/bin/env python3
"""cs35l26.py – Lautsprecher-Verstärker CS35L26 (AP-I2C2, Adresse 0x40) per /dev/mem-I2C (root, iPhone 7).
Vorher: PMGR i2c2 an (pmgr_ps.py 0x801b8 on) und Reset loslassen (GPIO 140 = 1, z. B.
`systemd-run --unit=amp-reset gpioset -c gpiochip0 140=1`).
Der Chip gehört zur CS35L35-Familie (ID-Register 0x01..0x03 = 35 a2 6x, Revision 0x05); die
Registerkarte stimmt mit Linux sound/soc/codecs/cs35l35.h überein (PWRCTL1 0x06 Bit 0 = PDN_ALL,
CLK_CTL1 0x0A, AMP_INP_DRV_CTL 0x14 Bit 5 = Stumm, INT_STATUS_1 0x74: MCLK_ERR 0x08, SPCLK_ERR 0x10,
LRCLK_ERR 0x20, INT_STATUS_2 0x75: PDN_DONE 0x10).
  cs35l26.py id | dump | rd REG | wr REG WERT
  cs35l26.py takttest   Verstärker stumm einschalten, Takt-Fehlerbits lesen, wieder abschalten"""
import sys, time
sys.path.insert(0, "/tmp")
from i2c_poll import Bus

ADR = 0x40
b = Bus(2)


def rd(r):
    return b.read(ADR, bytes([r]), 1)[0]


def wr(r, v):
    b.write(ADR, bytes([r, v & 0xff]))


def upd(r, mask, val):
    alt = rd(r)
    wr(r, (alt & ~mask) | (val & mask))
    return alt, rd(r)


def status():
    return [rd(0x74 + i) for i in range(4)]       # Lesen löscht (sticky)


def fehler(s):
    t = [n for bit, n in ((0x80, "CAL_ERR"), (0x40, "OTP_ERR"), (0x20, "LRCLK_ERR"), (0x10, "SPCLK_ERR"),
                          (0x08, "MCLK_ERR"), (0x04, "AMP_SHORT")) if s[0] & bit]
    if s[1] & 0x10:
        t.append("PDN_DONE")
    return ", ".join(t) or "keine"


cmd = sys.argv[1] if len(sys.argv) > 1 else "id"
if cmd == "id":
    i = [rd(r) for r in range(1, 6)]
    print(f"Geräte-ID {i[0]:02x}{i[1]:02x}{i[2] >> 4:x}  FAB {i[3]:#04x}  Revision {i[4]:#04x}")
elif cmd == "dump":
    for r0 in range(0, 0x80, 16):
        print(f"{r0:#04x}: " + " ".join(f"{rd(r):02x}" for r in range(r0, r0 + 16)))
elif cmd == "rd":
    r = int(sys.argv[2], 0); print(f"{r:#04x} = {rd(r):#04x}")
elif cmd == "wr":
    r, v = int(sys.argv[2], 0), int(sys.argv[3], 0); wr(r, v); print(f"{r:#04x} = {rd(r):#04x}")
elif cmd == "takttest":
    print("vorher: PWRCTL1-3", " ".join(f"{rd(r):02x}" for r in (6, 7, 8)), " CLK_CTL1-3",
          " ".join(f"{rd(r):02x}" for r in (0xa, 0xb, 0xc)), " PLL_STATUS", f"{rd(0x78):02x}")
    print("Status (alt, gelöscht):", fehler(status()))
    upd(0x14, 0x20, 0x20)                          # stumm
    upd(0x06, 0x01, 0x00)                          # PDN_ALL aus -> einschalten
    if "--amp" in sys.argv:
        upd(0x07, 0x01, 0x00)                      # PWRCTL2 PDN_AMP aus -> Endstufe an (stumm)
    time.sleep(0.05)
    s1 = status(); time.sleep(0.05); s2 = status()
    print("eingeschaltet:", " ".join(f"{x:02x}" for x in s1), "->", fehler(s1), "| nach 50 ms:", fehler(s2),
          " PLL_STATUS", f"{rd(0x78):02x}", " PWRCTL1", f"{rd(6):02x}")
    if "--amp" in sys.argv:
        upd(0x07, 0x01, 0x01)
    upd(0x06, 0x01, 0x01)                          # wieder aus
    time.sleep(0.05)
    print("ausgeschaltet:", fehler(status()))
else:
    sys.exit(__doc__)

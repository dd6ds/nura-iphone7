#!/usr/bin/env python3
"""gpu_rtkit.en.py [seconds] – EXPERIMENT: RTKit handshake with the running GPU coprocessor (root).
First: gpu_fw_boot.en.py <fw> 0 --laufen --neu  (starts the firmware, leaves its HELLO in the mailbox).
Message format of this generation (derived from the first HELLO 0x00100000000c000c):
  Bit 63:56 = endpoint, management (endpoint 0): bit 55:52 = type, rest = payload.
Management as in Asahi rtkit.c: HELLO 1 (min/max version bit 15:0/31:16) -> HELLO_ACK 2;
EPMAP 8 (base bit 34:32, bitmap 31:0, LAST bit 51) -> reply 8 with base + LAST or MORE (bit 0).
Starts no endpoints and allocates no memory – only shows what the firmware offers."""
import ctypes, mmap, os, sys, time

AKF = 0x201D20000
dauer = float(sys.argv[1]) if len(sys.argv) > 1 else 5
NAMEN = {0: "management", 1: "crashlog", 2: "syslog", 3: "debug", 4: "ioreport", 8: "oslog"}
TYPEN = {1: "HELLO", 2: "HELLO_ACK", 5: "STARTEP", 6: "IOP_PWR", 7: "IOP_PWR_ACK", 8: "EPMAP", 0xb: "AP_PWR"}

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
va = ctypes.addressof(ctypes.c_char.from_buffer(m))
r32 = lambda o: ctypes.c_uint32.from_address(va + o).value


def log(*a):
    print(*a, flush=True)


def senden(msg):
    for _ in range(1000):
        if not r32(0x4008) & (1 << 16):            # inbox not full
            break
        time.sleep(0.001)
    else:
        raise SystemExit(f"Inbox stays full ({r32(0x4008):#x})")
    ctypes.c_uint64.from_address(va + 0x4010).value = msg
    log(f"  -> {msg:#018x}")


def holen():
    out = r32(0x4020)
    if out & 0xc0000:
        raise SystemExit(f"Outbox error {out:#x}")
    if out & (1 << 17):                             # empty
        return None
    return ctypes.c_uint64.from_address(va + 0x4038).value


def verwaltung(typ, daten):
    senden((0 << 56) | (typ << 52) | daten)


if not r32(0x44) & 0x10:
    sys.exit("Coprocessor not running – first gpu_fw_boot.en.py <fw> 0 --laufen --neu")
endpunkte = []
t0 = time.time()
# After the handshake (0.5 s quiet) send power commands as a test (no reply so far):
# IOP_PWR_STATE (6) = 0x20 (on), then AP_PWR_STATE (0xb) = 0x20.
nachschub = [(6, 0x20), (0xb, 0x20)]
ack_zeit, letzte_nachricht = None, time.time()
while time.time() - t0 < dauer:
    msg = holen()
    if msg is None:
        if ack_zeit and nachschub and time.time() - letzte_nachricht > 0.5:
            typ, wert = nachschub.pop(0)
            log(f"  (0.5 s quiet) sending {TYPEN[typ]} = {wert:#x}")
            verwaltung(typ, wert)
            letzte_nachricht = time.time()
        time.sleep(0.002)
        continue
    letzte_nachricht = time.time()
    ep, typ = msg >> 56, (msg >> 52) & 0xf
    log(f"{time.time() - t0:6.3f}s <- {msg:#018x}  ep {ep} ({NAMEN.get(ep, '?')})"
        + (f", type {typ} ({TYPEN.get(typ, '?')})" if ep == 0 else ""))
    if ep != 0:
        continue
    if typ == 1:                                     # HELLO
        vmin, vmax = msg & 0xffff, (msg >> 16) & 0xffff
        v = vmax
        log(f"  HELLO: version {vmin}..{vmax} -> replying with {v}")
        # ACK format via environment: both (default, as Asahi: min | max << 16) or min only
        verwaltung(2, v if os.environ.get("ACK") == "min" else (v << 16) | v)
        ack_zeit = time.time()
    elif typ == 8:                                   # EPMAP
        basis, bitmap, letzte = (msg >> 32) & 7, msg & 0xffffffff, bool(msg >> 51 & 1)
        neu = [basis * 32 + b for b in range(32) if bitmap >> b & 1]
        endpunkte += neu
        log(f"  EPMAP base {basis}: endpoints {neu}{' (last)' if letzte else ''}")
        verwaltung(8, (basis << 32) | ((1 << 51) if letzte else 1))
        if letzte:
            log("Endpoints of the GPU firmware: " + ", ".join(f"{e} ({NAMEN.get(e, '?')})" for e in endpunkte))
log(f"End after {dauer:.0f}s; IDLE {r32(0x4040):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")

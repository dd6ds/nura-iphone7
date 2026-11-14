#!/usr/bin/env python3
"""gpu_rtkit.en.py [seconds] [--start] – EXPERIMENT: RTKit handshake with the running GPU coprocessor (root).
Also for the AOP: AKF=0x210800000 (HELLO_ACK=12 if aop_fw_boot.en.py has already picked up the HELLO).
--start: after the endpoint map start all endpoints via STARTEP (flag via STARTFLAG, default 2).
--puffer: serve the endpoints' buffer requests from the reserved RAM (IOP 0x90000..0xfffff).
First: gpu_fw_boot.en.py <fw> 0 --laufen --neu  (starts the firmware, leaves its HELLO in the mailbox).
Message format of this generation (derived from the first HELLO 0x00100000000c000c):
  Bit 63:56 = endpoint, management (endpoint 0): bit 55:52 = type, rest = payload.
Management as in Asahi rtkit.c: HELLO 1 (min/max version bit 15:0/31:16) -> HELLO_ACK 2;
EPMAP 8 (base bit 34:32, bitmap 31:0, LAST bit 51) -> reply 8 with base + LAST or MORE (bit 0).
Without options it starts no endpoints and allocates no memory."""
import ctypes, mmap, os, sys, time

AKF = int(os.environ.get("AKF", "0x201D20000"), 0)   # AOP: AKF=0x210800000
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
    sys.exit("coprocessor not running – run gpu_fw_boot.en.py <fw> 0 --laufen --neu first (AOP: aop_fw_boot.en.py)")
endpunkte = []
puffer_frei = int(os.environ.get("PUFFER_AB", "0x90000"), 0)   # next free IOP address for buffers
puffer_ende = int(os.environ.get("PUFFER_BIS", "0x100000"), 0)
t0 = time.time()
# After the handshake (0.5 s quiet) send power commands; IOP_PWR_ACK only arrives after the crashlog buffer:
# IOP_PWR_STATE (6) = 0x20 (on), then AP_PWR_STATE (0xb) = 0x20.
nachschub = [(6, 0x20), (0xb, 0x20)]
ack_zeit, letzte_nachricht = None, time.time()
# HELLO_ACK=<version>: the HELLO was already picked up by another script -> acknowledge immediately
if "HELLO_ACK" in os.environ:
    v = int(os.environ["HELLO_ACK"], 0)
    log(f"  HELLO already picked up – sending HELLO_ACK version {v}")
    verwaltung(2, (v << 16) | v)
    ack_zeit = time.time()
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
        # Buffer request (RTKit BUFFER_REQUEST): type bit 55:52 = 1, size in pages bit 51:44,
        # address bit 41:0 = 0 -> allocate memory from the free part of the reserved RAM
        # (IOP address 0x90000.., the firmware itself needs 0..0x8f000) and reply with the address.
        etyp, seiten, adr = (msg >> 52) & 0xf, (msg >> 44) & 0xff, msg & ((1 << 42) - 1)
        if etyp == 1 and adr == 0 and "--puffer" in sys.argv:
            groesse = seiten * 0x4000                      # 16 KB pages to be safe
            if puffer_frei + groesse > puffer_ende:
                log(f"  Buffer request ({seiten} pages) no longer fits into the reserved RAM")
                continue
            log(f"  Buffer request: {seiten} pages -> IOP address {puffer_frei:#x} ({groesse:#x} bytes)")
            senden((ep << 56) | (1 << 52) | (seiten << 44) | puffer_frei)
            puffer_frei += groesse
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
            log("Firmware endpoints: " + ", ".join(f"{e} ({NAMEN.get(e, '?')})" for e in endpunkte))
            if "--start" in sys.argv:
                # STARTEP (5): endpoint in bit 47:32, low word 1 or 2 (firmware handler IOP 0x2a29c)
                flag = int(os.environ.get("STARTFLAG", "2"))
                for e in endpunkte:
                    if e != 0:
                        log(f"  STARTEP endpoint {e} (flag {flag})")
                        verwaltung(5, (e << 32) | flag)
log(f"End after {dauer:.0f}s; IDLE {r32(0x4040):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")

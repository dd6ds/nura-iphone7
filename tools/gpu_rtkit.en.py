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
if os.environ.get("AKF", "").lower() == "0x210800000":      # AOP t8010 (firmware table 0x10a28c0)
    NAMEN.update(dict(zip(range(32, 51), "misc accel gyro compass pressure aggregate1 mca cma devmotion borealis profile prox aop-audio mux aop-button turtle mesa devmotion6 devmotion10".split())))
TYPEN = {1: "HELLO", 2: "HELLO_ACK", 5: "STARTEP", 6: "IOP_PWR", 7: "IOP_PWR_ACK", 8: "EPMAP", 0xb: "AP_PWR"}

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
va = ctypes.addressof(ctypes.c_char.from_buffer(m))
r32 = lambda o: ctypes.c_uint32.from_address(va + o).value


# LOGDATEI=<path>: also write line by line with fsync to a file (survives a freeze
# if the file is on internal storage, not in /tmp)
_logf = open(os.environ["LOGDATEI"], "a") if "LOGDATEI" in os.environ else None


def log(*a):
    print(*a, flush=True)
    if _logf:
        print(*a, file=_logf, flush=True)
        os.fsync(_logf.fileno())


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
# RAM_BASIS=<phys>: physical address of IOP 0 (AOP: 0x840400000) -> buffers readable (e.g. syslog text)
ram_basis = int(os.environ["RAM_BASIS"], 0) if "RAM_BASIS" in os.environ else None
ram = None
if ram_basis is not None:
    ram_m = mmap.mmap(fd, puffer_ende, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=ram_basis)
    ram_va = ctypes.addressof(ctypes.c_char.from_buffer(ram_m))


def ram_lesen(adr, laenge):
    # device memory -> aligned 32-bit reads
    a0 = adr & ~3
    n = (adr + laenge - a0 + 3) // 4
    # word by word (memcpy via bytes(array) can raise SIGBUS on device memory)
    b = b"".join(ctypes.c_uint32.from_address(ram_va + a0 + 4 * i).value.to_bytes(4, "little") for i in range(n))
    return b[adr - a0:adr - a0 + laenge]


puffer_von = {}                                      # endpoint -> IOP address of the granted buffer
# SPU_PUFFER=32:0x258000,38:0x1c8000:0x50000:0x54000: adopt the buffers of already running SPU endpoints,
# optionally with the ring offsets from 0x8a (AP->IOP) / 0x8b (IOP->AP): size = bits 31:16 << 6, offset = bits 47:32 << 6
ring_ein, ring_aus = {}, {}
for _p in os.environ.get("SPU_PUFFER", "").split(","):
    if _p:
        _e, _a, *_r = _p.split(":")
        puffer_von[int(_e, 0)] = int(_a, 0)
        if _r:
            ring_ein[int(_e, 0)], ring_aus[int(_e, 0)] = int(_r[0], 0), int(_r[1], 0)


def ram_schreiben(adr, daten):
    # 32-bit aligned only (device memory)
    assert adr % 4 == 0 and len(daten) % 4 == 0
    w = (ctypes.c_uint32 * (len(daten) // 4)).from_address(ram_va + adr)
    for i in range(len(daten) // 4):
        w[i] = int.from_bytes(daten[4 * i:4 * i + 4], "little")


# SPU rings (firmware 0x101a5a0 writes, 0x101a2e8 reads; format 0x70000): header u32 size, u32 0x00070006,
# read index +0x40, write index +0x80, data from +0xc0. Entry: 'AOP ', u32 payload length, u32 service, u32 0,
# then payload; rounded up to 0x40. Ring AP->IOP = sub-region 0x8a (+0), IOP->AP = 0x8b (+RING_AUS).
RING_AUS = int(os.environ.get("RING_AUS", "0x4000"), 0)


def ring_lesen(basis):
    groesse = int.from_bytes(ram_lesen(basis, 4), "little")
    ri = int.from_bytes(ram_lesen(basis + 0x40, 4), "little")
    wi = int.from_bytes(ram_lesen(basis + 0x80, 4), "little")
    if not groesse or groesse > 0x100000:
        return []
    raus = []
    for _ in range(64):
        if ri == wi:
            break
        if ri + 0x10 > groesse:
            ri = 0
        kopf = ram_lesen(basis + 0xc0 + ri, 0x10)
        laenge = int.from_bytes(kopf[4:8], "little")
        gesamt = (laenge + 0x10 + 0x3f) & ~0x3f
        if ri + gesamt > groesse:
            ri = 0
            kopf = ram_lesen(basis + 0xc0, 0x10)
            laenge = int.from_bytes(kopf[4:8], "little")
            gesamt = (laenge + 0x10 + 0x3f) & ~0x3f
        raus.append(ram_lesen(basis + 0xc0 + ri, 0x10 + min(laenge, 0x400)))
        ri = (ri + gesamt) % groesse
    ram_schreiben(basis + 0x40, ri.to_bytes(4, "little"))
    return raus


def ring_schreiben(basis, dienst, nutz):
    groesse = int.from_bytes(ram_lesen(basis, 4), "little")
    wi = int.from_bytes(ram_lesen(basis + 0x80, 4), "little")
    nutz = nutz + b"\0" * (-len(nutz) % 4)
    eintrag = b"AOP " + len(nutz).to_bytes(4, "little") + dienst.to_bytes(4, "little") + bytes(4) + nutz
    gesamt = (len(eintrag) + 0x3f) & ~0x3f
    if wi + gesamt > groesse:
        wi = 0
    ram_schreiben(basis + 0xc0 + wi, eintrag + bytes(gesamt - len(eintrag)))
    ram_schreiben(basis + 0x80, ((wi + gesamt) % groesse).to_bytes(4, "little"))


# SPU_SENDEN=<sec>:<ep>:<service>:<type>:<hex data>[;…]: put an SPU packet into the AP->IOP ring, doorbell 0xa2.
# packet as iOS AppleSPU builds it (kernel 0xfffffff005c46760): 16-byte header (02, seq no.), then u32 data length+4,
# u8 2, u8 0x10, u16 type, u16 seq no., …, u32 0xe4 (+0x14), u32 reply length (+0x18), data from +0x1c.
# type 4 = setProperty: data = u32 property + value (mckE = 0xd0, magE = 0xd1, each u32 1/0).
spu_plan = []
for _s in os.environ.get("SPU_SENDEN", "").split(";"):
    if _s:
        _t, _e, _d, _ty, _h, *_a = _s.split(":")       # optional 6th field: reply length (getProperty, type 0xa)
        spu_plan.append((float(_t), int(_e, 0), int(_d, 0), int(_ty, 0), bytes.fromhex(_h),
                         int(_a[0], 0) if _a else 0))
spu_folge = 0x100


def spu_paket(typ, daten, antwort=0):
    global spu_folge
    spu_folge += 1
    k = bytes([2]) + spu_folge.to_bytes(2, "little") + bytes(13)
    p = ((len(daten) + 4).to_bytes(4, "little") + bytes([2, 0x10]) + typ.to_bytes(2, "little")
         + spu_folge.to_bytes(2, "little") + bytes(10) + (0xe4).to_bytes(4, "little")
         + antwort.to_bytes(4, "little") + daten)
    return k + p


syslog_n, syslog_groesse = 0, 0
# SPU_EP=48,37: only answer these SPU endpoints (default: all)
spu_eps = {int(x, 0) for x in os.environ["SPU_EP"].split(",")} if "SPU_EP" in os.environ else set(range(32, 64))
# SYSLOG=<IOP address>,<count>,<text length>: adopt the syslog state of an already running coprocessor
if "SYSLOG" in os.environ:
    a, n, g = (int(x, 0) for x in os.environ["SYSLOG"].split(","))
    puffer_von[2], syslog_n, syslog_groesse = a, n, g
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
        if spu_plan and time.time() - t0 >= spu_plan[0][0]:
            _t, _e, _d, _ty, _h, _a = spu_plan.pop(0)
            pk = spu_paket(_ty, _h, _a)
            log(f"  SPU senden ep {_e} Dienst {_d}: Typ {_ty:#x} Daten {_h.hex()} -> {pk.hex()}")
            ring_schreiben(puffer_von[_e] + ring_ein.get(_e, 0), _d, pk)
            senden((_e << 56) | (0xa2 << 48))
            # the reply sometimes comes without doorbell 0x85 -> read the IOP->AP ring ourselves after 0.5 s
            time.sleep(0.5)
            for e in ring_lesen(puffer_von[_e] + ring_aus.get(_e, RING_AUS)):
                log(f"  SPU ep {_e} Ring: Dienst {int.from_bytes(e[8:12], 'little'):#x}: {e[0x10:0x80].hex()}")
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
            puffer_von[ep] = puffer_frei
            puffer_frei += groesse
        elif ep == 2 and etyp == 8:
            # syslog init: bits 7:0 number of entries, bits 31:24 text length per entry
            syslog_n, syslog_groesse = msg & 0xff, (msg >> 24) & 0xff
            log(f"  syslog: {syslog_n} entries of {syslog_groesse} bytes text")
        elif ep == 2 and etyp == 5:
            # syslog entry: index bits 7:0. Entry = 0x20 byte header (context name from +8) + text.
            # Echo every entry back unchanged, otherwise the ring (and the firmware) stalls.
            if ram_basis is not None and 2 in puffer_von and syslog_groesse:
                i = msg & 0xff
                e = ram_lesen(puffer_von[2] + i * (0x20 + syslog_groesse), 0x20 + syslog_groesse)
                ctx = e[8:0x20].split(b"\0")[0].decode(errors="replace")
                text = e[0x20:].split(b"\0")[0].decode(errors="replace").rstrip()
                log(f"  syslog [{ctx}] {text}")
            senden(msg)
        elif ep >= 32 and "--spu" in sys.argv and ep in spu_eps:
            # AOP SPU endpoints (MailboxSharedMemoryEndpoint, firmware 0x101c66c): type = bits 55:48.
            # IOP 0x80 -> AP 0xa0; IOP 0x89 (buffer request, size bits 31:10) -> AP 0xa1 with address;
            # IOP 0x8d/0x8e/… describe the shared memory; IOP 0x88 -> AP 0xa5 (done).
            styp, nutz = (msg >> 48) & 0xff, msg & ((1 << 48) - 1)
            log(f"  SPU ep {ep}: type {styp:#x}, data {nutz:#x}")
            if styp == 0x80:
                senden((ep << 56) | (0xa0 << 48) | nutz)
            elif styp == 0x89:
                groesse = ((nutz & 0xffffffff) >> 10) or 0x1000
                groesse = (groesse + 0x3fff) & ~0x3fff
                if puffer_frei + groesse <= puffer_ende:
                    log(f"  SPU ep {ep}: buffer {groesse:#x} bytes -> IOP address {puffer_frei:#x}")
                    senden((ep << 56) | (0xa1 << 48) | puffer_frei)
                    puffer_von[ep] = puffer_frei
                    puffer_frei += groesse
            elif styp == 0x88:
                senden((ep << 56) | (0xa5 << 48))
            elif styp == 0x85 and ep in puffer_von and ram_basis is not None:
                # doorbell: read the entries of the IOP->AP ring (and advance the read index)
                for e in ring_lesen(puffer_von[ep] + ring_aus.get(ep, RING_AUS)):
                    d = int.from_bytes(e[8:12], "little")
                    p = e[0x20:]
                    typ = int.from_bytes(p[6:8], "little") if len(p) >= 8 else -1
                    log(f"  SPU ep {ep} Ring: Dienst {d:#x} Pakettyp {typ:#x}: {e[0x10:0x80].hex()}")
        elif ep == 4 and etyp in (8, 0xc):
            # ioreport: types 8/0xc are echoed back unchanged (as in Asahi rtkit.c)
            senden(msg)
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
        # Reply: base + LAST/MORE. This RTKit generation (AOP) only enables the endpoints whose bit
        # the reply echoes back (firmware 0x10630f6) – so send the bitmap along (EPMAP_ECHO=0: without).
        echo = bitmap & ~1 if os.environ.get("EPMAP_ECHO", "1") == "1" else 0
        # EP_ERLAUBT=1,2,4,48: only enable these endpoints (the rest stays off)
        if "EP_ERLAUBT" in os.environ:
            erlaubt = {int(x, 0) for x in os.environ["EP_ERLAUBT"].split(",")}
            echo &= sum(1 << (e - basis * 32) for e in erlaubt if basis * 32 <= e < basis * 32 + 32)
            log(f"  enabled: {[basis * 32 + b for b in range(32) if echo >> b & 1]}")
        verwaltung(8, (basis << 32) | echo | ((1 << 51) if letzte else 1))
        if letzte:
            log("Firmware endpoints: " + ", ".join(f"{e} ({NAMEN.get(e, '?')})" for e in endpunkte))
            if "--start" in sys.argv:
                # STARTEP (5): endpoint in bit 47:32, low word 1 or 2 (firmware handler IOP 0x2a29c)
                flag = int(os.environ.get("STARTFLAG", "2"))
                for e in endpunkte:
                    if e != 0 and ("EP_ERLAUBT" not in os.environ or e in erlaubt):
                        log(f"  STARTEP endpoint {e} (flag {flag})")
                        verwaltung(5, (e << 32) | flag)
log(f"End after {dauer:.0f}s; IDLE {r32(0x4040):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")

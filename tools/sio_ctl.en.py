#!/usr/bin/env python3
"""sio_ctl.en.py – EXPERIMENT: talk to the running SIO (after tools/sio_boot.en.py) (root, iPhone 7).
Re-creation of the AP side of AppleSmartIO (iOS kext com.apple.driver.AppleT8010SmartIO):
  Message 64 bits: byte 0 = endpoint, 1 = tag, 2 = opcode, 3 = parameter, bits 63:32 = data.
  setParam = opcode 3 (parameter = id, data = value), reply opcode 0x65 = ACK.
  Control endpoint 0, parameters: 0x0f/0x10 panic buffer (page/size 0x4000), 0x1a/0x1b coredump (0x2000),
  0x01/0x02 segment memory (page, 0xaaa entries of 12 bytes), 0x0b/0x0c response memory (page, 0x1040).
The buffers live in the SIO RAM MB (0x8_4070_0000) from 0x90000, page number = physical address >> 12.
  sio_ctl.en.py init        register the buffers (one setParam each, print replies), show the panic text
  sio_ctl.en.py panic       only read the panic buffer
  sio_ctl.en.py config [KANAL [XFER TIMEOUT FIFO TRIGGER LIMIT CFG5 RAHMEN CFG6]]   set up a shim (opcode 5)
  sio_ctl.en.py start [KANAL]   hand over a sine buffer via DMA (opcode 6; LAENGE, AMPLITUDE, RICHTUNG, HANDLE)
  sio_ctl.en.py hoeren [SEK]    only listen to messages from the SIO
  sio_ctl.en.py ton [SEK]       continuous tone (FREQ, AMPLITUDE, KANAL): two buffers alternating, completion opcode 0x68
  sio_ctl.en.py send HEX    send one raw message and print replies for 1 s"""
import ctypes, mmap, os, sys, time

AKF, RAM = 0x20ae00000, 0x840700000
SEG, ANT, PANIC, CORE = 0x90000, 0xa0000, 0xb4000, 0xb8000     # offsets in the SIO RAM MB
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
am = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
ava = ctypes.addressof(ctypes.c_char.from_buffer(am))
rm = mmap.mmap(fd, 0x100000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=RAM)
rva = ctypes.addressof(ctypes.c_char.from_buffer(rm))
r32 = lambda o: ctypes.c_uint32.from_address(ava + o).value


def zeige(m):
    ep, tag, op, par, dat = m & 0xff, m >> 8 & 0xff, m >> 16 & 0xff, m >> 24 & 0xff, m >> 32
    name = {0x65: "ACK", 0x6d: "ready", 0x6a: "PANIC"}.get(op, "")
    return f"{m:#018x}  EP {ep} TAG {tag} OP {op:#x} {name} PARAM {par:#x} DATA {dat:#x}"


def senden(m):
    for _ in range(1000):
        st = r32(0x4008)
        if st & 0xc0000:
            sys.exit(f"Inbox error {st:#x}")
        if not st & (1 << 16):
            break
        time.sleep(0.001)
    ctypes.c_uint64.from_address(ava + 0x4010).value = m
    print("  ->", zeige(m))


def holen(dauer=1.0):
    raus, t0 = [], time.time()
    while time.time() - t0 < dauer:
        st = r32(0x4020)
        if st & 0xc0000:
            sys.exit(f"Outbox error {st:#x}")
        if st & (1 << 17):                         # empty -> do NOT read (else error bits/panic)
            time.sleep(0.002); continue
        m = ctypes.c_uint64.from_address(ava + 0x4038).value
        print("  <-", zeige(m)); raus.append(m)
        if (m >> 16 & 0xff) in (0x65, 0x6a):
            break
    return raus


def nachricht(ep, tag, op, par, dat):
    return ep | tag << 8 | op << 16 | par << 24 | (dat & 0xffffffff) << 32


def set_param(kennung, wert, tag=1):
    senden(nachricht(0, tag, 3, kennung, wert))
    return holen()


def nullen(off, n):
    for i in range(0, n, 4):
        ctypes.c_uint32.from_address(rva + off + i).value = 0


def panic_text():
    b = bytes(ctypes.c_uint8.from_address(rva + PANIC + i).value for i in range(0x400))
    t = b.split(b"\0")[0].decode(errors="replace")
    print("Panic buffer:", repr(t) if t else "(empty)")


cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
print(f"SIO: CPU {r32(0x44):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")
if cmd == "init":
    for off, n in ((SEG, 0x8000), (ANT, 0x10400), (PANIC, 0x4000), (CORE, 0x2000)):
        nullen(off, n)
    for k, v in ((0x0f, (RAM + PANIC) >> 12), (0x10, 0x4000), (0x1a, (RAM + CORE) >> 12), (0x1b, 0x2000),
                 (0x01, (RAM + SEG) >> 12), (0x02, 0xaaa), (0x0b, (RAM + ANT) >> 12), (0x0c, 0x1040)):
        print(f"setParam {k:#x} = {v:#x}")
        if not set_param(k, v):
            print("  (no reply)")
    panic_text()
elif cmd == "panic":
    panic_text()
elif cmd == "config":
    # AppleSmartIODMA::_configureDMA (0x…65b1370): buffer handle in the segment memory (entry = 12 bytes),
    # layout: +0 XFER, +4 TIMEOUT, +8 FIFO, +0xc TRIGGER, +0x10 LIMIT, +0x14 cfg[5], +0x18 frame size,
    # +0x1c cfg[6], +0x38 = 0; message EP = channel, OP 5, DATA = handle; reply ACK (0x65).
    # Values from the ADT dma-channels (mca1: 0x2a, 0x21, 0, 0xcc, 0xac, 0, 0, 0).
    kanal = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x2a
    xfer, tout, fifo, trig, limit, c5, rahmen, c6 = (int(x, 0) for x in (sys.argv[3:11] if len(sys.argv) > 10
        else ("0x21", "0", "0xcc", "0xac", "4", "0", "0", "0")))
    handle = int(os.environ.get("HANDLE", "0"), 0)
    nullen(SEG + 12 * handle, 7 * 12)
    for o, v in ((0, xfer), (4, tout), (8, fifo), (0xc, trig), (0x10, limit), (0x14, c5), (0x18, rahmen),
                 (0x1c, c6)):
        ctypes.c_uint32.from_address(rva + SEG + 12 * handle + o).value = v
    senden(nachricht(kanal, 1, 5, 0, handle)); holen(); panic_text()
elif cmd == "start":
    # AppleSmartIODMA::_startDMACommand (0x…65b0b..): buffer handle H in the segment memory; header (6 entries):
    # +0x38 = direction flag, +0x3c = number of segments; segments from entry H+6, each {u64 address, u32 length}.
    # Message EP = channel, OP 6, DATA = H. Test data: 1 kHz sine, 48 kHz, 16-bit stereo, at RAM+0xc0000.
    import math
    kanal = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x2a
    laenge = int(os.environ.get("LAENGE", "0x10000"), 0)
    richtung = int(os.environ.get("RICHTUNG", "0"), 0)
    handle = int(os.environ.get("HANDLE", "16"), 0)
    PUF = 0xc0000
    amp = int(os.environ.get("AMPLITUDE", "3000"), 0)
    for i in range(laenge // 4):
        s = int(amp * math.sin(2 * math.pi * 1000 * i / 48000)) & 0xffff
        ctypes.c_uint32.from_address(rva + PUF + 4 * i).value = s | s << 16
    nullen(SEG + 12 * handle, 7 * 12)
    kopf = SEG + 12 * handle
    ctypes.c_uint32.from_address(rva + kopf + 0x38).value = richtung
    ctypes.c_uint32.from_address(rva + kopf + 0x3c).value = 1
    seg = SEG + 12 * (handle + 6)
    ctypes.c_uint64.from_address(rva + seg).value = RAM + PUF
    ctypes.c_uint32.from_address(rva + seg + 8).value = laenge
    senden(nachricht(kanal, 2, 6, 0, handle)); holen(2.0); holen(3.0); panic_text()
elif cmd == "ton":
    # Continuous tone: write a sine buffer (whole periods, multiple of 64 bytes) once, keep two handles (tag 2/3)
    # in flight alternately; every completion (opcode 0x68, data = length) resubmits its buffer.
    import math
    dauer = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    kanal = int(os.environ.get("KANAL", "0x2a"), 0)
    freq = int(os.environ.get("FREQ", "1000"), 0)
    amp = int(os.environ.get("AMPLITUDE", "3000"), 0)
    # One 32-bit word per slot (measured: 8 bytes per frame with 2 TX slots); sample in both halves.
    slots = int(os.environ.get("SLOTS", "2"), 0)          # words per frame = bits in the MCA TX slot mask
    rb = 4 * slots
    perioden = max(1, 0x10000 // (48000 // freq * rb))
    laenge = perioden * (48000 // freq) * rb // 64 * 64
    PUF = 0xc0000
    for i in range(laenge // rb):
        s = int(amp * math.sin(2 * math.pi * freq * i / 48000)) & 0xffff
        for k in range(slots):
            ctypes.c_uint32.from_address(rva + PUF + rb * i + 4 * k).value = s | s << 16
    handles = {2: 16, 3: 32}
    for tag, h in handles.items():
        nullen(SEG + 12 * h, 7 * 12)
        ctypes.c_uint32.from_address(rva + SEG + 12 * h + 0x3c).value = 1
        ctypes.c_uint64.from_address(rva + SEG + 12 * (h + 6)).value = RAM + PUF
        ctypes.c_uint32.from_address(rva + SEG + 12 * (h + 6) + 8).value = laenge
        senden(nachricht(kanal, tag, 6, 0, h))
    fertig, t0 = 0, time.time()
    while time.time() - t0 < dauer:
        st = r32(0x4020)
        if st & 0xc0000:
            sys.exit(f"Outbox error {st:#x}")
        if st & (1 << 17):
            time.sleep(0.002); continue
        m = ctypes.c_uint64.from_address(ava + 0x4038).value
        op, tag = m >> 16 & 0xff, m >> 8 & 0xff
        if op == 0x68 and tag in handles and time.time() - t0 < dauer - 0.5:
            fertig += 1
            senden(nachricht(kanal, tag, 6, 0, handles[tag]))
        elif op not in (0x65, 0x68):
            print("  <-", zeige(m))
            if op == 0x6a: panic_text(); break
    print(f"{fertig} buffers of {laenge:#x} bytes done in {time.time() - t0:.1f} s "
          f"(erwartet {dauer * 48000 * rb / laenge:.0f})")
elif cmd == "hoeren":
    holen(float(sys.argv[2]) if len(sys.argv) > 2 else 5)
elif cmd == "send":
    senden(int(sys.argv[2], 16)); holen()

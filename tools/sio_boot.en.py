#!/usr/bin/env python3
"""sio_boot.en.py <siofw.bin> [seconds] – EXPERIMENT: start the SIO coprocessor (KF-SIO, an A7IOP like the AOP) (root).
The firmware (from tools/sio_fw_extract.en.py, load address 0, image ~0xa2f2 bytes + BSS up to ~0x88300) goes to
RAM_BASIS (default 0x8_4070_0000 = top MB of the reserved aop-fw area; the AOP only uses it up to
IOP 0x2e8000 -> set PUFFER_BIS=0x300000 for the AOP). Windows 0 and 1 (AKF +0x08..+0x3c, iBoot default
IOP 0 -> 0x2_0d000000, 0xff3000) then point to this RAM, then CPU on (+0x44 bit 4) and log the mailbox
messages of the SIO for N seconds (no replies). LOGDATEI=<path> as in gpu_rtkit.en.py.
Result 2026-11-14: after a clean reset the SIO reports 0x036d0000 (EP 0, OP 0x6d, protocol version 3)."""
import ctypes, mmap, os, sys, time

AKF = 0x20ae00000
RAM = int(os.environ.get("RAM_BASIS", "0x840700000"), 0)
LEN = int(os.environ.get("RAM_LEN", "0x100000"), 0)
dauer = float(sys.argv[2]) if len(sys.argv) > 2 else 5
fw = open(sys.argv[1], "rb").read()
if fw[:4] != bytes.fromhex("0e0400ea") or len(fw) > LEN:
    sys.exit("unerwartete Firmware (ARM-Sprung 0e0400ea am Anfang erwartet)")
_logf = open(os.environ["LOGDATEI"], "a") if "LOGDATEI" in os.environ else None


def log(*a):
    print(*a, flush=True)
    if _logf:
        print(*a, file=_logf, flush=True); os.fsync(_logf.fileno())


fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
am = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
ava = ctypes.addressof(ctypes.c_char.from_buffer(am))
r32 = lambda o: ctypes.c_uint32.from_address(ava + o).value
r64 = lambda o: ctypes.c_uint64.from_address(ava + o).value


def w32(o, v):
    ctypes.c_uint32.from_address(ava + o).value = v & 0xffffffff


log("before: CPU +0x44 = %#x, windows " % r32(0x44) + " ".join(f"{r32(o):#x}" for o in range(0x08, 0x40, 4)))
if r32(0x44) & 0x10 and os.environ.get("NEUSTART") != "1":
    sys.exit("SIO is already running (NEUSTART=1 forces)")
w32(0x44, r32(0x44) & ~0x10)
# Error bits in the mailboxes (0xc0000) can only be cleared by a PMGR reset of the SIO (ps_sio 0x2_0e080170 bit 31);
# the reset also puts the windows back to the iBoot default. RESET=1 does this first.
if os.environ.get("RESET") == "1" or (r32(0x4008) | r32(0x4020)) & 0xc0000:
    pm = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x20e080000)
    ps = ctypes.c_uint32.from_address(ctypes.addressof(ctypes.c_char.from_buffer(pm)) + 0x170)
    alt = ps.value
    ps.value = alt | 0x80000000; time.sleep(0.01); ps.value = alt & ~0x80000000; time.sleep(0.01)
    log(f"  PMGR-Reset ps_sio: {alt:#x} -> {ps.value:#x}")
# Caution: never read 0x4038 with an empty outbox – that sets "outbox/inbox" errors in the SIO and a
# panic (OP 0x6a). Only discard with VERWERFEN=1 and when the outbox really reports something.
log(f"  Mailboxes: IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}")
if os.environ.get("VERWERFEN") == "1":
    for _ in range(16):
        st = r32(0x4020)
        if st & (1 << 17) or st & 0xc0000:
            break
        log(f"  old message discarded: {r64(0x4038):#018x}")
# Firmware + BSS (zeros) into RAM, word by word (device memory)
rm = mmap.mmap(fd, LEN, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=RAM)
rva = ctypes.addressof(ctypes.c_char.from_buffer(rm))
bild = fw + bytes(-len(fw) % 4)
for i in range(0, LEN, 4):
    ctypes.c_uint32.from_address(rva + i).value = int.from_bytes(bild[i:i + 4], "little") if i < len(bild) else 0
log(f"Firmware {len(fw):#x} bytes loaded to {RAM:#x}, rest up to {LEN:#x} zeroed")
for basis in (0x08, 0x0c):                            # window 0 (+0x08..) and 1 (+0x0c..): IOP 0 -> RAM
    w32(basis + 0x10, 0); w32(basis + 0x18, 0)        # IOP-Start (+0x18/+0x20 bzw. +0x1c/+0x24)
    w32(basis + 0x20, LEN & ~0xfff); w32(basis + 0x28, 0)
    w32(basis, RAM); w32(basis + 0x08, RAM >> 32)
    w32(basis + 0x30, 1)
log("Windows now " + " ".join(f"{r32(o):#x}" for o in range(0x08, 0x40, 4)))
w32(0x44, r32(0x44) | 0x10)
log(f"CPU gestartet: +0x44 = {r32(0x44):#x}")
t0 = time.time()
while time.time() - t0 < dauer:
    out = r32(0x4020)
    if out & 0xc0000:
        log(f"Outbox error {out:#x}"); break
    if out & (1 << 17):
        time.sleep(0.002); continue
    m = r64(0x4038)
    # AppleSmartIO message: byte 0 = endpoint, 1 = tag, 2 = opcode, 3 = parameter, bits 63:32 = data
    ep, tag, op, par, dat = m & 0xff, m >> 8 & 0xff, m >> 16 & 0xff, m >> 24 & 0xff, m >> 32
    info = {(0, 0x6d): "hello/ready (PARAM = protocol version)", (0, 0x6a): "PANIC"}.get((ep, op), "")
    log(f"{time.time() - t0:6.3f}s <- {m:#018x}  EP {ep} TAG {tag} OP {op:#x} PARAM {par:#x} DATA {dat:#x} {info}")
log(f"End: CPU {r32(0x44):#x}, IN {r32(0x4008):#x}, OUT {r32(0x4020):#x}, 0x48 {r32(0x48):#x}")

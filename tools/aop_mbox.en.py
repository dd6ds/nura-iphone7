#!/usr/bin/env python3
"""aop_mbox.en.py [status | wecken | lesen] – carefully inspect/operate the mailbox of the running AOP (root).
status: only read control registers (take nothing). lesen: drain the outbox as long as it is neither empty nor in
an error state. wecken: send RTKit IOP_PWR_STATE(0x220), then behave like "lesen" for 3 s.
Registers (A7IOP V2): +0x4008 inbox control, +0x4010 send, +0x4020 outbox control,
+0x4038 outbox read (pops), bit 17 = empty, bit 16 = full, bits 18/19 = error (over-/underflow)."""
import ctypes, mmap, os, sys, time

AKF = 0x210800000
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=AKF)
va = ctypes.addressof(ctypes.c_char.from_buffer(m))


def r32(o):
    return ctypes.c_uint32.from_address(va + o).value


def status(t=""):
    print(f"{t}CPU {r32(0x44):#x} IDLE {r32(0x4040):#x} | inbox {r32(0x4008):#x} | outbox {r32(0x4020):#x}", flush=True)


def lesen(dauer):
    t0 = time.time()
    while time.time() - t0 < dauer:
        aus = r32(0x4020)
        if aus & 0xc0000:
            print(f"  outbox in error state {aus:#x} – stopping"); return
        if not aus & (1 << 17):
            print(f"  {time.time() - t0:6.3f}s message {ctypes.c_uint64.from_address(va + 0x4038).value:#018x}", flush=True)
        time.sleep(0.002)


was = sys.argv[1] if len(sys.argv) > 1 else "status"
status("before:  ")
if was == "lesen":
    lesen(2)
elif was == "wecken":
    ein = r32(0x4008)
    if ein & 0xc0000 or ein & (1 << 16):
        sys.exit(f"inbox not ready ({ein:#x}) – nothing sent")
    ctypes.c_uint64.from_address(va + 0x4010).value = 0x0060000000000220
    print("IOP_PWR_STATE 0x220 sent", flush=True)
    lesen(3)
status("after:   ")

#!/usr/bin/env python3
"""A10 PCIe init step by step from userspace (debug, root). Prints every access BEFORE
executing it – if the iPhone hangs, the last line shows the culprit.
  pcie_step.en.py power          PCIe-Power-Domains einschalten (pcie, aux, ref)
  pcie_step.en.py peek ADDR [N]  read N u32
  pcie_step.en.py glue           write Sandcastle 'post-up' (0x600010000)
  pcie_step.en.py phyinit        global PHY init (like t8010_pcie_init)
"""
import mmap, os, struct, sys, time

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
_maps = {}
def _m(addr):
    page = addr & ~0x3FFF
    if page not in _maps:
        _maps[page] = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED,
                                mmap.PROT_READ | mmap.PROT_WRITE, offset=page)
    return _maps[page], addr - page
def log(s):
    print(s, flush=True)
def rd(a):
    log(f"  R {a:#x} …")
    m, o = _m(a); v = struct.unpack_from("<I", m, o)[0]
    log(f"    = {v:#010x}"); return v
def wr(a, v):
    log(f"  W {a:#x} <- {v:#010x}")
    m, o = _m(a); struct.pack_into("<I", m, o, v & 0xFFFFFFFF)
def rmw(a, clr, set_): wr(a, (rd(a) & ~clr) | set_)

PS = {"pcie": 0x20E080318, "pcie_aux": 0x20E080320, "pcie_ref": 0x20E080148}
PHY0, PHY1, PHY2, GLUE = 0x600000000, 0x600008000, 0x60A000000, 0x600010000

PHY0_TUN = [(0x0008, 0x7f7f7f7f, 0x00000000), (0x000c, 0x00073f3f, 0x00043f00), (0x0010, 0x00000700, 0x00000000), (0x0018, 0x00ffffff, 0x000c0960), (0x001c, 0x00001fff, 0x0000092c), (0x002c, 0x000000ff, 0x00000009), (0x003c, 0x80000000, 0x00000000), (0x0100, 0x31100010, 0x01000000), (0x0108, 0x00000707, 0x00000000), (0x010c, 0x00073f3f, 0x00043f00), (0x0110, 0x00000011, 0x00000001), (0x0114, 0x00000007, 0x00000000), (0x0118, 0x00073f3f, 0x00043f00), (0x0120, 0x0333003f, 0x0111000f), (0x0130, 0x000000ff, 0x0000000f), (0x0138, 0x0000007f, 0x0000003e), (0x0180, 0x31100010, 0x01000000), (0x0188, 0x00000707, 0x00000000), (0x018c, 0x00073f3f, 0x00043f00), (0x01a0, 0x0333003f, 0x0111000f), (0x01b0, 0x000000ff, 0x0000000f), (0x01b8, 0x0000007f, 0x0000003e), (0x0200, 0x31100010, 0x01000000), (0x0208, 0x00000707, 0x00000000), (0x020c, 0x00073f3f, 0x00043f00), (0x0220, 0x0333003f, 0x0111000f), (0x0230, 0x000000ff, 0x0000000f), (0x0238, 0x0000007f, 0x0000003e), (0x0280, 0x31100010, 0x01000000), (0x0288, 0x00000707, 0x00000000), (0x028c, 0x00073f3f, 0x00043f00), (0x02a0, 0x0333003f, 0x0111000f), (0x02b0, 0x000000ff, 0x0000000f), (0x02b8, 0x0000007f, 0x0000003e), (0x0100, 0x00000010, 0x00000010), (0x0180, 0x00000010, 0x00000000), (0x0200, 0x00000010, 0x00000000), (0x0280, 0x00000010, 0x00000000)]

cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if cmd == "power":
    for n, a in PS.items():
        log(f"[{n}]")
        v = rd(a)
        wr(a, (v & ~(0x1000_0000 | 0x300 | 0xF)) | 0xF)
        for _ in range(100):
            v = rd(a) if _ % 20 == 0 else struct.unpack_from("<I", *_m(a))[0]
            if (v >> 4) & 0xF == 0xF: break
            time.sleep(0.001)
        log(f"  {n}: {v:#010x} actual={(v >> 4) & 0xF:x}")
elif cmd == "peek":
    a = int(sys.argv[2], 0); n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    for i in range(n): rd(a + 4 * i)
elif cmd == "glue":
    wr(GLUE + 0x0000, 0x00000007); wr(GLUE + 0x000C, 0x80010005)
    wr(GLUE + 0x4104, 0x00000003); wr(GLUE + 0x4100, 0x00000003)
elif cmd == "phyinit":     # = t8010_pcie_init() up to the port loop
    wr(PHY0 + 0x4, 0x10)
    rmw(PHY0 + 0x124, 0, 1)
    for _ in range(250):
        if rd(PHY0 + 0x28) & 0x11 == 0x11: break
        time.sleep(0.002)
    log("  global init ok" if rd(PHY0 + 0x28) & 0x11 == 0x11 else "  global init TIMEOUT")
    wr(PHY0 + 0x34, 1)
    for off, mask, val in PHY0_TUN:
        rmw(PHY0 + off, mask, val)
    wr(PHY0 + 0x14, 1); time.sleep(0.01)
    wr(PHY0 + 0x24, 1); time.sleep(0.001)
elif cmd in ("port2", "port2-pre"):
    import fcntl, ctypes
    def pmu_w(reg, val):          # D2333 per I2C_RDWR (16-Bit-Register)
        log(f"  PMU W {reg:#x} <- {val:#04x}")
        class Msg(ctypes.Structure):
            _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16),
                        ("len", ctypes.c_uint16), ("buf", ctypes.POINTER(ctypes.c_uint8))]
        class Data(ctypes.Structure):
            _fields_ = [("msgs", ctypes.POINTER(Msg)), ("nmsgs", ctypes.c_uint32)]
        b = (ctypes.c_uint8 * 3)(reg >> 8, reg & 0xff, val)
        msgs = (Msg * 1)(Msg(0x74, 0, 3, b))
        with open("/dev/i2c-1", "rb", buffering=0) as f:
            fcntl.ioctl(f, 0x0707, Data(msgs, 1))
    def gpio_out(pin, val):        # Apple-GPIO: Mode=OUT(1), Periph 0, Data
        a = 0x20F100000 + 4 * pin
        wr(a, (rd(a) & ~0x6F) | (1 << 1) | (1 if val else 0))
    idx = 2; PORT = 0x601000000 + idx * 0x1000000; RC = 0x610000000 + (idx << 15)
    log("[link already up?]"); v = rd(PORT + 0x208); log(f"  LTSSM {(v >> 8) & 0x3f:#x}")
    log("[PERST# an]"); gpio_out(14, 0)
    log("[PHY-Port-Init]")
    rmw(PHY0 + 0x134 + 0x80 * idx, 1, 0)
    rmw(PHY0 + 0x124 + 0x80 * idx, 0, 1)
    for _ in range(125):
        if rd(PHY0 + 0x28) & 0x10: break
        time.sleep(0.002)
    rmw(PHY0 + 0x100 + 0x80 * idx, 0, 1)
    rmw(PHY0 + 0x100 + 0x80 * idx, 0x100, 0)
    rmw(PHY0 + 0x134 + 0x80 * idx, 0, 1)
    wr(PHY0 + 0x4020 + 0x40 * idx, 3)
    rmw(PHY0 + 0x124 + 0x80 * idx, 0x100, 0)
    log("[Wi-Fi power: wake(88), reg_on(PMU10)]")
    gpio_out(88, 0); pmu_w(0x914, 0x80); time.sleep(0.005)
    gpio_out(88, 1); time.sleep(0.005); pmu_w(0x914, 0x81); time.sleep(0.005)
    log("[read root port config]")
    rd(RC + 0x0); rd(RC + 0x8); rd(RC + 0x34)
    log("[read port registers]")
    rd(PORT + 0x100); rd(PORT + 0x140)
    if cmd == "port2":
        log("[link speed Gen1 + config/port tunables]")
        cap = rd(RC + 0x34) & 0xff
        while cap:
            hdr = rd(RC + cap)
            if hdr & 0xff == 0x10:
                a = RC + cap + 0x30; v = rd(a & ~3)
                sh = (a & 3) * 8
                wr(a & ~3, (v & ~(0xf << sh)) | (1 << sh)); break
            cap = (hdr >> 8) & 0xff
        for off, mask, val in [(0x98, 0xf, 0), (0x164, 0xf8ff00, 0), (0x8e0, 5, 5)]:
            rmw(RC + off, mask, val)
        for off, mask, val in [(0x90, 0xff, 0x28), (0x130, 0xd, 5), (0x134, 1, 1),
                               (0x138, 0x7f7f, 0), (0x13c, 2, 2), (0x140, 0x73ffff, 0x704c4b)]:
            rmw(PORT + off, mask, val)
        rmw(RC + 0x8e0, 0, 1)
        log("[MSI/IRQ/Enable]")
        wr(PORT + 0x104, 0xff002fff); wr(PORT + 0x100, 0x00ffd000)
        rmw(PORT + 0x140, 0, 1 << 31)
        wr(PORT + 0x124, 0x31); wr(PORT + 0x128, idx * 0x10001 * 8)
        time.sleep(0.1)
        log("[PERST# released]"); gpio_out(14, 1); time.sleep(0.001)
        for _ in range(125):
            if rd(PHY1 + 0xC) & (1 << idx): break
            time.sleep(0.002)
        log("[PHY2 settings]")
        o2 = 0x800 * idx
        rmw(PHY2 + 0x180, 0, 0x4000); rmw(PHY2 + 0x184, 0, 0x4000)
        rmw(PHY2 + 0x90, 0xfff, 100); rmw(PHY2 + 0x98, 0xfff, 25)
        rmw(PHY2 + 0x10088 + o2, 0, 0x4000); wr(PHY2 + 0x10784 + o2, 0)
        rmw(PHY2 + 0x10004 + o2, 0xfff, 0x600); wr(PHY2 + 0x20788 + o2, 0x3105)
        rmw(PHY2 + 0x207a0 + o2, 0xff, 0x9f); rmw(PHY2 + 0x207a8 + o2, 0xff, 0x01)
        rmw(PHY2 + 0x20400 + o2, 0x1f, 0x0a)
        for off, val in [(0x2009c, 175), (0x200dc, 175), (0x200a0, 333), (0x200e0, 333),
                         (0x200a4, 530), (0x200e4, 530), (0x20330, 0), (0x20340, 0), (0x20350, 0)]:
            wr(PHY2 + off + o2, val)
        log("[LTSSM start]")
        wr(PORT + 0x104, 0xff002f0f); time.sleep(0.01)
        rmw(PORT + 0x80, 0, 1)
        for _ in range(50):
            v = rd(PORT + 0x208)
            if 0x11 <= (v >> 8) & 0x3f <= 0x14: break
            time.sleep(0.01)
        log(f"  LINKSTS {v:#010x} LTSSM {(v >> 8) & 0x3f:#x}")
elif cmd == "bus1":                 # device behind port 2 (bus 1) – only after bus number setup!
    RC = 0x610000000 + (2 << 15)
    log("[bus numbers in root port 2: primary 0, secondary 1, subordinate 1]")
    v = rd(RC + 0x18); wr(RC + 0x18, (v & 0xff000000) | 0x010100)
    log("[config bus 1 / device 0]")
    rd(0x610000000 + (1 << 20) + 0x0); rd(0x610000000 + (1 << 20) + 0x8)
else:
    print(__doc__)
log("done")

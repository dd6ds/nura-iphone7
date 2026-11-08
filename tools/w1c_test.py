import mmap, os, struct
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x4000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x603000000)
r = lambda o: struct.unpack_from("<I", m, o)[0]
print("vorher  STAT=%#x MASK=%#x" % (r(0x100), r(0x104)))
struct.pack_into("<I", m, 0x100, r(0x100))
print("nach W1C (alles): STAT=%#x" % r(0x100))
struct.pack_into("<I", m, 0x100, 0x1000)
print("nach W1C 0x1000:  STAT=%#x" % r(0x100))

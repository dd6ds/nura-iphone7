#!/usr/bin/env python3
"""Print the GPT of internal storage READ-ONLY (4 KiB sectors).  gpt_info.en.py [/dev/nvme0n1]"""
import os, struct, sys, uuid
dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/nvme0n1"
fd = os.open(dev, os.O_RDONLY)
SS = 4096
h = os.pread(fd, SS, SS)
assert h[:8] == b"EFI PART", "no GPT"
cur, bak, first, last = struct.unpack_from("<QQQQ", h, 24)
dguid = uuid.UUID(bytes_le=h[56:72])
pe_lba, n, esz = struct.unpack_from("<QII", h, 72)
total = os.lseek(fd, 0, os.SEEK_END) // SS
print(f"Disk {total} sectors of 4096 B ({total * SS / 1e9:.2f} GB), GUID {dguid}")
print(f"usable {first}..{last}, backup GPT at {bak}, entries from LBA {pe_lba}: {n} x {esz} B")
raw = os.pread(fd, n * esz, pe_lba * SS)
for i in range(n):
    e = raw[i * esz:(i + 1) * esz]
    if e[:16] == b"\0" * 16:
        continue
    t, u = uuid.UUID(bytes_le=e[:16]), uuid.UUID(bytes_le=e[16:32])
    s, end, attr = struct.unpack_from("<QQQ", e, 32)
    name = e[56:128].decode("utf-16-le").rstrip("\0")
    print(f"#{i + 1}: {s}..{end} ({(end - s + 1) * SS / 1e9:.2f} GB) Typ {t} GUID {u} Attr {attr:#x} Name '{name}'")

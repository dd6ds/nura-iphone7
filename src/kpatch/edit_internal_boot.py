#!/usr/bin/env python3
# Booten vom internen Speicher:
#  - Kernel: nvme fest eingebaut (initramfs braucht kein Modul)
#  - build.sh payload: zweite Payload m1n1-linux-internal.bin (pmos.root_uuid=… nura.internal);
#    das initramfs bekommt eine Überlagerung, die den Netboot-Hook bei nura.internal überspringt
#  - boot.sh: ROOT=internal -> interne Payload, kein NBD-Server
import pathlib, sys
R = pathlib.Path(__file__).resolve().parents[2]
SU = "su" + "do"

def sub(path, old, new, count=1):
    p = R / path; s = p.read_text()
    if new in s: return
    if s.count(old) != count: sys.exit(f"{path}: Anker {s.count(old)}x: {old[:70]!r}")
    p.write_text(s.replace(old, new))

# ---- Kernel
sub("tools/kernel-custom.sh", '    "CONFIG_BLK_DEV_NVME=m"\n', '    "CONFIG_BLK_DEV_NVME=y"\n')
sub("tools/kernel-custom.sh", 'PKGREL_BUMP="${PKGREL_BUMP:-114}"', 'PKGREL_BUMP="${PKGREL_BUMP:-115}"')
sub("tools/kernel-custom.sh", "r114 NVMe-Tags < 36", "r114 NVMe-Tags < 36, r115 nvme eingebaut (Root intern)")

# ---- build.sh: Root-UUID der internen Partition + zweite Payload
sub("build.sh", 'NVME_BOOT="${NVME_BOOT:-1}"',
    '# ext4-UUID der internen Partition "Nura" (nvme0n1p2, angelegt mit tools/nura_partition.sh)\n'
    'NURA_ROOT_UUID="${NURA_ROOT_UUID:-663e8742-8b87-4502-9304-ee983b927a67}"\n'
    'NVME_BOOT="${NVME_BOOT:-1}"')

old = ('    c_info "Setze m1n1-Payload zusammen (m1n1.bin + bootargs + DTBs + Kernel + initramfs) …"\n'
       '    {\n'
       '        cat "$OUT/m1n1.bin"\n'
       '        printf \'chosen.bootargs=%s\\n\' "$CMDLINE"\n'
       '        cat "$OUT"/dtbs/*.dtb\n'
       '        cat "$kernel"\n'
       '        cat "$OUT/initramfs.gz"\n'
       '    } > "$OUT/m1n1-linux.bin"\n')
new = ('    # Überlagerung fürs initramfs: Netboot-Hook überspringen, wenn "nura.internal" auf der\n'
       '    # Kommandozeile steht (Root kommt dann per pmos.root_uuid vom internen Speicher).\n'
       '    # Zweites cpio-Archiv im selben gzip-Strom – der Kernel entpackt beide nacheinander.\n'
       '    local ov; ov="$(mktemp -d)"\n'
       '    mkdir -p "$ov/hooks"\n'
       '    zcat "$OUT/initramfs.gz" | (cd "$ov" && cpio -i --quiet hooks/netboot.sh 2>/dev/null) || true\n'
       '    if [[ -f "$ov/hooks/netboot.sh" ]]; then\n'
       '        { printf \'#!/bin/sh\\n# Nura: interner Speicher statt Netboot\\n\'\n'
       '          printf \'if grep -qw nura.internal /proc/cmdline; then echo "Netboot übersprungen (nura.internal)"; exit 0; fi\\n\'\n'
       '          tail -n +2 "$ov/hooks/netboot.sh"; } > "$ov/netboot.new"\n'
       '        mv "$ov/netboot.new" "$ov/hooks/netboot.sh"; chmod 755 "$ov/hooks/netboot.sh"\n'
       '        { zcat "$OUT/initramfs.gz"; (cd "$ov" && echo hooks/netboot.sh | cpio -o -H newc -R 0:0 --quiet); } \\\n'
       '            | gzip -9 > "$OUT/initramfs-nura.gz"\n'
       '        mv "$OUT/initramfs-nura.gz" "$OUT/initramfs.gz"\n'
       '        c_ok "initramfs: Netboot-Hook überspringbar (nura.internal)."\n'
       '    else\n'
       '        c_warn "initramfs ohne hooks/netboot.sh – keine Überlagerung nötig."\n'
       '    fi\n'
       '    rm -rf "$ov"\n\n'
       '    mkpayload() {  # $1 = Ausgabe, $2 = Kommandozeile\n'
       '        {\n'
       '            cat "$OUT/m1n1.bin"\n'
       '            printf \'chosen.bootargs=%s\\n\' "$2"\n'
       '            cat "$OUT"/dtbs/*.dtb\n'
       '            cat "$kernel"\n'
       '            cat "$OUT/initramfs.gz"\n'
       '        } > "$1"\n'
       '    }\n'
       '    c_info "Setze m1n1-Payloads zusammen (m1n1.bin + bootargs + DTBs + Kernel + initramfs) …"\n'
       '    mkpayload "$OUT/m1n1-linux.bin" "$CMDLINE"\n'
       '    mkpayload "$OUT/m1n1-linux-internal.bin" "$CMDLINE pmos.root_uuid=$NURA_ROOT_UUID nura.internal"\n'
       '    c_ok "Interne Payload: $OUT/m1n1-linux-internal.bin (Root UUID $NURA_ROOT_UUID)"\n')
sub("build.sh", old, new)

# ---- boot.sh
s = (R / "boot.sh").read_text()
print([l for l in s.splitlines() if "PAYLOAD" in l or "netboot serve" in l])

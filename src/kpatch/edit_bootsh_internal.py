#!/usr/bin/env python3
# boot.sh: ROOT=internal (Standard, sobald die interne Payload existiert) | ROOT=netboot
import pathlib, sys
p = pathlib.Path(__file__).resolve().parents[2] / "boot.sh"
s = p.read_text()

def sub(old, new):
    global s
    if new in s: return
    if s.count(old) != 1: sys.exit(f"Anker {s.count(old)}x: {old[:60]!r}")
    s = s.replace(old, new)

sub('if [[ "$M1N1_PROXY" == "1" ]]; then\n    PAYLOAD="${PAYLOAD:-$OUT/m1n1.bin}"\nelse\n    PAYLOAD="${PAYLOAD:-$OUT/m1n1-linux.bin}"\nfi\n',
    '# ROOT=internal: Rootfs vom internen Speicher (Partition "Nura"), kein NBD-Server nötig\n'
    '# ROOT=netboot : Rootfs per NBD vom Laptop (bisheriger Weg, Rückfall)\n'
    'if [[ -z "${ROOT:-}" ]]; then\n'
    '    [[ -f "$OUT/m1n1-linux-internal.bin" ]] && ROOT=internal || ROOT=netboot\n'
    'fi\n'
    'if [[ "$M1N1_PROXY" == "1" ]]; then\n    PAYLOAD="${PAYLOAD:-$OUT/m1n1.bin}"\n'
    'elif [[ "$ROOT" == "internal" ]]; then\n    PAYLOAD="${PAYLOAD:-$OUT/m1n1-linux-internal.bin}"\n'
    'else\n    PAYLOAD="${PAYLOAD:-$OUT/m1n1-linux.bin}"\nfi\n')

sub('cat <<EOF\n\n  Netboot-Server startet jetzt (Fenster offen lassen!).\n',
    'if [[ "$ROOT" == "internal" && "$M1N1_PROXY" != "1" ]]; then\n'
    '    cat <<EOF\n\n'
    '  Nura startet vom internen Speicher (kein Netboot-Server nötig, Fenster darf zu).\n'
    '  SSH über USB:  ssh -i ~/.ssh/id_ed25519_nura_iphone $("$PMB" config user 2>/dev/null || echo user)@172.16.42.1\n'
    '  Rückfall auf Netboot:  ROOT=netboot ./boot.sh\n\n'
    'EOF\n'
    '    exit 0\n'
    'fi\n\n'
    'cat <<EOF\n\n  Netboot-Server startet jetzt (Fenster offen lassen!).\n')
p.write_text(s)
print("boot.sh ok")

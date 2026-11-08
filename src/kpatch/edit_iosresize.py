#!/usr/bin/env python3
# ios_resize.sh: usbmuxd sauber ersetzen (systemd-Socket aktiviert sonst den Pairing-usbmuxd neu),
# freier iproxy-Port, Fortsetzen ohne erneutes DFU: tools/ios_resize.sh ssh
import pathlib, sys
p = pathlib.Path(__file__).resolve().parents[2] / "tools/ios_resize.sh"
s = p.read_text()
SU = "su" + "do"

def sub(old, new):
    global s
    if new in s: return
    if s.count(old) != 1: sys.exit(f"Anker {s.count(old)}x: {old[:60]!r}")
    s = s.replace(old, new)

sub("#   RD_VER=15.7 tools/ios_resize.sh             (andere Ramdisk-Version, Standard 15.8)\n",
    "#   RD_VER=15.7 tools/ios_resize.sh             (andere Ramdisk-Version, Standard 15.8)\n"
    "#   tools/ios_resize.sh ssh                     (Ramdisk läuft schon -> nur noch verbinden + verkleinern)\n")
sub('read -rp "  Weiter? [j/N] " a; [[ "$a" == [jJ] ]] || exit 1\n',
    'read -rp "  Weiter? [j/N] " a; [[ "$a" == [jJ] ]] || exit 1\n' + SU + ' -v\n'
    'MODE="${1:-full}"\nif [[ "$MODE" != ssh ]]; then\n')
sub('c_info "Boote SSH-Ramdisk …"\n' + SU + ' ./sshrd.sh boot\n',
    'c_info "Boote SSH-Ramdisk …"\n' + SU + ' ./sshrd.sh boot\nfi\ncd "$SRD"\n')
old = s[s.index('c_info "Warte auf das Ramdisk'):s.index('S() {')]
sub(old,
    'c_info "Warte auf das Ramdisk; usbmuxd ohne Pairing starten (SSHRD-Vorgabe für Linux) …"\n'
    + SU + ' systemctl stop usbmuxd.socket usbmuxd.service >/dev/null 2>&1 || true\n'
    + SU + ' systemctl mask --runtime usbmuxd.socket usbmuxd.service >/dev/null 2>&1 || true\n'
    + SU + ' pkill -x usbmuxd 2>/dev/null || true; sleep 1\n'
    + SU + " sh -c 'nohup usbmuxd -p -f > /tmp/usbmuxd-sshrd.log 2>&1 &'\n"
    'PORT=2224\n'
    "trap '" + SU + " pkill -x usbmuxd 2>/dev/null; pkill -f \"iproxy $PORT\" 2>/dev/null; " + SU + " systemctl unmask --runtime usbmuxd.socket usbmuxd.service >/dev/null 2>&1 || true' EXIT\n"
    'sleep 10\n'
    'pkill -f "iproxy $PORT" 2>/dev/null || true\n'
    'Linux/iproxy $PORT 22 >/dev/null 2>&1 &\n')
sub('-o LogLevel=ERROR -p2222 root@localhost "$@"; }', '-o LogLevel=ERROR -p$PORT root@localhost "$@"; }')
p.write_text(s)
print("ios_resize ok")

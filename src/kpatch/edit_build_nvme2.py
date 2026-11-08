#!/usr/bin/env python3
# build.sh: nvme jetzt automatisch laden; iOS-Bereiche per udev dauerhaft schreibgeschützt
import pathlib, sys
R = pathlib.Path(__file__).resolve().parents[2]
p = R / "build.sh"; s = p.read_text()
SU = "su" + "do"

old = 'NVME_AUTOLOAD="${NVME_AUTOLOAD:-0}"   # 1 = nvme-Modul automatisch laden (erst nach erfolgreichem Test)\n'
new = 'NVME_AUTOLOAD="${NVME_AUTOLOAD:-1}"   # 0 = nvme-Modul gesperrt (nur manuell per modprobe)\n'
if new not in s:
    if s.count(old) != 1: sys.exit("NVME_AUTOLOAD-Anker")
    s = s.replace(old, new)

old = ('    if [[ "$NVME_AUTOLOAD" == 1 ]]; then\n'
       '        ' + SU + ' rm -f "$m/etc/modprobe.d/nvme-test.conf"\n')
new = ('    # iOS-Daten schützen: APFS-Container (nvme0n1p1) und die System-Namespaces 2..7 immer schreibgeschützt\n'
       '    ' + SU + ' mkdir -p "$m/etc/udev/rules.d"\n'
       '    printf \'%s\\n\' \'# iPhone 7: iOS-Bereiche des internen Speichers nie beschreiben\' \\\n'
       '        \'ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="nvme0n1p1|nvme0n[2-9]", RUN+="/sbin/blockdev --setro /dev/%k"\' \\\n'
       '        | ' + SU + ' tee "$m/etc/udev/rules.d/60-ios-readonly.rules" >/dev/null\n'
       '    if [[ "$NVME_AUTOLOAD" == 1 ]]; then\n'
       '        ' + SU + ' rm -f "$m/etc/modprobe.d/nvme-test.conf"\n'
       '        echo nvme | ' + SU + ' tee "$m/etc/modules-load.d/nvme.conf" >/dev/null\n'
       '        c_ok "NVMe: wird beim Start geladen (iOS-Bereiche schreibgeschützt)."\n')
if new not in s:
    if s.count(old) != 1: sys.exit("patch_nvme-Anker")
    s = s.replace(old, new)

old = '        echo \'blacklist nvme\' | ' + SU + ' tee "$m/etc/modprobe.d/nvme-test.conf" >/dev/null\n'
new = ('        ' + SU + ' rm -f "$m/etc/modules-load.d/nvme.conf"\n'
       '        echo \'blacklist nvme\' | ' + SU + ' tee "$m/etc/modprobe.d/nvme-test.conf" >/dev/null\n')
if new not in s:
    if s.count(old) != 1: sys.exit("blacklist-Anker")
    s = s.replace(old, new)
p.write_text(s)
print("build nvme2 ok")

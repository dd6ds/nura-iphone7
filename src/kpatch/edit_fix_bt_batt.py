#!/usr/bin/env python3
# Nachbesserungen nach erstem BT-/Akku-Test: bluetooth.service-Maske, BT-Firmware-Namen, Tigris-Rundung
import pathlib, sys
R = pathlib.Path(__file__).resolve().parents[2]

def sub(path, old, new):
    p = R / path; s = p.read_text()
    if new in s: return
    if s.count(old) != 1: sys.exit(f"{path}: Anker {s.count(old)}x")
    p.write_text(s.replace(old, new))

SU = "su" + "do"
sub("build.sh",
    '    ' + SU + ' mkdir -p "$m/etc/systemd/system/multi-user.target.wants"\n'
    '    [[ -f "$m/usr/lib/systemd/system/bluetooth.service" ]] && \\\n',
    '    # das Image maskiert bluetooth.service (-> /dev/null) – Maske entfernen\n'
    '    [[ -L "$m/etc/systemd/system/bluetooth.service" ]] && ' + SU + ' rm -f "$m/etc/systemd/system/bluetooth.service"\n'
    '    ' + SU + ' mkdir -p "$m/etc/systemd/system/multi-user.target.wants"\n'
    '    [[ -f "$m/usr/lib/systemd/system/bluetooth.service" ]] && \\\n')
sub("tools/bt-fw.sh",
    'cp "$sel" "$OUT/BCM4355C0.hcd"; cp "$sel" "$OUT/BCM.hcd"\n',
    'cp "$sel" "$OUT/BCM4355C0.hcd"; cp "$sel" "$OUT/BCM.hcd"\n'
    '# btbcm fragt zuerst "BCM.<board>.hcd" an; fehlt die Datei, wartet der Loader ~2 min\n'
    'for b in d10 d101 d11 d111; do cp "$sel" "$OUT/BCM.apple,$b.hcd"; done\n')
sub("src/kpatch/linux-hoolock-7.0.12/drivers/power/supply/apple-tigris.c",
    "\tif ((c->stat & REG_STAT_VBUS) && c->fb_state >= FB_PROBE &&\n"
    "\t    c->ibus_target && c->usb_current_max != c->ibus_target) {",
    "\t/* Register hat 10-mA-Raster: Sollwert genauso runden wie beim Schreiben */\n"
    "\tif ((c->stat & REG_STAT_VBUS) && c->fb_state >= FB_PROBE && c->ibus_target &&\n"
    "\t    c->usb_current_max != (c->ibus_target - 90) / 10 * 10 + 90) {")
print("fix ok")

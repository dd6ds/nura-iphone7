#!/usr/bin/env bash
# Bluetooth-Firmware (BCM4355C0, Modul "Elsa", Hersteller USI) aus iOS-BlueTool holen.
# iOS bettet die .hcd-Patches direkt ins BlueTool-Binary ein (nicht als Datei).
# Ergebnis: out/bt-fw/brcm/{BCM4355C0.hcd,BCM.hcd}
#   (btbcm kennt die Subversion des 4355C0 nicht -> sucht "BCM.hcd"; daher beide Namen)
set -euo pipefail
cd "$(dirname "$0")/.."
DMG="${IOS_DMG:-research/ios13/038-13736-056.dmg}"
VARIANT="${BT_VARIANT:-BCM4355C0 Elsa USI MCC}"
OUT=out/bt-fw/brcm
W=research/ios13/bt-ads
BT="$W/usr/sbin/BlueTool"

[[ -f "$BT.out" ]] || {
    [[ -f "$DMG" ]] || { echo "iOS-Rootfs fehlt: $DMG" >&2; exit 1; }
    mkdir -p "$W"
    (cd "$W" && 7z x -y -snc "$OLDPWD/$DMG" 'usr/sbin/BlueTool' >/dev/null)
    python3 research/tools/decmpfs.py "$BT:com.apple.decmpfs" "$BT:com.apple.ResourceFork" "$BT.out"
}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
python3 research/tools/hcd_scan.py "$BT.out" "$tmp" >/dev/null
sel=""
for f in "$tmp"/*.hcd; do
    if strings -n 8 "$f" | grep -qF "$VARIANT"; then sel="$f"; break; fi
done
[[ -n "$sel" ]] || { echo "Variante '$VARIANT' nicht gefunden" >&2; exit 1; }
mkdir -p "$OUT"
cp "$sel" "$OUT/BCM4355C0.hcd"; cp "$sel" "$OUT/BCM.hcd"
# btbcm fragt zuerst "BCM.<board>.hcd" an; fehlt die Datei, wartet der Loader ~2 min
for b in d10 d101 d11 d111; do cp "$sel" "$OUT/BCM.apple,$b.hcd"; done
echo "Bluetooth-Firmware: '$VARIANT' ($(stat -c%s "$sel") Byte) -> $OUT"

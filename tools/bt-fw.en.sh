#!/usr/bin/env bash
# Bluetooth firmware (BCM4355C0, module "Elsa", vendor USI) from iOS BlueTool.
# iOS embeds the .hcd patches directly into the BlueTool binary (not as a file).
# Result: out/bt-fw/brcm/{BCM4355C0.hcd,BCM.hcd}
#   (btbcm does not know the subversion of the 4355C0 -> looks for "BCM.hcd"; hence both names)
set -euo pipefail
cd "$(dirname "$0")/.."
DMG="${IOS_DMG:-research/ios13/038-13736-056.dmg}"
VARIANT="${BT_VARIANT:-BCM4355C0 Elsa USI MCC}"
OUT=out/bt-fw/brcm
W=research/ios13/bt-ads
BT="$W/usr/sbin/BlueTool"

[[ -f "$BT.out" ]] || {
    [[ -f "$DMG" ]] || { echo "iOS rootfs missing: $DMG" >&2; exit 1; }
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
[[ -n "$sel" ]] || { echo "Variant '$VARIANT' not found" >&2; exit 1; }
mkdir -p "$OUT"
cp "$sel" "$OUT/BCM4355C0.hcd"; cp "$sel" "$OUT/BCM.hcd"
# btbcm first requests "BCM.<board>.hcd"; if the file is missing, the loader waits ~2 min
for b in d10 d101 d11 d111; do cp "$sel" "$OUT/BCM.apple,$b.hcd"; done
echo "Bluetooth-Firmware: '$VARIANT' ($(stat -c%s "$sel") Byte) -> $OUT"

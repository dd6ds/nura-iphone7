#!/usr/bin/env bash
# Lädt aus einem IPSW (per HTTP-Range, ohne Komplett-Download) nur die Rootfs-DMG
# und extrahiert daraus usr/share/firmware/multitouch/D10.mtprops.
# Aufruf: ipsw_fetch_mtprops.sh <ipsw-url> <zielordner>
set -euo pipefail
URL="$1"; DST="$2"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
mkdir -p "$DST"; cd "$DST"
"$PY" -c 'import remotezip' 2>/dev/null || "$ROOT/.venv/bin/pip" install -q remotezip
DMG="$("$PY" - "$URL" <<'EOF'
import sys, remotezip
with remotezip.RemoteZip(sys.argv[1]) as z:
    dmgs = sorted((i for i in z.infolist() if i.filename.endswith(".dmg")), key=lambda i: -i.file_size)
    for i in dmgs[:3]: print(f"{i.filename} {i.file_size}", file=sys.stderr)
    print(dmgs[0].filename)
EOF
)"
echo "Rootfs-DMG: $DMG"
if [[ ! -f "$DMG" ]]; then
    "$PY" - "$URL" "$DMG" <<'EOF'
import sys, remotezip, shutil
with remotezip.RemoteZip(sys.argv[1]) as z, z.open(sys.argv[2]) as src, open(sys.argv[2] + ".part", "wb") as out:
    shutil.copyfileobj(src, out, 16 << 20)
EOF
    mv "$DMG.part" "$DMG"
fi
ls -la "$DMG"
7z l "$DMG" 2>/dev/null | grep -i "multitouch" | head
7z x -y "$DMG" '*/usr/share/firmware/multitouch/D10*' 'usr/share/firmware/multitouch/D10*' -r >/dev/null 2>&1 || true
find . -name 'D10*.mtprops' -exec ls -la {} \;
echo FERTIG

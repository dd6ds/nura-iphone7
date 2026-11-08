#!/usr/bin/env bash
# hx-touchd (Project Sandcastle, GPL-2.0+) statisch für aarch64 bauen
# + syscfg.bin aus der Live-ADT + Firmware nach out/hx-touch/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/src/psc/hx-touchd"
O="$ROOT/out/hx-touch"
B="$O/build"
CC="${CC:-aarch64-linux-gnu-gcc}"; AR="${AR:-aarch64-linux-gnu-ar}"
rm -rf "$B"; mkdir -p "$B" "$O"; cp -r "$SRC"/. "$B"/
[[ -f "$ROOT/tools/hx-touchd/hx-touchd.c" ]] && cp "$ROOT/tools/hx-touchd/hx-touchd.c" "$B/"
cd "$B"
CF="-O2 -Wall -I$B/mxml-3.1 -I$B/mtfw"
( cd mxml-3.1 && for f in mxml-attr mxml-entity mxml-file mxml-get mxml-index mxml-node mxml-private mxml-search mxml-set mxml-string; do
    $CC $CF -D_THREAD_SAFE -D_REENTRANT -c $f.c -o $f.o; done; $AR crs libmxml.a mxml-*.o )
( cd mtfw && for f in qdict eplist syscfg mtfw; do $CC $CF -c $f.c -o $f.o; done; $AR crs libmtfw.a qdict.o eplist.o syscfg.o mtfw.o )
$CC $CF -static -o hx-touchd hx-touchd.c -Lmtfw -Lmxml-3.1 -lmtfw -lmxml -lpthread
cp hx-touchd "$O/"
python3 "$ROOT/tools/hx-touchd/mk_syscfg.py" "$ROOT/research/live/multi-touch" "$O/syscfg.bin"
cp "$ROOT/research/firmware/D10.mtprops" "$O/"
file "$O/hx-touchd"
# Gegenprobe auf dem Host (testload liest ../D10.mtprops und ../syscfg.bin)
gcc -O2 -I"$SRC/mtfw" -I"$SRC/mxml-3.1" -o "$B/testload" "$SRC/mtfw/testload.c" \
    "$SRC"/mtfw/{qdict,eplist,syscfg,mtfw}.c "$SRC"/mxml-3.1/mxml-*.c -lpthread
"$B/testload" | cut -c1-110

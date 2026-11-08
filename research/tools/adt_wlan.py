#!/usr/bin/env python3
"""Liest WLAN-relevante Werte aus der Live-ADT (iBoot-ausgefüllt) und schreibt sie nach research/live/wlan/."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src/m1n1/proxyclient"))
from m1n1.adt import load_adt

adt = load_adt(open(os.path.join(ROOT, "research/live/live.adt"), "rb").read())
out = os.path.join(ROOT, "research/live/wlan"); os.makedirs(out, exist_ok=True)
for node in adt.walk_tree():
    if node.name not in ("wlan",):
        continue
    print("Knoten:", node._path if hasattr(node, "_path") else node.name)
    for k in sorted(node._properties.keys()):
        v = node._properties[k]
        raw = v if isinstance(v, (bytes, bytearray)) else None
        if raw is None:
            try: raw = node._properties_raw[k] if hasattr(node, "_properties_raw") else None
            except Exception: raw = None
        if k in ("local-mac-address", "wifi-calibration-msf", "wifi-antenna-sku-info",
                 "module-instance", "compatible", "function-reg_on"):
            s = v.hex() if isinstance(v, (bytes, bytearray)) else repr(v)
            print(f"  {k} = {s[:120]}{'…' if len(s) > 120 else ''}  ({len(v) if hasattr(v, '__len__') else '-'} )")
            if isinstance(v, (bytes, bytearray)):
                open(os.path.join(out, k), "wb").write(v)

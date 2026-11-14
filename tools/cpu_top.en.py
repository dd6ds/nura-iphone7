#!/usr/bin/env python3
"""cpu_top.en.py [seconds] – measure the CPU usage of all processes over a period (sum over both cores).
Meant for comparing "smooth/slow": use the iPhone while it measures."""
import os, sys, time

dauer = float(sys.argv[1]) if len(sys.argv) > 1 else 20
hz = os.sysconf("SC_CLK_TCK")


def stand():
    werte = {}
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            stat = open(f"/proc/{p}/stat").read()
            name = stat[stat.index("(") + 1:stat.rindex(")")]
            felder = stat[stat.rindex(")") + 2:].split()
            werte[int(p)] = (name, int(felder[11]) + int(felder[12]))
        except (OSError, ValueError):
            pass
    return werte


def gesamt():
    z = open("/proc/stat").readline().split()[1:]
    return sum(map(int, z)), int(z[3]) + int(z[4])


a, (ga, ia) = stand(), gesamt()
time.sleep(dauer)
b, (gb, ib) = stand(), gesamt()
belegt = 100 * (1 - (ib - ia) / max(1, gb - ga))
print(f"Total load over {dauer:.0f} s: {belegt:.0f} % (both cores together = 100 %)")
diffs = sorted(((b[p][1] - a[p][1], p, b[p][0]) for p in b if p in a), reverse=True)
for ticks, pid, name in diffs[:12]:
    if ticks:
        print(f"  {100 * ticks / hz / dauer:6.1f} % of one core  {name} ({pid})")

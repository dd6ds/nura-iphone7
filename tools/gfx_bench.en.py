#!/usr/bin/env python3
"""gfx_bench.en.py [seconds] [mode] – graphics measurement on the iPhone (as user, in the Phosh session).
Fullscreen GTK4 window with animation (needs py3-cairo; the iPhone must be unlocked); measures the frames/s actually shown (frame clock)
and the CPU time of phoc and this process. Mode: full (whole window changes),
small (only a small rectangle moves – typical for UI), scroll (long list scrolls).
Start via SSH:  WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/$(id -u) python3 gfx_bench.en.py 15 full"""
import math, os, sys, time
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

DAUER = float(sys.argv[1]) if len(sys.argv) > 1 else 15
MODUS = sys.argv[2] if len(sys.argv) > 2 else "full"
TICK = os.sysconf("SC_CLK_TCK")


def cpu_ticks(pid):
    f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
    return int(f[11]) + int(f[12])                     # utime + stime


def pid_von(name):
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                if open(f"/proc/{p}/comm").read().strip() == name:
                    return int(p)
            except OSError:
                pass


class Bench(Gtk.Application):
    def do_activate(self):
        w = Gtk.ApplicationWindow(application=self, title="gfx_bench")
        if MODUS == "scroll":
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            for i in range(400):
                box.append(Gtk.Label(label=f"Line {i:03d} – software rendering test", xalign=0))
            self.sw = Gtk.ScrolledWindow(child=box)
            w.set_child(self.sw)
        else:
            da = Gtk.DrawingArea(hexpand=True, vexpand=True)
            da.set_draw_func(self.zeichnen)
            w.set_child(da)
            self.da = da
        w.fullscreen()
        w.present()
        self.frames = 0
        self.t0 = None
        w.add_tick_callback(self.tick)

    def zeichnen(self, da, cr, wd, ht):
        t = time.monotonic()
        if MODUS == "full":
            for i in range(8):                          # colour stripes moving across the whole picture
                cr.set_source_rgb(0.5 + 0.5 * math.sin(t * 2 + i), 0.5 + 0.5 * math.sin(t * 3 + i * 0.7), 0.6)
                cr.rectangle(0, (i * ht / 8 + t * 120) % ht, wd, ht / 8 + 1)
                cr.fill()
        else:
            cr.set_source_rgb(0.15, 0.15, 0.2); cr.paint()
            x = (wd - 60) * (0.5 + 0.5 * math.sin(t * 2))
            cr.set_source_rgb(0.9, 0.5, 0.1); cr.rectangle(x, ht / 2 - 30, 60, 60); cr.fill()

    def tick(self, w, clock):
        now = time.monotonic()
        if self.t0 is None:                              # settle for 1 s, then measure
            self.t0 = now + 1.0
            return GLib.SOURCE_CONTINUE
        if now < self.t0:
            self.start_cpu = (cpu_ticks(PHOC), cpu_ticks(os.getpid()))
            return GLib.SOURCE_CONTINUE
        self.frames += 1
        if MODUS == "scroll":
            adj = self.sw.get_vadjustment()
            span = adj.get_upper() - adj.get_page_size()
            adj.set_value(span * (0.5 + 0.5 * math.sin((now - self.t0) * 1.5)))
        else:
            self.da.queue_draw()
        if now - self.t0 >= DAUER:
            dt = now - self.t0
            p, s = cpu_ticks(PHOC), cpu_ticks(os.getpid())
            print(f"{MODUS}: {self.frames / dt:5.1f} frames/s | CPU phoc {100 * (p - self.start_cpu[0]) / TICK / dt:5.1f} % "
                  f"| CPU client {100 * (s - self.start_cpu[1]) / TICK / dt:5.1f} %  (100 % = 1 core)", flush=True)
            self.quit()
        return GLib.SOURCE_CONTINUE


PHOC = pid_von("phoc")
if not PHOC:
    sys.exit("phoc is not running")
Bench(application_id="de.dd6ds.gfxbench").run([])

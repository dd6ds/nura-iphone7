#!/usr/bin/env python3
# Akku Runde 2: Ladeschlussspannung untersuchen/einstellbar, Status "voll/lädt nicht" korrekt
import pathlib, sys
T = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12"
F = "drivers/power/supply/apple-tigris.c"

def sub(old, new):
    p = T / F; s = p.read_text()
    if new in s: return
    if s.count(old) != 1: sys.exit(f"Anker {s.count(old)}x: {old[:70]!r}")
    p.write_text(s.replace(old, new))

# Modulparameter: Ladeschlussspannung (0 = Tigris/Gauge entscheiden lassen)
sub("MODULE_PARM_DESC(ibus_max_ma, \"Obergrenze USB-Eingangsstrom in mA (90..2000)\");\n",
    "MODULE_PARM_DESC(ibus_max_ma, \"Obergrenze USB-Eingangsstrom in mA (90..2000)\");\n\n"
    "static unsigned int vchg_mv;\n"
    "module_param(vchg_mv, uint, 0644);\n"
    "MODULE_PARM_DESC(vchg_mv, \"Ladeschlussspannung in mV erzwingen (0 = nicht anfassen, 4000..4400)\");\n")

# im Arbeitszyklus: wenn gesetzt und abweichend -> schreiben (Register: (mV-3000)/10)
sub("\tif (((prev ^ c->stat) & REG_STAT_VBUS) || c->fb_state == FB_INIT) {",
    "\tif (vchg_mv >= 4000 && vchg_mv <= 4400 && (c->stat & REG_STAT_VBUS) &&\n"
    "\t    c->batt_charge_voltage != (int)(vchg_mv - 3000) / 10 * 10 + 3000) {\n"
    "\t\tdev_info_ratelimited(c->dev, \"Ladeschlussspannung %d -> %u mV\\n\",\n"
    "\t\t\t\t     c->batt_charge_voltage, vchg_mv);\n"
    "\t\ttigris_write(c, REG_VCHG, (vchg_mv - 3000) / 10);\n"
    "\t}\n\n"
    "\tif (((prev ^ c->stat) & REG_STAT_VBUS) || c->fb_state == FB_INIT) {")

# Gauge: beim ersten Zyklus zusätzliche Register protokollieren (SOC, Lade-Soll von der Gauge)
sub("\tif (!ret && g->first)\n\t\thdq_read_word(g, GG_DesignCapacity, &cd);\n",
    "\tif (!ret && g->first) {\n"
    "\t\tint soc = -1, cv = -1, cc = -1;\n\n"
    "\t\thdq_read_word(g, GG_DesignCapacity, &cd);\n"
    "\t\thdq_read_word(g, 0x2c, &soc);\t/* StateOfCharge */\n"
    "\t\thdq_read_word(g, 0x30, &cv);\t/* ChargingVoltage (bq27545) */\n"
    "\t\thdq_read_word(g, 0x32, &cc);\t/* ChargingCurrent */\n"
    "\t\tdev_info(&g->serdev->dev, \"Gauge: Design %d mAh, SOC %d %%, Soll %d mV / %d mA\\n\",\n"
    "\t\t\t cd, soc, cv, cc);\n"
    "\t}\n")

# Status: am Kabel ohne nennenswerten Strom -> voll bzw. "lädt nicht", nicht "lädt"
sub("\t\t\tif (g->s_ia < -50)\t/* Kabel dran, aber Netto-Entladung */\n"
    "\t\t\t\tval->intval = POWER_SUPPLY_STATUS_DISCHARGING;\n"
    "\t\t\telse if ((c->stat & REG_STAT_CHARGING) || g->s_ia > 0)\n"
    "\t\t\t\tval->intval = POWER_SUPPLY_STATUS_CHARGING;\n",
    "\t\t\tif (g->s_ia < -50)\t/* Kabel dran, aber Netto-Entladung */\n"
    "\t\t\t\tval->intval = POWER_SUPPLY_STATUS_DISCHARGING;\n"
    "\t\t\telse if (g->s_ia > 20)\n"
    "\t\t\t\tval->intval = POWER_SUPPLY_STATUS_CHARGING;\n")
print("batt2 ok")

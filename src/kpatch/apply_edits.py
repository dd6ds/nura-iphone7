#!/usr/bin/env python3
"""Bearbeitet Kconfig/Makefile/simple-mfd-i2c/hx-touch im Testbaum (idempotent)."""
import os, re, sys
T = sys.argv[1] if len(sys.argv) > 1 else "linux-hoolock-7.0.12"

def edit(path, fn):
    p = os.path.join(T, path)
    s = open(p, encoding="utf-8").read()
    n = fn(s)
    if n != s:
        open(p, "w", encoding="utf-8").write(n)
        print("bearbeitet:", path)
    else:
        print("unverändert:", path)

def ins_after(s, anchor, text, marker):
    if marker in s:
        return s
    i = s.index(anchor)
    j = s.index("\n", i) + 1
    return s[:j] + text + s[j:]

def ins_before(s, anchor, text, marker):
    if marker in s:
        return s
    i = s.index(anchor)
    return s[:i] + text + s[i:]

# --- SPI ---------------------------------------------------------------
edit("drivers/spi/Kconfig", lambda s: ins_before(s, "config SPI_APPLE\n", """config SPI_APPLE_S5L
	tristate "Apple S5L-style SPI controller (A9/A10)"
	depends on ARCH_APPLE || COMPILE_TEST
	help
	  SPI controller found in older Apple SoCs such as the A10 (T8010),
	  used for example for the touch screen of the iPhone 7.

""", "SPI_APPLE_S5L"))
edit("drivers/spi/Makefile", lambda s: ins_after(s, "obj-$(CONFIG_SPI_APPLE)",
     "obj-$(CONFIG_SPI_APPLE_S5L)\t\t+= spi-apple-s5l.o\n", "spi-apple-s5l.o"))

# --- Clock -------------------------------------------------------------
edit("drivers/clk/Kconfig", lambda s: ins_before(s, "config COMMON_CLK_APPLE_NCO\n", """config COMMON_CLK_APPLE_TOUCH
	tristate "Apple PMGR touch controller clock (A9/A10)"
	depends on ARCH_APPLE || COMPILE_TEST
	help
	  Clock for the multi-touch controller of iPhones with A9/A10 SoCs.

""", "COMMON_CLK_APPLE_TOUCH"))
edit("drivers/clk/Makefile", lambda s: ins_after(s, "obj-$(CONFIG_COMMON_CLK_APPLE_NCO)",
     "obj-$(CONFIG_COMMON_CLK_APPLE_TOUCH)\t+= clk-apple-touch.o\n", "clk-apple-touch.o"))

# --- Regulator ---------------------------------------------------------
edit("drivers/regulator/Kconfig", lambda s: ins_before(s, "config REGULATOR_RT5739\n", """config REGULATOR_APPLE_PMIC_SWITCH
	tristate "Power switches in Apple I2C PMICs"
	depends on MFD_SIMPLE_MFD_I2C
	help
	  On/off power switches inside Apple I2C PMICs (e.g. touch screen
	  supplies on the iPhone 7).

""", "REGULATOR_APPLE_PMIC_SWITCH"))
edit("drivers/regulator/Makefile", lambda s: s if "apple-pmic-switch.o" in s else
     s.rstrip("\n") + "\nobj-$(CONFIG_REGULATOR_APPLE_PMIC_SWITCH) += apple-pmic-switch.o\n")

# --- Touchscreen -------------------------------------------------------
edit("drivers/input/touchscreen/Kconfig", lambda s: ins_before(s, "config TOUCHSCREEN_APPLE_Z2\n", """config TOUCHSCREEN_HX
	tristate "Apple A9/A10 iPhone multi-touch (Sandcastle hx-touch)"
	depends on SPI
	help
	  Multi-touch controller of iPhones with A9/A10 SoCs. Firmware upload
	  is done from user space (hx-touchd) via /dev/hx-touch.

""", "TOUCHSCREEN_HX"))
edit("drivers/input/touchscreen/Makefile", lambda s: ins_after(s, "obj-$(CONFIG_TOUCHSCREEN_APPLE_Z2)",
     "obj-$(CONFIG_TOUCHSCREEN_HX)\t\t+= hx-touch.o\n", "hx-touch.o"))

def touch_compat(s):
    if "apple,t8010-multitouch" in s:
        return s
    return s.replace('{ .compatible = "hx,touch" },',
                     '{ .compatible = "apple,t8010-multitouch" },\n    { .compatible = "hx,touch" },', 1)
edit("drivers/input/touchscreen/hx-touch.c", touch_compat)

# --- simple-mfd-i2c: Display-PMU chestnut (8-Bit-Register) -------------
def mfd(s):
    if "apple,chestnut-pmic" in s:
        return s
    s = s.replace("static const struct simple_mfd_data apple_i2c_pmic = {",
                  "static const struct simple_mfd_data apple_i2c_pmic_8 = {\n"
                  "\t.regmap_config = &regmap_config_8r_8v\n};\n\n"
                  "static const struct simple_mfd_data apple_i2c_pmic = {", 1)
    s = s.replace('\t{ .compatible = "apple,i2c-pmic", .data = &apple_i2c_pmic },',
                  '\t{ .compatible = "apple,chestnut-pmic", .data = &apple_i2c_pmic_8 },\n'
                  '\t{ .compatible = "apple,i2c-pmic", .data = &apple_i2c_pmic },', 1)
    return s
edit("drivers/mfd/simple-mfd-i2c.c", mfd)

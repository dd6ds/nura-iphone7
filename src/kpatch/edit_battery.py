#!/usr/bin/env python3
# Kconfig/Makefile/DT für apple-tigris (Akkuanzeige iPhone 7)
import pathlib, sys
T = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12"
DTS = "arch/arm64/boot/dts/apple/"

def sub(path, old, new):
    p = T / path; s = p.read_text()
    if new in s: return
    if s.count(old) != 1: sys.exit(f"{path}: Anker nicht eindeutig: {old[:50]!r}")
    p.write_text(s.replace(old, new))

sub("drivers/power/supply/apple-tigris.c",
    "#include <linux/delay.h>\n", "#include <linux/delay.h>\n#include <linux/devm-helpers.h>\n")
sub("drivers/power/supply/apple-tigris.c",
    "\t\t.name = \"apple-tigris\",\n",
    "\t\t.name = \"apple-tigris\",\n\t\t.suppress_bind_attrs = true,\n")

sub("drivers/power/supply/Kconfig", "config BATTERY_BQ27XXX\n",
    "config CHARGER_APPLE_TIGRIS\n"
    "\ttristate \"Apple Tigris charger and bq27545 HDQ-UART gauge\"\n"
    "\tdepends on I2C && SERIAL_DEV_BUS && OF\n"
    "\tdepends on ARCH_APPLE || COMPILE_TEST\n"
    "\thelp\n"
    "\t  Charger (SN2400 \"Tigris\") and battery fuel gauge (TI bq27545,\n"
    "\t  reached via HDQ over a UART) found in A10 iPhones.\n\n"
    "config BATTERY_BQ27XXX\n")
sub("drivers/power/supply/Makefile",
    "obj-$(CONFIG_BATTERY_BQ27XXX)\t+= bq27xxx_battery.o\n",
    "obj-$(CONFIG_CHARGER_APPLE_TIGRIS)\t+= apple-tigris.o\n"
    "obj-$(CONFIG_BATTERY_BQ27XXX)\t+= bq27xxx_battery.o\n")

# SoC: UART4 (Bluetooth) und UART5 (HDQ-Gasgauge)
sub(DTS + "t8010.dtsi",
    "\t\ti2c0: i2c@20a110000 {\n",
    "\t\tserial4: serial@20a0d0000 {\n"
    "\t\t\tcompatible = \"apple,s5l-uart\";\n"
    "\t\t\treg = <0x2 0x0a0d0000 0x0 0x4000>;\n"
    "\t\t\treg-io-width = <4>;\n"
    "\t\t\tinterrupt-parent = <&aic>;\n"
    "\t\t\tinterrupts = <AIC_IRQ 222 IRQ_TYPE_LEVEL_HIGH>;\n"
    "\t\t\tclocks = <&clkref>, <&clkref>;\n"
    "\t\t\tclock-names = \"uart\", \"clk_uart_baud0\";\n"
    "\t\t\tpower-domains = <&ps_uart4>;\n"
    "\t\t\tstatus = \"disabled\";\n"
    "\t\t};\n\n"
    "\t\tserial5: serial@20a0d4000 {\n"
    "\t\t\tcompatible = \"apple,s5l-uart\";\n"
    "\t\t\treg = <0x2 0x0a0d4000 0x0 0x4000>;\n"
    "\t\t\treg-io-width = <4>;\n"
    "\t\t\tinterrupt-parent = <&aic>;\n"
    "\t\t\tinterrupts = <AIC_IRQ 223 IRQ_TYPE_LEVEL_HIGH>;\n"
    "\t\t\tclocks = <&clkref>, <&clkref>;\n"
    "\t\t\tclock-names = \"uart\", \"clk_uart_baud0\";\n"
    "\t\t\tpower-domains = <&ps_uart5>;\n"
    "\t\t\tstatus = \"disabled\";\n"
    "\t\t};\n\n"
    "\t\ti2c0: i2c@20a110000 {\n")

# Board: Tigris an i2c1, Gasgauge an UART5
sub(DTS + "t8010-7.dtsi",
    "\t\t/* D2333-GPIOs (Sandcastle pmu_gpio): GPIO 10 = WLAN reg_on */\n",
    "\t\t/* D2333-GPIOs (Sandcastle pmu_gpio): GPIO 10 = WLAN reg_on */\n")  # nur Prüfung
s = (T / (DTS + "t8010-7.dtsi")).read_text()
if "tigris: charger@75" not in s:
    s = s.replace("&i2c1 {\n\tstatus = \"okay\";\n",
        "&i2c1 {\n\tstatus = \"okay\";\n\n"
        "\t/* SN2400 \"Tigris\": Lader + HDQ-Mux für die Gasgauge */\n"
        "\ttigris: charger@75 {\n"
        "\t\tcompatible = \"apple,tigris-charger\";\n"
        "\t\treg = <0x75>;\n"
        "\t\tcharge-current = <1950>;\n"
        "\t};\n", 1)
    s = s.replace("\taliases {\n\t\twifi0 = &wifi0;\n\t};\n",
        "\taliases {\n\t\twifi0 = &wifi0;\n\t\tserial4 = &serial4;\n\t\tserial5 = &serial5;\n\t};\n", 1)
    s += ("\n&serial5 {\n\tstatus = \"okay\";\n\n"
          "\t/* TI bq27545 per HDQ (über Tigris gemuxt) */\n"
          "\tgas-gauge {\n\t\tcompatible = \"ti,bq27545-hdquart\";\n"
          "\t\tcharger = <&tigris>;\n\t};\n};\n")
    if "tigris: charger@75" not in s or "serial5 = &serial5" not in s:
        sys.exit("t8010-7.dtsi: Einfügen fehlgeschlagen")
    (T / (DTS + "t8010-7.dtsi")).write_text(s)
print("battery ok")

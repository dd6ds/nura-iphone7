#!/usr/bin/env python3
"""spi-apple-s5l: SPI-Modus (CPOL/CPHA) je Gerät, wenn der Controller-Knoten
'apple,honor-spi-mode' trägt (sonst fest 0x1E = Mode 3 wie bisher, z. B. für Touch).
DT: spi1 mit Opt-in, maggie@1 Mode 3 (CS42L71 an CS0 bleibt Mode 0, laut ADT)."""
import re
T = "linux-hoolock-7.0.12/"
p = T + "drivers/spi/spi-apple-s5l.c"
s = open(p).read()
def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (a, s.count(a))
    s = s.replace(a, b)
rep("#define  REG_CONFIG_SET\t\t\t0x0010401E\n",
    "#define  REG_CONFIG_SET\t\t\t0x0010401E\n"
    "#define  REG_CONFIG_CPHA\t\t\tBIT(1)\n"
    "#define  REG_CONFIG_CPOL\t\t\tBIT(2)\n"
    "#define  REG_CONFIG_BASE\t\t\t(REG_CONFIG_SET & ~(REG_CONFIG_CPHA | REG_CONFIG_CPOL))\n")
rep("\tunsigned int tx_compl, rx_compl, len;\n",
    "\tunsigned int tx_compl, rx_compl, len;\n\tu32 cfg;\t\t/* CONFIG-Basiswert der laufenden Nachricht */\n"
    "\tbool honor_mode;\t/* DT apple,honor-spi-mode */\n")
s = s.replace("writel(REG_CONFIG_SET | REG_CONFIG_PIOEN", "writel(spi->cfg | REG_CONFIG_PIOEN")
s = s.replace("writel(REG_CONFIG_SET, spi->base + REG_CONFIG);", "writel(spi->cfg, spi->base + REG_CONFIG);")
rep("static int s5l_spi_prepare(struct apple_s5l_spi *spi, unsigned int speed)\n{\n",
    "static int s5l_spi_prepare(struct apple_s5l_spi *spi, unsigned int speed, u32 mode)\n{\n")
rep("\twritel(0, spi->base + REG_CLKCFG);\n",
    "\tspi->cfg = REG_CONFIG_SET;\n"
    "\tif (spi->honor_mode) {\n"
    "\t\tspi->cfg = REG_CONFIG_BASE;\n"
    "\t\tif (mode & SPI_CPHA)\n\t\t\tspi->cfg |= REG_CONFIG_CPHA;\n"
    "\t\tif (mode & SPI_CPOL)\n\t\t\tspi->cfg |= REG_CONFIG_CPOL;\n"
    "\t}\n\n"
    "\twritel(0, spi->base + REG_CLKCFG);\n")
rep("if (s5l_spi_prepare(spi, speed)) {", "if (s5l_spi_prepare(spi, speed, sdev->mode)) {")
rep("\tctlr->mode_bits = SPI_LSB_FIRST;\n",
    "\tspi->honor_mode = of_property_read_bool(dev->of_node, \"apple,honor-spi-mode\");\n"
    "\tspi->cfg = REG_CONFIG_SET;\n"
    "\tctlr->mode_bits = SPI_LSB_FIRST | SPI_CPOL | SPI_CPHA;\n")
assert "REG_CONFIG_SET |" not in s and "writel(REG_CONFIG_SET," not in s
if "#include <linux/of.h>" not in s:
    s = s.replace("#include <linux/module.h>\n", "#include <linux/module.h>\n#include <linux/of.h>\n", 1)
open(p, "w").write(s)

d = T + "arch/arm64/boot/dts/apple/t8010-7.dtsi"
t = open(d).read()
a = "\tcs-gpios = <&pinctrl_ap 131 GPIO_ACTIVE_HIGH>, <&pinctrl_ap 177 GPIO_ACTIVE_HIGH>;\n"
assert t.count(a) == 1
t = t.replace(a, a + "\t/* ADT: Codec Mode 0, Maggie Mode 3 – Modus je Gerät beachten */\n\tapple,honor-spi-mode;\n")
b = "\t\treg = <1>;\n\t\tspi-max-frequency = <4000000>;\n"
assert t.count(b) == 1
t = t.replace(b, b + "\t\tspi-cpol;\n\t\tspi-cpha;\n")
open(d, "w").write(t)
print("ok")

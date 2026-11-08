#!/usr/bin/env python3
# Audio Stufe 1/2: spi1 (Codec CS42L71 an CS0, Maggie-FPGA an CS1) als spidev für Tests aus dem Userspace
import pathlib, sys
T = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12"
DTS = "arch/arm64/boot/dts/apple/"

def sub(path, old, new):
    p = T / path; s = p.read_text()
    if new in s: return
    if s.count(old) != 1: sys.exit(f"{path}: Anker {s.count(old)}x: {old[:60]!r}")
    p.write_text(s.replace(old, new))

sub(DTS + "t8010.dtsi", "\t\tspi2: spi@20a088000 {\n",
    "\t\tspi1: spi@20a084000 {\n"
    "\t\t\tcompatible = \"apple,t8010-spi\";\n"
    "\t\t\treg = <0x2 0x0a084000 0x0 0x4000>;\n"
    "\t\t\tclocks = <&clkref>;\n"
    "\t\t\tinterrupt-parent = <&aic>;\n"
    "\t\t\tinterrupts = <AIC_IRQ 215 IRQ_TYPE_LEVEL_HIGH>;\n"
    "\t\t\tpower-domains = <&ps_spi1>;\n"
    "\t\t\t#address-cells = <1>;\n"
    "\t\t\t#size-cells = <0>;\n"
    "\t\t\tstatus = \"disabled\";\n"
    "\t\t};\n\n"
    "\t\tspi2: spi@20a088000 {\n")

s = (T / (DTS + "t8010-7.dtsi")).read_text()
if "maggie@1" not in s:
    s += ("\n/* Audio (Test): ADT spi1 – audio-codec (CS42L71) an CS0 = GPIO 0x83,\n"
          " * maggie-arc (Lattice iCE5LP4K) an CS1 = GPIO 0xb1. Zugriff per spidev. */\n"
          "&spi1 {\n\tstatus = \"okay\";\n"
          "\tcs-gpios = <&pinctrl_ap 131 GPIO_ACTIVE_HIGH>, <&pinctrl_ap 177 GPIO_ACTIVE_HIGH>;\n\n"
          "\taudio_codec_spi: spidev@0 {\n\t\tcompatible = \"rohm,dh2228fv\";\n"
          "\t\treg = <0>;\n\t\tspi-max-frequency = <2500000>;\n\t};\n\n"
          "\tmaggie_spi: maggie@1 {\n\t\tcompatible = \"rohm,dh2228fv\";\n"
          "\t\treg = <1>;\n\t\tspi-max-frequency = <4000000>;\n\t};\n};\n")
    (T / (DTS + "t8010-7.dtsi")).write_text(s)
print("spi1 ok")

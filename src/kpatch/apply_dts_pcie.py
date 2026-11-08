#!/usr/bin/env python3
"""Device-Tree: PCIe (A10) + PMU-GPIO + WLAN-Port für das iPhone 7 (idempotent).
Werte: Live-ADT (apcie, dart-apcie2, wlan) + Project Sandcastle hx-h9p-d101.dts."""
import os, shutil, sys
T = sys.argv[1] if len(sys.argv) > 1 else "linux-hoolock-7.0.12"
D = os.path.join(T, "arch/arm64/boot/dts/apple")
STAGE = "stage-touch"   # Stand nach den Touch-Patches -> Basis für Patch 0009
for f in ("t8010.dtsi", "t8010-7.dtsi"):
    dst = os.path.join(STAGE, "arch/arm64/boot/dts/apple", f)
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(os.path.join(D, f), dst)

# --- t8010.dtsi -----------------------------------------------------------
p = os.path.join(D, "t8010.dtsi"); s = open(p).read()
if "pcie_clkreq_pins" not in s:
    a = "\t\t\ti2c0_pins: i2c0-pins {"
    assert a in s
    s = s.replace(a, """\t\t\tpcie_clkreq_pins: pcie-clkreq-pins {
\t\t\t\tpinmux = <APPLE_PINMUX(16, 1)>,
\t\t\t\t\t <APPLE_PINMUX(17, 1)>,
\t\t\t\t\t <APPLE_PINMUX(18, 1)>,
\t\t\t\t\t <APPLE_PINMUX(19, 1)>;
\t\t\t};

""" + a, 1)
if "apple,t8010-pcie" not in s:
    a = "\t\tspi2: spi@20a088000 {"
    assert a in s
    s = s.replace(a, """\t\tpcie: pcie@610000000 {
\t\t\tcompatible = "apple,t8010-pcie";
\t\t\tdevice_type = "pci";
\t\t\treg = <0x6 0x10000000 0x0 0x1000000>,	/* ECAM, muss Index 0 sein */
\t\t\t      <0x6 0x00000000 0x0 0x8000>,
\t\t\t      <0x6 0x00008000 0x0 0x4000>,
\t\t\t      <0x6 0x0a000000 0x0 0x40000>,
\t\t\t      <0x6 0x00010000 0x0 0x8000>,
\t\t\t      <0x6 0x01000000 0x0 0x4000>,
\t\t\t      <0x6 0x02000000 0x0 0x4000>,
\t\t\t      <0x6 0x03000000 0x0 0x4000>,
\t\t\t      <0x6 0x04000000 0x0 0x4000>,
\t\t\t      <0x6 0x03008000 0x0 0x4000>;
\t\t\treg-names = "config", "phy0", "phy1", "phy2", "glue",
\t\t\t\t    "port0", "port1", "port2", "port3", "dart2";
\t\t\tinterrupt-parent = <&aic>;
\t\t\tinterrupts = <AIC_IRQ 270 IRQ_TYPE_LEVEL_HIGH>,
\t\t\t\t     <AIC_IRQ 273 IRQ_TYPE_LEVEL_HIGH>,
\t\t\t\t     <AIC_IRQ 276 IRQ_TYPE_LEVEL_HIGH>,
\t\t\t\t     <AIC_IRQ 279 IRQ_TYPE_LEVEL_HIGH>;
\t\t\tmsi-controller;
\t\t\tmsi-parent = <&pcie>;
\t\t\tmsi-ranges = <&aic AIC_IRQ 288 IRQ_TYPE_EDGE_RISING 32>;
\t\t\tapple,msi-doorbell = /bits/ 64 <0xbffff000>;
\t\t\tbus-range = <0x00 0x0f>;
\t\t\t#address-cells = <3>;
\t\t\t#size-cells = <2>;
\t\t\tranges = <0x02000000 0x0 0xc0000000 0x7 0xc0000000 0x0 0x40000000>;
\t\t\t/* statisches DART-Fenster: Bus 0x80000000 -> RAM 0x800000000, 512 MiB */
\t\t\tdma-ranges = <0x02000000 0x0 0x80000000 0x8 0x00000000 0x0 0x20000000>;
\t\t\tapple,dma-window = <0x80000000 0x8 0x00000000 0x20000000>;
\t\t\tpower-domains = <&ps_pcie>, <&ps_pcie_aux>, <&ps_pcie_ref>;
\t\t\tpinctrl-0 = <&pcie_clkreq_pins>;
\t\t\tpinctrl-names = "default";
\t\t\tdebug-gpios = <&pinctrl_ap 206 GPIO_ACTIVE_HIGH>;
\t\t\tstatus = "disabled";
\t\t};

""" + a, 1)
if "dt-bindings/gpio/gpio.h" not in s:
    s = s.replace("#include <dt-bindings/interrupt-controller/apple-aic.h>",
                  "#include <dt-bindings/interrupt-controller/apple-aic.h>\n#include <dt-bindings/gpio/gpio.h>", 1)
open(p, "w").write(s)

# --- t8010-7.dtsi ---------------------------------------------------------
p = os.path.join(D, "t8010-7.dtsi"); s = open(p).read()
if "apple,pmic-gpio" not in s:
    a = "\t\t/* Touch-Controller Kern-Versorgung"
    assert a in s
    s = s.replace(a, """\t\t/* D2333-GPIOs (Sandcastle pmu_gpio): GPIO 10 = WLAN reg_on */
\t\tpmic_gpio: gpio@900 {
\t\t\tcompatible = "apple,pmic-gpio";
\t\t\treg = <0x900 0x40>;
\t\t\tapple,input-reg = <0x186>;
\t\t\tapple,gpio-offsets = <0x00 0x02 0x04 0x06 0x08 0x0a 0x0c 0x0e
\t\t\t\t\t      0x10 0x12 0x14 0x16 0x18 0x1a 0x1c 0x1e
\t\t\t\t\t      0x20 0x27 0x2d 0x33 0x39>;
\t\t\tgpio-controller;
\t\t\t#gpio-cells = <2>;
\t\t};

""" + a, 1)
if "pci@2,0" not in s:
    s += """
&pcie {
\tstatus = "okay";

\t/* Port 2: WLAN (BCM4355, ADT pci-bridge2/wlan) */
\tport02: pci@2,0 {
\t\tdevice_type = "pci";
\t\treg = <0x1000 0x0 0x0 0x0 0x0>;
\t\treset-gpios = <&pinctrl_ap 14 GPIO_ACTIVE_LOW>;
\t\t/* Einschaltreihenfolge: device_wake (SoC 88), dann reg_on (PMU 10) */
\t\tpower-gpios = <&pinctrl_ap 88 GPIO_ACTIVE_HIGH>,
\t\t\t      <&pmic_gpio 10 GPIO_ACTIVE_HIGH>;
\t\tmax-link-speed = <1>;
\t\t#address-cells = <3>;
\t\t#size-cells = <2>;
\t\tranges;
\t};
};
"""
open(p, "w").write(s)
print("DT ok")

#!/usr/bin/env python3
"""Device-Tree-Ergänzungen für Touch auf dem iPhone 7 (idempotent).
Werte aus Project Sandcastle hx-h9p-d101.dts + Live-ADT (2026-11-06)."""
import os, sys
T = sys.argv[1] if len(sys.argv) > 1 else "linux-hoolock-7.0.12"
D = os.path.join(T, "arch/arm64/boot/dts/apple")

# --- t8010.dtsi: spi2 (SoC, standardmäßig aus) --------------------------
p = os.path.join(D, "t8010.dtsi"); s = open(p).read()
if "spi@20a088000" not in s:
    anchor = "\t\tbus@20c000000 {"
    node = """\t\tspi2: spi@20a088000 {
\t\t\tcompatible = "apple,t8010-spi";
\t\t\treg = <0x2 0x0a088000 0x0 0x4000>;
\t\t\tclocks = <&clkref>;
\t\t\tinterrupt-parent = <&aic>;
\t\t\tinterrupts = <AIC_IRQ 216 IRQ_TYPE_LEVEL_HIGH>;
\t\t\tpower-domains = <&ps_spi2>;
\t\t\t#address-cells = <1>;
\t\t\t#size-cells = <0>;
\t\t\tstatus = "disabled";
\t\t};

"""
    assert anchor in s
    s = s.replace(anchor, node + anchor, 1)
    open(p, "w").write(s); print("t8010.dtsi: spi2 ergänzt")

# --- t8010-7.dtsi: Touch für iPhone 7 / 7 Plus ---------------------------
p = os.path.join(D, "t8010-7.dtsi"); s = open(p).read()
if "apple,t8010-multitouch" not in s:
    if "dt-bindings/gpio/gpio.h" not in s:
        s = s.replace('#include "t8010.dtsi"', '#include "t8010.dtsi"\n#include <dt-bindings/gpio/gpio.h>', 1)
    # Kern-Versorgung im D2333 (pmic@74)
    a = "\t\tnvmem@5000 {"
    assert a in s
    s = s.replace(a, """\t\t/* Touch-Controller Kern-Versorgung (Sandcastle: touch_pwrsw) */
\t\ttouch_core: touch-core@31f {
\t\t\tcompatible = "apple,pmic-switch";
\t\t\treg = <0x31f 1>;
\t\t\tapple,enable-mask = <0x01>;
\t\t\tregulator-name = "touch-core";
\t\t};

""" + a, 1)
    s += """
&pmgr {
\ttouch_clk: clock-controller@78000 {
\t\tcompatible = "apple,t8010-touch-clk";
\t\treg = <0x78000 0x8>;
\t\tclocks = <&clkref>;
\t\t#clock-cells = <0>;
\t\tclock-frequency = <32768>;
\t\tclock-output-names = "touch_clk";
\t};
};

&i2c0 {
\tstatus = "okay";

\t/* Display-PMU "chestnut": Reg 0x05 Bits 0-3 = LCD-LDO (nicht anfassen!), Bit 4 = Touch HV */
\tpmic@27 {
\t\tcompatible = "apple,chestnut-pmic";
\t\treg = <0x27>;
\t\t#address-cells = <1>;
\t\t#size-cells = <1>;

\t\ttouch_hv: touch-hv@5 {
\t\t\tcompatible = "apple,pmic-switch";
\t\t\treg = <0x5 1>;
\t\t\tapple,enable-mask = <0x10>;
\t\t\tregulator-name = "touch-hv";
\t\t};
\t};
};

&spi2 {
\tstatus = "okay";

\ttouchscreen@0 {
\t\tcompatible = "apple,t8010-multitouch";
\t\treg = <0>;
\t\tspi-max-frequency = <3000000>;
\t\thv-supply = <&touch_hv>;
\t\tcore-supply = <&touch_core>;
\t\treset-gpios = <&pinctrl_ap 161 GPIO_ACTIVE_HIGH>;
\t\tcs-gpios = <&pinctrl_ap 81 GPIO_ACTIVE_HIGH>;
\t\tirq-gpios = <&pinctrl_ap 166 GPIO_ACTIVE_LOW>;
\t\tclocks = <&touch_clk>;
\t};
};
"""
    open(p, "w").write(s); print("t8010-7.dtsi: Touch ergänzt")

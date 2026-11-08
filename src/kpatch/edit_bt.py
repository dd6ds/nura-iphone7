#!/usr/bin/env python3
# Bluetooth iPhone 7 (BCM4355C0 an UART1): hci_bcm-Erweiterung + DT
# Taurus-Kalibrierung nach HoolockLinux tests/bluetooth (Nick Chan), hier optional/nicht fatal.
import pathlib, sys
T = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12"
DTS = "arch/arm64/boot/dts/apple/"

def sub(path, old, new, count=1):
    p = T / path; s = p.read_text()
    if new in s: return
    if s.count(old) != count: sys.exit(f"{path}: Anker {s.count(old)}x: {old[:60]!r}")
    p.write_text(s.replace(old, new))

H = "drivers/bluetooth/hci_bcm.c"
sub(H, "\tbool	drive_rts_on_open;\n",
    "\tbool	drive_rts_on_open;\n"
    "\tbool	taurus_cal;\n"
    "\tbool	use_bdaddr_property;\n")
sub(H, "\tbool			drive_rts_on_open;\n",
    "\tbool			drive_rts_on_open;\n"
    "\tbool			use_bdaddr_property;\n\n"
    "\t/* Apple: \"Taurus\"-Kalibrierblob aus der ADT (m1n1 -> brcm,taurus-cal-blob) */\n"
    "\tconst void		*taurus_cal_blob;\n"
    "\tint			taurus_cal_size;\n")

sub(H, "static int bcm_setup(struct hci_uart *hu)\n{",
    "#define BCM_TAURUS_CAL_CHUNK 0xe6\n"
    "struct bcm_taurus_cal_cmd {\n"
    "\tu8 unk;\n\t__le16 blocks_left;\n\tu8 data[BCM_TAURUS_CAL_CHUNK];\n} __packed;\n\n"
    "static int bcm_send_taurus_cal(struct hci_uart *hu, const u8 *data, size_t size)\n{\n"
    "\tsize_t blocks = DIV_ROUND_UP(size, (size_t)BCM_TAURUS_CAL_CHUNK);\n"
    "\tstruct bcm_taurus_cal_cmd cmd;\n\tstruct sk_buff *skb;\n\tsize_t i, len;\n\n"
    "\tbt_dev_info(hu->hdev, \"sende %zu Byte Taurus-Kalibrierung\", size);\n"
    "\tfor (i = 0; i < blocks; i++) {\n"
    "\t\tlen = min_t(size_t, size - i * BCM_TAURUS_CAL_CHUNK, BCM_TAURUS_CAL_CHUNK);\n"
    "\t\tmemset(&cmd, 0, sizeof(cmd));\n"
    "\t\tcmd.unk = 0x03;\n"
    "\t\tcmd.blocks_left = cpu_to_le16(blocks - i - 1);\n"
    "\t\tmemcpy(cmd.data, data + i * BCM_TAURUS_CAL_CHUNK, len);\n"
    "\t\tskb = __hci_cmd_sync(hu->hdev, 0xfd97, sizeof(cmd), &cmd, HCI_INIT_TIMEOUT);\n"
    "\t\tif (IS_ERR(skb))\n\t\t\treturn PTR_ERR(skb);\n"
    "\t\tkfree_skb(skb);\n\t}\n\treturn 0;\n}\n\n"
    "static int bcm_setup(struct hci_uart *hu)\n{")

sub(H, "\terr = btbcm_finalize(hu->hdev, &fw_load_done, use_autobaud_mode);\n",
    "\tif (bcm->dev && bcm->dev->taurus_cal_blob) {\n"
    "\t\terr = bcm_send_taurus_cal(hu, bcm->dev->taurus_cal_blob,\n"
    "\t\t\t\t\t  bcm->dev->taurus_cal_size);\n"
    "\t\tif (err)\t/* nicht fatal: Funk geht auch unkalibriert */\n"
    "\t\t\tbt_dev_warn(hu->hdev, \"Taurus-Kalibrierung fehlgeschlagen: %d\", err);\n"
    "\t}\n\n"
    "\terr = btbcm_finalize(hu->hdev, &fw_load_done, use_autobaud_mode);\n")

sub(H, "\tif (hci_test_quirk(hu->hdev, HCI_QUIRK_INVALID_BDADDR))\n",
    "\tif (hci_test_quirk(hu->hdev, HCI_QUIRK_INVALID_BDADDR) ||\n"
    "\t    (bcm->dev && bcm->dev->use_bdaddr_property))\n")

sub(H, "\tbdev->irq = of_irq_get_byname(bdev->dev->of_node, \"host-wakeup\");\n",
    "\tbdev->irq = of_irq_get_byname(bdev->dev->of_node, \"host-wakeup\");\n"
    "\tbdev->taurus_cal_blob = of_get_property(bdev->dev->of_node,\n"
    "\t\t\t\t\t\t\"brcm,taurus-cal-blob\",\n"
    "\t\t\t\t\t\t&bdev->taurus_cal_size);\n")

sub(H, "\t\tbcmdev->drive_rts_on_open = data->drive_rts_on_open;\n",
    "\t\tbcmdev->drive_rts_on_open = data->drive_rts_on_open;\n"
    "\t\tbcmdev->use_bdaddr_property = data->use_bdaddr_property;\n"
    "\t\tif (!data->taurus_cal)\n"
    "\t\t\tbcmdev->taurus_cal_blob = NULL;\n")

sub(H, "static const struct of_device_id bcm_bluetooth_of_match[] = {\n",
    "static struct bcm_device_data bcm4355_apple_device_data = {\n"
    "\t.drive_rts_on_open = true,\n"
    "\t.taurus_cal = true,\n"
    "\t.use_bdaddr_property = true,\n"
    "};\n\n"
    "static const struct of_device_id bcm_bluetooth_of_match[] = {\n")
sub(H, "\t{ .compatible = \"brcm,bcm4335a0\" },\n",
    "\t{ .compatible = \"brcm,bcm4335a0\" },\n"
    "\t{ .compatible = \"brcm,bcm4355c0-bt-apple\", .data = &bcm4355_apple_device_data },\n")

# ---- DT: UART1 + Pinmux (TX GPIO 96, RTS GPIO 98 laut ADT function-tx/-rts)
sub(DTS + "t8010.dtsi",
    "\t\tserial4: serial@20a0d0000 {\n",
    "\t\tserial1: serial@20a0c4000 {\n"
    "\t\t\tcompatible = \"apple,s5l-uart\";\n"
    "\t\t\treg = <0x2 0x0a0c4000 0x0 0x4000>;\n"
    "\t\t\treg-io-width = <4>;\n"
    "\t\t\tinterrupt-parent = <&aic>;\n"
    "\t\t\tinterrupts = <AIC_IRQ 219 IRQ_TYPE_LEVEL_HIGH>;\n"
    "\t\t\tclocks = <&clkref>, <&clkref>;\n"
    "\t\t\tclock-names = \"uart\", \"clk_uart_baud0\";\n"
    "\t\t\tpinctrl-0 = <&uart1_pins>;\n"
    "\t\t\tpinctrl-names = \"default\";\n"
    "\t\t\tpower-domains = <&ps_uart1>;\n"
    "\t\t\tstatus = \"disabled\";\n"
    "\t\t};\n\n"
    "\t\tserial4: serial@20a0d0000 {\n")
sub(DTS + "t8010.dtsi",
    "\t\t\tpcie_clkreq_pins: pcie-clkreq-pins {\n",
    "\t\t\tuart1_pins: uart1-pins {\n"
    "\t\t\t\tpinmux = <APPLE_PINMUX(96, 1)>,\n"
    "\t\t\t\t\t <APPLE_PINMUX(98, 1)>;\n"
    "\t\t\t};\n\n"
    "\t\t\tpcie_clkreq_pins: pcie-clkreq-pins {\n")

# ---- Board: BCM4355C0 (Modul "Elsa") an UART1
s = (T / (DTS + "t8010-7.dtsi")).read_text()
if "bluetooth0 = &bluetooth0" not in s:
    s = s.replace("\t\tserial5 = &serial5;\n\t};\n",
                  "\t\tserial5 = &serial5;\n\t\tserial1 = &serial1;\n"
                  "\t\tbluetooth0 = &bluetooth0;\n\t};\n", 1)
    s += ("\n&serial1 {\n\tstatus = \"okay\";\n\n"
          "\t/* BCM4355C0-Bluetooth (ADT: uart1/bluetooth, Firmware \"Elsa\") */\n"
          "\tbluetooth0: bluetooth {\n"
          "\t\tcompatible = \"brcm,bcm4355c0-bt-apple\";\n"
          "\t\tdevice-wakeup-gpios = <&pinctrl_ap 87 GPIO_ACTIVE_HIGH>;\n"
          "\t\tshutdown-gpios = <&pmic_gpio 8 GPIO_ACTIVE_HIGH>;\n"
          "\t\tmax-speed = <1500000>;\n"
          "\t\tlocal-bd-address = [00 00 00 00 00 00];\n"
          "\t};\n};\n")
    if "bluetooth0 = &bluetooth0" not in s:
        sys.exit("t8010-7.dtsi: Alias einfügen fehlgeschlagen")
    (T / (DTS + "t8010-7.dtsi")).write_text(s)
print("bt ok")

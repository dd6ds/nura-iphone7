#!/usr/bin/env python3
# Interner Speicher iPhone 7: Apple-Embedded-NVMe (ANS2/S3E, 106b:2002) an PCIe-Port 0
#  - pcie-apple-t8010: Port 0 + SART (Scratch-Fenster der NVMe-Firmware), skip_ports-Notschalter,
#    Konfig-Zugriffe nur auf Busse hinter Ports mit Link
#  - nvme-pci: Quirk NVME_QUIRK_APPLE_EMBEDDED nach Sandcastle hx.c (Scratch-Setup vor CC.EN),
#    zunächst OHNE NVMMU (Standard-PRPs über das statische DART-Fenster)
import pathlib, sys
T = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12"
DTS = "arch/arm64/boot/dts/apple/"

def sub(path, old, new, count=1):
    p = T / path; s = p.read_text()
    if new in s: return
    if s.count(old) != count: sys.exit(f"{path}: Anker {s.count(old)}x: {old[:70]!r}")
    p.write_text(s.replace(old, new))

# ------------------------------------------------------------ PCIe-Treiber
P = "drivers/pci/controller/pcie-apple-t8010.c"
sub(P, "\tu32 max_speed;\n\tbool link_up;\n};\n",
    "\tu32 max_speed;\n\tbool link_up;\n"
    "\t/* NVMe-Port: SART bildet das Scratch-Fenster (IOVA) auf reservierten RAM ab */\n"
    "\tvoid __iomem *sart;\n\tu32 sart_iova, sart_size;\n\tu64 sart_pa;\n};\n")

sub(P, "static bool t8010_link_up(struct t8010_port *port)\n",
    "#define SART_CTRL\t\t0x20\n#define SART_VA_BASE\t\t0x24\n"
    "#define SART_VA_END\t\t0x28\n#define SART_PA_BASE\t\t0x2c\n\n"
    "static void t8010_setup_sart(struct t8010_pcie *pcie, struct t8010_port *port)\n{\n"
    "\tvoid __iomem *s = port->sart;\n\n"
    "\tdev_info(pcie->dev, \"port%u: SART vorher ctrl %#x va %#x-%#x pa %#x\\n\", port->idx,\n"
    "\t\t readl(s + SART_CTRL), readl(s + SART_VA_BASE), readl(s + SART_VA_END),\n"
    "\t\t readl(s + SART_PA_BASE));\n"
    "\twritel(port->sart_iova - 0x80000000u, s + SART_VA_BASE);\n"
    "\twritel(port->sart_iova + ALIGN(port->sart_size, SZ_1M) - 0x80100000u,\n"
    "\t       s + SART_VA_END);\n"
    "\twritel(port->sart_pa >> 20, s + SART_PA_BASE);\n"
    "\twritel(1, s + SART_CTRL);\n"
    "\tdev_info(pcie->dev, \"port%u: SART %#x+%#x -> %#llx\\n\", port->idx,\n"
    "\t\t port->sart_iova, port->sart_size, port->sart_pa);\n}\n\n"
    "static bool t8010_link_up(struct t8010_port *port)\n")

sub(P, "\t\tt8010_setup_port(pcie, cfg->win, port);\n",
    "\t\tt8010_setup_port(pcie, cfg->win, port);\n"
    "\t\tif (port->sart)\n\t\t\tt8010_setup_sart(pcie, port);\n")

# Konfig-Zugriffe hinter einem Port ohne Link -> nicht vorhanden (sonst SError/Hänger)
sub(P, "\tif (bus->number != cfg->busr.start)\n\t\treturn true;\n\tpcie = pci_host_bridge_priv(dev_get_drvdata(cfg->parent));\n",
    "\tpcie = pci_host_bridge_priv(dev_get_drvdata(cfg->parent));\n"
    "\tif (bus->number != cfg->busr.start) {\n"
    "\t\tstruct pci_dev *rp = bus->self;\n\n"
    "\t\tif (PCI_SLOT(devfn) != 0)\n\t\t\treturn false;\n"
    "\t\tif (rp && rp->bus->number == cfg->busr.start &&\n"
    "\t\t    PCI_SLOT(rp->devfn) < NUM_PORT)\n"
    "\t\t\treturn pcie->port[PCI_SLOT(rp->devfn)].link_up;\n"
    "\t\treturn true;\n\t}\n")

sub(P, "static bool disable;\nmodule_param(disable, bool, 0644);\n",
    "static bool disable;\nmodule_param(disable, bool, 0644);\n"
    "/* Ports trotz DT auslassen, z.B. skip_ports=0x1 = ohne NVMe */\n"
    "static uint skip_ports;\nmodule_param(skip_ports, uint, 0444);\n")

sub(P, "\tport->idx = PCI_SLOT(devfn);\n",
    "\tport->idx = PCI_SLOT(devfn);\n"
    "\tif (skip_ports & BIT(port->idx)) {\n"
    "\t\tdev_info(dev, \"port%u: per skip_ports ausgelassen\\n\", port->idx);\n"
    "\t\treturn 0;\n\t}\n")

sub(P, "\tif (of_property_read_u32(np, \"max-link-speed\", &port->max_speed))\n",
    "\tsnprintf(name, sizeof(name), \"sart%u\", port->idx);\n"
    "\tif (platform_get_resource_byname(pdev, IORESOURCE_MEM, name)) {\n"
    "\t\tu32 sart[4];\n\n"
    "\t\tif (of_property_read_u32_array(np, \"apple,sart\", sart, 4))\n"
    "\t\t\treturn dev_err_probe(dev, -EINVAL, \"port%u: apple,sart fehlt\\n\", port->idx);\n"
    "\t\tport->sart = devm_platform_ioremap_resource_byname(pdev, name);\n"
    "\t\tif (IS_ERR(port->sart))\n\t\t\treturn PTR_ERR(port->sart);\n"
    "\t\tport->sart_iova = sart[0];\n"
    "\t\tport->sart_pa = ((u64)sart[1] << 32) | sart[2];\n"
    "\t\tport->sart_size = sart[3];\n\t}\n\n"
    "\tif (of_property_read_u32(np, \"max-link-speed\", &port->max_speed))\n")

# ------------------------------------------------------------ nvme-pci
H = "drivers/nvme/host/nvme.h"
sub(H, "\tNVME_QUIRK_DMAPOOL_ALIGN_512\t\t= (1 << 22),\n};\n",
    "\tNVME_QUIRK_DMAPOOL_ALIGN_512\t\t= (1 << 22),\n\n"
    "\t/*\n\t * Apple embedded NVMe (iPhone/iPad, ANS2/S3E): firmware scratch area\n"
    "\t * must be handed over before CC.EN\n\t */\n"
    "\tNVME_QUIRK_APPLE_EMBEDDED\t\t= (1 << 23),\n};\n")

C = "drivers/nvme/host/pci.c"
sub(C, "\t{ PCI_DEVICE(PCI_VENDOR_ID_APPLE, 0x2003) },\n",
    "\t{ PCI_DEVICE(PCI_VENDOR_ID_APPLE, 0x2002),\t/* iPhone 7 (A10) S3E */\n"
    "\t\t.driver_data = NVME_QUIRK_APPLE_EMBEDDED |\n"
    "\t\t\t\tNVME_QUIRK_SINGLE_VECTOR |\n"
    "\t\t\t\tNVME_QUIRK_SHARED_TAGS, },\n"
    "\t{ PCI_DEVICE(PCI_VENDOR_ID_APPLE, 0x2003) },\n")

sub(C, "static int nvme_pci_configure_admin_queue(struct nvme_dev *dev)\n",
    "/* ---- Apple embedded NVMe (nach Corellium Sandcastle nvme/host/hx.c) ---- */\n"
    "#define APPLE_EMB_INIT\t\t\t0x1800\n"
    "#define APPLE_EMB_SCRATCH_SIZE_REQ\t0x1808\n"
    "#define APPLE_EMB_SCRATCH_ALIGN_REQ\t0x180c\n"
    "#define APPLE_EMB_SCRATCH_BASE_LO\t0x1810\n"
    "#define APPLE_EMB_SCRATCH_BASE_HI\t0x1814\n"
    "#define APPLE_EMB_SCRATCH_SIZE\t\t0x1818\n"
    "#define APPLE_EMB_CORE_MASK\t\t0x1824\n"
    "#define APPLE_EMB_LOG_SIZE\t\t0x1828\n"
    "#define APPLE_EMB_BOOT_STATE\t\t0x1b18\n\n"
    "static int nvme_apple_emb_preinit(struct nvme_dev *dev)\n{\n"
    "\tstruct pci_dev *pdev = to_pci_dev(dev->dev);\n"
    "\tu32 req, align, sc[2];\n\n"
    "\tpci_write_config_byte(pdev, PCI_LATENCY_TIMER, 0x40);\n"
    "\tpci_write_config_dword(pdev, 0x17c, 0x10081008);\t/* LTR max (no-)snoop */\n"
    "\tpci_write_config_dword(pdev, 0x18c, 0x00000000);\t/* L1SS ctl2 */\n"
    "\tpci_write_config_dword(pdev, 0x188, 0x40550000);\t/* L1SS ctl1 */\n\n"
    "\treq = readl(dev->bar + APPLE_EMB_SCRATCH_SIZE_REQ);\n"
    "\talign = readl(dev->bar + APPLE_EMB_SCRATCH_ALIGN_REQ);\n"
    "\tdev_info(dev->ctrl.device,\n"
    "\t\t \"Apple-NVMe: boot-state %#x, Scratch %#x/%#x, Kerne %#x, Log %#x, CSTS %#x\\n\",\n"
    "\t\t readl(dev->bar + APPLE_EMB_BOOT_STATE), req, align,\n"
    "\t\t readl(dev->bar + APPLE_EMB_CORE_MASK),\n"
    "\t\t readl(dev->bar + APPLE_EMB_LOG_SIZE), readl(dev->bar + NVME_REG_CSTS));\n\n"
    "\tif (!pdev->dev.of_node ||\n"
    "\t    of_property_read_u32_array(pdev->dev.of_node, \"apple,nvme-scratch\", sc, 2)) {\n"
    "\t\tdev_err(dev->ctrl.device, \"apple,nvme-scratch fehlt im DT\\n\");\n"
    "\t\treturn -ENODEV;\n\t}\n"
    "\tif (sc[1] < req || (align && (sc[0] & (align - 1)))) {\n"
    "\t\tdev_err(dev->ctrl.device, \"Scratch %#x+%#x passt nicht (Bedarf %#x/%#x)\\n\",\n"
    "\t\t\tsc[0], sc[1], req, align);\n\t\treturn -ENOSPC;\n\t}\n"
    "\tdev->apple_scratch_iova = sc[0];\n\tdev->apple_scratch_size = sc[1];\n"
    "\treturn 0;\n}\n\n"
    "static void nvme_apple_emb_preenable(struct nvme_dev *dev)\n{\n"
    "\twritel(0, dev->bar + APPLE_EMB_INIT);\t/* regular */\n"
    "\twritel(dev->apple_scratch_iova, dev->bar + APPLE_EMB_SCRATCH_BASE_LO);\n"
    "\twritel(0, dev->bar + APPLE_EMB_SCRATCH_BASE_HI);\n"
    "\twritel(dev->apple_scratch_size, dev->bar + APPLE_EMB_SCRATCH_SIZE);\n}\n\n"
    "static int nvme_pci_configure_admin_queue(struct nvme_dev *dev)\n")

sub(C, "\tlo_hi_writeq(nvmeq->cq_dma_addr, dev->bar + NVME_REG_ACQ);\n\n\tresult = nvme_enable_ctrl(&dev->ctrl);\n",
    "\tlo_hi_writeq(nvmeq->cq_dma_addr, dev->bar + NVME_REG_ACQ);\n\n"
    "\tif (dev->ctrl.quirks & NVME_QUIRK_APPLE_EMBEDDED)\n"
    "\t\tnvme_apple_emb_preenable(dev);\n\n"
    "\tresult = nvme_enable_ctrl(&dev->ctrl);\n")

sub(C, "\tdev->ctrl.sqsize = dev->q_depth - 1; /* 0's based queue depth */\n\n\tnvme_map_cmb(dev);\n",
    "\tdev->ctrl.sqsize = dev->q_depth - 1; /* 0's based queue depth */\n\n"
    "\tif (dev->ctrl.quirks & NVME_QUIRK_APPLE_EMBEDDED) {\n"
    "\t\tresult = nvme_apple_emb_preinit(dev);\n"
    "\t\tif (result)\n\t\t\tgoto disable;\n"
    "\t\t/* Sandcastle: max. 256 Sektoren je Befehl */\n"
    "\t\tdev->ctrl.max_hw_sectors = min_t(u32, dev->ctrl.max_hw_sectors, 256);\n\t}\n\n"
    "\tnvme_map_cmb(dev);\n")
print("nvme ok")

sub(C, "struct nvme_dev {\n\tstruct nvme_queue *queues;\n",
    "struct nvme_dev {\n\tstruct nvme_queue *queues;\n"
    "\tu32 apple_scratch_iova, apple_scratch_size;\t/* NVME_QUIRK_APPLE_EMBEDDED */\n")
s = (T / C).read_text()
if "#include <linux/of.h>" not in s:
    sub(C, "#include <linux/once.h>\n", "#include <linux/of.h>\n#include <linux/once.h>\n")
sub(H, "\tcase NVME_QUIRK_DMAPOOL_ALIGN_512:\n\t\treturn \"dmapool_align_512\";\n",
    "\tcase NVME_QUIRK_DMAPOOL_ALIGN_512:\n\t\treturn \"dmapool_align_512\";\n"
    "\tcase NVME_QUIRK_APPLE_EMBEDDED:\n\t\treturn \"apple_embedded\";\n")

# ------------------------------------------------------------ DT
sub(DTS + "t8010.dtsi",
    "\t\t\t      <0x6 0x03008000 0x0 0x4000>;\n"
    "\t\t\treg-names = \"config\", \"phy0\", \"phy1\", \"phy2\", \"glue\",\n"
    "\t\t\t\t    \"port0\", \"port1\", \"port2\", \"port3\", \"dart2\";\n",
    "\t\t\t      <0x6 0x03008000 0x0 0x4000>,\n"
    "\t\t\t      <0x6 0x01008000 0x0 0x4000>,\n"
    "\t\t\t      <0x6 0x01004000 0x0 0x4000>;\n"
    "\t\t\treg-names = \"config\", \"phy0\", \"phy1\", \"phy2\", \"glue\",\n"
    "\t\t\t\t    \"port0\", \"port1\", \"port2\", \"port3\", \"dart2\",\n"
    "\t\t\t\t    \"dart0\", \"sart0\";\n")
sub(DTS + "t8010-7.dtsi",
    "\t/* Port 2: WLAN (BCM4355, ADT pci-bridge2/wlan) */\n",
    "\t/* Port 0: interner Speicher (S3E/ANS2-NVMe, ADT pci-bridge0/s3e) */\n"
    "\tport00: pci@0,0 {\n"
    "\t\tdevice_type = \"pci\";\n"
    "\t\treg = <0x0 0x0 0x0 0x0 0x0>;\n"
    "\t\treset-gpios = <&pinctrl_ap 12 GPIO_ACTIVE_LOW>;\n"
    "\t\tmax-link-speed = <3>;\n"
    "\t\tbus-range = <1 1>;\n"
    "\t\t/* ADT nvme-mmu0 sart-region / sart-virtual-base: IOVA PA(hi lo) Größe */\n"
    "\t\tapple,sart = <0xbc000000 0x8 0x7ee00000 0x1200000>;\n"
    "\t\t#address-cells = <3>;\n"
    "\t\t#size-cells = <2>;\n"
    "\t\tranges;\n\n"
    "\t\tnvme@0,0 {\n"
    "\t\t\tcompatible = \"pci106b,2002\";\n"
    "\t\t\treg = <0x10000 0x0 0x0 0x0 0x0>;\n"
    "\t\t\t/* ADT s3e nvme-scratch-virt-region: IOVA Größe */\n"
    "\t\t\tapple,nvme-scratch = <0xbc000000 0x1200000>;\n"
    "\t\t};\n"
    "\t};\n\n"
    "\t/* Port 2: WLAN (BCM4355, ADT pci-bridge2/wlan) */\n")
sub(DTS + "t8010-7.dtsi",
    "\t\tmax-link-speed = <1>;\n\t\tbus-range = <1 1>;\n",
    "\t\tmax-link-speed = <1>;\n\t\tbus-range = <2 2>;\n")
s = (T / (DTS + "t8010-7.dtsi")).read_text()
s = s.replace("\t\twifi0: wifi@0,0 {\n\t\t\tcompatible = \"pci14e4,43dc\";\n\t\t\treg = <0x10000 ",
              "\t\twifi0: wifi@0,0 {\n\t\t\tcompatible = \"pci14e4,43dc\";\n\t\t\treg = <0x20000 ")
(T / (DTS + "t8010-7.dtsi")).write_text(s)
print("nvme+dt ok")

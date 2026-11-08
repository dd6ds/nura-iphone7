#!/usr/bin/env python3
# NVMe Runde 3: NVMMU ("flat DMA") wie iOS/Sandcastle.
# Befund r112: Befehle mit genau einer 4-KiB-Seite gehen, alles mit PRP2/PRP-Liste legt den
# ANS-Controller lahm. iOS adressiert Daten ausschließlich über die NVMMU: je Befehls-Tag ein
# TCB-Eintrag mit Liste physischer 4-KiB-Seiten; der Befehl bekommt Flag-Bit 5 und als PRP1 die
# NVMMU-Adresse 0x40000000 + (tag << 23) + Offset.
import pathlib, sys
T = pathlib.Path(__file__).parent / "linux-hoolock-7.0.12"

def sub(path, old, new):
    p = T / path; s = p.read_text()
    if new in s: return
    if s.count(old) != 1: sys.exit(f"{path}: Anker {s.count(old)}x: {old[:70]!r}")
    p.write_text(s.replace(old, new))

# ------------------------------------------------------------ Header (Schnittstelle RC <-> nvme)
hdr = T / "include/linux/pcie-apple-t8010.h"
hdr.write_text('''/* SPDX-License-Identifier: GPL-2.0 */
/* Apple A10 (t8010) PCIe: NVMMU-Schnittstelle für die eingebaute ANS2-NVMe */
#ifndef _LINUX_PCIE_APPLE_T8010_H
#define _LINUX_PCIE_APPLE_T8010_H

#include <linux/types.h>

struct pci_dev;

#define APPLE_NVMMU_TAGS	64
#define APPLE_NVMMU_SGL		256	/* 4-KiB-Seiten je Tag */
#define APPLE_NVMMU_PAGE	4096

#if IS_BUILTIN(CONFIG_PCIE_APPLE_T8010)
bool apple_t8010_nvmmu_available(struct pci_dev *pdev);
phys_addr_t apple_t8010_bus_to_phys(struct pci_dev *pdev, dma_addr_t bus);
int apple_t8010_nvmmu_map(struct pci_dev *pdev, unsigned int tag,
			  const u64 *pages, unsigned int npages, u64 *iova);
void apple_t8010_nvmmu_unmap(struct pci_dev *pdev, unsigned int tag);
#else
static inline bool apple_t8010_nvmmu_available(struct pci_dev *pdev) { return false; }
static inline phys_addr_t apple_t8010_bus_to_phys(struct pci_dev *pdev, dma_addr_t bus) { return 0; }
static inline int apple_t8010_nvmmu_map(struct pci_dev *pdev, unsigned int tag,
					const u64 *pages, unsigned int npages, u64 *iova)
{ return -ENODEV; }
static inline void apple_t8010_nvmmu_unmap(struct pci_dev *pdev, unsigned int tag) { }
#endif
#endif
''')

P = "drivers/pci/controller/pcie-apple-t8010.c"
s = (T / P).read_text()
if "#include <linux/pcie-apple-t8010.h>" not in s:
    i = s.index("#include")
    s = s[:i] + "#include <linux/dma-direct.h>\n#include <linux/pcie-apple-t8010.h>\n" + s[i:]
    (T / P).write_text(s)

sub(P, "\tvoid __iomem *sart;\n\tu32 sart_iova, sart_size;\n\tu64 sart_pa;\n};\n",
    "\tvoid __iomem *sart;\n\tu32 sart_iova, sart_size;\n\tu64 sart_pa;\n"
    "\t/* NVMMU (gleicher Registerblock wie SART): TCB je Tag + Seitenlisten */\n"
    "\tu32 *tcb, *sgl;\n\tvoid *tcb_table;\n"
    "\tdma_addr_t tcb_bus, sgl_bus, table_bus;\n"
    "\tspinlock_t nvmmu_lock;\n};\n")

sub(P, "#define SART_CTRL\t\t0x20\n",
    "#define NVMMU_TCB_CTRL\t\t0x04\n#define NVMMU_TCB_BASE_LO\t0x08\n#define NVMMU_TCB_BASE_HI\t0x0c\n"
    "#define NVMMU_TCB_TABLE_LO\t0x10\n#define NVMMU_TCB_TABLE_HI\t0x14\n"
    "#define NVMMU_TCB_SIZE\t\t0x80\n#define NVMMU_TCB_PERM_READ\t0x100\n#define NVMMU_TCB_PERM_WRITE\t0x200\n"
    "#define NVMMU_IOVA_BASE\t\t0x40000000u\n#define NVMMU_TABLE_SIZE\tSZ_64K\n\n"
    "#define SART_CTRL\t\t0x20\n")

# TCB-Register vor der SART setzen (Reihenfolge wie Sandcastle pcie_hx_setup_sart)
sub(P, "\twritel(port->sart_iova - 0x80000000u, s + SART_VA_BASE);\n",
    "\tif (port->tcb) {\n"
    "\t\tu64 tcb = dma_to_phys(pcie->dev, port->tcb_bus);\n"
    "\t\tu64 tab = dma_to_phys(pcie->dev, port->table_bus);\n\n"
    "\t\twritel(lower_32_bits(tcb), s + NVMMU_TCB_BASE_LO);\n"
    "\t\twritel(upper_32_bits(tcb), s + NVMMU_TCB_BASE_HI);\n"
    "\t\twritel(lower_32_bits(tab), s + NVMMU_TCB_TABLE_LO);\n"
    "\t\twritel(upper_32_bits(tab), s + NVMMU_TCB_TABLE_HI);\n"
    "\t\twritel(0x10000, s + NVMMU_TCB_CTRL);\n"
    "\t\tif (wait_bits(pcie, s + NVMMU_TCB_CTRL, 0x10, 0, 0, 250, \"NVMMU TCB start\"))\n"
    "\t\t\tdev_warn(pcie->dev, \"port%u: NVMMU startet nicht\\n\", port->idx);\n"
    "\t\telse\n"
    "\t\t\tdev_info(pcie->dev, \"port%u: NVMMU TCB %#llx, Tabelle %#llx\\n\",\n"
    "\t\t\t\t port->idx, tcb, tab);\n"
    "\t}\n"
    "\twritel(port->sart_iova - 0x80000000u, s + SART_VA_BASE);\n")

# Hilfsfunktionen + Exporte vor t8010_setup_sart
sub(P, "static void t8010_setup_sart(struct t8010_pcie *pcie, struct t8010_port *port)\n{\n",
    "static struct t8010_port *apple_nvmmu_port(struct pci_dev *pdev, struct t8010_pcie **pp)\n{\n"
    "\tstruct pci_host_bridge *bridge = pci_find_host_bridge(pdev->bus);\n"
    "\tstruct t8010_pcie *pcie;\n\tstruct pci_dev *rp = pcie_find_root_port(pdev);\n\n"
    "\tif (!bridge || !rp || !bridge->dev.parent ||\n"
    "\t    !of_device_is_compatible(bridge->dev.parent->of_node, \"apple,t8010-pcie\"))\n"
    "\t\treturn NULL;\n"
    "\tpcie = pci_host_bridge_priv(bridge);\n"
    "\tif (PCI_SLOT(rp->devfn) >= NUM_PORT || !pcie->port[PCI_SLOT(rp->devfn)].tcb)\n"
    "\t\treturn NULL;\n"
    "\tif (pp)\n\t\t*pp = pcie;\n"
    "\treturn &pcie->port[PCI_SLOT(rp->devfn)];\n}\n\n"
    "bool apple_t8010_nvmmu_available(struct pci_dev *pdev)\n{\n"
    "\treturn apple_nvmmu_port(pdev, NULL) != NULL;\n}\n"
    "EXPORT_SYMBOL_GPL(apple_t8010_nvmmu_available);\n\n"
    "phys_addr_t apple_t8010_bus_to_phys(struct pci_dev *pdev, dma_addr_t bus)\n{\n"
    "\t/* DMA-Adresse des PCI-Geräts (DART-Fenster/swiotlb) -> physisch, für die NVMMU */\n"
    "\treturn dma_to_phys(&pdev->dev, bus);\n}\n"
    "EXPORT_SYMBOL_GPL(apple_t8010_bus_to_phys);\n\n"
    "int apple_t8010_nvmmu_map(struct pci_dev *pdev, unsigned int tag,\n"
    "\t\t\t  const u64 *pages, unsigned int npages, u64 *iova)\n{\n"
    "\tstruct t8010_pcie *pcie;\n"
    "\tstruct t8010_port *port = apple_nvmmu_port(pdev, &pcie);\n"
    "\tu32 *tcb, *sgl;\n\tunsigned long flags;\n\tunsigned int i;\n\n"
    "\tif (!port)\n\t\treturn -ENODEV;\n"
    "\tif (tag >= APPLE_NVMMU_TAGS || !npages || npages > APPLE_NVMMU_SGL)\n"
    "\t\treturn -EINVAL;\n\n"
    "\ttcb = port->tcb + tag * (NVMMU_TCB_SIZE / 4);\n"
    "\tsgl = port->sgl + tag * APPLE_NVMMU_SGL;\n"
    "\tspin_lock_irqsave(&port->nvmmu_lock, flags);\n"
    "\tfor (i = 0; i < npages; i++)\n"
    "\t\tsgl[i] = pages[i] >> 12;\n"
    "\ttcb[0] = NVMMU_TCB_PERM_READ | NVMMU_TCB_PERM_WRITE;\n"
    "\ttcb[1] = npages;\n"
    "\ttcb[2] = pages[0] >> 12;\n"
    "\t*(u64 *)&tcb[4] = dma_to_phys(pcie->dev, port->sgl_bus) +\n"
    "\t\t\t   tag * APPLE_NVMMU_SGL * 4;\n"
    "\twmb();\t/* Tabellen sichtbar, bevor der Befehl die Doorbell erreicht */\n"
    "\tspin_unlock_irqrestore(&port->nvmmu_lock, flags);\n"
    "\t*iova = NVMMU_IOVA_BASE + ((u64)tag << 23);\n"
    "\treturn 0;\n}\n"
    "EXPORT_SYMBOL_GPL(apple_t8010_nvmmu_map);\n\n"
    "void apple_t8010_nvmmu_unmap(struct pci_dev *pdev, unsigned int tag)\n{\n"
    "\tstruct t8010_port *port = apple_nvmmu_port(pdev, NULL);\n"
    "\tunsigned long flags;\n\tu32 *tcb;\n\n"
    "\tif (!port || tag >= APPLE_NVMMU_TAGS)\n\t\treturn;\n"
    "\ttcb = port->tcb + tag * (NVMMU_TCB_SIZE / 4);\n"
    "\tspin_lock_irqsave(&port->nvmmu_lock, flags);\n"
    "\ttcb[0] = 0;\n\ttcb[1] = 0;\n\ttcb[2] = 0;\n"
    "\twmb();\n"
    "\twritel(tag, port->sart + NVMMU_TCB_CTRL);\t/* TLB des Tags verwerfen */\n"
    "\tspin_unlock_irqrestore(&port->nvmmu_lock, flags);\n}\n"
    "EXPORT_SYMBOL_GPL(apple_t8010_nvmmu_unmap);\n\n"
    "static void t8010_setup_sart(struct t8010_pcie *pcie, struct t8010_port *port)\n{\n")

# Tabellen beim Port-Parsen anlegen (kohärent = ungecacht, liegt im DART-Fenster -> phys bekannt)
sub(P, "\t\tport->sart_iova = sart[0];\n",
    "\t\tspin_lock_init(&port->nvmmu_lock);\n"
    "\t\tport->tcb = dmam_alloc_coherent(dev, APPLE_NVMMU_TAGS * NVMMU_TCB_SIZE,\n"
    "\t\t\t\t\t\t&port->tcb_bus, GFP_KERNEL);\n"
    "\t\tport->sgl = dmam_alloc_coherent(dev, APPLE_NVMMU_TAGS * APPLE_NVMMU_SGL * 4,\n"
    "\t\t\t\t\t\t&port->sgl_bus, GFP_KERNEL);\n"
    "\t\tport->tcb_table = dmam_alloc_coherent(dev, NVMMU_TABLE_SIZE,\n"
    "\t\t\t\t\t\t      &port->table_bus, GFP_KERNEL);\n"
    "\t\tif (!port->tcb || !port->sgl || !port->tcb_table)\n"
    "\t\t\treturn dev_err_probe(dev, -ENOMEM, \"NVMMU-Tabellen\\n\");\n"
    "\t\tport->sart_iova = sart[0];\n")
print("RC ok")

# ------------------------------------------------------------ nvme-pci
C = "drivers/nvme/host/pci.c"
s = (T / C).read_text()
if "#include <linux/pcie-apple-t8010.h>" not in s:
    sub(C, "#include <linux/of.h>\n", "#include <linux/of.h>\n#include <linux/pcie-apple-t8010.h>\n")

sub(C, "\tIOD_META_MMIO\t\t= 1U << 6,\n",
    "\tIOD_META_MMIO\t\t= 1U << 6,\n\n"
    "\t/* Daten über die Apple-NVMMU abgebildet */\n"
    "\tIOD_APPLE_NVMMU\t\t= 1U << 7,\n")

sub(C, "\tu32 apple_scratch_iova, apple_scratch_size;\t/* NVME_QUIRK_APPLE_EMBEDDED */\n",
    "\tu32 apple_scratch_iova, apple_scratch_size;\t/* NVME_QUIRK_APPLE_EMBEDDED */\n"
    "\tbool apple_nvmmu;\n"
    "\tstruct scatterlist *apple_sg;\t\t/* [APPLE_NVMMU_TAGS][APPLE_SG_ENTS] */\n"
    "\tint apple_nents[APPLE_NVMMU_TAGS];\n")

sub(C, "static int nvme_apple_emb_preinit(struct nvme_dev *dev)\n{\n",
    "static bool apple_nvmmu = true;\n"
    "module_param(apple_nvmmu, bool, 0444);\n"
    "MODULE_PARM_DESC(apple_nvmmu, \"Apple embedded NVMe: Daten über die NVMMU (wie iOS)\");\n\n"
    "#define APPLE_SG_ENTS\t40\t/* >= max_hw_sectors(128 KiB)/16 KiB + Reserve */\n\n"
    "static blk_status_t nvme_apple_map_data(struct nvme_dev *dev, struct request *req)\n{\n"
    "\tstruct nvme_iod *iod = blk_mq_rq_to_pdu(req);\n"
    "\tstruct pci_dev *pdev = to_pci_dev(dev->dev);\n"
    "\tunsigned int tag = req->tag, i, npages = 0;\n"
    "\tstruct scatterlist *sg, *sgl;\n"
    "\tu64 pages[64], iova, offs = 0;\t/* 128 KiB = 32 Seiten + Versatz */\n"
    "\tint mapped, nents, ret;\n\n"
    "\tif (tag >= APPLE_NVMMU_TAGS)\n\t\treturn BLK_STS_RESOURCE;\n"
    "\tsgl = dev->apple_sg + tag * APPLE_SG_ENTS;\n"
    "\tsg_init_table(sgl, APPLE_SG_ENTS);\n"
    "\tmapped = blk_rq_map_sg(req, sgl);\n"
    "\tif (!mapped)\n\t\treturn BLK_STS_IOERR;\n"
    "\tnents = dma_map_sg(dev->dev, sgl, mapped, rq_dma_dir(req));\n"
    "\tif (!nents)\n\t\treturn BLK_STS_RESOURCE;\n\n"
    "\tfor_each_sg(sgl, sg, nents, i) {\n"
    "\t\tu64 pa = apple_t8010_bus_to_phys(pdev, sg_dma_address(sg));\n"
    "\t\tu64 len = sg_dma_len(sg);\n\n"
    "\t\tif (i == 0) {\n"
    "\t\t\toffs = pa & (APPLE_NVMMU_PAGE - 1);\n"
    "\t\t\tpa -= offs;\n\t\t\tlen += offs;\n"
    "\t\t} else if (pa & (APPLE_NVMMU_PAGE - 1)) {\n"
    "\t\t\tgoto bad;\n\t\t}\n"
    "\t\tif (i != nents - 1 && (len & (APPLE_NVMMU_PAGE - 1)))\n\t\t\tgoto bad;\n"
    "\t\twhile (len) {\n"
    "\t\t\tif (npages >= ARRAY_SIZE(pages))\n\t\t\t\tgoto bad;\n"
    "\t\t\tpages[npages++] = pa;\n"
    "\t\t\tpa += APPLE_NVMMU_PAGE;\n"
    "\t\t\tlen = len > APPLE_NVMMU_PAGE ? len - APPLE_NVMMU_PAGE : 0;\n\t\t}\n\t}\n\n"
    "\tret = apple_t8010_nvmmu_map(pdev, tag, pages, npages, &iova);\n"
    "\tif (ret)\n\t\tgoto bad;\n"
    "\tdev->apple_nents[tag] = mapped;\n"
    "\tiod->flags |= IOD_APPLE_NVMMU;\n"
    "\tiod->total_len = blk_rq_payload_bytes(req);\n"
    "\tiod->cmd.common.flags = 1 << 5;\t/* \"flat DMA\" über die NVMMU */\n"
    "\tiod->cmd.common.dptr.prp1 = cpu_to_le64(iova + offs);\n"
    "\tiod->cmd.common.dptr.prp2 = 0;\n"
    "\treturn BLK_STS_OK;\n"
    "bad:\n"
    "\tdev_err_ratelimited(dev->dev, \"NVMMU: Anfrage nicht abbildbar (%d Segmente, %u Seiten)\\n\",\n"
    "\t\t\t    nents, npages);\n"
    "\tdma_unmap_sg(dev->dev, sgl, mapped, rq_dma_dir(req));\n"
    "\treturn BLK_STS_IOERR;\n}\n\n"
    "static void nvme_apple_unmap_data(struct nvme_dev *dev, struct request *req)\n{\n"
    "\tstruct nvme_iod *iod = blk_mq_rq_to_pdu(req);\n"
    "\tunsigned int tag = req->tag;\n\n"
    "\tapple_t8010_nvmmu_unmap(to_pci_dev(dev->dev), tag);\n"
    "\tdma_unmap_sg(dev->dev, dev->apple_sg + tag * APPLE_SG_ENTS,\n"
    "\t\t     dev->apple_nents[tag], rq_dma_dir(req));\n"
    "\tiod->flags &= ~IOD_APPLE_NVMMU;\n}\n\n"
    "static int nvme_apple_emb_preinit(struct nvme_dev *dev)\n{\n")

# Preinit: NVMMU einschalten, Tags auf 64 begrenzen, Puffer für Scatterlisten
sub(C, "\tdev->apple_scratch_iova = sc[0];\n\tdev->apple_scratch_size = sc[1];\n\treturn 0;\n}\n",
    "\tdev->apple_scratch_iova = sc[0];\n\tdev->apple_scratch_size = sc[1];\n\n"
    "\tdev->apple_nvmmu = apple_nvmmu && apple_t8010_nvmmu_available(pdev);\n"
    "\tif (dev->apple_nvmmu) {\n"
    "\t\tdev->apple_sg = devm_kcalloc(dev->dev, APPLE_NVMMU_TAGS * APPLE_SG_ENTS,\n"
    "\t\t\t\t\t     sizeof(*dev->apple_sg), GFP_KERNEL);\n"
    "\t\tif (!dev->apple_sg)\n\t\t\treturn -ENOMEM;\n"
    "\t\t/* Befehls-Tag = NVMMU-Tag: alle Tags (inkl. Admin) müssen < 64 bleiben */\n"
    "\t\tdev->q_depth = min_t(u32, dev->q_depth, APPLE_NVMMU_TAGS);\n"
    "\t\tdev->ctrl.sqsize = dev->q_depth - 1;\n"
    "\t}\n"
    "\tdev_info(dev->ctrl.device, \"Apple-NVMe: Daten über %s, Warteschlange %u\\n\",\n"
    "\t\t dev->apple_nvmmu ? \"NVMMU\" : \"PRP\", dev->q_depth);\n"
    "\treturn 0;\n}\n")

sub(C, "\t\t/* Sandcastle: max. 256 Sektoren je Befehl */\n"
    "\t\tdev->ctrl.max_hw_sectors = min_t(u32, dev->ctrl.max_hw_sectors, 256);\n",
    "\t\t/* Sandcastle: max. 256 Sektoren je Befehl */\n"
    "\t\tdev->ctrl.max_hw_sectors = min_t(u32, dev->ctrl.max_hw_sectors, 256);\n"
    "\t\tif (dev->apple_nvmmu)\n"
    "\t\t\tdev->ctrl.max_segments = min_t(u32, dev->ctrl.max_segments, APPLE_SG_ENTS);\n")

# Vorwärtsdeklarationen (Funktionen stehen weiter unten bei den Apple-Hilfen)
sub(C, "static void nvme_unmap_data(struct request *req)\n{\n",
    "static blk_status_t nvme_apple_map_data(struct nvme_dev *dev, struct request *req);\n"
    "static void nvme_apple_unmap_data(struct nvme_dev *dev, struct request *req);\n\n"
    "static void nvme_unmap_data(struct request *req)\n{\n")

# Einhängen in den Datenpfad
sub(C, "\tenum nvme_use_sgl use_sgl = nvme_pci_use_sgls(dev, req);\n\tstruct blk_dma_iter iter;\n\tblk_status_t ret;\n\n",
    "\tenum nvme_use_sgl use_sgl = nvme_pci_use_sgls(dev, req);\n\tstruct blk_dma_iter iter;\n\tblk_status_t ret;\n\n"
    "\tif (dev->apple_nvmmu)\n\t\treturn nvme_apple_map_data(dev, req);\n\n")
sub(C, "\tunsigned int attrs = 0;\n\n\tif (iod->flags & IOD_SINGLE_SEGMENT) {\n",
    "\tunsigned int attrs = 0;\n\n"
    "\tif (iod->flags & IOD_APPLE_NVMMU) {\n"
    "\t\tnvme_apple_unmap_data(nvmeq->dev, req);\n\t\treturn;\n\t}\n\n"
    "\tif (iod->flags & IOD_SINGLE_SEGMENT) {\n")
print("nvme-nvmmu ok")

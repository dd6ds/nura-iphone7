// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * PCIe root complex of the Apple A10 (T8010, "H9P"), e.g. iPhone 7.
 *
 * PHY/port bring-up sequence and tunables come from Corellium's Project
 * Sandcastle (drivers/pci/controller/pcie-hx.c, GPL-2.0, Linux 5.4).
 * MSI handling follows the structure of pcie-apple.c (M1), whose port
 * register block is a descendant of the one found here.
 *
 * The per-port DARTs are not driven through the IOMMU framework: each
 * enabled port gets a static, linear translation (apple,dma-window) that
 * matches the dma-ranges of this node; devices then DMA via swiotlb.
 */
#include <linux/bitfield.h>
#include <linux/bitmap.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/gpio/consumer.h>
#include <linux/interrupt.h>
#include <linux/iopoll.h>
#include <linux/irqchip/irq-msi-lib.h>
#include <linux/irqdomain.h>
#include <linux/module.h>
#include <linux/msi.h>
#include <linux/of.h>
#include <linux/of_irq.h>
#include <linux/of_pci.h>
#include <linux/pci-ecam.h>
#include <linux/platform_device.h>
#include <linux/pm_domain.h>

#include "pci-host-common.h"

#define NUM_PORT		4

/* Schrittmeldungen (Debug): erscheinen vor jedem Abschnitt im Kernel-Log */
#define STEP(dev, fmt, ...) dev_info(dev, "[step] " fmt "\n", ##__VA_ARGS__)
#define MSI_PER_PORT		8

#define PORT_LTSSMCTL		0x0080
#define PORT_IRQSTAT		0x0100
#define PORT_IRQMASK		0x0104
#define PORT_MSICFG		0x0124
#define PORT_MSIVECBASE		0x0128
#define PORT_ENABLE		0x0140
#define PORT_LINKSTS		0x0208
#define PORT_LINKSTS_LTSSM	GENMASK(13, 8)

#define PHY1_PORTMASK		0x000c

/* DART (static use, see header) */
#define DART_TLB_OP		0x0000
#define  DART_TLB_OP_FLUSH	BIT(1)
#define  DART_TLB_OP_BUSY	BIT(3)
#define DART_CONFIG		0x000c
#define  DART_CONFIG_TXEN(sid)	BIT((sid) * 8 + 7)
#define DART_DIAG_CONFIG	0x0020
#define DART_UNKNOWN_24		0x0024
#define DART_UNKNOWN_2C		0x002c
#define DART_FETCH_CONFIG	0x0030
#define DART_TTBR(sid, i)	(0x0040 + 16 * (sid) + 4 * (i))
#define  DART_TTBR_VALID	BIT(31)
#define DART_TLB_STATUS		0x1000
#define DART_TLB_UNKNOWN(i)	(0x1004 + 4 * (i))
#define DART_PTE_VALID		3ull
#define DART_PTE_ADDR		0xffffff000ull
#define DART_PG			4096u
#define DART_L2_SPAN		(512u * DART_PG)	/* 2 MiB per L1 entry */

struct t8010_tunable {
	u32 off, mask, val;
};

static const struct t8010_tunable phy0_tunables[] = {
	{ 0x0008, 0x7f7f7f7f, 0x00000000 }, { 0x000c, 0x00073f3f, 0x00043f00 },
	{ 0x0010, 0x00000700, 0x00000000 }, { 0x0018, 0x00ffffff, 0x000c0960 },
	{ 0x001c, 0x00001fff, 0x0000092c }, { 0x002c, 0x000000ff, 0x00000009 },
	{ 0x003c, 0x80000000, 0x00000000 }, { 0x0100, 0x31100010, 0x01000000 },
	{ 0x0108, 0x00000707, 0x00000000 }, { 0x010c, 0x00073f3f, 0x00043f00 },
	{ 0x0110, 0x00000011, 0x00000001 }, { 0x0114, 0x00000007, 0x00000000 },
	{ 0x0118, 0x00073f3f, 0x00043f00 }, { 0x0120, 0x0333003f, 0x0111000f },
	{ 0x0130, 0x000000ff, 0x0000000f }, { 0x0138, 0x0000007f, 0x0000003e },
	{ 0x0180, 0x31100010, 0x01000000 }, { 0x0188, 0x00000707, 0x00000000 },
	{ 0x018c, 0x00073f3f, 0x00043f00 }, { 0x01a0, 0x0333003f, 0x0111000f },
	{ 0x01b0, 0x000000ff, 0x0000000f }, { 0x01b8, 0x0000007f, 0x0000003e },
	{ 0x0200, 0x31100010, 0x01000000 }, { 0x0208, 0x00000707, 0x00000000 },
	{ 0x020c, 0x00073f3f, 0x00043f00 }, { 0x0220, 0x0333003f, 0x0111000f },
	{ 0x0230, 0x000000ff, 0x0000000f }, { 0x0238, 0x0000007f, 0x0000003e },
	{ 0x0280, 0x31100010, 0x01000000 }, { 0x0288, 0x00000707, 0x00000000 },
	{ 0x028c, 0x00073f3f, 0x00043f00 }, { 0x02a0, 0x0333003f, 0x0111000f },
	{ 0x02b0, 0x000000ff, 0x0000000f }, { 0x02b8, 0x0000007f, 0x0000003e },
	{ 0x0100, 0x00000010, 0x00000010 }, { 0x0180, 0x00000010, 0x00000000 },
	{ 0x0200, 0x00000010, 0x00000000 }, { 0x0280, 0x00000010, 0x00000000 },
};

static const struct t8010_tunable config_tunables[] = {
	{ 0x0098, 0x0000000f, 0x00000000 }, { 0x0164, 0x00f8ff00, 0x00000000 },
	{ 0x08e0, 0x00000005, 0x00000005 },
};

static const struct t8010_tunable port_tunables[] = {
	{ 0x0090, 0x000000ff, 0x00000028 }, { 0x0130, 0x0000000d, 0x00000005 },
	{ 0x0134, 0x00000001, 0x00000001 }, { 0x0138, 0x00007f7f, 0x00000000 },
	{ 0x013c, 0x00000002, 0x00000002 }, { 0x0140, 0x0073ffff, 0x00704c4b },
};

struct t8010_pcie;

struct t8010_port {
	struct t8010_pcie *pcie;
	struct device_node *np;
	unsigned int idx;
	void __iomem *base;
	void __iomem *dart;
	struct gpio_desc *reset;
	struct gpio_desc *pwr[4];
	int npwr;
	u32 max_speed;
	bool link_up;
};

struct t8010_pcie {
	struct device *dev;
	struct mutex lock;
	void __iomem *phy[3];
	void __iomem *glue;
	struct t8010_port port[NUM_PORT];
	u32 port_mask;
	struct gpio_desc *debug;
	struct dev_pm_domain_list *pd_list;
	u64 doorbell;
	u32 win_bus, win_size;
	u64 win_pa;
	/* MSI */
	struct irq_fwspec fwspec;
	u32 nvecs;
	unsigned long *bitmap;
};

static void rmwl(void __iomem *a, u32 clr, u32 set)
{
	writel((readl(a) & ~clr) | set, a);
}

static void apply_tunables(void __iomem *base, const struct t8010_tunable *t, int n)
{
	int i;

	for (i = 0; i < n; i++)
		rmwl(base + t[i].off, t[i].mask, t[i].val);
}

static int wait_bits(struct t8010_pcie *pcie, void __iomem *a, u32 mask, u32 min,
		     u32 max, unsigned int ms, const char *what)
{
	u32 v;
	int ret;

	ret = readl_poll_timeout(a, v, (v & mask) >= min && (v & mask) <= max,
				 1000, ms * 1000);
	if (ret)
		dev_warn(pcie->dev, "%s timed out (0x%08x)\n", what, v);
	return ret;
}

/* ------------------------------------------------------------------ MSI -- */

static void t8010_msi_compose_msg(struct irq_data *d, struct msi_msg *msg)
{
	struct t8010_pcie *pcie = irq_data_get_irq_chip_data(d);

	msg->address_hi = upper_32_bits(pcie->doorbell);
	msg->address_lo = lower_32_bits(pcie->doorbell);
	msg->data = d->hwirq;
}

static struct irq_chip t8010_msi_bottom_chip = {
	.name			= "MSI",
	.irq_mask		= irq_chip_mask_parent,
	.irq_unmask		= irq_chip_unmask_parent,
	.irq_eoi		= irq_chip_eoi_parent,
	.irq_set_affinity	= irq_chip_set_affinity_parent,
	.irq_set_type		= irq_chip_set_type_parent,
	.irq_compose_msi_msg	= t8010_msi_compose_msg,
};

/* MSI vectors are split into one window of MSI_PER_PORT per root port. */
static int t8010_msi_port_of(void *args)
{
	msi_alloc_info_t *info = args;
	struct pci_dev *pdev, *rp;

	if (!info || !info->desc || !dev_is_pci(msi_desc_to_dev(info->desc)))
		return -EINVAL;
	pdev = to_pci_dev(msi_desc_to_dev(info->desc));
	rp = pcie_find_root_port(pdev);
	if (!rp || rp == pdev)
		return -EINVAL;
	return PCI_SLOT(rp->devfn);
}

static int t8010_msi_domain_alloc(struct irq_domain *domain, unsigned int virq,
				  unsigned int nr_irqs, void *args)
{
	struct t8010_pcie *pcie = domain->host_data;
	struct irq_fwspec fwspec = pcie->fwspec;
	int port, order = order_base_2(nr_irqs), hwirq = -ENOSPC, start, ret;
	unsigned int i;

	port = t8010_msi_port_of(args);
	if (port < 0 || port >= NUM_PORT || nr_irqs > MSI_PER_PORT)
		return -ENOSPC;

	mutex_lock(&pcie->lock);
	for (start = port * MSI_PER_PORT; start < (port + 1) * MSI_PER_PORT;
	     start += 1 << order) {
		if (!bitmap_allocate_region(pcie->bitmap, start, order)) {
			hwirq = start;
			break;
		}
	}
	mutex_unlock(&pcie->lock);
	if (hwirq < 0)
		return hwirq;

	fwspec.param[fwspec.param_count - 2] += hwirq;
	ret = irq_domain_alloc_irqs_parent(domain, virq, nr_irqs, &fwspec);
	if (ret) {
		mutex_lock(&pcie->lock);
		bitmap_release_region(pcie->bitmap, hwirq, order);
		mutex_unlock(&pcie->lock);
		return ret;
	}

	for (i = 0; i < nr_irqs; i++)
		irq_domain_set_hwirq_and_chip(domain, virq + i, hwirq + i,
					      &t8010_msi_bottom_chip, pcie);
	return 0;
}

static void t8010_msi_domain_free(struct irq_domain *domain, unsigned int virq,
				  unsigned int nr_irqs)
{
	struct irq_data *d = irq_domain_get_irq_data(domain, virq);
	struct t8010_pcie *pcie = domain->host_data;

	mutex_lock(&pcie->lock);
	bitmap_release_region(pcie->bitmap, d->hwirq, order_base_2(nr_irqs));
	mutex_unlock(&pcie->lock);
	irq_domain_free_irqs_parent(domain, virq, nr_irqs);
}

static const struct irq_domain_ops t8010_msi_domain_ops = {
	.alloc	= t8010_msi_domain_alloc,
	.free	= t8010_msi_domain_free,
};

static const struct msi_parent_ops t8010_msi_parent_ops = {
	.supported_flags	= MSI_GENERIC_FLAGS_MASK | MSI_FLAG_PCI_MSIX |
				  MSI_FLAG_MULTI_PCI_MSI,
	.required_flags		= MSI_FLAG_USE_DEF_DOM_OPS | MSI_FLAG_USE_DEF_CHIP_OPS |
				  MSI_FLAG_PCI_MSI_MASK_PARENT,
	.chip_flags		= MSI_CHIP_FLAG_SET_EOI,
	.bus_select_token	= DOMAIN_BUS_PCI_MSI,
	.init_dev_msi_info	= msi_lib_init_dev_msi_info,
};

static int t8010_msi_init(struct t8010_pcie *pcie)
{
	struct fwnode_handle *fwnode = dev_fwnode(pcie->dev);
	struct irq_domain_info info = {
		.fwnode		= fwnode,
		.ops		= &t8010_msi_domain_ops,
		.host_data	= pcie,
	};
	struct of_phandle_args args = {};
	int ret;

	ret = of_parse_phandle_with_args(pcie->dev->of_node, "msi-ranges",
					 "#interrupt-cells", 0, &args);
	if (ret)
		return ret;
	ret = of_property_read_u32_index(pcie->dev->of_node, "msi-ranges",
					 args.args_count + 1, &pcie->nvecs);
	if (ret)
		return ret;
	if (pcie->nvecs != NUM_PORT * MSI_PER_PORT)
		return dev_err_probe(pcie->dev, -EINVAL, "need %d MSI vectors\n",
				     NUM_PORT * MSI_PER_PORT);

	of_phandle_args_to_fwspec(args.np, args.args, args.args_count, &pcie->fwspec);
	pcie->bitmap = devm_bitmap_zalloc(pcie->dev, pcie->nvecs, GFP_KERNEL);
	if (!pcie->bitmap)
		return -ENOMEM;

	info.size = pcie->nvecs;
	info.parent = irq_find_matching_fwspec(&pcie->fwspec, DOMAIN_BUS_WIRED);
	if (!info.parent)
		return dev_err_probe(pcie->dev, -ENXIO, "no parent IRQ domain\n");
	if (!msi_create_parent_irq_domain(&info, &t8010_msi_parent_ops))
		return dev_err_probe(pcie->dev, -ENOMEM, "MSI domain failed\n");
	return 0;
}

static irqreturn_t t8010_port_irq(int irq, void *data)
{
	struct t8010_port *port = data;
	u32 st = readl(port->base + PORT_IRQSTAT);

	writel(st, port->base + PORT_IRQSTAT);
	dev_dbg(port->pcie->dev, "port%u irq 0x%08x\n", port->idx, st);
	return IRQ_HANDLED;
}

/* --------------------------------------------------------- static DART -- */

static int t8010_dart_static_map(struct t8010_pcie *pcie, struct t8010_port *port)
{
	struct device *dev = pcie->dev;
	void __iomem *d = port->dart;
	u32 nl2 = DIV_ROUND_UP(pcie->win_size, DART_L2_SPAN), i, n;
	u64 *l1, *l2, pa;
	dma_addr_t l1_dma, l2_dma;
	u32 v;

	l1 = dmam_alloc_coherent(dev, 4 * DART_PG, &l1_dma, GFP_KERNEL);
	l2 = dmam_alloc_coherent(dev, (size_t)nl2 * DART_PG, &l2_dma, GFP_KERNEL);
	if (!l1 || !l2)
		return -ENOMEM;

	n = pcie->win_size / DART_PG;
	for (i = 0, pa = pcie->win_pa; i < n; i++, pa += DART_PG)
		l2[i] = (pa & DART_PTE_ADDR) | DART_PTE_VALID;
	for (i = 0; i < nl2; i++)
		l1[i] = ((l2_dma + (u64)i * DART_PG) & DART_PTE_ADDR) | DART_PTE_VALID;
	wmb();

	STEP(dev, "8a dart tables %u KiB", nl2 * 4);
	/* init sequence from Sandcastle / ADT (fetch-config, diag-config) */
	writel(0x0020fffc, d + DART_UNKNOWN_24);
	writel(0, d + DART_UNKNOWN_2C);
	for (i = 0; i < 16; i++)
		writel(0, d + DART_TTBR(i / 4, i % 4));
	writel(0x000e0303, d + DART_FETCH_CONFIG);
	writel(0x00000100, d + DART_DIAG_CONFIG);
	for (i = 0; i < 6; i++)
		writel(0, d + DART_TLB_UNKNOWN(i));
	writel(0x03f3ffff, d + DART_TLB_STATUS);

	/* window starts at bus address win_bus == DART VA 0, SID 0 */
	for (i = 0; i < 4; i++)
		writel((((l1_dma >> 12) + i) & 0x00ffffff) | DART_TTBR_VALID,
		       d + DART_TTBR(0, i));

	STEP(dev, "8b dart flush");
	writel(DART_TLB_OP_FLUSH | (0xf << 8), d + DART_TLB_OP);
	if (readl_poll_timeout(d + DART_TLB_OP, v, !(v & DART_TLB_OP_BUSY), 1, 10000))
		dev_warn(dev, "port%u: DART flush timeout\n", port->idx);

	rmwl(d + DART_CONFIG, 0, DART_CONFIG_TXEN(0));
	dev_info(dev, "port%u: DART bus 0x%x+0x%x -> 0x%llx, config 0x%08x\n",
		 port->idx, pcie->win_bus, pcie->win_size, pcie->win_pa,
		 readl(d + DART_CONFIG));
	return 0;
}

/* -------------------------------------------------------- bring-up ------ */

static bool t8010_link_up(struct t8010_port *port)
{
	u32 st = FIELD_GET(PORT_LINKSTS_LTSSM, readl(port->base + PORT_LINKSTS));

	return st >= 0x11 && st <= 0x14;
}

static void t8010_port_power_on(struct t8010_port *port)
{
	int i;

	if (!port->npwr)
		return;
	/* all supplies off, then on in DT order (Sandcastle devpwr-on-2) */
	for (i = 0; i < port->npwr; i++) {
		usleep_range(2500, 5000);
		gpiod_set_value_cansleep(port->pwr[i], 0);
	}
	for (i = 0; i < port->npwr; i++) {
		usleep_range(2500, 5000);
		gpiod_set_value_cansleep(port->pwr[i], 1);
	}
	usleep_range(2500, 5000);
}

static void t8010_setup_port(struct t8010_pcie *pcie, void __iomem *cfg,
			     struct t8010_port *port)
{
	void __iomem *phy0 = pcie->phy[0], *phy2 = pcie->phy[2];
	void __iomem *rc = cfg + (port->idx << 15);
	unsigned int idx = port->idx, o2 = 0x800 * idx;
	u8 cap;

	if (t8010_link_up(port)) {
		dev_info(pcie->dev, "port%u: link already up\n", idx);
		port->link_up = true;
		return;
	}

	gpiod_set_value_cansleep(port->reset, 1);

	rmwl(phy0 + 0x134 + 0x80 * idx, 1, 0);
	rmwl(phy0 + 0x124 + 0x80 * idx, 0, 1);
	wait_bits(pcie, phy0 + 0x28, 0x10, 0x10, 0x10, 250, "port init");
	usleep_range(250, 1000);
	rmwl(phy0 + 0x100 + 0x80 * idx, 0, 1);
	rmwl(phy0 + 0x100 + 0x80 * idx, 0x100, 0);
	usleep_range(500, 1000);
	rmwl(phy0 + 0x134 + 0x80 * idx, 0, 1);
	writel(3, phy0 + 0x4020 + 0x40 * idx);
	rmwl(phy0 + 0x124 + 0x80 * idx, 0x100, 0);

	STEP(pcie->dev, "7a port%u device power", idx);
	t8010_port_power_on(port);
	STEP(pcie->dev, "7b port%u root config", idx);

	cap = readb(rc + PCI_CAPABILITY_LIST);
	while (cap) {
		u32 hdr = readl(rc + cap);

		if ((hdr & 0xff) == PCI_CAP_ID_EXP) {
			u16 lnkctl2 = readw(rc + cap + PCI_EXP_LNKCTL2);

			lnkctl2 = (lnkctl2 & ~PCI_EXP_LNKCTL2_TLS) | port->max_speed;
			writew(lnkctl2, rc + cap + PCI_EXP_LNKCTL2);
			break;
		}
		cap = (hdr >> 8) & 0xff;
	}
	apply_tunables(rc, config_tunables, ARRAY_SIZE(config_tunables));
	apply_tunables(port->base, port_tunables, ARRAY_SIZE(port_tunables));
	rmwl(rc + 0x8e0, 0, 1);

	STEP(pcie->dev, "7c port%u irq/msi/enable", idx);
	writel(0xff002fff, port->base + PORT_IRQMASK);
	writel(0x00ffd000, port->base + PORT_IRQSTAT);
	rmwl(port->base + PORT_ENABLE, 0, BIT(31));
	writel(0x31, port->base + PORT_MSICFG);	/* enable, 2^3 vectors */
	writel(idx * 0x10001 * MSI_PER_PORT, port->base + PORT_MSIVECBASE);

	STEP(pcie->dev, "7d port%u PERST# release", idx);
	msleep(100);	/* ADT clkreq-wait-time; CLKREQ# is muxed to the PHY */
	gpiod_set_value_cansleep(port->reset, 0);
	usleep_range(250, 1000);

	wait_bits(pcie, pcie->phy[1] + PHY1_PORTMASK, BIT(idx), BIT(idx), BIT(idx),
		  250, "port up");
	rmwl(phy2 + 0x180, 0, 0x4000);
	rmwl(phy2 + 0x184, 0, 0x4000);
	rmwl(phy2 + 0x90, 0xfff, 100);
	rmwl(phy2 + 0x98, 0xfff, 25);

	rmwl(phy2 + 0x10088 + o2, 0, 0x4000);
	writel(0, phy2 + 0x10784 + o2);
	rmwl(phy2 + 0x10004 + o2, 0xfff, 0x600);
	writel(0x3105, phy2 + 0x20788 + o2);
	rmwl(phy2 + 0x207a0 + o2, 0xff, 0x9f);
	rmwl(phy2 + 0x207a8 + o2, 0xff, 0x01);
	rmwl(phy2 + 0x20400 + o2, 0x1f, 0x0a);
	writel(175, phy2 + 0x2009c + o2);
	writel(175, phy2 + 0x200dc + o2);
	writel(333, phy2 + 0x200a0 + o2);
	writel(333, phy2 + 0x200e0 + o2);
	writel(530, phy2 + 0x200a4 + o2);
	writel(530, phy2 + 0x200e4 + o2);
	writel(0, phy2 + 0x20330 + o2);
	writel(0, phy2 + 0x20340 + o2);
	writel(0, phy2 + 0x20350 + o2);

	STEP(pcie->dev, "7e port%u ltssm start", idx);
	writel(0xff002f0f, port->base + PORT_IRQMASK);
	usleep_range(5000, 10000);
	rmwl(port->base + PORT_LTSSMCTL, 0, 1);

	port->link_up = !wait_bits(pcie, port->base + PORT_LINKSTS, PORT_LINKSTS_LTSSM,
				   0x1100, 0x1400, 500, "link up");
	dev_info(pcie->dev, "port%u: link %s (LINKSTS 0x%08x)\n", idx,
		 port->link_up ? "up" : "DOWN", readl(port->base + PORT_LINKSTS));
}

static int t8010_pcie_init(struct pci_config_window *cfg)
{
	struct device *dev = cfg->parent;
	struct pci_host_bridge *bridge = dev_get_drvdata(dev);
	struct t8010_pcie *pcie = pci_host_bridge_priv(bridge);
	void __iomem *phy0 = pcie->phy[0];
	unsigned int i;
	int ret;

	STEP(dev, "6 global phy init");
	gpiod_set_value_cansleep(pcie->debug, 0);

	writel(0x10, phy0 + 0x0004);
	rmwl(phy0 + 0x124, 0, 1);
	wait_bits(pcie, phy0 + 0x28, 0x10, 0x10, 0x10, 250, "global init 1");
	wait_bits(pcie, phy0 + 0x28, 1, 1, 1, 250, "global init 2");
	writel(1, phy0 + 0x34);
	apply_tunables(phy0, phy0_tunables, ARRAY_SIZE(phy0_tunables));
	writel(1, phy0 + 0x14);
	usleep_range(5000, 10000);
	writel(1, phy0 + 0x24);
	usleep_range(500, 1000);

	for (i = 0; i < NUM_PORT; i++) {
		struct t8010_port *port = &pcie->port[i];

		if (!(pcie->port_mask & BIT(i)))
			continue;
		STEP(dev, "7 setup port%u", i);
		t8010_setup_port(pcie, cfg->win, port);
		if (port->dart) {
			STEP(dev, "8 dart port%u", i);
			ret = t8010_dart_static_map(pcie, port);
			if (ret)
				return ret;
		}
	}
	STEP(dev, "9 init done, PCI core scans now");
	return 0;
}

/* only enabled root ports exist; INTx is not wired (MSI only) */
static bool t8010_dev_ok(struct pci_bus *bus, unsigned int devfn)
{
	struct pci_config_window *cfg = bus->sysdata;
	struct t8010_pcie *pcie;

	if (bus->number != cfg->busr.start)
		return true;
	pcie = pci_host_bridge_priv(dev_get_drvdata(cfg->parent));
	return PCI_SLOT(devfn) < NUM_PORT && PCI_FUNC(devfn) == 0 &&
	       (pcie->port_mask & BIT(PCI_SLOT(devfn)));
}

static int t8010_config_read(struct pci_bus *bus, unsigned int devfn, int where,
			     int size, u32 *val)
{
	if (!t8010_dev_ok(bus, devfn)) {
		PCI_SET_ERROR_RESPONSE(val);
		return PCIBIOS_DEVICE_NOT_FOUND;
	}
	return pci_generic_config_read(bus, devfn, where, size, val);
}

static int t8010_config_write(struct pci_bus *bus, unsigned int devfn, int where,
			      int size, u32 val)
{
	if (!t8010_dev_ok(bus, devfn))
		return PCIBIOS_DEVICE_NOT_FOUND;
	if (where <= PCI_INTERRUPT_LINE && where + size > PCI_INTERRUPT_LINE)
		val |= 0xffu << ((PCI_INTERRUPT_LINE - where) * 8);
	return pci_generic_config_write(bus, devfn, where, size, val);
}

static const struct pci_ecam_ops t8010_ecam_ops = {
	.init		= t8010_pcie_init,
	.pci_ops	= {
		.map_bus	= pci_ecam_map_bus,
		.read		= t8010_config_read,
		.write		= t8010_config_write,
	},
};

/* --------------------------------------------------------------- probe -- */

static const struct dev_pm_domain_attach_data t8010_pd_data = {
	.pd_flags = PD_FLAG_DEV_LINK_ON | PD_FLAG_ATTACH_POWER_ON,
};

/* Notschalter: pcie_apple_t8010.disable=1 auf der Kernel-Kommandozeile */
static bool disable;
module_param(disable, bool, 0644);
MODULE_PARM_DESC(disable, "do not touch the PCIe hardware");

static int t8010_parse_port(struct t8010_pcie *pcie, struct platform_device *pdev,
			    struct device_node *np)
{
	struct device *dev = pcie->dev;
	struct t8010_port *port;
	char name[8];
	u32 devfn;
	int ret, irq;

	ret = of_pci_get_devfn(np);
	if (ret < 0)
		return dev_err_probe(dev, ret, "%pOF: bad reg\n", np);
	devfn = ret;
	if (PCI_SLOT(devfn) >= NUM_PORT)
		return dev_err_probe(dev, -EINVAL, "%pOF: bad port\n", np);

	port = &pcie->port[PCI_SLOT(devfn)];
	port->pcie = pcie;
	port->np = np;
	port->idx = PCI_SLOT(devfn);

	snprintf(name, sizeof(name), "port%u", port->idx);
	port->base = devm_platform_ioremap_resource_byname(pdev, name);
	if (IS_ERR(port->base))
		return PTR_ERR(port->base);

	snprintf(name, sizeof(name), "dart%u", port->idx);
	if (platform_get_resource_byname(pdev, IORESOURCE_MEM, name)) {
		port->dart = devm_platform_ioremap_resource_byname(pdev, name);
		if (IS_ERR(port->dart))
			return PTR_ERR(port->dart);
	}

	port->reset = devm_fwnode_gpiod_get(dev, of_fwnode_handle(np), "reset",
					    GPIOD_OUT_HIGH, "PERST#");
	if (IS_ERR(port->reset))
		return dev_err_probe(dev, PTR_ERR(port->reset), "port%u PERST#\n", port->idx);

	/* device power, switched on in this order: power-gpios = <wake>, <reg_on> */
	for (port->npwr = 0; port->npwr < ARRAY_SIZE(port->pwr); port->npwr++) {
		struct gpio_desc *g;

		g = devm_fwnode_gpiod_get_index(dev, of_fwnode_handle(np), "power",
						port->npwr, GPIOD_OUT_LOW, "pcie-pwr");
		if (PTR_ERR(g) == -ENOENT)
			break;
		if (IS_ERR(g))
			return dev_err_probe(dev, PTR_ERR(g), "port%u power%d\n",
					     port->idx, port->npwr);
		port->pwr[port->npwr] = g;
	}

	if (of_property_read_u32(np, "max-link-speed", &port->max_speed))
		port->max_speed = 1;

	irq = platform_get_irq(pdev, port->idx);
	if (irq < 0)
		return irq;
	ret = devm_request_irq(dev, irq, t8010_port_irq, 0, dev_name(dev), port);
	if (ret)
		return ret;

	pcie->port_mask |= BIT(port->idx);
	return 0;
}

static int t8010_pcie_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct pci_host_bridge *bridge;
	struct t8010_pcie *pcie;
	u32 win[4];
	int i, ret;

	if (disable) {
		dev_info(dev, "disabled on command line\n");
		return -ENODEV;
	}
	bridge = devm_pci_alloc_host_bridge(dev, sizeof(*pcie));
	if (!bridge)
		return -ENOMEM;
	pcie = pci_host_bridge_priv(bridge);
	pcie->dev = dev;
	mutex_init(&pcie->lock);

	STEP(dev, "1 power domains attach");
	/* Kernel 7.0 schreibt das Ergebnis immer nach *list – NULL führt zum Oops */
	ret = devm_pm_domain_attach_list(dev, &t8010_pd_data, &pcie->pd_list);
	if (ret < 0)
		return dev_err_probe(dev, ret, "power domains\n");

	for (i = 0; i < 3; i++) {
		char name[8];

		snprintf(name, sizeof(name), "phy%d", i);
		pcie->phy[i] = devm_platform_ioremap_resource_byname(pdev, name);
		if (IS_ERR(pcie->phy[i]))
			return PTR_ERR(pcie->phy[i]);
	}
	pcie->glue = devm_platform_ioremap_resource_byname(pdev, "glue");
	if (IS_ERR(pcie->glue))
		return PTR_ERR(pcie->glue);

	STEP(dev, "2 glue post-up");
	/* "post-up" of Sandcastle's pcieclk gate */
	writel(0x00000007, pcie->glue + 0x0000);
	writel(0x80010005, pcie->glue + 0x000c);
	writel(0x00000003, pcie->glue + 0x4104);
	writel(0x00000003, pcie->glue + 0x4100);

	pcie->debug = devm_gpiod_get_optional(dev, "debug", GPIOD_OUT_LOW);
	if (IS_ERR(pcie->debug))
		return PTR_ERR(pcie->debug);

	if (of_property_read_u64(dev->of_node, "apple,msi-doorbell", &pcie->doorbell))
		pcie->doorbell = 0xbffff000;

	ret = of_property_read_u32_array(dev->of_node, "apple,dma-window", win, 4);
	if (ret)
		return dev_err_probe(dev, ret, "missing apple,dma-window\n");
	pcie->win_bus = win[0];
	pcie->win_pa = ((u64)win[1] << 32) | win[2];
	pcie->win_size = win[3];
	if (!IS_ALIGNED(pcie->win_pa | pcie->win_size, DART_L2_SPAN))
		return dev_err_probe(dev, -EINVAL, "dma-window not 2 MiB aligned\n");

	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(64));
	if (ret)
		return ret;

	STEP(dev, "3 ports/gpios");
	for_each_available_child_of_node_scoped(dev->of_node, np) {
		ret = t8010_parse_port(pcie, pdev, np);
		if (ret)
			return ret;
	}
	if (!pcie->port_mask)
		return dev_err_probe(dev, -ENODEV, "no ports enabled\n");

	STEP(dev, "4 msi init");
	ret = t8010_msi_init(pcie);
	if (ret)
		return ret;

	STEP(dev, "5 host init (ecam + scan)");
	return pci_host_common_init(pdev, bridge, &t8010_ecam_ops);
}

static const struct of_device_id t8010_pcie_of_match[] = {
	{ .compatible = "apple,t8010-pcie" },
	{ }
};
MODULE_DEVICE_TABLE(of, t8010_pcie_of_match);

static struct platform_driver t8010_pcie_driver = {
	.probe	= t8010_pcie_probe,
	.driver	= {
		.name			= "pcie-apple-t8010",
		.of_match_table		= t8010_pcie_of_match,
		.suppress_bind_attrs	= false,	/* Debug: Start per sysfs bind */
	},
};
builtin_platform_driver(t8010_pcie_driver);

MODULE_DESCRIPTION("Apple A10 (T8010) PCIe root complex");
MODULE_LICENSE("GPL");

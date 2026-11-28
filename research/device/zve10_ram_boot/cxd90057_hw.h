/* SPDX-License-Identifier: GPL-2.0 */
#ifndef CXD90057_HW_H
#define CXD90057_HW_H

#include <stdint.h>

#define BIT(n) (1U << (n))

/* ---- Power-Save & PMU ---- */
#define DDRCB_PSAVE_BASE        0xf0105000U
#define DDRCB_PSAVE_CFG0        (DDRCB_PSAVE_BASE + 0x068U)
#define DDRCB_PSAVE_STATE       (DDRCB_PSAVE_BASE + 0x090U)
#define DDRCB_PSAVE_RDY0        (DDRCB_PSAVE_BASE + 0x0a0U)
#define DDRCB_PSAVE_RDY1        (DDRCB_PSAVE_BASE + 0x0a4U)
#define DDRCB_PSAVE_CLR1        (DDRCB_PSAVE_BASE + 0x118U)
#define DDRCB_PSAVE_WAKE        (DDRCB_PSAVE_BASE + 0x138U)
#define DDRCB_PSAVE_STAT        (DDRCB_PSAVE_BASE + 0x148U)
#define DDRCB_PSAVE_IRQ_CLR     (DDRCB_PSAVE_BASE + 0x14cU)
#define DDRCB_PSAVE_CLR2        (DDRCB_PSAVE_BASE + 0x218U)

#define PMU_BASE_PA             0xf290e000U
#define PMU_PWR_REQ0            (PMU_BASE_PA + 0x004U)
#define PMU_PWR_REQ1            (PMU_BASE_PA + 0x008U)
#define PMU_WAKE_CTRL           (PMU_BASE_PA + 0x210U)

/* ---- SoC CRG & SysCRG (FUN_63a26438, FUN_63a2551c, FUN_63dbb4fe) ---- */
#define SOC_CRG_SYS_BASE        0xf2900000U
#define SOC_CRG_SYS_RST_SET     (SOC_CRG_SYS_BASE + 0x044U)
#define SOC_CRG_SYS_CLK_SET     (SOC_CRG_SYS_BASE + 0x0a4U)

#define SOC_CRG0_BASE           0xf2a00000U
#define SOC_CRG0_CLK_SET        (SOC_CRG0_BASE + 0x004U)
#define SOC_CRG0_CLK_CLR        (SOC_CRG0_BASE + 0x008U)
#define SOC_CRG0_RST_SET        (SOC_CRG0_BASE + 0x024U)
#define SOC_CRG0_RST_CLR        (SOC_CRG0_BASE + 0x028U)
#define SOC_CRG0_CLK2_SET       (SOC_CRG0_BASE + 0x0a4U)
#define SOC_CRG0_SGC1_DIV       (SOC_CRG0_BASE + 0x1140U)
#define SOC_CRG0_SGC1_GATE_BIT  BIT(16)

#define SOC_CRG1_BASE           0xf2a30000U
#define SOC_CRG1_RST_SET        (SOC_CRG1_BASE + 0x024U)
#define SOC_CRG1_CLK0_STAT      (SOC_CRG1_BASE + 0x030U)
#define SOC_CRG1_CLK0_SET       (SOC_CRG1_BASE + 0x034U)
#define SOC_CRG1_CLK0_CLR       (SOC_CRG1_BASE + 0x038U)
#define SOC_CRG1_RST1_SET       (SOC_CRG1_BASE + 0x044U)
#define SOC_CRG1_CLK1_STAT      (SOC_CRG1_BASE + 0x060U)
#define SOC_CRG1_CLK1_SET       (SOC_CRG1_BASE + 0x064U)
#define SOC_CRG1_CLK1_CLR       (SOC_CRG1_BASE + 0x068U)
#define SOC_CRG1_CLK2_SET       (SOC_CRG1_BASE + 0x0a4U)
#define SOC_CRG1_CLK2_CLR       (SOC_CRG1_BASE + 0x0a8U)
#define SOC_CRG1_RST2_SET       (SOC_CRG1_BASE + 0x0b4U)
#define SOC_CRG1_RST2_CLR       (SOC_CRG1_BASE + 0x0b8U)

enum soc_clk_id {
    SOC_CLK_SLVS_IMAGER = 0x3b, /* FUN_63a26e34 / case 0x3b */
    SOC_CLK_PMIC_SPI    = 0x4e  /* PMIC SPI ch 0xb (FUN_63a26438 case 0x2b/4e) */
};

/* ---- ComboPHY, SLVS Pinmux & AFE (FUN_63d2a15e, FUN_63d2a04a) ---- */
#define PINMUX_SLVS_A           0xf2910f38U
#define PINMUX_SLVS_B           0xf2912f04U

#define COMBOPHY_BASE           0xf292a000U
#define COMBOPHY_CTRL           (COMBOPHY_BASE + 0x010U)
#define COMBOPHY_CFG            (COMBOPHY_BASE + 0x044U)
#define COMBOPHY_RELEASE        (COMBOPHY_BASE + 0x074U)

#define AFE_BASE                0xf2931100U
#define AFE_CTRL                (AFE_BASE + 0x00U)
#define AFE_LANE_PD             (AFE_BASE + 0x04U)
#define AFE_CFG0                (AFE_BASE + 0x2cU)
#define AFE_CFG1                (AFE_BASE + 0x30U)

/* ---- CamCore SGC1 Master Sync & Sync Routing (dfeSgc1.cpp) ---- */
#define ISP0_SYNC_BASE          0xf3000000U
#define ISP1_SYNC_BASE          0xf3100000U
#define SGC1_TOP_BASE           0xf3120000U

#define CAMCORE_CLK_EN(b)       ((b) + 0x000U)
#define CAMCORE_RST_REL(b)      ((b) + 0x008U)
#define CAMCORE_RST_STAT(b)     ((b) + 0x010U)
#define CAMCORE_RST_CLR(b)      ((b) + 0x014U)
#define CAMCORE_SYNC_ROUTE(b)   ((b) + 0x038U)
#define CAMCORE_SYNC_EXT_EN     BIT(0)
#define CAMCORE_SYNC_ROUTE_EN   BIT(8)
#define CAMCORE_SYNC_ROUTE_SEL  BIT(16)
#define CAMCORE_ISP_AUX_EN(b)   ((b) + 0x050U)
#define CAMCORE_MUX_CFG(b)      ((b) + 0x070U)
#define CAMCORE_BLK_EN(b)       ((b) + 0x110U)

#define SGC1_CORE_BASE          0xf3120200U
#define SGC1_TRIG_MODE          (SGC1_CORE_BASE + 0x008U) /* bit0: 1=master, 0=ext */
#define SGC1_CORE_CFG           (SGC1_CORE_BASE + 0x00cU)
#define SGC1_START_CTRL         (SGC1_CORE_BASE + 0x010U) /* bit 0: run, bit 8: slave */
#define SGC1_HV_CYCLE           (SGC1_CORE_BASE + 0x020U) /* ((V-1)<<16) | (H-1) */
#define SGC1_H_SYNC_POS         (SGC1_CORE_BASE + 0x024U)
#define SGC1_INIT_PARAM0        (SGC1_CORE_BASE + 0x034U)
#define SGC1_INIT_PARAM1        (SGC1_CORE_BASE + 0x038U)
#define SGC1_VD_HD_DLY0         (SGC1_CORE_BASE + 0x048U)
#define SGC1_VD_HD_DLY1         (SGC1_CORE_BASE + 0x04cU)
#define SGC1_MODE_FLAG          (SGC1_CORE_BASE + 0x058U)
#define SGC1_EXT_H              (SGC1_CORE_BASE + 0x064U)
#define SGC1_FRAC_V             (SGC1_CORE_BASE + 0x06cU)
#define SGC1_DLY_DISABLED       0x3ffe3ffeU

#define SLVS_SIF0_BASE          0xf3122000U
#define SLVS_SIF1_BASE          0xf3123000U
#define SLVS_SIF_EN(b)          ((b) + 0x000U)
#define SLVS_SIF_CFG0(b)        ((b) + 0x130U)
#define SLVS_SIF_CFG1(b)        ((b) + 0x138U)
#define SLVS_SIF_CFG2(b)        ((b) + 0x144U)
#define SLVS_SIF_CFG3(b)        ((b) + 0x148U)
#define SLVS_SIF_CFG4(b)        ((b) + 0x160U)

/* ---- DFE IRQ & Coprocessor Doorbell (FUN_63d26c3e..d54) ---- */
#define DFE_IRQ_CPU_BASE        0xfc01e000U
#define DFE_IRQ_CPU_MASK        (DFE_IRQ_CPU_BASE + 0x008U)
#define DFE_IRQ_CPU_STAT        (DFE_IRQ_CPU_BASE + 0x010U)
#define DFE_IRQ_CPU_DOORBELL    (DFE_IRQ_CPU_BASE + 0x018U)
#define DFE_DOORBELL_COPROC     BIT(27)

#define DFE_IRQ_BASE            0xfc01f000U
#define DFE_IRQ_MASK            (DFE_IRQ_BASE + 0x008U)
#define DFE_IRQ_EN_SET          (DFE_IRQ_BASE + 0x010U)
#define DFE_IRQ_EN_CLR          (DFE_IRQ_BASE + 0x014U)
#define DFE_IRQ_EDGE_CLR        (DFE_IRQ_BASE + 0x01cU)
#define DFE_IRQ_STAT_ID         (DFE_IRQ_BASE + 0x310U)
#define DFE_IRQ_VEC(ch)         (DFE_IRQ_BASE + 0x100U + ((ch) * 4U))

enum dfe_irq_channel {
    DFE_IRQ_CH_SYNCSEQ_AUX = 17, /* vec 0x0e (FUN_63d26d54) */
    DFE_IRQ_CH_SYNCSEQ_SPI = 18, /* vec 0x00 (FUN_63d26c3e) */
    DFE_IRQ_CH_SGC0_VD0    = 23, /* vec 0x0a (FUN_63d26d04) */
    DFE_IRQ_CH_SGC0_VD1    = 24, /* vec 0x0b (FUN_63d26d18) */
    DFE_IRQ_CH_DFE_EVENT   = 26  /* vec 0x09 (FUN_63d26ce8) */
};

/* ---- DFE CRG & PLLs (FUN_63d23710, FUN_6379e6c4, FUN_6379e404) ---- */
#define DFE_CRG_BASE            0xfc020000U
#define DFE_CRG_TOP_EN          (DFE_CRG_BASE + 0x028U)
#define DFE_CRG_MOD_CLK(bank)   (DFE_CRG_BASE + 0x104U + ((bank) * 0x10U))

#define DFE_PLL_BASE            0xfc021000U
#define DFE_PLL_EN              (DFE_PLL_BASE + 0x000U)
#define DFE_PLL_AUX_EN          (DFE_PLL_BASE + 0x008U)
#define DFE_PLL_CLK_DIV0        (DFE_PLL_BASE + 0x00cU)
#define DFE_PLL_CLK_DIV1        (DFE_PLL_BASE + 0x010U)
#define DFE_PLL_CLK_DIV2        (DFE_PLL_BASE + 0x014U)
#define DFE_PLL_SIF_CLK_EN      (DFE_PLL_BASE + 0x01cU)
#define DFE_PLL_RST_CTRL        (DFE_PLL_BASE + 0x024U)
#define DFE_PLL_LOCK(idx)       (DFE_PLL_BASE + 0x050U + ((idx) * 4U))
#define DFE_RST_SGC0_BIT        BIT(6)

/* ---- Imager GPIO / Power Sequencer (FUN_63d23260/90/c0) ---- */
#define IMAGER_GPIO_BASE        0xfc029000U
#define IMAGER_GPIO_EN(bank)    (IMAGER_GPIO_BASE + 0x000U + ((bank) * 4U))
#define IMAGER_GPIO_DIR(bank)   (IMAGER_GPIO_BASE + 0x010U + ((bank) * 4U))
#define IMAGER_GPIO_LVL(bank)   (IMAGER_GPIO_BASE + 0x020U + ((bank) * 4U))
#define IMAGER_PAD_DRIVE        0xfc02a0d0U

/* ---- DFE MPHY / D-PHY PLL / SLVS PHY ---- */
#define DFE_MPHY_BASE           0xfc02a000U
#define DFE_MPHY_CLK_EN         (DFE_MPHY_BASE + 0x008U)
#define DFE_MPHY_GRP_BASE(g)    (DFE_MPHY_BASE + 0x040U + ((g) * 0x10U))
#define DFE_MPHY_GLOBAL_CTRL    (DFE_MPHY_BASE + 0x040U)
#define DFE_MPHY_GRP_MODE(g)    (DFE_MPHY_GRP_BASE(g) + 0x04U)
#define DFE_MPHY_GRP_RST(g)     (DFE_MPHY_GRP_BASE(g) + 0x08U)
#define DFE_MPHY_GRP_LANE(g)    (DFE_MPHY_GRP_BASE(g) + 0x0cU)

#define DFE_DPHY_BASE           0xfc02a060U
#define DFE_DPHY_CTRL0          (DFE_DPHY_BASE + 0x00U)
#define DFE_DPHY_CTRL1          (DFE_DPHY_BASE + 0x04U)
#define DFE_DPHY_CTRL2          (DFE_DPHY_BASE + 0x08U)
#define DFE_DPHY_CFG            (DFE_DPHY_BASE + 0x0cU)
#define DFE_DPHY_PWR            (DFE_DPHY_BASE + 0x10U)
#define DFE_DPHY_AUX            (DFE_DPHY_BASE + 0x20U) /* bit 0: PLL status / acknowledge */

#define SLVS_PHY_BASE           0xfc02d000U
#define SLVS_PHY_CFG0           (SLVS_PHY_BASE + 0x00U)
#define SLVS_PHY_CFG1           (SLVS_PHY_BASE + 0x04U)
#define SLVS_PHY_CFG2           (SLVS_PHY_BASE + 0x08U)
#define SLVS_PHY_MODE           (SLVS_PHY_BASE + 0x0cU)
#define SLVS_PHY_EN             (SLVS_PHY_BASE + 0x10U)
#define SLVS_PHY_TOUT           (SLVS_PHY_BASE + 0x14U)
#define SLVS_PHY_CAL0           (SLVS_PHY_BASE + 0x28U)
#define SLVS_PHY_CAL1           (SLVS_PHY_BASE + 0x2cU)
#define SLVS_PHY_TERM0          (SLVS_PHY_BASE + 0x40U)
#define SLVS_PHY_TERM1          (SLVS_PHY_BASE + 0x44U)

/* ---- DFE Coprocessor Mailbox (FUN_639dfa3c, dfe_dat.bin) ---- */
#define DFE_MBOX_CMD            0xfc0300f4U
#define DFE_MBOX_STATUS         0xfc0300f8U
#define DFE_MBOX_CTRL           0xfc0300fcU
#define DFE_MBOX_BUSY_MASK      0x00000030U
#define DFE_MBOX_STATE_SHIFT    8U
#define DFE_MBOX_STATE_RUN      0xffU
#define DFE_MBOX_STATE_IDLE     0xfeU
#define DFE_MBOX_CTRL_RUN       BIT(28)
#define DFE_MBOX_CTRL_STOP_REQ  BIT(20)
#define DFE_MBOX_CTRL_ABORT     BIT(16)
#define DFE_MBOX_CTRL_CLR_MASK  0xffeefffeU

/* ---- SyncSeq & P2S SPI Sequencer ---- */
#define SYNCSEQ_BASE            0xfc080000U
#define SYNCSEQ_TRIG_PULSE      (SYNCSEQ_BASE + 0x014U)
#define SYNCSEQ_MODE_CFG        (SYNCSEQ_BASE + 0x01cU)
#define SYNCSEQ_EVT_MASK        (SYNCSEQ_BASE + 0x020U)
#define SYNCSEQ_SYNC_CLR        (SYNCSEQ_BASE + 0x024U)
#define SYNCSEQ_EVT_PERIOD      (SYNCSEQ_BASE + 0x028U)
#define SYNCSEQ_COUNTER         (SYNCSEQ_BASE + 0x030U)
#define SYNCSEQ_SLOT_CFG        (SYNCSEQ_BASE + 0x038U)
#define SYNCSEQ_EXT_TRIG_TIMER  (SYNCSEQ_BASE + 0x0f4U)
#define SYNCSEQ_EXT_DELAY0      (SYNCSEQ_BASE + 0x0f8U)
#define SYNCSEQ_EXT_DELAY1      (SYNCSEQ_BASE + 0x0fcU)
#define SYNCSEQ_ARB_CTRL        (SYNCSEQ_BASE + 0x100U)
#define SYNCSEQ_ARB_CLR         (SYNCSEQ_BASE + 0x104U)
#define SYNCSEQ_ARB_MASK        (SYNCSEQ_BASE + 0x108U)
#define SYNCSEQ_ARB_STAT        (SYNCSEQ_BASE + 0x10cU)
#define SYNCSEQ_AUX_CLR         (SYNCSEQ_BASE + 0x110U)
#define SYNCSEQ_AUX_EN          (SYNCSEQ_BASE + 0x114U)

#define SEQ_PORT                0xfc088300U
#define SEQ_RUN                 0xfc088e00U
#define SEQ_IRQ                 0xfc088f00U

/* ---- DfeTimer (FUN_63d272d4, FUN_637a4588..ac) ---- */
#define DFE_TIMER_BASE          0xfc098800U
#define DFE_TIMER_CTRL          (DFE_TIMER_BASE + 0x000U)
#define DFE_TIMER_GATE_SET      (DFE_TIMER_BASE + 0x008U)
#define DFE_TIMER_GATE_CLR      (DFE_TIMER_BASE + 0x00cU)
#define DFE_TIMER_AUX_GATE      (DFE_TIMER_BASE + 0x108U)
#define DFE_TIMER_GATE_BITS     0x00020001U

#define DFE_TIMER_AUX_BASE      0xfc099100U
#define DFE_TIMER_AUX_EN        (DFE_TIMER_AUX_BASE + 0x000U)
#define DFE_TIMER_AUX_START     (DFE_TIMER_AUX_BASE + 0x010U)

/* ---- DfeTop, Crossbar, Bridge, Port0 ---- */
#define DFE_TOP_BASE            0xfc0a0000U
#define DFE_TOP_CORE_EN_SET     (DFE_TOP_BASE + 0x000U)
#define DFE_TOP_CORE_EN_CLR     (DFE_TOP_BASE + 0x004U)
#define DFE_TOP_IRQ_STAT0       (DFE_TOP_BASE + 0x010U)
#define DFE_TOP_IRQ_CLR0        (DFE_TOP_BASE + 0x014U)
#define DFE_TOP_IRQ_EN0         (DFE_TOP_BASE + 0x018U)
#define DFE_TOP_IRQ_STAT1       (DFE_TOP_BASE + 0x028U)
#define DFE_TOP_IRQ_CLR1        (DFE_TOP_BASE + 0x02cU)
#define DFE_TOP_XBAR_IN(idx)    (DFE_TOP_BASE + 0x150U + ((idx) * 4U)) /* idx 0..6 */
#define DFE_TOP_XBAR_OUT(idx)   (DFE_TOP_BASE + 0x170U + ((idx) * 4U)) /* idx 0..7 */
#define DFE_TOP_BRIDGE_SET      (DFE_TOP_BASE + 0x200U)
#define DFE_TOP_BRIDGE_CLR      (DFE_TOP_BASE + 0x204U)
#define DFE_TOP_ERR_CTRL        (DFE_TOP_BASE + 0x504U)
#define DFE_TOP_ERR_MASK_SET    (DFE_TOP_BASE + 0x560U)
#define DFE_TOP_ERR_MASK_CLR    (DFE_TOP_BASE + 0x564U)

#define DFE_CORE_BIT_IFMT       BIT(1)
#define DFE_CORE_BIT_SIF        BIT(4)
#define DFE_CORE_BIT_SYNCSEQ    BIT(5)
#define DFE_CORE_BIT_PIN        BIT(6)
#define DFE_CORE_BIT_RDC        BIT(7)
#define DFE_CORE_BIT_SGC0       BIT(8)
#define DFE_CORE_BIT_AIF        BIT(15)

#define DFE_PORT0_BASE          0xfc0a7000U
#define DFE_PORT0_EN            (DFE_PORT0_BASE + 0x000U)
#define DFE_PORT0_RUN           (DFE_PORT0_BASE + 0x004U)

/* ---- DrvSGC0, Ifmt_RcvSgc, Ifmt_LnkSgc, Ifmt_Win, SIF, RdcW0, FOPD ---- */
#define DFE_DRVSGC0_BASE        0xfc0a1100U
#define DFE_DRVSGC0_EN          (DFE_DRVSGC0_BASE + 0x000U)
#define DFE_DRVSGC0_INT_TRIG    (DFE_DRVSGC0_BASE + 0x008U)
#define DFE_DRVSGC0_CFG_EN      (DFE_DRVSGC0_BASE + 0x00cU)
#define DFE_DRVSGC0_START_STAT  (DFE_DRVSGC0_BASE + 0x010U)
#define DFE_DRVSGC0_HV_LATCH    (DFE_DRVSGC0_BASE + 0x014U)
#define DFE_DRVSGC0_HV_COUNT    (DFE_DRVSGC0_BASE + 0x018U)
#define DFE_DRVSGC0_FRAME_LATCH (DFE_DRVSGC0_BASE + 0x01cU)
#define DFE_DRVSGC0_FRAME_COUNT (DFE_DRVSGC0_BASE + 0x028U)
#define DFE_DRVSGC0_HV_CYCLE    (DFE_DRVSGC0_BASE + 0x020U)
#define DFE_DRVSGC0_V_END       (DFE_DRVSGC0_BASE + 0x024U)
#define DFE_DRVSGC0_RUN_FLAG    (DFE_DRVSGC0_BASE + 0x02cU)
#define DFE_DRVSGC0_EXT_SYNC    (DFE_DRVSGC0_BASE + 0x030U)
#define DFE_DRVSGC0_CLK_MODE    (DFE_DRVSGC0_BASE + 0x040U)
#define DFE_DRVSGC0_H_PW0       (DFE_DRVSGC0_BASE + 0x04cU)
#define DFE_DRVSGC0_HV_PW       (DFE_DRVSGC0_BASE + 0x050U)
#define DFE_DRVSGC0_VD_MASK0    (DFE_DRVSGC0_BASE + 0x094U)
#define DFE_DRVSGC0_VD_MASK1    (DFE_DRVSGC0_BASE + 0x098U)
#define DFE_DRVSGC0_NLR_CFG     (DFE_DRVSGC0_BASE + 0x0a8U)
#define DFE_DRVSGC0_NLR_FRAC    (DFE_DRVSGC0_BASE + 0x0acU)

#define DFE_RCVSGC_BASE         0xfc0a1200U
#define DFE_LNKSGC_BASE         0xfc0a1300U
#define DFE_ZPD_SGC_BASE        0xfc0a1400U
#define DFE_IFMT_WIN_BASE       0xfc0a1c00U
#define DFE_SIF_BASE            0xfc0a3000U
#define DFE_SIF0_EN             (DFE_SIF_BASE + 0x000U)
#define DFE_SIF2_CTRL           (DFE_SIF_BASE + 0x200U)
#define DFE_SIF2_CFG            (DFE_SIF_BASE + 0x204U)
#define DFE_SIF2_LANE_MAP       (DFE_SIF_BASE + 0x208U)
#define DFE_SIF2_TRIG           (DFE_SIF_BASE + 0x214U)
#define DFE_SIF3_EN             (DFE_SIF_BASE + 0x300U)

#define DFE_RDC_BASE            0xfc0a8000U
#define DFE_RDC_CTL             (DFE_RDC_BASE + 0x014U)
#define DFE_RDC_BYPASS0         (DFE_RDC_BASE + 0x700U)
#define DFE_RDC_BYPASS0_EN      (DFE_RDC_BASE + 0x704U)
#define DFE_RDC_BYPASS1_EN      (DFE_RDC_BASE + 0x804U)
#define DFE_RDC_OUT_EN          (DFE_RDC_BASE + 0x900U)

#define DFE_AIF_TOP_BASE        0xfc0a9000U
#define DFE_AIF_TOP_RESET       (DFE_AIF_TOP_BASE + 0x000U)
#define DFE_AIF_TOP_EN          (DFE_AIF_TOP_BASE + 0x004U)

#define DFE_RDCW0_BASE          0xfc0a9200U
#define DFE_RDCW0_CTL           (DFE_RDCW0_BASE + 0x000U)
#define DFE_RDCW0_STATUS        (DFE_RDCW0_BASE + 0x004U)
#define DFE_RDCW0_ERR           (DFE_RDCW0_BASE + 0x008U)
#define DFE_RDCW0_CURSOR        (DFE_RDCW0_BASE + 0x010U)
#define DFE_RDCW0_ADDR          (DFE_RDCW0_BASE + 0x020U)
#define DFE_RDCW0_LINE_BYTES    (DFE_RDCW0_BASE + 0x024U)
#define DFE_RDCW0_LINE_GAP      (DFE_RDCW0_BASE + 0x028U)
#define DFE_RDCW0_HEIGHT_M1     (DFE_RDCW0_BASE + 0x02cU)

#define DFE_FOPD_BASE           0xfc0ad600U
#define DFE_FOPD_EN             (DFE_FOPD_BASE + 0x000U)
#define DFE_FOPD_START          (DFE_FOPD_BASE + 0x010U)

/* ---- SLVS-EC Receiver (FUN_637a7e78, FUN_637a7c34, FUN_637a7d70) ---- */
#define SLVSEC_BASE             0xfc0f0000U
#define SLVSEC_TOP_CTRL         (SLVSEC_BASE + 0x000U)
#define SLVSEC_TOP_PORT_CFG     (SLVSEC_BASE + 0x004U)
#define SLVSEC_PORT_BASE(p)     (SLVSEC_BASE + ((p) * 0x100U))
#define SLVSEC_PORT_STOP(p)     (SLVSEC_PORT_BASE(p) + 0x04cU)
#define SLVSEC_PORT_START(p)    (SLVSEC_PORT_BASE(p) + 0x050U)
#define SLVSEC_PORT_LOCK(p)     (SLVSEC_PORT_BASE(p) + 0x0b0U)

#endif /* CXD90057_HW_H */

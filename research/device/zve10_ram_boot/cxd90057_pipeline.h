/* SPDX-License-Identifier: GPL-2.0 */
#ifndef CXD90057_PIPELINE_H
#define CXD90057_PIPELINE_H

#include <stdint.h>
#include "cxd90057_hw.h"
#include "imx284_sensor.h"

#define SGC_INACTIVE_MARK 0x3ffe3ffeU

struct mode1_input_sample {
    uint32_t ticks;
    uint32_t syncseq_count;
    uint32_t syncseq_timing;
    uint32_t sgc0_status;
    uint32_t slvs_status;
    uint32_t spi_irqs;
    uint32_t spi_timeouts;
};

struct sgc_timing_cfg {
    uint32_t freq_mhz;
    uint32_t h_total;
    uint32_t v_total;
    uint32_t nlr_delta;
    uint32_t nlr_num;
    uint32_t nlr_den;
    uint32_t lead_us;
};

/* ---- SoC Clock & Reset Generator (FUN_63a26438, FUN_63a2551c, FUN_63dbb4fe) ---- */

static inline void soc_crg_enable(enum soc_clk_id id) {
    if (id == SOC_CLK_SLVS_IMAGER) {
        w32(SOC_CRG1_RST1_SET, BIT(9));
        w32(SOC_CRG1_CLK1_SET, BIT(24));
        (void)r32(SOC_CRG1_CLK1_STAT);
        w32(SOC_CRG1_CLK2_SET, BIT(10));
        dsb();
    } else if (id == SOC_CLK_PMIC_SPI) {
        imx284_pmic_spi_enable();
    }
}

static inline void soc_crg_disable(enum soc_clk_id id) {
    if (id == SOC_CLK_SLVS_IMAGER) {
        w32(SOC_CRG1_CLK1_CLR, BIT(24));
        (void)r32(SOC_CRG1_CLK1_STAT);
        w32(SOC_CRG1_CLK2_CLR, BIT(10));
        dsb();
    }
}

static inline void soc_crg_configure_sgc1_clock(uint32_t freq_mhz) {
    uint32_t div_code;
    if (freq_mhz == 54U) {
        div_code = 0x0bU;
    } else if (freq_mhz == 72U || freq_mhz == 108U) {
        div_code = 0x08U;
    } else if (freq_mhz == 24U) {
        div_code = 0x1aU;
    } else {
        w32(SOC_CRG0_RST_CLR, SOC_CRG0_SGC1_GATE_BIT);
        w32(SOC_CRG0_CLK_SET, SOC_CRG0_SGC1_GATE_BIT);
        dsb();
        return;
    }
    w32(SOC_CRG0_SGC1_DIV, div_code);
    (void)r32(SOC_CRG0_SGC1_DIV);
    w32(SOC_CRG0_CLK_CLR, SOC_CRG0_SGC1_GATE_BIT);
    (void)r32(SOC_CRG0_CLK_CLR);
    dsb();
}

/* ---- DFE Interrupt / Event Controller (FUN_63d26c3e..d54) ---- */

static inline void dfe_irq_enable_channel(enum dfe_irq_channel ch, uint32_t vec, int clear_edge) {
    w32(DFE_IRQ_VEC((uint32_t)ch), vec);
    if (clear_edge) {
        w32(DFE_IRQ_EDGE_CLR, BIT((uint32_t)ch));
    }
    w32(DFE_IRQ_EN_SET, BIT((uint32_t)ch));
    dsb();
}

static inline void dfe_irq_disable_channel(enum dfe_irq_channel ch) {
    w32(DFE_IRQ_EN_CLR, BIT((uint32_t)ch));
    w32(DFE_IRQ_VEC((uint32_t)ch), 0U);
    dsb();
}

static inline void dfe_irq_set_cpu_masks(void) {
    w32(DFE_IRQ_MASK, r32(DFE_IRQ_MASK) | BIT(16));
    w32(DFE_IRQ_CPU_MASK, r32(DFE_IRQ_CPU_MASK) | BIT(16) | DFE_DOORBELL_COPROC);
    dsb();
}

/* ---- DFE Coprocessor Mailbox (FUN_63da03f2, dfe_dat.bin) ---- */

/* FUN_63da0880 consumes the latched command by reading and clearing it. */
static uint32_t dfe_coproc_take_command(void) {
    uint32_t cmd = r32(DFE_MBOX_CMD);
    w32(DFE_MBOX_CMD, 0U);
    return cmd;
}

static int dfe_coproc_wait(uint8_t want_state) {
    for (uint32_t i = 0U; i < 1000U; ++i) {
        uint32_t st = r32(DFE_MBOX_STATUS);
        if ((st & DFE_MBOX_BUSY_MASK) == 0U &&
            ((st >> DFE_MBOX_STATE_SHIFT) & 0xffU) == (uint32_t)want_state) {
            return 1;
        }
        delay_us(100U);
    }
    (void)dfe_coproc_take_command();
    return 0;
}

static void dfe_coproc_abort_busy(void) {
    w32(DFE_MBOX_CTRL, r32(DFE_MBOX_CTRL) | DFE_MBOX_CTRL_ABORT);
    dsb();
    w32(DFE_IRQ_CPU_DOORBELL, DFE_DOORBELL_COPROC);
    dsb();
    (void)dfe_coproc_wait(0U);
}

static int dfe_coproc_start(void) {
    uint32_t ctrl = r32(DFE_MBOX_CTRL);
    uint32_t st = r32(DFE_MBOX_STATUS);
    uint32_t f4 = dfe_coproc_take_command();
    prints("DFE_MBOX_PRE f4="); print_hex8(f4);
    prints(" f8="); print_hex8(st);
    prints(" fc="); print_hex8(ctrl);
    prints("\n");

    int busy_at_entry = (st & DFE_MBOX_BUSY_MASK) != 0U;
    if (busy_at_entry) {
        dfe_coproc_abort_busy();
    } else {
        w32(DFE_MBOX_CTRL, ctrl & DFE_MBOX_CTRL_CLR_MASK);
    }
    w32(DFE_MBOX_CTRL, r32(DFE_MBOX_CTRL) | DFE_MBOX_CTRL_RUN);
    dsb();
    w32(DFE_IRQ_CPU_DOORBELL, DFE_DOORBELL_COPROC);
    dsb();

    int ok = dfe_coproc_wait(DFE_MBOX_STATE_RUN);
    prints("DFE_MBOX_POST ready="); print_dec((uint32_t)ok);
    prints(" busy_at_entry="); print_dec((uint32_t)busy_at_entry);
    prints(" f8="); print_hex8(r32(DFE_MBOX_STATUS));
    prints(" fc="); print_hex8(r32(DFE_MBOX_CTRL));
    prints(" 1e10="); print_hex8(r32(DFE_IRQ_CPU_STAT));
    prints(" 98000="); print_hex8(r32(0xfc098000U));
    prints(" 98808="); print_hex8(r32(DFE_TIMER_GATE_SET));
    prints(" 98908="); print_hex8(r32(DFE_TIMER_AUX_GATE));
    prints("\n");
    return ok && !busy_at_entry;
}

static void dfe_coproc_stop(void) {
    uint32_t ctrl = r32(DFE_MBOX_CTRL);
    uint32_t st = r32(DFE_MBOX_STATUS);
    (void)dfe_coproc_take_command();
    if ((st & DFE_MBOX_BUSY_MASK) != 0U) {
        dfe_coproc_abort_busy();
    } else {
        w32(DFE_MBOX_CTRL, (ctrl & DFE_MBOX_CTRL_CLR_MASK) | DFE_MBOX_CTRL_STOP_REQ);
    }
    w32(DFE_MBOX_CTRL, r32(DFE_MBOX_CTRL) & ~DFE_MBOX_CTRL_RUN);
    dsb();
    w32(DFE_IRQ_CPU_DOORBELL, DFE_DOORBELL_COPROC);
    dsb();
    (void)dfe_coproc_wait(DFE_MBOX_STATE_IDLE);
}

/* ---- DFE CRG, PLLs, D-PHY PLL & SLVS PHY (FUN_63d238b2, FUN_637a19dc, FUN_63d24b54) ---- */

/* FUN_637a19dc's configuration readbacks precede the MIPI-TX PLL wait. */
static void dfe_dphy_write_and_wait(uint32_t addr, uint32_t value, uint32_t mask) {
    w32(addr, value);
    dsb();
    for (uint32_t i = 0U; i < 1000U; ++i) {
        if ((r32(addr) & mask) == (value & mask)) {
            break;
        }
    }
}

static void dfe_dphy_pll_init(void) {
    w32(DFE_DPHY_PWR, r32(DFE_DPHY_PWR) | 1U);
    dsb();
    dfe_dphy_write_and_wait(DFE_DPHY_CFG, r32(DFE_DPHY_CFG) & ~BIT(12), BIT(12));
    dfe_dphy_write_and_wait(DFE_DPHY_CFG, (r32(DFE_DPHY_CFG) & ~0x7fU) | 0x7cU, 0x7fU);
    dfe_dphy_write_and_wait(DFE_DPHY_CFG, r32(DFE_DPHY_CFG) & ~(0xfU << 8), 0xfU << 8);
    dfe_dphy_write_and_wait(DFE_DPHY_CTRL2, 1U, 1U);
    dfe_dphy_write_and_wait(DFE_DPHY_CTRL0, 1U, 1U);
    dfe_dphy_write_and_wait(DFE_DPHY_CTRL1, 0x1111U, 0xffffffffU);

    for (uint32_t i = 0U; i < 1000U; ++i) {
        if ((r32(DFE_DPHY_AUX) & 1U) != 0U) {
            break;
        }
        delay_us(1U);
    }
    w32(DFE_DPHY_AUX, r32(DFE_DPHY_AUX) | 1U);
    dsb();
}

static void slvs_phy_init(void) {
    w32(SLVS_PHY_CFG0, 3U);
    w32(SLVS_PHY_CFG1, 0x50U);
    w32(SLVS_PHY_CFG2, 0x10U);
    w32(SLVS_PHY_MODE, 0x13U);
    w32(SLVS_PHY_TOUT, 12000U); /* 0x2ee0 */
    w32(SLVS_PHY_CAL0, 0U);
    w32(SLVS_PHY_TERM0, 0x0e0c350bU);
    w32(SLVS_PHY_TERM1, 0x0f0d170aU);
    w32(SLVS_PHY_CAL1, 0U);
    dsb();
    delay_us(100U);

    w32(SLVS_PHY_MODE, 0x11U);
    w32(SLVS_PHY_EN, 1U);
    dsb();
}

static void dfe_crg_and_pll_init(uint32_t freq_mhz) {
    /* Module clock bitmasks across banks 0..9 (FUN_63d23710 + FUN_63d23620). */
    static const uint8_t dfe_mod_clk_masks[10] = {
        0x00U, 0x00U, 0x00U, 0x37U, 0x9fU, 0x7fU, 0x0aU, 0x02U, 0x01U, 0x01U
    };
    uint32_t div_code = 3U;
    if (freq_mhz == 144U) {
        div_code = 0U;
    } else if (freq_mhz == 72U) {
        div_code = 1U;
    } else if (freq_mhz == 108U) {
        div_code = 2U;
    }

    w32(DFE_CRG_TOP_EN, r32(DFE_CRG_TOP_EN) | 0x3bU);
    for (uint32_t bank = 0U; bank < 10U; ++bank) {
        uint32_t addr = DFE_CRG_MOD_CLK(bank);
        w32(addr, (r32(addr) & ~0xffU) | dfe_mod_clk_masks[bank]);
    }
    w32(DFE_CRG_TOP_EN, r32(DFE_CRG_TOP_EN) | 0x80U);
    dsb();

    /* Enable DFE PLLs 0..2 and poll lock indicators (FUN_6379e6c4). */
    for (uint32_t pll = 0U; pll < 3U; ++pll) {
        w32(DFE_PLL_EN, r32(DFE_PLL_EN) | BIT(pll * 4U));
        dsb();
        for (uint32_t i = 0U; i < 1000U; ++i) {
            if ((r32(DFE_PLL_LOCK(pll)) & 1U) != 0U) {
                break;
            }
            delay_us(1U);
        }
    }

    w32(DFE_PLL_CLK_DIV0, (r32(DFE_PLL_CLK_DIV0) & ~3U) | div_code);
    w32(DFE_PLL_CLK_DIV1, (r32(DFE_PLL_CLK_DIV1) & ~0x33U) | div_code | (div_code << 4));
    w32(DFE_PLL_CLK_DIV2, (r32(DFE_PLL_CLK_DIV2) & ~0x333U) |
                          div_code | (div_code << 4) | (div_code << 8));
    w32(DFE_PLL_RST_CTRL, r32(DFE_PLL_RST_CTRL) & ~0x0002083cU);
    dsb();

    /* Release DFE PHY / MPHY / D-PHY / SLVS PHY & bridge. */
    w32(DFE_MPHY_CLK_EN, r32(DFE_MPHY_CLK_EN) | 1U);
    dfe_dphy_pll_init();
    slvs_phy_init();
    w32(DFE_PLL_AUX_EN, 1U);

    /* FUN_63d272d4: DFE bridge (0xfc0a7000) & DfeTimer (0xfc098800). */
    w32(DFE_PORT0_EN, 1U);
    w32(DFE_PORT0_RUN, 1U);
    w32(DFE_TIMER_CTRL, 2U);
    w32(DFE_TIMER_CTRL, 1U);
    dsb();
    delay_us(1000U);
}

/* ---- DrvSGC0 & SyncSeq Init (FUN_6379c994, FUN_63d267a4, FUN_63d26a42, FUN_637a3858) ---- */

static void dfe_drv_sgc0_and_syncseq_init(void) {
    /* Pin group selection + DFE core enables for PIN(6), SYNCSEQ(5), SGC0(8). */
    w32(DFE_TOP_CORE_EN_SET, DFE_CORE_BIT_PIN);
    w32(DFE_TOP_CORE_EN_SET, DFE_CORE_BIT_SYNCSEQ);
    dfe_irq_enable_channel(DFE_IRQ_CH_SGC0_VD0, 0x0aU, 0);
    dfe_irq_enable_channel(DFE_IRQ_CH_SGC0_VD1, 0x0bU, 0);

    w32(DFE_PLL_RST_CTRL, r32(DFE_PLL_RST_CTRL) & ~DFE_RST_SGC0_BIT);
    w32(DFE_TOP_CORE_EN_SET, DFE_CORE_BIT_SGC0);
    w32(DFE_DRVSGC0_EN, 1U);

    /* FUN_63d26a42(obj, freq=72, h_pulse=3, h_width=32, v_pulse=4) */
    w32(DFE_DRVSGC0_CLK_MODE, (r32(DFE_DRVSGC0_CLK_MODE) & ~7U) | 7U);
    w32(DFE_DRVSGC0_H_PW0, (r32(DFE_DRVSGC0_H_PW0) & ~0x3fffU) | 4U);
    w32(DFE_DRVSGC0_CLK_MODE, (r32(DFE_DRVSGC0_CLK_MODE) & ~(7U << 16)) | (4U << 16));
    w32(DFE_DRVSGC0_HV_PW, (r32(DFE_DRVSGC0_HV_PW) & ~0x3fffU) | 5U);
    w32(DFE_DRVSGC0_HV_PW, (r32(DFE_DRVSGC0_HV_PW) & ~(0x3fffU << 16)) | (0x25U << 16));
    w32(DFE_DRVSGC0_CFG_EN, 1U);
    w32(DFE_DRVSGC0_VD_MASK1, r32(DFE_DRVSGC0_VD_MASK1) | BIT(16));
    w32(DFE_DRVSGC0_VD_MASK0, r32(DFE_DRVSGC0_VD_MASK0) | BIT(16));

    /* FUN_637a3858: SyncSeq slot defaults & event mask. */
    static const uint16_t syncseq_slot_offs[] = {
        0x3cU, 0x54U, 0x6cU, 0x84U, 0x9cU, 0xb4U, 0xc4U, 0xd4U, 0xe4U, 0xf4U
    };
    for (uint32_t i = 0U; i < (uint32_t)(sizeof(syncseq_slot_offs) / sizeof(syncseq_slot_offs[0])); ++i) {
        w32(SYNCSEQ_BASE + syncseq_slot_offs[i], 0x10U);
    }
    w32(SYNCSEQ_MODE_CFG, r32(SYNCSEQ_MODE_CFG) & ~0x00ff0000U);
    w32(SYNCSEQ_EVT_MASK, 0x00fffff0U);

    /* Enable SyncSeq auxiliary event bit 0. */
    uint32_t aux = r32(SYNCSEQ_AUX_EN);
    w32(SYNCSEQ_AUX_CLR, 1U & ~aux);
    w32(SYNCSEQ_AUX_EN, aux | 1U);
    dsb();
}

/* ---- CamCore SGC1 & Sync Routing (dfeSgc1.cpp: FUN_637787f0, FUN_63778410) ---- */

static void camcore_sgc1_init(uint32_t freq_mhz) {
    soc_crg_configure_sgc1_clock(freq_mhz);

    /* Release SGC1 block clock/reset and enable core config + inactive delays. */
    w32(CAMCORE_RST_REL(SGC1_TOP_BASE), r32(CAMCORE_RST_REL(SGC1_TOP_BASE)) | 1U);
    w32(CAMCORE_CLK_EN(SGC1_TOP_BASE), r32(CAMCORE_CLK_EN(SGC1_TOP_BASE)) | 1U);
    w32(CAMCORE_BLK_EN(SGC1_TOP_BASE), 1U);
    w32(CAMCORE_MUX_CFG(SGC1_TOP_BASE), 0U);
    w32(SGC1_CORE_CFG, 1U);
    /* IMX284 InitParam words at +4, +8, and +0xc are 3, 5, and 3. */
    w32(SGC1_INIT_PARAM0, (3U << 16) | 5U);
    w32(SGC1_INIT_PARAM1, 3U);
    w32(SGC1_VD_HD_DLY0, SGC_INACTIVE_MARK);
    w32(SGC1_VD_HD_DLY1, SGC_INACTIVE_MARK);

    /* FUN_637769e0, port 0 IMX284 profile. */
    w32(CAMCORE_BLK_EN(SGC1_TOP_BASE), 0x0fU);
    w32(SGC1_TOP_BASE + 0x100U, 2U);
    w32(SGC1_TOP_BASE + 0x074U, 0xff000300U);
    w32(SGC1_TOP_BASE + 0x120U, 0x1fU);
    dsb();
}

static void camcore_set_sync_route(uint32_t base, uint32_t ext_en, uint32_t sel, uint32_t en) {
    w32(CAMCORE_SYNC_ROUTE(base),
        (ext_en & 1U) | ((sel & 1U) << 8) | ((en & 1U) << 16));
}

static void camcore_sgc1_start_mode1(const struct sgc_timing_cfg *timing) {
    uint32_t v_m1 = timing->v_total - 1U;

    /* FUN_63778410 case 1. Use the external DrvSGC0 routes seen in stock Mode 1. */
    camcore_set_sync_route(SGC1_TOP_BASE, 1U, 1U, 0U);
    camcore_set_sync_route(ISP0_SYNC_BASE, 1U, 1U, 1U);
    w32(SGC1_TRIG_MODE, r32(SGC1_TRIG_MODE) & ~1U);
    w32(SGC1_MODE_FLAG, 0U);
    w32(SGC1_H_SYNC_POS, v_m1 - 100U);
    w32(SGC1_HV_CYCLE, (v_m1 << 16) | (timing->h_total - 1U));
    w32(SGC1_EXT_H, ((timing->nlr_delta + v_m1) << 16) | 1U);
    w32(SGC1_FRAC_V, (timing->nlr_num << 16) | timing->nlr_den);
    w32(SGC1_VD_HD_DLY0, SGC_INACTIVE_MARK);
    w32(SGC1_START_CTRL, 1U | BIT(8));
    dsb();
}

static void camcore_sgc1_stop(void) {
    w32(SGC1_START_CTRL, 0U);
    dsb();
}

/* ---- ComboPHY, AFE, MPHY Lanes & SLVS-EC Receiver (FUN_637aeae0, FUN_637aebd0) ---- */

static void slvs_pinmux_and_sif_pre_init(void) {
    dfe_irq_enable_channel(DFE_IRQ_CH_SYNCSEQ_SPI, 0U, 0);
    w32(PINMUX_SLVS_A, 0x20U);
    w32(PINMUX_SLVS_B, 0x20U);

    w32(SLVS_SIF_CFG0(SLVS_SIF0_BASE), 0U);
    w32(SLVS_SIF_CFG1(SLVS_SIF0_BASE), 0U);
    w32(SLVS_SIF_CFG3(SLVS_SIF0_BASE), 0U);
    w32(SLVS_SIF_CFG4(SLVS_SIF0_BASE), 0U);
    w32(SLVS_SIF_CFG2(SLVS_SIF0_BASE), 0U);

    w32(DFE_SIF2_CTRL, 0U);
    w32(DFE_SIF2_CFG, 1U);
    w32(DFE_SIF2_LANE_MAP, 0x76543210U);
    dsb();
}

/* Prior-mode shutdown from FUN_637a76b8. Modes 1 and 3 share the ComboPHY. */
static void combophy_stop_previous_mode(void) {
    uint32_t mode = (r32(COMBOPHY_BASE + 0x70U) >> 8) & 0x1fU;
    if (mode == 1U) {
        w32(COMBOPHY_BASE + 0x48U, 4U);
        w32(SOC_CRG1_CLK2_CLR, BIT(22));
        w32(SOC_CRG1_CLK2_CLR, BIT(23));
        for (uint32_t bit = 24U; bit <= 27U; ++bit) {
            w32(SOC_CRG_SYS_BASE + 0x0a8U, BIT(bit));
        }
        w32(SOC_CRG0_BASE + 0x0a8U, 1U);
        w32(SOC_CRG1_BASE + 0x028U, BIT(28));
        w32(SOC_CRG1_BASE + 0x028U, BIT(31));
        w32(SOC_CRG_SYS_BASE + 0x048U, BIT(30));
        w32(SOC_CRG0_RST_CLR, BIT(28));
        w32(SOC_CRG0_RST_CLR, BIT(31));
    } else if (mode == 3U) {
        w32(COMBOPHY_BASE + 0x28U, 0x0f00U);
        if (((r32(COMBOPHY_BASE + 0x80U) >> 8) & 0x1fU) == 3U) {
            w32(COMBOPHY_BASE + 0x38U, 0x0f00U);
        }
        w32(COMBOPHY_BASE + 0x48U, 1U);
        w32(COMBOPHY_BASE + 0x48U, 2U);
        w32(COMBOPHY_BASE + 0x1e8U, 1U);
        w32(COMBOPHY_BASE + 0x1e8U, 0x100U);
        w32(COMBOPHY_BASE + 0x28U, 1U);
        w32(COMBOPHY_BASE + 0x38U, 1U);
        w32(COMBOPHY_BASE + 0x48U, 4U);
        w32(SOC_CRG_SYS_BASE + 0x0a8U, BIT(25));
        w32(SOC_CRG_SYS_BASE + 0x0a8U, BIT(24));
    } else if (mode != 0U) {
        prints("Unknown prior ComboPHY mode=");
        print_dec(mode);
        prints("\n");
        return;
    }
    w32(COMBOPHY_CTRL, 0U);
    dsb();
}

static void combophy_and_afe_enable(void) {
    combophy_stop_previous_mode();
    w32(COMBOPHY_CTRL, 0U);
    w32(COMBOPHY_CTRL, 0U);

    w32(SOC_CRG0_RST_SET, BIT(31));
    w32(SOC_CRG0_RST_SET, BIT(28));
    w32(SOC_CRG_SYS_RST_SET, BIT(30));
    w32(SOC_CRG1_RST_SET, BIT(31));
    w32(SOC_CRG1_RST_SET, BIT(28));
    w32(SOC_CRG0_CLK2_SET, BIT(0));
    w32(SOC_CRG_SYS_CLK_SET, BIT(27) | BIT(26) | BIT(25) | BIT(24));
    w32(SOC_CRG1_CLK2_SET, BIT(23) | BIT(22));

    w32(COMBOPHY_CFG, 4U);
    w32(COMBOPHY_RELEASE, 0U);
    w32(COMBOPHY_RELEASE, 0x100U);
    dsb();
    delay_us(100U);

    /* AFE initialization (FUN_63d2a04a) */
    w32(AFE_LANE_PD, 0x0fU);
    w32(AFE_CTRL, 3U);
    w32(AFE_CFG0, 0U);
    w32(AFE_CFG1, 0x00010000U);
    w32(AFE_LANE_PD, 0U);
    dsb();
}

/* FUN_63d2a25e uses a volatile loop with these iteration counts. */
static void dfe_mphy_wait(uint32_t iterations) {
    for (volatile uint32_t i = 0U; i < iterations; ++i) {
    }
}

static void dfe_mphy_reset_lanes(uint32_t grp, uint32_t active_mask) {
    uint32_t lane = DFE_MPHY_GRP_LANE(grp);
    uint32_t reset = DFE_MPHY_GRP_RST(grp);
    uint32_t mode = DFE_MPHY_GRP_MODE(grp);
    w32(lane, r32(lane) & ~0x0fU);
    w32(reset, r32(reset) & ~1U);
    w32(mode, (r32(mode) & ~0x0f0fU) | 3U);
    w32(reset, r32(reset) | 1U);
    dsb();
    dfe_mphy_wait(0xc80U);
    w32(lane, (r32(lane) & ~0x0fU) | active_mask);
    dsb();
    dfe_mphy_wait(0x50U);
}

static void dfe_mphy_configure(void) {
    w32(SLVS_PHY_MODE, 0x13U);
    w32(SLVS_PHY_EN, 0U);
    dsb();
    delay_us(1U);
    w32(SLVS_PHY_MODE, 0x11U);
    w32(SLVS_PHY_EN, 1U);

    w32(SLVS_SIF_EN(SLVS_SIF0_BASE), 1U);
    w32(SLVS_SIF_EN(SLVS_SIF1_BASE), 1U);

    uint32_t global_ctrl = r32(DFE_MPHY_GLOBAL_CTRL);
    if ((global_ctrl & 1U) != 0U) {
        w32(DFE_MPHY_GLOBAL_CTRL, global_ctrl & ~1U);
        dsb();
        dfe_mphy_wait(400U);
    }
    w32(DFE_MPHY_CLK_EN, r32(DFE_MPHY_CLK_EN) | BIT(8));
    w32(DFE_MPHY_CLK_EN, r32(DFE_MPHY_CLK_EN) | BIT(12));
    dfe_mphy_reset_lanes(0U, 0x0fU);
    dfe_mphy_reset_lanes(1U, 0x0fU);
}

static void slvsec_rx_stop(void) {
    w32(SLVSEC_PORT_START(0U), 0U);
    w32(SLVSEC_PORT_START(1U), 0U);
    w32(SLVSEC_TOP_CTRL, 0U);
    dsb();
}

static void slvsec_rx_configure_port_idle(uint32_t p) {
    uint32_t base = SLVSEC_PORT_BASE(p);
    w32(base + 0x4cU, 0U);
    w32(base + 0x70U, 0U);
    w32(base + 0x54U, 0x50U);
    w32(base + 0x58U, 0U);
    w32(base + 0x5cU, 0U);
    w32(base + 0x64U, 0U);
    w32(base + 0x84U, 1U);
    w32(base + 0x88U, 0U);
    w32(base + 0x8cU, 0U);
    w32(base + 0xc4U, 0U);
    w32(base + 0x74U, 0U);
}

static void slvsec_rx_configure_port_active(uint32_t p, uint32_t aux_cfg) {
    uint32_t base = SLVSEC_PORT_BASE(p);
    w32(base + 0x54U, 0x60U);
    w32(base + 0x58U, 0U);
    w32(base + 0x5cU, 2U);
    w32(base + 0x64U, 0U);
    w32(base + 0x84U, 3U);
    w32(base + 0x88U, 0x60U);
    w32(base + 0x8cU, 1U);
    w32(base + 0xc4U, aux_cfg);
    w32(base + 0x74U, 0x0fU);
}

static void combophy_afe_and_slvsec_init(void) {
    slvs_pinmux_and_sif_pre_init();
    combophy_and_afe_enable();
    dfe_mphy_configure();

    /* FUN_637aeae0: initialize SLVS-EC common protocol registers & reset state. */
    slvsec_rx_stop();
    w32(SLVSEC_TOP_PORT_CFG, 0U);
    w32(SLVSEC_BASE + 0x08U, 0xaaU);
    w32(SLVSEC_BASE + 0x10U, 0x60U);
    w32(SLVSEC_BASE + 0x1cU, 1U);
    w32(SLVSEC_BASE + 0x20U, 0x57U);
    w32(SLVSEC_BASE + 0x24U, 0x30dU);
    w32(SLVSEC_BASE + 0x28U, 0x309U);
    w32(SLVSEC_BASE + 0x2cU, 0x30cU);
    w32(SLVSEC_BASE + 0x30U, 0U);
    w32(SLVSEC_BASE + 0x34U, 3U);
    w32(SLVSEC_BASE + 0x38U, 5U);
    w32(SLVSEC_BASE + 0x3cU, 10U);
    w32(SLVSEC_BASE + 0x40U, 0x11U);
    w32(SLVSEC_BASE + 0x44U, 0U);
    w32(SLVSEC_BASE + 0x48U, 1U);
    w32(SLVSEC_BASE + 0x68U, 9U);
    w32(SLVSEC_BASE + 0x6cU, 3U);
    w32(SLVSEC_BASE + 0x90U, 0U);
    w32(SLVSEC_BASE + 0xc8U, 0U);

    w32(SLVSEC_BASE + 0x60U, 0U);
    slvsec_rx_configure_port_idle(0U);
    slvsec_rx_configure_port_idle(1U);
    w32(SLVSEC_TOP_PORT_CFG, 3U);
    w32(SLVSEC_TOP_CTRL, 0U);

    /* FUN_637aebd0: relock MPHY lanes and enable 8-lane dual-port SLVS-EC RX. */
    slvsec_rx_stop();
    w32(SLVS_SIF_EN(SLVS_SIF0_BASE), 1U);
    w32(SLVS_SIF_EN(SLVS_SIF1_BASE), 1U);
    slvsec_rx_stop();
    w32(SLVSEC_TOP_PORT_CFG, 0U);

    for (uint32_t grp = 0U; grp < 2U; ++grp) {
        w32(DFE_MPHY_GRP_LANE(grp), 0U);
        w32(DFE_MPHY_GRP_RST(grp), 0U);
        w32(DFE_MPHY_GRP_RST(grp), 1U);
        w32(DFE_MPHY_GRP_LANE(grp), 0x0fU);
    }

    w32(SLVSEC_BASE + 0x60U, 0U);
    slvsec_rx_configure_port_active(0U, 3U);
    slvsec_rx_configure_port_active(1U, 2U);
    w32(SLVSEC_TOP_PORT_CFG, 3U);

    /* Staged SLVS-EC RX lane/port release matching FUN_637a8320..68. */
    w32(SLVSEC_TOP_CTRL, 0x01000000U);
    w32(SLVSEC_TOP_CTRL, 0x01030000U);
    w32(SLVSEC_TOP_CTRL, 0x0103ff00U);
    w32(SLVSEC_TOP_CTRL, 0x0103ffffU);
    w32(SLVSEC_PORT_START(0U), 1U);
    w32(SLVSEC_PORT_START(1U), 1U);

    for (uint32_t p = 0U; p < 2U; ++p) {
        uint32_t sif = (p == 0U) ? SLVS_SIF0_BASE : SLVS_SIF1_BASE;
        w32(SLVS_SIF_CFG0(sif), 0U);
        w32(SLVS_SIF_CFG1(sif), 0U);
        w32(SLVS_SIF_CFG3(sif), 0U);
        w32(SLVS_SIF_CFG4(sif), 0U);
        w32(SLVS_SIF_CFG2(sif), 0U);
    }
    w32(DFE_SIF2_CTRL, 0U);
    w32(DFE_SIF2_CFG, 1U);
    w32(DFE_SIF2_LANE_MAP, 0x76543210U);
    dsb();
}

/* ---- SyncSeq & DrvSGC0 Mode-1 Timing (FUN_6379ce58, FUN_635c8628, FUN_63d26acc) ---- */

static void syncseq_configure_timing(const struct sgc_timing_cfg *t) {
    uint32_t frame_cycles = t->h_total * t->v_total;
    if (t->nlr_den != 0U) {
        uint64_t num = (uint64_t)(t->nlr_delta * t->nlr_num + t->nlr_den * t->v_total) * (uint64_t)t->h_total;
        frame_cycles = udiv64_32(num, t->nlr_den);
    }
    uint32_t lead_cycles = t->freq_mhz * t->lead_us;
    uint32_t ext_timer = (frame_cycles > lead_cycles) ? (frame_cycles - lead_cycles) : 0x11U;
    if (ext_timer < 0x11U) {
        ext_timer = 0x11U;
    }

    w32(SYNCSEQ_EVT_PERIOD, 0x00fffffcU);
    w32(SYNCSEQ_SLOT_CFG, 0U);
    w32(SYNCSEQ_EXT_TRIG_TIMER, ext_timer);
    w32(SYNCSEQ_BASE + 0x040U, 0U);
    w32(SYNCSEQ_BASE + 0x058U, 0U);
    w32(SYNCSEQ_BASE + 0x070U, 0U);
    w32(SYNCSEQ_BASE + 0x088U, 0U);
    w32(SYNCSEQ_BASE + 0x0b8U, 0U);
    w32(SYNCSEQ_BASE + 0x0c8U, 0U);
    w32(SYNCSEQ_BASE + 0x0d8U, 0U);
    w32(SYNCSEQ_BASE + 0x0e8U, 0U);
    w32(SYNCSEQ_SYNC_CLR, 0U);
    w32(SYNCSEQ_EXT_DELAY1, 0U);
    w32(SYNCSEQ_EXT_DELAY0, 0U);
    w32(SYNCSEQ_BASE + 0x06cU, 0x10U);
    w32(SYNCSEQ_BASE + 0x084U, 0x10U);
    w32(SYNCSEQ_BASE + 0x09cU, 0x10U);

    w32(SYNCSEQ_ARB_CLR, r32(SYNCSEQ_ARB_CLR));
    w32(SYNCSEQ_ARB_MASK, 0U);
    dsb();
}

/* The native setters use BFI and update one field at a time. */
static void dfe_sgc0_set_field(uint32_t addr, uint32_t field_mask, uint32_t shift,
                               uint32_t value) {
    w32(addr, (r32(addr) & ~(field_mask << shift)) | ((value & field_mask) << shift));
}

static void dfe_drv_sgc0_configure_and_start(const struct sgc_timing_cfg *t, uint32_t trig_mode,
                                             uint32_t vd_num) {
    const uint32_t cycle_mask = (1U << 14) - 1U;
    const uint32_t fraction_mask = (1U << 8) - 1U;
    const uint32_t v_end = t->v_total - 1U;

    /* FUN_63d26acc programs horizontal, vertical, fractional line timing, and end. */
    dfe_sgc0_set_field(DFE_DRVSGC0_HV_CYCLE, cycle_mask, 0U, t->h_total - 1U);
    dfe_sgc0_set_field(DFE_DRVSGC0_HV_CYCLE, cycle_mask, 16U, v_end);
    dfe_sgc0_set_field(DFE_DRVSGC0_NLR_CFG, 1U, 0U, t->nlr_delta != 0U);
    if (t->nlr_delta != 0U) {
        dfe_sgc0_set_field(DFE_DRVSGC0_NLR_CFG, cycle_mask, 16U, v_end + t->nlr_delta);
        dfe_sgc0_set_field(DFE_DRVSGC0_NLR_FRAC, fraction_mask, 0U, t->nlr_den);
        dfe_sgc0_set_field(DFE_DRVSGC0_NLR_FRAC, fraction_mask, 16U, t->nlr_num);
    }
    w32(DFE_DRVSGC0_V_END, v_end - 100U);

    w32(DFE_DRVSGC0_RUN_FLAG, vd_num);
    if (trig_mode == 1U) {
        w32(DFE_DRVSGC0_EXT_SYNC, r32(DFE_DRVSGC0_EXT_SYNC) & ~BIT(16));
        w32(DFE_DRVSGC0_INT_TRIG, r32(DFE_DRVSGC0_INT_TRIG) & ~1U);
    } else if (trig_mode == 2U) {
        w32(DFE_DRVSGC0_EXT_SYNC, r32(DFE_DRVSGC0_EXT_SYNC) | BIT(16));
        w32(DFE_DRVSGC0_INT_TRIG, r32(DFE_DRVSGC0_INT_TRIG) & ~1U);
    } else {
        w32(DFE_DRVSGC0_INT_TRIG, r32(DFE_DRVSGC0_INT_TRIG) | 1U);
    }
    dsb();
    w32(DFE_DRVSGC0_START_STAT, r32(DFE_DRVSGC0_START_STAT) | 1U);
    dsb();
}

struct sgc0_counters {
    uint32_t hv;
    uint32_t frames;
};

/* The diagnostic at FUN_637a4324 reads HVcnt and Fcnt using these latches. */
static struct sgc0_counters dfe_sgc0_read_counters(void) {
    struct sgc0_counters counters;
    w32(DFE_DRVSGC0_HV_LATCH, 1U);
    dsb();
    (void)r32(DFE_DRVSGC0_HV_COUNT);
    w32(DFE_DRVSGC0_HV_LATCH, 1U);
    dsb();
    counters.hv = r32(DFE_DRVSGC0_HV_COUNT);

    dfe_sgc0_set_field(DFE_DRVSGC0_FRAME_LATCH, 1U, 0U, 1U);
    dsb();
    dfe_sgc0_set_field(DFE_DRVSGC0_FRAME_LATCH, 1U, 0U, 0U);
    dsb();
    counters.frames = r32(DFE_DRVSGC0_FRAME_COUNT) & UINT8_MAX;
    return counters;
}

/* ---- DFE Top, Crossbar, Ifmt_RcvSgc/LnkSgc/Win & RdcW0 (FUN_6379df58, resource 0x2f) ---- */

static void dfe_isp_sync_enable(void) {
    w32(CAMCORE_CLK_EN(ISP0_SYNC_BASE), r32(CAMCORE_CLK_EN(ISP0_SYNC_BASE)) | 0x00003f40U);
    w32(CAMCORE_RST_REL(ISP0_SYNC_BASE), r32(CAMCORE_RST_REL(ISP0_SYNC_BASE)) | 0x00003f40U);
    w32(CAMCORE_RST_CLR(ISP0_SYNC_BASE), 0x0000000cU);
    w32(CAMCORE_ISP_AUX_EN(ISP0_SYNC_BASE), 0x0c000000U);

    w32(CAMCORE_CLK_EN(SGC1_TOP_BASE), r32(CAMCORE_CLK_EN(SGC1_TOP_BASE)) | 0x00000006U);
    w32(CAMCORE_RST_REL(SGC1_TOP_BASE), r32(CAMCORE_RST_REL(SGC1_TOP_BASE)) | 0x00000006U);
    w32(CAMCORE_RST_CLR(SGC1_TOP_BASE), 0x00000002U);
    dsb();
}

static void dfe_crossbar_route_ifmt_to_rdcw0(void) {
    for (uint32_t i = 0U; i < 7U; ++i) {
        w32(DFE_TOP_XBAR_IN(i), 0U);
    }
    for (uint32_t i = 0U; i < 8U; ++i) {
        w32(DFE_TOP_XBAR_OUT(i), 0U);
    }
    /* Native Mode-1 RAW resource 0x2f: route Ifmt source 0x03 -> RdcW0 dest 0x1c. */
    w32(DFE_TOP_XBAR_IN(1U), 0x40000000U);
    w32(DFE_TOP_XBAR_OUT(4U), 0x00010000U);
    dsb();
}

static void dfe_ifmt_configure_mode1(void) {
    /* Ifmt_RcvSgc (0xfc0a1200) */
    for (uint32_t off = 0x30U; off <= 0x3cU; off += 4U) {
        w32(DFE_RCVSGC_BASE + off, SGC_INACTIVE_MARK);
    }
    for (uint32_t off = 0x48U; off <= 0x54U; off += 4U) {
        w32(DFE_RCVSGC_BASE + off, SGC_INACTIVE_MARK);
    }
    for (uint32_t off = 0x60U; off <= 0xacU; off += 4U) {
        w32(DFE_RCVSGC_BASE + off, 0U);
    }
    w32(DFE_RCVSGC_BASE + 0x08U, 0U);
    w32(DFE_RCVSGC_BASE + 0x20U, 0x032a3ffeU);
    w32(DFE_RCVSGC_BASE + 0x24U, 0x00000289U);
    w32(DFE_RCVSGC_BASE + 0x2cU, 0U);
    w32(DFE_RCVSGC_BASE + 0x40U, 0U);
    w32(DFE_RCVSGC_BASE + 0x44U, 0x02f80289U);
    w32(DFE_RCVSGC_BASE + 0x58U, 0x0000000cU);
    w32(DFE_RCVSGC_BASE + 0x5cU, 0x02f80287U);
    w32(DFE_RCVSGC_BASE + 0x68U, 0x00040001U);
    w32(DFE_RCVSGC_BASE + 0x6cU, 0x031a0312U);
    w32(DFE_RCVSGC_BASE + 0xb0U, 0x00270024U);
    w32(DFE_RCVSGC_BASE + 0xb4U, 0x00000436U);
    w32(DFE_RCVSGC_BASE + 0xb8U, 0x00020000U);
    w32(DFE_RCVSGC_BASE + 0xc0U, 0U);
    w32(DFE_RCVSGC_BASE + 0x00U, 1U);

    /* Ifmt_LnkSgc (0xfc0a1300) */
    for (uint32_t off = 0x30U; off <= 0x3cU; off += 4U) {
        w32(DFE_LNKSGC_BASE + off, SGC_INACTIVE_MARK);
    }
    for (uint32_t off = 0x80U; off <= 0x8cU; off += 4U) {
        w32(DFE_LNKSGC_BASE + off, SGC_INACTIVE_MARK);
    }
    for (uint32_t off = 0x90U; off <= 0xa4U; off += 4U) {
        w32(DFE_LNKSGC_BASE + off, 0U);
    }
    w32(DFE_LNKSGC_BASE + 0x04U, 0U);
    w32(DFE_LNKSGC_BASE + 0x08U, 0U);
    w32(DFE_LNKSGC_BASE + 0x0cU, 3U);
    w32(DFE_LNKSGC_BASE + 0x20U, 0x064b027bU);
    w32(DFE_LNKSGC_BASE + 0x24U, 0x0000064bU);
    w32(DFE_LNKSGC_BASE + 0x2cU, 0U);
    w32(DFE_LNKSGC_BASE + 0x40U, 0U);
    w32(DFE_LNKSGC_BASE + 0x44U, 0x05f1027bU);
    w32(DFE_LNKSGC_BASE + 0x48U, SGC_INACTIVE_MARK);
    w32(DFE_LNKSGC_BASE + 0x4cU, SGC_INACTIVE_MARK);
    w32(DFE_LNKSGC_BASE + 0x50U, 0U);
    w32(DFE_LNKSGC_BASE + 0x54U, 0x01fb0263U);
    w32(DFE_LNKSGC_BASE + 0x58U, 0x000d0269U);
    w32(DFE_LNKSGC_BASE + 0x5cU, 0x05f10279U);
    w32(DFE_LNKSGC_BASE + 0x60U, SGC_INACTIVE_MARK);
    w32(DFE_LNKSGC_BASE + 0x64U, SGC_INACTIVE_MARK);
    w32(DFE_LNKSGC_BASE + 0x68U, 0x06423fffU);
    w32(DFE_LNKSGC_BASE + 0x6cU, 0x063c3fffU);
    w32(DFE_LNKSGC_BASE + 0x70U, 0x061d3fffU);
    w32(DFE_LNKSGC_BASE + 0x74U, 0x06423fffU);
    w32(DFE_LNKSGC_BASE + 0x78U, 0x0004001cU);
    w32(DFE_LNKSGC_BASE + 0x7cU, 0x01fa0279U);
    w32(DFE_LNKSGC_BASE + 0xa8U, 0x00010101U);
    w32(DFE_LNKSGC_BASE + 0xacU, 0U);
    w32(DFE_LNKSGC_BASE + 0xb0U, 0x002d0025U);
    w32(DFE_LNKSGC_BASE + 0xb4U, 0x0023001bU);
    w32(DFE_LNKSGC_BASE + 0xb8U, 0x00040000U);
    w32(DFE_LNKSGC_BASE + 0xbcU, 0x027b0000U);
    w32(DFE_LNKSGC_BASE + 0xd0U, 0x06720000U);
    w32(DFE_LNKSGC_BASE + 0xd4U, 0x00000436U);
    w32(DFE_LNKSGC_BASE + 0xd8U, 0x00020000U);
    w32(DFE_LNKSGC_BASE + 0xe0U, SGC_INACTIVE_MARK);
    w32(DFE_LNKSGC_BASE + 0xe4U, SGC_INACTIVE_MARK);
    w32(DFE_LNKSGC_BASE + 0xe8U, 0U);
    w32(DFE_LNKSGC_BASE + 0xecU, 0U);
    w32(DFE_LNKSGC_BASE + 0x00U, 1U);

    /* Ifmt_Win (0xfc0a1c00) active crop & OB window */
    w32(DFE_IFMT_WIN_BASE + 0x00U, 0x00003fffU);
    w32(DFE_IFMT_WIN_BASE + 0x10U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x14U, 1U);
    w32(DFE_IFMT_WIN_BASE + 0x1cU, 1U);
    w32(DFE_IFMT_WIN_BASE + 0x20U, 0x025d024dU);
    w32(DFE_IFMT_WIN_BASE + 0x24U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x28U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x2cU, 0x05f1000dU);
    w32(DFE_IFMT_WIN_BASE + 0x30U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x34U, 0x0aU);
    w32(DFE_IFMT_WIN_BASE + 0x44U, 0x025d024dU);
    w32(DFE_IFMT_WIN_BASE + 0x48U, 0x05f0000dU);
    w32(DFE_IFMT_WIN_BASE + 0x4cU, 1U);
    w32(DFE_IFMT_WIN_BASE + 0x0cU, 3U);
    w32(DFE_IFMT_WIN_BASE + 0x50U, 0x0263001cU);
    w32(DFE_IFMT_WIN_BASE + 0x54U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x58U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x5cU, 0x01fa0004U);
    w32(DFE_IFMT_WIN_BASE + 0x60U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x64U, 0x0aU);
    w32(DFE_IFMT_WIN_BASE + 0x68U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x6cU, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x70U, 0U);
    w32(DFE_IFMT_WIN_BASE + 0x74U, 0x0263001cU);
    w32(DFE_IFMT_WIN_BASE + 0x78U, 0x01fa0004U);
    w32(DFE_IFMT_WIN_BASE + 0x7cU, 0U);
    dsb();
}

static void dfe_rdcw0_configure_and_start(uint32_t dst_pa, uint32_t width, uint32_t height,
                                          uint32_t stride_px) {
    /* Soft-reset AIF & RDC bypass */
    w32(DFE_AIF_TOP_RESET, 4U);
    w32(DFE_AIF_TOP_RESET, 2U);
    w32(DFE_RDC_BYPASS0, 0x100U);
    w32(DFE_RDC_BYPASS0_EN, 1U);
    w32(DFE_RDC_BYPASS1_EN, 1U);
    w32(DFE_RDC_OUT_EN, 1U);
    w32(DFE_RDC_CTL, 0U);

    w32(DFE_RDCW0_ADDR, dst_pa);
    w32(DFE_RDCW0_LINE_BYTES, width * 2U);
    w32(DFE_RDCW0_LINE_GAP, (stride_px - width) * 2U);
    w32(DFE_RDCW0_BASE + 0x30U, 0U);
    w32(DFE_RDCW0_BASE + 0x38U, 0U);
    w32(DFE_RDCW0_BASE + 0x40U, 0U);
    w32(DFE_RDCW0_HEIGHT_M1, height - 1U);
    w32(DFE_RDCW0_BASE + 0x34U, 0U);
    w32(DFE_RDCW0_BASE + 0x3cU, 0U);
    w32(DFE_RDCW0_BASE + 0x44U, 0U);
    w32(DFE_RDCW0_BASE + 0x50U, 0U);
    w32(DFE_RDCW0_STATUS, 0U);
    w32(DFE_RDCW0_CTL, 2U);
    w32(DFE_RDCW0_BASE + 0x78U, 0U);
    w32(DFE_RDCW0_BASE + 0x74U, 0U);

    w32(DFE_AIF_TOP_EN, 4U);
    w32(DFE_RDCW0_CTL, 3U);
    dsb();
}

#define DFE_MODE1_CORE_BITS (DFE_CORE_BIT_IFMT | DFE_CORE_BIT_SIF | DFE_CORE_BIT_RDC | DFE_CORE_BIT_AIF)

static void dfe_top_enable_and_route_mode1(uint32_t dst_pa, uint32_t width, uint32_t height,
                                           uint32_t stride_px, uint32_t *out_timer_gate) {
    dfe_isp_sync_enable();

    w32(DFE_TOP_CORE_EN_SET, DFE_MODE1_CORE_BITS);
    dsb();
    w32(DFE_TOP_BRIDGE_SET, BIT(0));
    w32(DFE_TOP_BRIDGE_SET, BIT(4));
    dsb();

    uint32_t gate = DFE_TIMER_GATE_BITS & ~r32(DFE_TIMER_GATE_SET);
    w32(DFE_TIMER_GATE_SET, gate);
    if (out_timer_gate) {
        *out_timer_gate = gate;
    }
    w32(DFE_TIMER_AUX_EN, 1U);

    w32(DFE_TOP_ERR_MASK_SET, 0x0000ffffU);
    /* FUN_637a0090 brackets configuration with SIF0 reset bit 12. */
    w32(DFE_PLL_RST_CTRL, r32(DFE_PLL_RST_CTRL) | BIT(12));
    dsb();
    w32(DFE_SIF0_EN, 1U);
    w32(DFE_PLL_SIF_CLK_EN, 1U);
    w32(DFE_SIF2_TRIG, 0x00200000U);
    w32(DFE_PLL_RST_CTRL, r32(DFE_PLL_RST_CTRL) & ~BIT(14));
    w32(DFE_PLL_RST_CTRL, r32(DFE_PLL_RST_CTRL) & ~BIT(12));
    dsb();
    w32(DFE_SIF3_EN, 0U);

    dfe_crossbar_route_ifmt_to_rdcw0();
    dfe_ifmt_configure_mode1();
    dfe_rdcw0_configure_and_start(dst_pa, width, height, stride_px);

    w32(DFE_FOPD_EN, 1U);
    w32(DFE_LNKSGC_BASE + 0x10U, 1U);
    w32(DFE_RCVSGC_BASE + 0x10U, 1U);
    dsb();
}

static void dfe_top_disable(uint32_t timer_gate) {
    w32(DFE_TIMER_AUX_START, 0U);
    w32(0xfc098280U, 0U);
    w32(DFE_DRVSGC0_START_STAT, 0U);
    w32(DFE_RCVSGC_BASE + 0x10U, 0U);
    w32(DFE_LNKSGC_BASE + 0x10U, 0U);
    w32(DFE_RCVSGC_BASE + 0x00U, 0U);
    w32(DFE_LNKSGC_BASE + 0x00U, 0U);
    w32(DFE_FOPD_EN, 0U);
    w32(DFE_ZPD_SGC_BASE + 0x10U, 0U);
    w32(DFE_ZPD_SGC_BASE + 0x00U, 0U);
    w32(DFE_RDCW0_CTL, 0U);
    slvsec_rx_stop();
    if (timer_gate != 0U) {
        w32(DFE_TIMER_GATE_CLR, timer_gate);
    }
    w32(DFE_TOP_BRIDGE_CLR, BIT(4) | BIT(0));
    w32(DFE_TOP_CORE_EN_CLR, DFE_MODE1_CORE_BITS);
    w32(DFE_TOP_CORE_EN_SET, 0x00000160U);
    camcore_set_sync_route(ISP0_SYNC_BASE, 0U, 1U, 1U);
    camcore_set_sync_route(SGC1_TOP_BASE, 0U, 1U, 1U);
    dsb();
}

#endif /* CXD90057_PIPELINE_H */

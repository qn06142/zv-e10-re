/* SPDX-License-Identifier: GPL-2.0 */
#ifndef ZV_BAYER_CAPTURE_H
#define ZV_BAYER_CAPTURE_H

#include "zvrt_runtime.h"
#include "bayer_sensor_tables.h"
#include "bayer_probe.h"

#define BAYER_SEQ_PORT      0xfc088300U
#define BAYER_SEQ_RUN       0xfc088e00U
#define BAYER_SEQ_IRQ       0xfc088f00U
#define BAYER_DFE_EVENT     0xfc01ff00U
#define BAYER_SEQ_GIC_IRQ   132U
#define BAYER_STILL_WIDTH      6048U
#define BAYER_STILL_HEIGHT     4024U
#define BAYER_STILL_LINE_BYTES (BAYER_STILL_WIDTH * 2U)
#define BAYER_STILL_BYTES      (BAYER_STILL_LINE_BYTES * BAYER_STILL_HEIGHT)
#define BAYER_STILL_TIMEOUT    2000000U /* 1 second at 2 MHz */
#define BAYER_AIF_START        1U
#define BAYER_AIF_MODE         2U
#define BAYER_AIF_STOP         (1U << 30)
#define BAYER_AIF_ERROR_MASK   0x000f001fU /* Native +0x08 getters at 0x639e233c/2360. */
#define BAYER_TAIL_MARKER      0xc0debfadU

_Static_assert(BAYER_STILL_BYTES <= ZVRT_STILL_RAW_END - ZVRT_STILL_RAW_PA,
               "Still RAW frame exceeds its DMA reservation");

struct bayer_capture_state {
    volatile uint32_t seq_irqs;
    uint32_t seq_timeouts;
    uint32_t armed_at;
    uint32_t max_offset;
    uint32_t busy_seen;
    uint32_t armed;
    uint32_t owns_pipeline;
};

static inline void bayer_seq_configure(uint32_t config0, uint32_t config1) {
    *zvrt_reg(BAYER_SEQ_PORT + 4U) = (*zvrt_reg(BAYER_SEQ_PORT + 4U) & ~1U) | (config0 & 1U);
    *zvrt_reg(BAYER_SEQ_PORT + 8U) = (*zvrt_reg(BAYER_SEQ_PORT + 8U) & ~7U) | (config1 & 7U);
    *zvrt_reg(BAYER_SEQ_RUN) = 2U;
    *zvrt_reg(BAYER_SEQ_PORT) |= 1U;
    zvrt_dsb();
}

static inline int bayer_seq_upload(const uint8_t *bytes, uint32_t count) {
    if (count > 256U || (count && !bytes)) {
        return -1;
    }
    *zvrt_reg(BAYER_SEQ_PORT + 12U) &= ~255U;
    for (uint32_t i = 0U; i < count; ++i) {
        *zvrt_reg(BAYER_SEQ_PORT + 0x40U + i * 4U) = bytes[i];
    }
    zvrt_dsb();
    return 0;
}

static inline int bayer_seq_run(uint32_t mode) {
    if (mode > 2U) {
        return -1;
    }
    *zvrt_reg(BAYER_SEQ_RUN) = mode;
    zvrt_dsb();
    if (mode == 2U) {
        zvrt_delay_ticks(20U);
        *zvrt_reg(BAYER_SEQ_RUN + 8U) = 1U;
        zvrt_dsb();
        zvrt_delay_ticks(20U);
        *zvrt_reg(BAYER_SEQ_RUN + 8U) = 0U;
        zvrt_dsb();
        zvrt_delay_ticks(20U);
        *zvrt_reg(BAYER_SEQ_RUN + 8U) = 1U;
        zvrt_dsb();
    }
    return 0;
}

static inline void bayer_seq_stop(void) {
    *zvrt_reg(BAYER_SEQ_PORT) &= ~1U;
    zvrt_dsb();
}

static inline void bayer_seq_ack(void) {
    *zvrt_reg(BAYER_SEQ_IRQ + 4U) |= 1U;
    zvrt_dsb();
}

static inline void bayer_seq_irq_enable(uint32_t enable) {
    bayer_seq_ack();
    uint32_t mask = *zvrt_reg(BAYER_SEQ_IRQ + 8U);
    *zvrt_reg(BAYER_SEQ_IRQ + 8U) = enable ? (mask | 1U) : (mask & ~1U);
    zvrt_dsb();
}

/* Dispatch DFE event 0 on GIC IRQ 132: acknowledge, park sequencer, ack DFE. */
static void bayer_seq_irq_handler(uint32_t irq, void *ctx) {
    (void)irq;
    struct bayer_capture_state *st = (struct bayer_capture_state *)ctx;
    if (*zvrt_reg(BAYER_DFE_EVENT) != 0U) {
        return;
    }
    bayer_seq_ack();
    *zvrt_reg(BAYER_SEQ_RUN) = 2U;
    *zvrt_reg(BAYER_DFE_EVENT) = 1U;
    zvrt_dsb();
    if (st) {
        st->seq_irqs++;
    }
}

static inline void bayer_capture_wait_seq_irq(struct bayer_capture_state *st,
                                              uint32_t prev, uint32_t timeout_us) {
    uint32_t start = zvrt_timer_ticks();
    for (uint32_t spin = 0U; spin < 20000000U; ++spin) {
        if (st->seq_irqs != prev) {
            return;
        }
        if (*zvrt_reg(BAYER_SEQ_IRQ + 4U) & 1U) {
            bayer_seq_ack();
            *zvrt_reg(BAYER_SEQ_RUN) = 2U;
            zvrt_dsb();
            st->seq_irqs++;
            return;
        }
        if ((uint32_t)(zvrt_timer_ticks() - start) >= timeout_us) {
            break;
        }
    }
    st->seq_timeouts++;
}

static inline void bayer_run_seq_burst(struct bayer_capture_state *st,
                                       const uint8_t *bytes, uint32_t count,
                                       uint32_t run_mode, int wait_irq) {
    uint32_t prev = st->seq_irqs;
    bayer_seq_configure(0U, 3U);
    bayer_seq_upload(bytes, count);
    bayer_seq_run(run_mode);
    if (wait_irq) {
        bayer_capture_wait_seq_irq(st, prev, 200000U);
        if (run_mode == 2U && st->seq_irqs == prev) {
            bayer_seq_run(0U);
            bayer_capture_wait_seq_irq(st, prev, 200000U);
        }
    }
}

#define BAYER_PSAVE_DDRC_B  0xf0105000U
#define BAYER_PSAVE_PMU     0xf290e000U

/* Port upm.ko PSAVE_IMAGER_WAKE (0x103f8..0x10654) to release DDRC B & DFE isolation. */
static inline void bayer_psave_imager_wake(void) {
    for (uint32_t i = 0U; i < 100000U; ++i) {
        if ((*zvrt_reg(BAYER_PSAVE_DDRC_B + 0xa0U) & 0x01000000U) != 0U &&
            (*zvrt_reg(BAYER_PSAVE_DDRC_B + 0xa4U) & 1U) != 0U) {
            break;
        }
    }
    *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x138U) |= 0x300U;
    zvrt_dsb();

    for (uint32_t i = 0U; i < 100000U; ++i) {
        uint32_t st = *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x148U);
        if ((st & 0x20000000U) != 0U && (st & 0x00200000U) != 0U) {
            break;
        }
    }
    *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x14cU) = 0x1fffffffU;
    *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x68U) &= ~0x10000U;
    zvrt_dsb();

    *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x218U) = 0U;
    *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x118U) = 0U;
    zvrt_dsb();

    *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x90U) = 0x26U;
    zvrt_dsb();
    for (uint32_t i = 0U; i < 100000U; ++i) {
        uint32_t st = *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x148U);
        if ((st & 0x20000000U) != 0U && (st & 0x10U) != 0U) {
            break;
        }
    }
    *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x14cU) = 0x1fffffffU;

    uint32_t cfg = *zvrt_reg(BAYER_PSAVE_DDRC_B + 0x138U);
    uint32_t mask = (cfg & 0x20000U) ? 0x3f3f0000U : 0x003f0000U;
    uint32_t want = (cfg & 0x20000U) ? 0x24240000U : 0x00240000U;
    for (uint32_t i = 0U; i < 100000U; ++i) {
        if ((*zvrt_reg(BAYER_PSAVE_DDRC_B + 0x90U) & mask) == want) {
            break;
        }
    }
    zvrt_dsb();

    *zvrt_reg(BAYER_PSAVE_PMU + 0x210U) = 0U;
    zvrt_dsb();
    *zvrt_reg(BAYER_PSAVE_PMU + 0x008U) = 0U;
    zvrt_dsb();
    *zvrt_reg(BAYER_PSAVE_PMU + 0x004U) = 0U;
    zvrt_dsb();
}

static inline void bayer_write_reg_ops(const struct bayer_reg_op *ops, uint32_t count) {
    for (uint32_t i = 0U; i < count; ++i) {
        *zvrt_reg(ops[i].addr) = ops[i].value;
    }
    zvrt_dsb();
}

#define BAYER_WRITE_TABLE(tbl) bayer_write_reg_ops((tbl), (uint32_t)(sizeof(tbl) / sizeof((tbl)[0])))

static inline int bayer_capture_rearm(struct bayer_capture_state *st) {
    volatile uint32_t *writer = zvrt_reg(BAYER_ISP0_WRITE);
    if (st->armed || (writer[0] & BAYER_AIF_START) ||
        (writer[1] & (BAYER_WRITER_BUSY | BAYER_AIF_STOP))) {
        return -1;
    }

    /* The stock still task prepares sensor readout for each shot. */
    bayer_run_seq_burst(st, imx284_still_upload_0, sizeof(imx284_still_upload_0), 2U, 1);
    bayer_run_seq_burst(st, imx284_still_upload_1, sizeof(imx284_still_upload_1), 2U, 1);
    /* Mode 0 queues the frame-synchronous burst for the upcoming DFE start. */
    bayer_run_seq_burst(st, imx284_still_upload_2, sizeof(imx284_still_upload_2), 0U, 0);

    writer[0] = BAYER_AIF_MODE;
    writer[3] = 0U;
    writer[8] = ZVRT_STILL_RAW_PA;
    writer[9] = BAYER_STILL_LINE_BYTES;
    writer[10] = 0U;
    writer[11] = BAYER_STILL_HEIGHT - 1U;
    /* Check the end of the frame after DMA. The cursor resets on idle,
     * so an idle edge alone cannot distinguish a short write. */
    volatile uint32_t *tail = (volatile uint32_t *)zvrt_ddr0_va(ZVRT_STILL_RAW_PA + BAYER_STILL_BYTES - 8U);
    tail[0] = BAYER_TAIL_MARKER;
    tail[1] = ~BAYER_TAIL_MARKER;
    zvrt_dsb();

    st->max_offset = 0U;
    st->busy_seen = 0U;
    st->armed_at = zvrt_timer_ticks();
    st->armed = 1U;
    writer[0] = BAYER_AIF_MODE | BAYER_AIF_START;
    zvrt_dsb();

    BAYER_WRITE_TABLE(dfe_still_start_writes);
    return 0;
}

/* Bring up IMX284 and the native still timing before arming the ISP0 writer. */
static inline int bayer_capture_start(struct bayer_capture_state *st) {
    volatile uint32_t *writer = zvrt_reg(BAYER_ISP0_WRITE);
    st->seq_irqs = 0U;
    st->seq_timeouts = 0U;
    st->armed = 0U;
    st->owns_pipeline = 0U;
    if ((writer[0] & BAYER_AIF_START) ||
        (writer[1] & (BAYER_WRITER_BUSY | BAYER_AIF_STOP))) {
        return -1;
    }
    st->owns_pipeline = 1U;

    bayer_psave_imager_wake();

    uint32_t count = (uint32_t)(sizeof(imx284_power_on_ops) / sizeof(imx284_power_on_ops[0]));
    for (uint32_t i = 0U; i < count; ++i) {
        uint32_t addr = imx284_power_on_ops[i].addr;
        uint32_t val = imx284_power_on_ops[i].value;
        if (addr == 0U) {
            zvrt_delay_ticks(val * 2U);
        } else {
            *zvrt_reg(addr) = val;
            zvrt_dsb();
        }
    }

    zvrt_irq_register(BAYER_SEQ_GIC_IRQ, bayer_seq_irq_handler, st);
    zvrt_irq_enable(BAYER_SEQ_GIC_IRQ);

    BAYER_WRITE_TABLE(dfe_mode5_pll_phy_writes);
    zvrt_delay_ticks(2000U);

    BAYER_WRITE_TABLE(dfe_still_clock_writes);
    BAYER_WRITE_TABLE(dfe_still_setup_writes);

    BAYER_WRITE_TABLE(imx284_wake_pre_writes);
    bayer_seq_irq_enable(1U);

    bayer_run_seq_burst(st, imx284_wake_upload_0, sizeof(imx284_wake_upload_0), 2U, 1);
    bayer_run_seq_burst(st, imx284_wake_upload_0, sizeof(imx284_wake_upload_0), 2U, 1);
    zvrt_delay_ticks(12000U * 2U);
    bayer_run_seq_burst(st, imx284_wake_upload_1, sizeof(imx284_wake_upload_1), 2U, 1);
    bayer_run_seq_burst(st, imx284_wake_upload_2, sizeof(imx284_wake_upload_2), 2U, 1);
    zvrt_delay_ticks(6000U * 2U);

    BAYER_WRITE_TABLE(imx284_wake_post_writes);
    zvrt_delay_ticks(20000U * 2U);

    BAYER_WRITE_TABLE(imx284_still_pre_writes);
    return bayer_capture_rearm(st);
}

static inline int bayer_capture_complete(struct bayer_capture_state *st) {
    if (!st->armed) {
        return 0;
    }
    volatile uint32_t *writer = zvrt_reg(BAYER_ISP0_WRITE);
    uint32_t status = writer[1];
    st->busy_seen |= status & BAYER_WRITER_BUSY;
    uint32_t cursor = writer[4];
    uint32_t offset = cursor - ZVRT_STILL_RAW_PA;
    if ((status & BAYER_WRITER_BUSY) && offset < BAYER_STILL_BYTES && offset > st->max_offset) {
        st->max_offset = offset;
    }
    /* The stock cursor resets to zero on completion. Require a substantial
     * in-flight transfer before accepting the observed busy-to-idle edge. */
    if (st->max_offset < BAYER_STILL_BYTES / 2U || cursor != 0U ||
        (status & (BAYER_WRITER_BUSY | BAYER_AIF_STOP)) ||
        (writer[0] & BAYER_AIF_START) || (writer[2] & BAYER_AIF_ERROR_MASK) ||
        writer[8] != ZVRT_STILL_RAW_PA) {
        return 0;
    }
    zvrt_dsb();
    if (writer[1] != status || writer[4] != 0U) {
        return 0;
    }
    volatile const uint32_t *tail = (volatile const uint32_t *)zvrt_ddr0_va(ZVRT_STILL_RAW_PA + BAYER_STILL_BYTES - 8U);
    if (tail[0] == BAYER_TAIL_MARKER || tail[1] == ~BAYER_TAIL_MARKER) {
        return 0;
    }
    st->armed = 0U;
    return 1;
}

static inline int bayer_capture_stop(struct bayer_capture_state *st) {
    if (!st->owns_pipeline) {
        return 0;
    }
    volatile uint32_t *writer = zvrt_reg(BAYER_ISP0_WRITE);
    writer[0] &= ~BAYER_AIF_START;
    if (writer[1] & BAYER_WRITER_BUSY) {
        writer[1] |= BAYER_AIF_STOP;
    }
    zvrt_dsb();
    bayer_seq_stop();
    bayer_seq_irq_enable(0U);
    zvrt_irq_disable(BAYER_SEQ_GIC_IRQ);
    if (writer[1] & BAYER_WRITER_BUSY) {
        return -1;
    }
    st->owns_pipeline = 0U;
    st->armed = 0U;
    return 0;
}

#endif

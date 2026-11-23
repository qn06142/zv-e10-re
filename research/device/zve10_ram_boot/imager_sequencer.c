/* SPDX-License-Identifier: GPL-2.0 */
#include "imager_sequencer.h"
#include "zvrt_runtime.h"

#define SEQ_PORT 0xfc088300U
#define SEQ_RUN  0xfc088e00U
#define SEQ_IRQ  0xfc088f00U

/* Native helpers: 637a8c04/28, 637a8c80, 637a8c98, 637a8ccc,
 * 637a8c50, 637a8d38, 637a8cf0/637a8d14 (reference av-cam.bin). */
void imager_seq_configure(uint32_t config0, uint32_t config1) {
    *zvrt_reg(SEQ_PORT + 4U) = (*zvrt_reg(SEQ_PORT + 4U) & ~1U) | (config0 & 1U);
    *zvrt_reg(SEQ_PORT + 8U) = (*zvrt_reg(SEQ_PORT + 8U) & ~7U) | (config1 & 7U);
    *zvrt_reg(SEQ_RUN) = 2U;
    *zvrt_reg(SEQ_PORT) |= 1U;
    zvrt_dsb();
}

int imager_seq_upload(const uint8_t *bytes, uint32_t count) {
    if (count > 256U || (count && !bytes)) return -1;
    /* Native 637a8b7e calls 637a8c80 with zero before each upload. */
    *zvrt_reg(SEQ_PORT + 12U) &= ~255U;
    for (uint32_t i = 0; i < count; ++i)
        *zvrt_reg(SEQ_PORT + 0x40U + i * 4U) = bytes[i];
    zvrt_dsb();
    return 0;
}

int imager_seq_run(uint32_t mode) {
    if (mode > 2U) return -1;
    *zvrt_reg(SEQ_RUN) = mode;
    if (mode == 2U) {
        *zvrt_reg(SEQ_RUN + 8U) = 1U;
        *zvrt_reg(SEQ_RUN + 8U) = 0U;
        *zvrt_reg(SEQ_RUN + 8U) = 1U;
    }
    zvrt_dsb();
    return 0;
}

void imager_seq_stop(void) {
    *zvrt_reg(SEQ_PORT) &= ~1U;
    zvrt_dsb();
}

void imager_seq_ack(void) {
    *zvrt_reg(SEQ_IRQ + 4U) |= 1U;
    zvrt_dsb();
}

void imager_seq_irq_enable(uint32_t enable) {
    imager_seq_ack();
    uint32_t mask = *zvrt_reg(SEQ_IRQ + 8U);
    *zvrt_reg(SEQ_IRQ + 8U) = enable ? (mask | 1U) : (mask & ~1U);
    zvrt_dsb();
}

int imager_seq_handle_irq(void) {
    /* Native IRQ 132 dispatches DFE event 0 to the index-1 sequencer callback.
     * 6379d1f4 -> 637a8998 -> 63d2a3c4 acknowledges and parks the engine;
     * 63d26ebe then acknowledges the DFE interrupt controller. */
    if (*zvrt_reg(0xfc01ff00U) != 0U) return -1;
    imager_seq_ack();
    *zvrt_reg(SEQ_RUN) = 2U; /* Park, without the software-start pulse. */
    *zvrt_reg(0xfc01ff00U) = 1U;
    zvrt_dsb();
    return 0;
}

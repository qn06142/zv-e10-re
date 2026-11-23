/* SPDX-License-Identifier: GPL-2.0 */
#include "bayer_probe.h"

static struct bayer_writer_observation writer, reader;
static uint32_t polls;

/* Use a bounded elapsed interval and an independent instruction budget.
 * Skip repeated reads within the same interval even if the timer stalls. */
static void sample_writers(void) {
    bayer_reset_observation(&writer, BAYER_ISP0_WRITE);
    bayer_reset_observation(&reader, BAYER_ISP1_READ);
    uint32_t start = zvrt_timer_ticks();
    uint32_t last_poll = start;
    for (uint32_t spin = 0; spin < 16000000U; ++spin) {
        uint32_t now = zvrt_timer_ticks();
        if (now - start >= 300000U) {
            break;
        }
        if (now - last_poll < 500U) {
            continue;
        }
        bayer_observe_writer(&writer, bayer_read_writer(BAYER_ISP0_WRITE));
        bayer_observe_writer(&reader, bayer_read_writer(BAYER_ISP1_READ));
        last_poll = now;
        ++polls;
    }
}

void rtos_main(struct zvrt_handoff *handoff) {
    sample_writers();
    uint16_t *frame = zvrt_ddr0_va(ZVRT_DISPLAY_PA);
    bayer_draw_probe_screen(
        frame,
        "Bayer RAW DMA probe",
        &writer,
        &reader,
        polls,
        "Post-GO register samples. Values are hex.",
        "Address changes and busy edges are observations only."
    );
    zvrt_dsb();
    if (zvrt_display_init(ZVRT_DISPLAY_PA) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(8U);
    }
    handoff->result = ZVRT_PROBE_OK;
    for (;;) {
        zvrt_display_wait(ZVRT_DISPLAY_PA, 200000U);
    }
}

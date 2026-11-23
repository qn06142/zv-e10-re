/* SPDX-License-Identifier: GPL-2.0 */
#include "bayer_display.h"

#define FRAME_WAIT_TICKS 100000U
#define FLIP_ATTEMPTS 4U

static uint16_t test_pixels[BAYER_TEST_WIDTH * BAYER_TEST_HEIGHT];

void rtos_main(struct zvrt_handoff *handoff) {
    struct bayer_source source = {{test_pixels, BAYER_TEST_WIDTH, BAYER_TEST_HEIGHT, BAYER_TEST_WIDTH}, 0U, 0U};
    const char *label = "TEST PATTERN  |  SOFTWARE RESIZE";
    if (bayer_has_embedded_fixture(&source)) {
        label = "SENSER RAW  |  SOFTWARE RESIZE";
    } else if (bayer_has_staged_clip(&source, handoff)) {
        label = "STAGED BAYER  |  SOFTWARE RESIZE";
    }
    uint32_t front = ZVRT_DISPLAY_PA, back = front + ZVRT_FRAME_BYTES;
    struct bayer_frame frame = bayer_acquire_frame(&source, test_pixels);
    uint16_t *fb = zvrt_ddr0_va(front);
    bayer_resize_lcd(fb, &frame);
    zvrt_draw_text(fb, 12, 10, label, 0xFFFFU, 0x000FU, 2);
    zvrt_dsb();
    if (zvrt_display_init(front) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(8U);
    }
    handoff->result = ZVRT_PROBE_OK;

    for (;;) {
        zvrt_display_wait(front, FRAME_WAIT_TICKS);
        frame = bayer_acquire_frame(&source, test_pixels);
        fb = zvrt_ddr0_va(back);
        bayer_resize_lcd(fb, &frame);
        zvrt_draw_text(fb, 12, 10, label, 0xFFFFU, 0x000FU, 2);
        zvrt_dsb();
        uint32_t attempt = 1;
        while (zvrt_display_flip(back, 30000U) != 0) {
            if (++attempt > FLIP_ATTEMPTS) {
                handoff->result = ZVRT_PROBE_FAIL;
                zvrt_report_error(8U);
            }
        }
        uint32_t previous = front;
        front = back;
        back = previous;
    }
}

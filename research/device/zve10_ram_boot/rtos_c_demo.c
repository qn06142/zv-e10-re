/* SPDX-License-Identifier: GPL-2.0 */
/* Minimal C bare-metal demo exercising crt0, .data/.rodata/.bss, heap, MMU, and 640x480 OSD0. */
#include "zvrt_runtime.h"

/* Exercise .rodata, initialized .data, and .bss sections across relocation. */
static const uint16_t palette[4] = {0xF00F, 0x0F0F, 0x00FF, 0xFFFF};
static uint32_t frame_counter = 1;
static uint32_t bss_guard[4];

_Static_assert(2U * ZVRT_FRAME_BYTES <= ZVRT_DISPLAY_SIZE, "DMA range must hold two frames");

static void fill_frame(uint32_t pa, uint16_t color) {
    uint32_t pair = ((uint32_t)color << 16) | color;
    uint32_t *pixels = (uint32_t *)zvrt_ddr0_va(pa);
    for (uint32_t i = 0; i < ZVRT_FRAME_BYTES / 4U; i++) {
        pixels[i] = pair;
    }
    zvrt_dsb();
}

void rtos_main(struct zvrt_handoff *handoff) {

    if (bss_guard[0] != 0 || bss_guard[3] != 0 || frame_counter != 1) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(7U);
    }

    uint32_t front_pa = ZVRT_DISPLAY_PA;
    uint32_t back_pa = front_pa + ZVRT_FRAME_BYTES;
    fill_frame(front_pa, palette[0]);
    if (zvrt_display_init(front_pa) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(8U);
    }

    uint32_t *scratch = (uint32_t *)zvrt_alloc(256U, 64U);
    if (!scratch) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(9U);
    }
    scratch[0] = 0xCAFEBABEU;

    handoff->result = ZVRT_PROBE_OK;

    int led = 0;
    for (;;) {
        fill_frame(back_pa, palette[frame_counter & 3U]);
        while (zvrt_display_flip(back_pa, 30000U) != 0) {
            /* Keep the pending frame and retry without recycling either buffer. */
        }

        uint32_t tmp = front_pa;
        front_pa = back_pa;
        back_pa = tmp;

        frame_counter++;
        led ^= 1;
        zvrt_led_set(led);
        zvrt_display_wait(front_pa, 200000U);
    }
}

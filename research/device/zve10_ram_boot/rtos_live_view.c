/* SPDX-License-Identifier: GPL-2.0 */
/* Live-view bring-up: observe register activity without reading image buffers.
 * crt0 has already quiesced the platform. These are post-takeover samples,
 * not evidence that the stock producer survived or a frame completed. */
#include "zvrt_runtime.h"

#define BANK_COUNT 10U

static const struct {
    const char *name;
    uint32_t base;
} banks[BANK_COUNT] = {
    {"ISP3", 0xf3002380U}, {"ISP9", 0xf3102380U},
    {"FOPD-R0", 0xf3020200U}, {"FOPD-W0", 0xf3020280U},
    {"FOPD-W1", 0xf3020300U}, {"DFE-W0", 0xfc0a9200U},
    {"YUV0-P0", 0xf3441280U}, {"YUV0-P1", 0xf3441580U},
    {"YUV1-P0", 0xf3441200U}, {"YUV1-P1", 0xf3441500U},
};

/* Symbol retained for debugger/readback. Each row: control, status, address,
 * changed observations, address changes. Counters count samples, not frames. */
uint32_t live_view_samples[BANK_COUNT][5];
uint32_t live_view_initial[BANK_COUNT][3];
uint32_t live_view_polls;

void live_view_sample(void) {
    for (uint32_t i = 0; i < BANK_COUNT; ++i) {
        uint32_t control = *zvrt_reg(banks[i].base);
        uint32_t status = *zvrt_reg(banks[i].base + 4U);
        uint32_t address = *zvrt_reg(banks[i].base + 0x10U);
        uint32_t *row = live_view_samples[i];
        if (live_view_polls == 0U) {
            live_view_initial[i][0] = control;
            live_view_initial[i][1] = status;
            live_view_initial[i][2] = address;
        } else {
            if (row[0] != control || row[1] != status || row[2] != address)
                if (row[3] != UINT32_MAX) ++row[3];
            if (row[2] != address)
                if (row[4] != UINT32_MAX) ++row[4];
        }
        row[0] = control;
        row[1] = status;
        row[2] = address;
    }
    /* Keep zero reserved for the first sample even after counter saturation. */
    if (live_view_polls != UINT32_MAX) ++live_view_polls;
}

static void hex_word(char *dst, uint32_t value) {
    static const char digits[] = "0123456789ABCDEF";
    for (uint32_t i = 0; i < 8U; ++i)
        dst[i] = digits[(value >> (28U - i * 4U)) & 15U];
}

void live_view_draw(uint16_t *fb, int frozen) {
    zvrt_fill_rect(fb, 0, 0, ZVRT_WIDTH, ZVRT_HEIGHT, 0x002FU);
    zvrt_draw_text(fb, 16, 16, "LIVE VIEW - REGISTER DIAGNOSTICS", 0xFFFFU, 0, 2);
    zvrt_draw_text(fb, 16, 48, "Post-takeover samples; sensor start pending", 0xFF0FU, 0, 1);
    zvrt_draw_text(fb, 16, 72, "BANK      CONTROL  STATUS   ADDRESS  CHANGES  ADDR-CHG", 0x0FFFU, 0, 1);
    for (uint32_t i = 0; i < BANK_COUNT; ++i) {
        char words[45];
        for (uint32_t j = 0; j < 5U; ++j) {
            hex_word(words + j * 9U, live_view_samples[i][j]);
            words[j * 9U + 8U] = ' ';
        }
        words[44] = '\0';
        uint32_t y = 96U + i * 28U;
        zvrt_draw_text(fb, 16, y, banks[i].name, 0xFFFFU, 0, 1);
        zvrt_draw_text(fb, 96, y, words, 0xCCCFU, 0, 1);
    }
    zvrt_draw_text(fb, 16, 392, frozen ? "OK: Resume sampling" : "OK: Freeze sampling", 0xFFFFU, 0, 2);
    zvrt_draw_text(fb, 16, 424, "Address changes do not prove frame completion.", 0xFF0FU, 0, 1);
    zvrt_draw_text(fb, 16, 448, "No sensor buffer read. Battery removal returns to stock.", 0xCCCFU, 0, 1);
}

void rtos_main(struct zvrt_handoff *handoff) {
    uint32_t front = ZVRT_DISPLAY_PA, back = front + ZVRT_FRAME_BYTES;
    int frozen = 0;
    /* Save before display_init drains inherited video AIF channels. */
    live_view_sample();
    live_view_draw(zvrt_ddr0_va(front), frozen);
    zvrt_dsb();
    if (zvrt_display_init(front) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(8U);
    }
    zvrt_input_init();
    handoff->result = ZVRT_PROBE_OK;
    for (;;) {
        struct zvrt_keys keys;
        zvrt_poll_keys(&keys);
        if (keys.pressed & ZVRT_KEY_OK) frozen = !frozen;
        if (!frozen) live_view_sample();
        live_view_draw(zvrt_ddr0_va(back), frozen);
        zvrt_dsb();
        /* Preserve both buffers on timeout; never repaint pending scanout. */
        while (zvrt_display_flip(back, 30000U) != 0) {}
        uint32_t old_front = front;
        front = back;
        back = old_front;
    }
}

/* SPDX-License-Identifier: GPL-2.0 */
/* Live bare-metal GPIO (G00..G23, high-speed polled) + ADC0/1 probe on 640x480 LCD. */
#include "zvrt_runtime.h"

#define GPIO_BASE 0xF2910000U
#define ADC0_BASE 0xF2406000U
#define ADC1_BASE 0xF2407000U
#define OSD0_BASE 0xF3441300U
#define NUM_BANKS 24U

static void fmt_hex8(char *dst, uint32_t v) {
    static const char hex[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; i--) {
        dst[i] = hex[v & 0xFU];
        v >>= 4;
    }
    dst[8] = '\0';
}

static void fmt_hex3(char *dst, uint32_t v) {
    static const char hex[] = "0123456789ABCDEF";
    dst[0] = hex[(v >> 8) & 0x3U];
    dst[1] = hex[(v >> 4) & 0xFU];
    dst[2] = hex[v & 0xFU];
    dst[3] = '\0';
}

static uint16_t adc_read_ch(uint32_t base, uint32_t ch) {
    volatile uint16_t *r = (volatile uint16_t *)(uintptr_t)base;
    r[0x44U / 2U] = (0xFEU << 8) | 0x03U;
    r[0x00U / 2U] = (uint16_t)(1U << ch);
    r[0x48U / 2U] = 0x2FU;
    r[0x0CU / 2U] = 0U;
    r[0x08U / 2U] = 1U;
    r[0x04U / 2U] = 1U;
    zvrt_delay_ticks(2U);
    uint32_t spins = 10000U;
    while ((r[0x10U / 2U] & 0x11U) && --spins) {
    }
    return r[(0x14U + ch * 4U) / 2U] & 0x3FFU;
}

void rtos_main(struct zvrt_handoff *handoff) {
    uint32_t front_pa = ZVRT_DISPLAY_PA;
    uint32_t back_pa = front_pa + ZVRT_FRAME_BYTES;
    zvrt_fill_rect(zvrt_ddr0_va(front_pa), 0, 0, ZVRT_WIDTH, ZVRT_HEIGHT, 0x000FU);
    zvrt_dsb();
    if (zvrt_display_init(front_pa) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(8U);
    }
    handoff->result = ZVRT_PROBE_OK;

    uint32_t base_val[NUM_BANKS];
    uint32_t frame_diff[NUM_BANKS];
    uint32_t sticky_diff[NUM_BANKS];
    for (uint32_t b = 0; b < NUM_BANKS; b++) {
        base_val[b] = *zvrt_reg(GPIO_BASE + (b << 8) + 0x10U);
        frame_diff[b] = 0U;
        sticky_diff[b] = 0U;
    }

    uint16_t adc_base[16];
    for (uint32_t i = 0; i < 8U; i++) {
        adc_base[i] = adc_read_ch(ADC0_BASE, i);
        adc_base[8U + i] = adc_read_ch(ADC1_BASE, i);
    }

    char line[32];
    int led = 0;
    uint32_t ticks = 0;
    volatile uint32_t *osd = zvrt_reg(OSD0_BASE);

    for (;;) {
        uint16_t *fb = zvrt_ddr0_va(back_pa);
        zvrt_fill_rect(fb, 0, 0, ZVRT_WIDTH, ZVRT_HEIGHT, 0x001FU);
        zvrt_draw_text(fb, 24U, 72U, "GPIO(0..23) + ADC0/1 PROBE", 0xFFFFU, 0U, 2U);

        for (uint32_t b = 0; b < NUM_BANKS; b++) {
            uint32_t cur = *zvrt_reg(GPIO_BASE + (b << 8) + 0x10U);
            uint32_t diff = frame_diff[b] | (cur ^ base_val[b]);
            sticky_diff[b] |= diff;
            frame_diff[b] = 0U;

            line[0] = 'G';
            line[1] = (char)('0' + (b / 10U));
            line[2] = (char)('0' + (b % 10U));
            line[3] = ':';
            fmt_hex8(line + 4, diff ? diff : sticky_diff[b]);
            line[12] = '\0';

            uint32_t col_x = 24U + (b / 8U) * 200U;
            uint32_t row_y = 100U + (b & 7U) * 22U;
            uint16_t fg = diff ? 0x0F0FU : (sticky_diff[b] ? 0xFF0FU : 0xCCCFU);
            zvrt_draw_text(fb, col_x, row_y, line, fg, 0U, 2U);
        }

        for (uint32_t u = 0; u < 2U; u++) {
            uint32_t base = (u == 0U) ? ADC0_BASE : ADC1_BASE;
            for (uint32_t ch = 0; ch < 8U; ch++) {
                uint16_t val = adc_read_ch(base, ch);
                int32_t delta = (int32_t)val - (int32_t)adc_base[u * 8U + ch];
                if (delta < 0) delta = -delta;
                uint16_t fg = (delta > 8) ? 0x0F0FU : 0x0FFFU;

                line[0] = u ? 'B' : 'A';
                line[1] = (char)('0' + ch);
                line[2] = ':';
                fmt_hex3(line + 3, val);
                line[6] = '\0';
                uint32_t col_x = 24U + (ch & 3U) * 148U;
                uint32_t row_y = 292U + (u * 2U + (ch >> 2)) * 26U;
                zvrt_draw_text(fb, col_x, row_y, line, fg, 0U, 2U);
            }
        }

        zvrt_dsb();
        /* Poll GPIO continuously while waiting for VSYNC so fast wheel edges are caught. */
        uint32_t spins = 20000000U;
        while (osd[0] != 2U && --spins) {
            for (uint32_t b = 0; b < NUM_BANKS; b++) {
                frame_diff[b] |= (*zvrt_reg(GPIO_BASE + (b << 8) + 0x10U)) ^ base_val[b];
            }
        }
        osd[0x20 / 4U] = back_pa;
        zvrt_dsb();
        osd[0] = 3U;
        zvrt_dsb();

        uint32_t tmp = front_pa;
        front_pa = back_pa;
        back_pa = tmp;

        ticks++;
        if ((ticks & 15U) == 0U) {
            led ^= 1;
            zvrt_led_set(led);
        }
    }
}

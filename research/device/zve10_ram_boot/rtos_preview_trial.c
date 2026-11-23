/* SPDX-License-Identifier: GPL-2.0 */
#include "zvrt_runtime.h"

/* Trial for the captured stock YUV1 configuration. OSD0 wrap is a sampling
 * clock. It conveys no ownership of the YUV1 producer's buffer. */
#define YUV1 0xf3441200U
#define OSD0_CURRENT 0xf3441310U
#define FOPD_W0_CURRENT 0xf3020290U
#define SOURCE_PA 0x16a00000U
#define SOURCE_PITCH 1152U
#define SOURCE_ROWS 570U
#define SOURCE_FETCH 1024U
#define SOURCE_SPAN ((SOURCE_ROWS - 1U) * SOURCE_PITCH + SOURCE_FETCH)
#define SAMPLE_W 80U
#define SAMPLE_H 54U

static uint8_t samples[2][SAMPLE_W * SAMPLE_H];
static const char *outcome;
static uint32_t osd_wraps, yuv_moved, fopd_moved;

static int expected_source(void) {
    return *zvrt_reg(YUV1 + 0x20U) == SOURCE_PA &&
           *zvrt_reg(YUV1 + 0x24U) == SOURCE_FETCH &&
           *zvrt_reg(YUV1 + 0x28U) == SOURCE_PITCH - SOURCE_FETCH &&
           *zvrt_reg(YUV1 + 0x2cU) == SOURCE_ROWS - 1U;
}

static void wait_sample_clock(void) {
    uint32_t start = zvrt_timer_ticks();
    uint32_t previous = *zvrt_reg(OSD0_CURRENT);
    uint32_t yuv_initial = *zvrt_reg(YUV1 + 0x10U);
    uint32_t fopd_initial = *zvrt_reg(FOPD_W0_CURRENT);
    for (uint32_t spin = 0; spin < 4000000U; ++spin) {
        uint32_t current = *zvrt_reg(OSD0_CURRENT);
        yuv_moved |= *zvrt_reg(YUV1 + 0x10U) != yuv_initial;
        fopd_moved |= *zvrt_reg(FOPD_W0_CURRENT) != fopd_initial;
        if (current && current < previous && previous - current > ZVRT_PITCH) {
            ++osd_wraps;
            return;
        }
        previous = current;
        if ((uint32_t)(zvrt_timer_ticks() - start) >= 200000U) break;
    }
    /* The timer fallback still tests for a retained image if scanout stopped. */
}

static int capture(uint8_t *sample) {
    if (!expected_source()) return -1;
    wait_sample_clock();
    if (!expected_source()) return -1;
    const volatile uint8_t *source = (const volatile uint8_t *)zvrt_ddr0_va(SOURCE_PA);
    zvrt_dcache_inv((const void *)source, SOURCE_SPAN);
    for (uint32_t y = 0; y < SAMPLE_H; ++y) {
        for (uint32_t x = 0; x < SAMPLE_W; ++x) {
            /* Try the even-byte luma position in a packed 4:2:2 stream. */
            sample[y * SAMPLE_W + x] = source[(y * 10U + 5U) * SOURCE_PITCH + x * 12U + 6U];
        }
    }
    return expected_source() ? 0 : -1;
}

static void render(uint16_t *frame) {
    int first = capture(samples[0]);
    int second = first ? first : capture(samples[1]);
    int changed = 0;
    zvrt_fill_rect(frame, 0, 0, ZVRT_WIDTH, ZVRT_HEIGHT, 0x000f);
    if (!second) {
        for (uint32_t i = 0; i < SAMPLE_W * SAMPLE_H; ++i)
            changed |= samples[0][i] != samples[1][i];
    }
    if (!first) {
        uint8_t *sample = samples[second ? 0 : 1];
        for (uint32_t y = 0; y < SAMPLE_H; ++y) {
            for (uint32_t x = 0; x < SAMPLE_W; ++x) {
                uint32_t level = sample[y * SAMPLE_W + x] >> 4;
                zvrt_fill_rect(frame, x * 8U, y * 8U, 8U, 8U, (uint16_t)(level * 0x1110U | 15U));
            }
        }
    }
    if (second == -1) outcome = "YUV1 geometry or address mismatch";
    else outcome = changed ? "Two different YUV1 samples" : "Two identical YUV1 samples";
    char motion[] = "OSD wraps: 0  YUV moved: 0  FOPD moved: 0";
    motion[11] = (char)('0' + osd_wraps);
    motion[25] = (char)('0' + yuv_moved);
    motion[40] = (char)('0' + fopd_moved);
    zvrt_draw_text(frame, 8, 436, outcome, 0xffff, 0, 1);
    zvrt_draw_text(frame, 8, 449, motion, 0xffff, 0, 1);
    zvrt_draw_text(frame, 8, 462, "Guessed luma format | OSD wrap or timer", 0xffff, 0, 1);
}

void rtos_main(struct zvrt_handoff *handoff) {
    uint16_t *frame = zvrt_ddr0_va(ZVRT_DISPLAY_PA);
    render(frame);
    zvrt_dsb();
    if (zvrt_display_init(ZVRT_DISPLAY_PA) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(8U);
    }
    handoff->result = ZVRT_PROBE_OK;
    for (;;) zvrt_display_wait(ZVRT_DISPLAY_PA, 200000U);
}

/* SPDX-License-Identifier: GPL-2.0 */
/* ZVOS bare-metal shell: GIC IRQ dispatch, mode switching, font UI, Fire & Bad Apple modes. */
#include "os_mode.h"
#include "bayer_display.h"
#include "bayer_probe.h"
#include "bayer_capture.h"

#define FIRE_W 80U
#define FIRE_H 60U
#define ZVBA_MAGIC 0x4142565AU
#define DISPLAY_REFRESH_HZ 50U

struct zvba_header {
    uint32_t magic;
    uint16_t width;
    uint16_t height;
    uint32_t fps;
    uint32_t frame_count;
};

static volatile uint32_t gic_test_irqs = 0;

static void on_test_irq(uint32_t irq, void *ctx) {
    (void)irq;
    (void)ctx;
    gic_test_irqs++;
}

/* --- Mode 0: System Status / Launcher --- */
static uint32_t menu_sel = 0;
static int has_clip = 0;
static uint32_t next_mode_idx = 1U;

static void fmt_adc3(char *dst, int v) {
    static const char hex[] = "0123456789ABCDEF";
    if (v == -1) { dst[0] = 'B'; dst[1] = 'S'; dst[2] = 'Y'; dst[3] = '\0'; return; }
    if (v < 0) { dst[0] = 'T'; dst[1] = 'M'; dst[2] = 'O'; dst[3] = '\0'; return; }
    dst[0] = hex[((uint32_t)v >> 8) & 3U];
    dst[1] = hex[((uint32_t)v >> 4) & 0xFU];
    dst[2] = hex[(uint32_t)v & 0xFU];
    dst[3] = '\0';
}

static void draw_input_diag(uint16_t *fb, uint32_t y) {
    char buf[20];
    buf[0] = 'B'; buf[1] = '0'; buf[2] = ':';
    fmt_adc3(buf + 3, zvrt_adc_last(0U));
    buf[6] = ' '; buf[7] = 'B'; buf[8] = '3'; buf[9] = ':';
    fmt_adc3(buf + 10, zvrt_adc_last(3U));
    zvrt_draw_text(fb, 32U, y, buf, 0x0FFFU, 0x000FU, 2U);
}

static int status_enter(const struct zvrt_handoff *handoff) {
    const struct zvba_header *hdr = (const struct zvba_header *)ZVRT_CLIP_ADDR;
    has_clip = (handoff->clip_bytes >= sizeof(*hdr) && hdr->magic == ZVBA_MAGIC && hdr->frame_count > 0U);
    void *scratch = zvrt_mode_alloc(4096U, 64U);
    void *dma_buf = zvrt_dma_alloc(4096U, 64U);
    return (scratch && dma_buf) ? 0 : -1;
}
static enum os_tick_result status_tick(uint32_t keys_pressed, uint16_t *fb) {
    if (keys_pressed & (ZVRT_KEY_UP | ZVRT_KEY_LEFT)) {
        menu_sel = (menu_sel == 0U) ? 3U : (menu_sel - 1U);
    }
    if (keys_pressed & (ZVRT_KEY_DOWN | ZVRT_KEY_RIGHT)) {
        menu_sel = (menu_sel == 3U) ? 0U : (menu_sel + 1U);
    }
    zvrt_fill_rect(fb, 0, 0, ZVRT_WIDTH, ZVRT_HEIGHT, 0x002FU);
    zvrt_fill_rect(fb, 0, 0, ZVRT_WIDTH, 64U, 0x124FU);
    zvrt_draw_text(fb, 32U, 36U, "ZVOS v0.1 - Sony ZV-E10", 0xFFFFU, 0U, 2U);
    zvrt_draw_text(fb, 32U, 88U, (menu_sel == 0U) ? "> 1. Procedural Fire" : "  1. Procedural Fire",
                   (menu_sel == 0U) ? 0xFF0FU : 0xCCCFU, 0U, 2U);
    zvrt_draw_text(fb, 32U, 120U, (menu_sel == 1U) ? "> 2. Bad Apple!!" : "  2. Bad Apple!!",
                   has_clip ? ((menu_sel == 1U) ? 0xFF0FU : 0xCCCFU) : 0x666FU, 0U, 2U);
    zvrt_draw_text(fb, 32U, 152U, (menu_sel == 2U) ? "> 3. Live Bayer RAW" : "  3. Live Bayer RAW",
                   (menu_sel == 2U) ? 0xFF0FU : 0xCCCFU, 0U, 2U);
    zvrt_draw_text(fb, 32U, 184U, (menu_sel == 3U) ? "> 4. Bayer Probe" : "  4. Bayer Probe",
                   (menu_sel == 3U) ? 0xFF0FU : 0xCCCFU, 0U, 2U);
    zvrt_draw_text(fb, 32U, 228U, "ARROWS: Select  OK: Launch", 0x0FFFU, 0U, 2U);
    zvrt_draw_text(fb, 32U, 256U, "DELETE: Exit mode", 0x0FFFU, 0U, 2U);
    draw_input_diag(fb, 300U);
    if (keys_pressed & ZVRT_KEY_OK) {
        if (menu_sel == 0U) {
            next_mode_idx = 1U;
            return OS_TICK_EXIT;
        }
        if (menu_sel == 1U && has_clip) {
            next_mode_idx = 2U;
            return OS_TICK_EXIT;
        }
        if (menu_sel == 2U) {
            next_mode_idx = 3U;
            return OS_TICK_EXIT;
        }
        if (menu_sel == 3U) {
            next_mode_idx = 4U;
            return OS_TICK_EXIT;
        }
    }
    return OS_TICK_DRAW;
}
static void status_exit(void) {}
static const struct os_mode mode_status = { "Status", status_enter, status_tick, status_exit };

/* --- Mode 1: Procedural Fire --- */
static const uint16_t fire_palette[16] = {
    0x000F, 0x200F, 0x400F, 0x600F, 0x810F, 0xA10F, 0xC20F, 0xE30F,
    0xF40F, 0xF50F, 0xF70F, 0xF90F, 0xFB1F, 0xFD4F, 0xFF9F, 0xFFFF,
};
static uint8_t *fire_heat = NULL;
static uint32_t fire_seed = 0x5AD0C0DEU;
static uint32_t fire_frames = 0;

static void step_fire(void) {
    uint32_t r = fire_seed;
    for (uint32_t y = 0; y < FIRE_H - 1U; y++) {
        uint8_t *dst = fire_heat + y * FIRE_W;
        const uint8_t *src = dst + FIRE_W;
        for (uint32_t x = 1; x < FIRE_W - 1U; x++) {
            uint32_t v = ((uint32_t)src[x] * 2U + src[x - 1U] + src[x + 1U]) >> 2;
            r ^= r << 13; r ^= r >> 17; r ^= r << 5;
            if (v > 0U && (r & 3U) == 0U) {
                v--;
            }
            dst[x] = (uint8_t)v;
        }
    }
    uint8_t *bot = fire_heat + (FIRE_H - 1U) * FIRE_W;
    for (uint32_t x = 1; x < FIRE_W - 1U; x++) {
        r = r * 1664525U + 1013904223U;
        bot[x] = (uint8_t)(11U + ((r >> 29) % 5U));
    }
    fire_seed = r;
}

static int fire_enter(const struct zvrt_handoff *handoff) {
    (void)handoff;
    fire_heat = (uint8_t *)zvrt_mode_alloc(FIRE_W * FIRE_H, 64U);
    if (!fire_heat) {
        return -1;
    }
    for (uint32_t i = 0; i < FIRE_W * FIRE_H; i++) {
        fire_heat[i] = 0U;
    }
    fire_frames = 0;
    for (uint32_t i = 0; i < 24U; i++) {
        step_fire();
    }
    return 0;
}

static enum os_tick_result fire_tick(uint32_t keys_pressed, uint16_t *fb) {
    (void)keys_pressed;
    step_fire();
    uint32_t *fb32 = (uint32_t *)fb;
    for (uint32_t hy = 0; hy < FIRE_H; hy++) {
        for (uint32_t sub = 0; sub < 8U; sub++) {
            for (uint32_t hx = 0; hx < FIRE_W; hx++) {
                uint16_t c = fire_palette[fire_heat[hy * FIRE_W + hx] & 15U];
                uint32_t pair = (uint32_t)c | ((uint32_t)c << 16);
                fb32[0] = pair; fb32[1] = pair; fb32[2] = pair; fb32[3] = pair;
                fb32 += 4;
            }
        }
    }
    zvrt_draw_text(fb, 32U, 36U, "MODE: FIRE (DELETE=EXIT)", 0xFFFFU, 0U, 2U);
    draw_input_diag(fb, 440U);
    fire_frames++;
    return (keys_pressed & (ZVRT_KEY_MENU | ZVRT_KEY_DELETE)) ? OS_TICK_EXIT : OS_TICK_DRAW;
}

static void fire_exit(void) { fire_heat = NULL; }
static const struct os_mode mode_fire = { "Fire", fire_enter, fire_tick, fire_exit };

/* --- Mode 2: Bad Apple!! --- */
static const struct zvba_header *ba_hdr = NULL;
static const uint8_t *ba_ptr = NULL;
static const uint8_t *ba_end = NULL;
static uint8_t *ba_shadow = NULL;
static uint32_t ba_shadow_bytes = 0;
static uint32_t ba_frame = 0;
static uint32_t ba_fps;
static uint32_t ba_phase;

static int bad_apple_enter(const struct zvrt_handoff *handoff) {
    ba_hdr = (const struct zvba_header *)ZVRT_CLIP_ADDR;
    if (handoff->clip_bytes < sizeof(*ba_hdr) || ba_hdr->magic != ZVBA_MAGIC || ba_hdr->frame_count == 0U) {
        return -1;
    }
    ba_shadow_bytes = ((uint32_t)ba_hdr->width * (uint32_t)ba_hdr->height) / 8U;
    ba_shadow = (uint8_t *)zvrt_mode_alloc(ba_shadow_bytes, 64U);
    if (!ba_shadow) {
        return -1;
    }
    for (uint32_t i = 0; i < ba_shadow_bytes; i++) {
        ba_shadow[i] = 0U;
    }
    ba_ptr = (const uint8_t *)(ba_hdr + 1);
    ba_end = (const uint8_t *)ZVRT_CLIP_ADDR + handoff->clip_bytes;
    ba_frame = 0;
    ba_fps = ba_hdr->fps;
    if (ba_fps == 0U || ba_fps > DISPLAY_REFRESH_HZ) {
        ba_fps = 24U; /* Match the standalone player's fallback. */
    }
    ba_phase = DISPLAY_REFRESH_HZ - ba_fps;
    return 0;
}

static enum os_tick_result bad_apple_tick(uint32_t keys_pressed, uint16_t *fb) {
    if (keys_pressed & (ZVRT_KEY_MENU | ZVRT_KEY_DELETE)) {
        return OS_TICK_EXIT;
    }
    /* One tick per scanout. Keep the fractional phase across clip loops. */
    ba_phase += ba_fps;
    if (ba_phase < DISPLAY_REFRESH_HZ) {
        return OS_TICK_HOLD;
    }
    ba_phase -= DISPLAY_REFRESH_HZ;
    if (ba_frame >= ba_hdr->frame_count || ba_ptr + 4U > ba_end) {
        ba_frame = 0;
        ba_ptr = (const uint8_t *)(ba_hdr + 1);
        for (uint32_t i = 0; i < ba_shadow_bytes; i++) {
            ba_shadow[i] = 0U;
        }
    }
    uint32_t len = *(const uint32_t *)ba_ptr;
    ba_ptr += 4U;
    uint32_t pos = 0, i = 0;
    while (i < len && pos < ba_shadow_bytes) {
        uint8_t ctrl = ba_ptr[i++];
        if (ctrl & 0x80U) {
            uint32_t cnt = (uint32_t)(ctrl & 0x7FU) + 2U;
            uint8_t val = ba_ptr[i++];
            if (pos + cnt > ba_shadow_bytes) cnt = ba_shadow_bytes - pos;
            if (val) { for (uint32_t k = 0; k < cnt; k++) ba_shadow[pos++] ^= val; }
            else { pos += cnt; }
        } else {
            uint32_t cnt = (uint32_t)ctrl + 1U;
            if (pos + cnt > ba_shadow_bytes) cnt = ba_shadow_bytes - pos;
            for (uint32_t k = 0; k < cnt; k++) ba_shadow[pos++] ^= ba_ptr[i++];
        }
    }
    ba_ptr += (len + 3U) & ~3U;

    uint32_t *fb32 = (uint32_t *)fb;
    uint32_t row_bytes = ba_hdr->width / 8U;
    uint32_t scale = (ba_hdr->width == 320U) ? 2U : 1U;
    for (uint32_t y = 0; y < ba_hdr->height; y++) {
        for (uint32_t sy = 0; sy < scale; sy++) {
            for (uint32_t bx = 0; bx < row_bytes; bx++) {
                uint8_t b = ba_shadow[y * row_bytes + bx];
                for (uint32_t bit = 0; bit < 8U; bit++) {
                    uint16_t px = (b & (0x80U >> bit)) ? 0xFFFFU : 0x000FU;
                    uint32_t pair = (uint32_t)px | ((uint32_t)px << 16);
                    if (scale == 2U) {
                        *fb32++ = pair;
                    } else {
                        ((uint16_t *)fb32)[0] = px;
                        fb32 = (uint32_t *)((uint16_t *)fb32 + 1);
                    }
                }
            }
        }
    }
    ba_frame++;
    return OS_TICK_DRAW;
}

static void bad_apple_exit(void) { ba_shadow = NULL; }
static const struct os_mode mode_bad_apple = { "BadApple", bad_apple_enter, bad_apple_tick, bad_apple_exit };

/* --- Mode 3: Repeated IMX284 still RAW through ISP0 AIF --- */
static struct bayer_capture_state bayer_cap;
static uint32_t bayer_shift;
static uint32_t bayer_frames;
static int bayer_stopping;
static const char *bayer_error;

static struct {
    struct bayer_writer_sample writer;
    uint32_t writer_error;
    uint32_t slvs_monitor;
    uint32_t slvs_status;
    uint32_t sgc0;
    uint32_t sgc2;
    uint32_t isp_normal;
    uint32_t isp_alternate;
    int valid;
} bayer_timeout;

static void fmt_hex8(char *dst, uint32_t val) {
    static const char hex[] = "0123456789ABCDEF";
    for (uint32_t i = 0U; i < 8U; ++i) {
        dst[i] = hex[(val >> (28U - i * 4U)) & 15U];
    }
    dst[8] = '\0';
}

static void fmt_hex4(char *dst, uint32_t val) {
    static const char hex[] = "0123456789ABCDEF";
    for (uint32_t i = 0U; i < 4U; ++i) {
        dst[i] = hex[(val >> (12U - i * 4U)) & 15U];
    }
    dst[4] = '\0';
}

static void fmt_dec2(char *dst, uint32_t val) {
    dst[0] = (char)('0' + ((val / 10U) % 10U));
    dst[1] = (char)('0' + (val % 10U));
    dst[2] = '\0';
}

/* Format a 2-character tag plus three 32-bit hex registers for the Bayer HUD. */
static void fmt_hud_regs(char *out, char c0, char c1, uint32_t a, uint32_t b, uint32_t c) {
    out[0] = c0;
    out[1] = c1;
    out[2] = ':';
    fmt_hex8(out + 3, a);
    out[11] = ' ';
    fmt_hex8(out + 12, b);
    out[20] = ' ';
    fmt_hex8(out + 21, c);
}

static int bayer_enter(const struct zvrt_handoff *handoff) {
    (void)handoff;
    bayer_shift = 10U;
    bayer_frames = 0U;
    bayer_stopping = 0;
    bayer_timeout.valid = 0;
    bayer_error = bayer_capture_start(&bayer_cap) == 0 ? NULL : "ISP0 RAW ARM FAILED";
    return 0;
}

static enum os_tick_result bayer_tick(uint32_t keys_pressed, uint16_t *fb) {
    if (keys_pressed & (ZVRT_KEY_MENU | ZVRT_KEY_DELETE)) {
        bayer_stopping = 1;
    }
    if (bayer_stopping) {
        if (bayer_capture_stop(&bayer_cap) == 0) {
            return OS_TICK_EXIT;
        }
        zvrt_fill_rect(fb, 0U, 0U, ZVRT_WIDTH, ZVRT_HEIGHT, 0x000FU);
        zvrt_draw_text(fb, 12U, 8U, "RAW DMA STILL BUSY", 0xFFFFU, 0x000FU, 2U);
        return OS_TICK_DRAW;
    }
    if (keys_pressed & ZVRT_KEY_UP) {
        bayer_shift = (bayer_shift == 8U) ? 10U : (bayer_shift == 10U) ? 12U : 8U;
    }
    if (keys_pressed & ZVRT_KEY_DOWN) {
        bayer_shift = (bayer_shift == 8U) ? 12U : (bayer_shift == 12U) ? 10U : 8U;
    }

    struct bayer_frame frame = {
        zvrt_ddr0_va(ZVRT_STILL_RAW_PA),
        BAYER_STILL_WIDTH,
        BAYER_STILL_HEIGHT,
        BAYER_STILL_WIDTH,
    };
    int frame_ready = !bayer_error && bayer_capture_complete(&bayer_cap);
    if (!frame_ready && !bayer_error &&
        zvrt_timer_ticks() - bayer_cap.armed_at >= BAYER_STILL_TIMEOUT) {
        bayer_timeout.writer = bayer_read_writer(BAYER_ISP0_WRITE);
        bayer_timeout.writer_error = *zvrt_reg(BAYER_ISP0_WRITE + 8U);
        bayer_timeout.slvs_monitor = *zvrt_reg(0xfc0f00acU);
        bayer_timeout.slvs_status = *zvrt_reg(0xfc0f00b0U);
        bayer_timeout.sgc0 = *zvrt_reg(0xfc0a1110U);
        bayer_timeout.sgc2 = *zvrt_reg(0xfc0a1310U);
        bayer_timeout.isp_normal = *zvrt_reg(0xf3120048U);
        bayer_timeout.isp_alternate = *zvrt_reg(0xf312004cU);
        bayer_timeout.valid = 1;
        bayer_error = bayer_cap.busy_seen ? "ISP0 DMA INCOMPLETE" : "ISP0 DMA NOT OBSERVED";
        bayer_capture_stop(&bayer_cap);
    }
    if (!frame_ready && bayer_frames && !bayer_error) {
        return OS_TICK_HOLD;
    }
    if (frame_ready) {
        bayer_resize_lcd_shifted(fb, &frame, bayer_shift);
        ++bayer_frames;
    } else {
        zvrt_fill_rect(fb, 0U, 0U, ZVRT_WIDTH, ZVRT_HEIGHT, 0x000FU);
        zvrt_draw_text(fb, 12U, 116U, bayer_error ? bayer_error : "WAITING FOR FIRST RAW FRAME",
                       0xFFFFU, 0x000FU, 2U);
    }

    char diag[30];
    if (bayer_timeout.valid) {
        fmt_hud_regs(diag, 'D', 'M', bayer_timeout.writer.control, bayer_timeout.writer.status,
                     bayer_cap.max_offset);
        zvrt_draw_text(fb, 12U, 136U, diag, 0x0FFFU, 0x000FU, 2U);
        fmt_hud_regs(diag, 'R', 'X', bayer_timeout.slvs_monitor, bayer_timeout.slvs_status,
                     bayer_timeout.sgc0);
        zvrt_draw_text(fb, 12U, 156U, diag, 0x0FFFU, 0x000FU, 2U);
        fmt_hud_regs(diag, 'I', 'Q', bayer_timeout.sgc2, bayer_timeout.isp_normal,
                     bayer_timeout.isp_alternate);
        zvrt_draw_text(fb, 12U, 176U, diag, 0x0FFFU, 0x000FU, 2U);
        fmt_hud_regs(diag, 'W', 'R', bayer_timeout.writer.current, bayer_timeout.writer_error,
                     bayer_cap.seq_timeouts);
        zvrt_draw_text(fb, 12U, 196U, diag, 0x0FFFU, 0x000FU, 2U);
        zvrt_draw_text(fb, 12U, 456U, "DEL:EXIT", 0xFF0FU, 0x000FU, 2U);
        return OS_TICK_DRAW;
    }

    uint32_t w0_stat = *zvrt_reg(BAYER_ISP0_WRITE + 4U);
    uint32_t w0_cur = *zvrt_reg(BAYER_ISP0_WRITE + 0x10U);
    char hud1[28];
    hud1[0] = 'W'; hud1[1] = '0'; hud1[2] = ':';
    fmt_hex8(hud1 + 3, w0_stat);
    hud1[11] = ' '; hud1[12] = 'C'; hud1[13] = ':';
    fmt_hex8(hud1 + 14, w0_cur);

    char hud2[28];
    hud2[0] = 'I'; hud2[1] = ':';
    fmt_dec2(hud2 + 2, bayer_cap.seq_irqs);
    hud2[4] = ' '; hud2[5] = 'T'; hud2[6] = ':';
    fmt_dec2(hud2 + 7, bayer_cap.seq_timeouts);
    hud2[9] = ' '; hud2[10] = 'M'; hud2[11] = ':';
    fmt_hex4(hud2 + 12, bayer_frames);
    hud2[16] = ' ';
    fmt_dec2(hud2 + 17, bayer_shift + 4U);
    hud2[19] = 'b'; hud2[20] = '\0';

    zvrt_draw_text(fb, 12U, 8U, hud1, 0xFFFFU, 0x000FU, 2U);
    zvrt_draw_text(fb, 12U, 28U, hud2, 0x0FFFU, 0x000FU, 2U);
    fmt_hud_regs(diag, 'S', 'Q', *zvrt_reg(0xfc088300U), *zvrt_reg(0xfc088e00U), *zvrt_reg(0xfc088f04U));
    zvrt_draw_text(fb, 12U, 48U, diag, 0x0FFFU, 0x000FU, 2U);
    fmt_hud_regs(diag, 'S', 'L', *zvrt_reg(0xfc0f0000U), *zvrt_reg(0xfc0f0050U), *zvrt_reg(0xfc029028U));
    zvrt_draw_text(fb, 12U, 68U, diag, 0x0FFFU, 0x000FU, 2U);
    fmt_hud_regs(diag, 'D', 'F', *zvrt_reg(0xfc0a0010U), *zvrt_reg(0xfc0a1310U),
                 *zvrt_reg(BAYER_ISP0_WRITE + 8U));
    zvrt_draw_text(fb, 12U, 88U, diag, 0x0FFFU, 0x000FU, 2U);
    zvrt_draw_text(fb, 12U, 456U, "UP/DN:BITS DEL:EXIT", 0xFF0FU, 0x000FU, 2U);
    if (frame_ready) {
        /* The CPU has finished reading RAW before the writer can reuse it. */
        if (bayer_capture_rearm(&bayer_cap) != 0) {
            bayer_error = "ISP0 RAW REARM FAILED";
            bayer_capture_stop(&bayer_cap);
        }
    }
    return OS_TICK_DRAW;
}

static void bayer_exit(void) {}

static const struct os_mode mode_bayer = { "BayerRAW", bayer_enter, bayer_tick, bayer_exit };

/* --- Mode 4: Bayer RAW DMA Probe --- */
static struct bayer_writer_observation bp_writer, bp_reader;
static uint32_t bp_polls = 0;

static int bayer_probe_enter(const struct zvrt_handoff *handoff) {
    (void)handoff;
    bayer_reset_observation(&bp_writer, BAYER_ISP0_WRITE);
    bayer_reset_observation(&bp_reader, BAYER_ISP1_READ);
    bp_polls = 0U;
    return 0;
}

static enum os_tick_result bayer_probe_tick(uint32_t keys_pressed, uint16_t *fb) {
    if (keys_pressed & (ZVRT_KEY_MENU | ZVRT_KEY_DELETE)) {
        return OS_TICK_EXIT;
    }
    if (keys_pressed & ZVRT_KEY_OK) {
        bayer_probe_enter(NULL);
    } else {
        bayer_observe_writer(&bp_writer, bayer_read_writer(BAYER_ISP0_WRITE));
        bayer_observe_writer(&bp_reader, bayer_read_writer(BAYER_ISP1_READ));
        bp_polls++;
    }
    bayer_draw_probe_screen(
        fb,
        "MODE: BAYER PROBE",
        &bp_writer,
        &bp_reader,
        bp_polls,
        "Stock still RAW DMA (hex)",
        "OK: Reset counters  DELETE: Exit"
    );
    return OS_TICK_DRAW;
}

static void bayer_probe_exit(void) {}

static const struct os_mode mode_bayer_probe = {
    "BayerProbe",
    bayer_probe_enter,
    bayer_probe_tick,
    bayer_probe_exit,
};

static const struct os_mode *const modes[] = {
    &mode_status,
    &mode_fire,
    &mode_bad_apple,
    &mode_bayer,
    &mode_bayer_probe,
};

void rtos_main(struct zvrt_handoff *handoff) {
    zvrt_irq_init();
    zvrt_irq_register(50U, on_test_irq, NULL);
    zvrt_irq_enable(50U);
    zvrt_irq_enable_all();
    zvrt_input_init();

    uint32_t front_pa = ZVRT_DISPLAY_PA;
    uint32_t back_pa = front_pa + ZVRT_FRAME_BYTES;
    zvrt_fill_rect(zvrt_ddr0_va(front_pa), 0, 0, ZVRT_WIDTH, ZVRT_HEIGHT, 0x000FU);
    zvrt_dsb();
    if (zvrt_display_init(front_pa) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(8U);
    }

    uint32_t idx = 0U;
    if (modes[idx]->enter(handoff) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(9U);
    }
    handoff->result = ZVRT_PROBE_OK;

    int led = 0;
    for (;;) {
        struct zvrt_keys keys;
        zvrt_poll_keys(&keys);

        uint16_t *fb = zvrt_ddr0_va(back_pa);
        enum os_tick_result result = modes[idx]->tick(keys.pressed, fb);
        uint32_t frame_pa = (result == OS_TICK_DRAW) ? back_pa : front_pa;
        zvrt_dsb();
        while (zvrt_display_flip(frame_pa, 30000U) != 0) {
        }
        if (result == OS_TICK_DRAW) {
            back_pa = front_pa;
            front_pa = frame_pa;
        }

        if (result == OS_TICK_EXIT) {
            modes[idx]->exit();
            zvrt_mode_reset();
            zvrt_dma_reset();
            idx = (idx == 0U) ? next_mode_idx : 0U;
            if (modes[idx]->enter(handoff) != 0) {
                idx = 0U;
                modes[idx]->enter(handoff);
            }
            led ^= 1;
            zvrt_led_set(led);
        }
    }
}

/* SPDX-License-Identifier: GPL-2.0 */
#include "zvrt_runtime.h"
#include "zvrt_font.h"

#define TIMER_READ_ADDR 0xF240310CU
#define LED_GPIO_ADDR   0xF2910000U
#define ADC0_BASE       0xF2406000U
#define ADC1_BASE       0xF2407000U
#define PL310_BASE      0xF8002000U
#define GICC_BASE       0xF8000100U
#define GICD_BASE       0xF8001000U
#define VPH_BASE        0xF3440000U
#define OSD0_BASE       0xF3441300U
#define AIF_MODE_TABLE  0x643EB19CU

#define HEAP_START      (ZVRT_DISPLAY_VA + ZVRT_DISPLAY_SIZE)
#define HEAP_END        0x98000000U

static uint32_t heap_cursor = HEAP_START;
static uint32_t dma_cursor = ZVRT_DMA_NC_VA;
static uint32_t mode_cursor = ZVRT_MODE_HEAP_VA;

struct zvrt_irq_entry {
    zvrt_irq_fn fn;
    void *ctx;
};

static struct zvrt_irq_entry irq_table[256];

uint32_t zvrt_timer_ticks(void) {
    return *zvrt_reg(TIMER_READ_ADDR);
}

void zvrt_delay_ticks(uint32_t ticks) {
    uint32_t start = zvrt_timer_ticks();
    while ((uint32_t)(zvrt_timer_ticks() - start) < ticks) {
    }
}

void zvrt_led_set(int on) {
    *zvrt_reg(LED_GPIO_ADDR + (on ? 0x44U : 0x48U)) = 1U;
}

static uint32_t va_to_ddr0_pa(uint32_t va) {
    if (va >= 0x60000000U && va < 0xA0000000U) {
        return va - 0x60000000U;
    }
    return va;
}

void zvrt_dcache_clean(const void *va, uint32_t bytes) {
    uint32_t start = (uint32_t)(uintptr_t)va & ~31U;
    uint32_t end = ((uint32_t)(uintptr_t)va + bytes + 31U) & ~31U;
    for (uint32_t p = start; p < end; p += 32U) {
        __asm__ volatile("mcr p15, 0, %0, c7, c10, 1" :: "r"(p) : "memory");
    }
    zvrt_dsb();

    if (*zvrt_reg(PL310_BASE + 0x100U) & 1U) {
        (void)va_to_ddr0_pa(start);
        *zvrt_reg(PL310_BASE + 0x7BCU) = 0xFFFFU;
        while (*zvrt_reg(PL310_BASE + 0x7BCU) & 0xFFFFU) {
        }
        *zvrt_reg(PL310_BASE + 0x730U) = 0U;
        while (*zvrt_reg(PL310_BASE + 0x730U) & 1U) {
        }
        zvrt_dsb();
    }
}

void zvrt_dcache_inv(const void *va, uint32_t bytes) {
    uint32_t start = (uint32_t)(uintptr_t)va & ~31U;
    uint32_t end = ((uint32_t)(uintptr_t)va + bytes + 31U) & ~31U;
    if (*zvrt_reg(PL310_BASE + 0x100U) & 1U) {
        uint32_t pa = va_to_ddr0_pa(start);
        uint32_t pa_end = pa + (end - start);
        for (uint32_t p = pa; p < pa_end; p += 32U) {
            *zvrt_reg(PL310_BASE + 0x770U) = p;
        }
        *zvrt_reg(PL310_BASE + 0x730U) = 0U;
        while (*zvrt_reg(PL310_BASE + 0x730U) & 1U) {
        }
        zvrt_dsb();
    }
    for (uint32_t p = start; p < end; p += 32U) {
        __asm__ volatile("mcr p15, 0, %0, c7, c6, 1" :: "r"(p) : "memory");
    }
    zvrt_dsb();
}

void *zvrt_alloc(uint32_t bytes, uint32_t align) {
    if (align < 4U) {
        align = 4U;
    }
    uint32_t addr = (heap_cursor + align - 1U) & ~(align - 1U);
    if (addr + bytes > HEAP_END || addr + bytes < addr) {
        return NULL;
    }
    heap_cursor = addr + bytes;
    return (void *)(uintptr_t)addr;
}

static void *bump_alloc(uint32_t *cursor, uint32_t limit, uint32_t bytes, uint32_t align) {
    if (align < 4U) {
        align = 4U;
    }
    uint32_t addr = (*cursor + align - 1U) & ~(align - 1U);
    if (addr + bytes > limit || addr + bytes < addr) {
        return NULL;
    }
    *cursor = addr + bytes;
    return (void *)(uintptr_t)addr;
}

void *zvrt_mode_alloc(uint32_t bytes, uint32_t align) {
    return bump_alloc(&mode_cursor, ZVRT_MODE_HEAP_VA + ZVRT_MODE_HEAP_SIZE, bytes, align);
}

void zvrt_mode_reset(void) {
    mode_cursor = ZVRT_MODE_HEAP_VA;
}

void *zvrt_dma_alloc(uint32_t bytes, uint32_t align) {
    return bump_alloc(&dma_cursor, ZVRT_DMA_NC_VA + ZVRT_DMA_NC_SIZE, bytes, align);
}

void zvrt_dma_reset(void) {
    dma_cursor = ZVRT_DMA_NC_VA;
}

void zvrt_irq_init(void) {
    volatile uint32_t *gicc = zvrt_reg(GICC_BASE);
    volatile uint32_t *gicd = zvrt_reg(GICD_BASE);
    gicc[0] = 0U;
    gicd[0] = 0U;
    for (uint32_t i = 0; i < 8U; i++) {
        gicd[0x180U / 4U + i] = 0xFFFFFFFFU;
        gicd[0x280U / 4U + i] = 0xFFFFFFFFU;
    }
    for (uint32_t i = 0; i < 256U; i++) {
        irq_table[i].fn = NULL;
        irq_table[i].ctx = NULL;
    }
    gicc[0x04U / 4U] = 0xFFU; /* GICC_PMR */
    gicd[0] = 1U;             /* GICD_CTRL */
    gicc[0] = 1U;             /* GICC_CTRL */
    zvrt_dsb();
}

void zvrt_irq_register(uint32_t irq, zvrt_irq_fn fn, void *ctx) {
    if (irq < 256U) {
        irq_table[irq].fn = fn;
        irq_table[irq].ctx = ctx;
    }
}

void zvrt_irq_enable(uint32_t irq) {
    if (irq < 256U) {
        zvrt_reg(GICD_BASE)[0x100U / 4U + (irq >> 5)] = 1U << (irq & 31U);
        zvrt_dsb();
    }
}

void zvrt_irq_disable(uint32_t irq) {
    if (irq < 256U) {
        zvrt_reg(GICD_BASE)[0x180U / 4U + (irq >> 5)] = 1U << (irq & 31U);
        zvrt_dsb();
    }
}

void zvrt_irq_dispatch(void) {
    volatile uint32_t *gicc = zvrt_reg(GICC_BASE);
    uint32_t iar = gicc[0x0CU / 4U];
    uint32_t irq = iar & 0x3FFU;
    if (irq < 256U) {
        if (irq_table[irq].fn) {
            irq_table[irq].fn(irq, irq_table[irq].ctx);
        }
        gicc[0x10U / 4U] = iar;
    }
}

static int check_osd_slot(uint32_t slot_va, uint32_t cur_dma) {
    const volatile uint32_t *s = zvrt_reg(slot_va);
    if (s[1] != 0x01E00280U || s[3] != 0x01E00280U) {
        return -1;
    }
    if ((s[2] | s[4] | s[7] | s[8]) != 0U || s[12] == 0U) {
        return -1;
    }
    uint32_t frame_pa = s[0];
    if ((frame_pa & 7U) != 0U ||
        frame_pa < 0x01000000U ||
        frame_pa > (0x3F000000U - ZVRT_FRAME_BYTES)) {
        return -1;
    }
    if (cur_dma < frame_pa || (cur_dma - frame_pa) >= ZVRT_FRAME_BYTES) {
        return -1;
    }
    return 0;
}

static int stop_display_aif(void) {
    static const struct {
        uint32_t base;
        uint32_t ch;
    } banks[] = {
        {0xF3441200U, 0x39U}, {0xF3441280U, 0x3AU}, {0xF3441300U, 0x3BU}, {0xF3441380U, 0x3CU},
        {0xF3441400U, 0x3DU}, {0xF3441480U, 0x3EU}, {0xF3441500U, 0x3FU}, {0xF3441580U, 0x40U},
    };
    const volatile uint32_t *mode_tbl = zvrt_reg(AIF_MODE_TABLE);

    for (uint32_t i = 0; i < sizeof(banks) / sizeof(banks[0]); i++) {
        volatile uint32_t *r = zvrt_reg(banks[i].base);
        uint32_t r0 = r[0];
        uint32_t r1 = r[1];
        if ((r0 & 1U) || (r1 & 0x80000000U)) {
            if ((r0 & 0x800U) || mode_tbl[banks[i].ch] != 0x22BU) {
                return -1;
            }
        }
    }

    for (uint32_t i = 0; i < sizeof(banks) / sizeof(banks[0]); i++) {
        volatile uint32_t *r = zvrt_reg(banks[i].base);
        uint32_t r0 = r[0];
        uint32_t r1 = r[1];
        if ((r0 & 1U) || (r1 & 0x80000000U)) {
            r[1] = r1 & ~1U;
            r[0] = r0 & ~1U;
            r[1] = r[1] | 0x40000000U;
            zvrt_dsb();
            uint32_t t0 = zvrt_timer_ticks();
            uint32_t spins = 20000000U;
            while (r[1] & 0x80000000U) {
                if ((uint32_t)(zvrt_timer_ticks() - t0) >= 160000U || --spins == 0U) {
                    return -1;
                }
            }
            r[2] = r[2] | 0x80000000U;
            zvrt_dsb();
        }
    }
    return 0;
}

int zvrt_display_init(uint32_t frame_pa) {
    uint32_t cur_dma = *zvrt_reg(OSD0_BASE + 0x10U);
    if (check_osd_slot(0x6441B27CU, cur_dma) != 0 &&
        check_osd_slot(0x644194D8U, cur_dma) != 0) {
        return -1;
    }

    if (*zvrt_reg(VPH_BASE + 0x5000U) != 0x00010114U ||
        *zvrt_reg(VPH_BASE + 0x6000U) != 0U ||
        ((*zvrt_reg(VPH_BASE + 0x144U) & 2U) == 0U) ||
        ((*zvrt_reg(VPH_BASE + 0x404U) & 1U) != 0U)) {
        return -1;
    }

    if (stop_display_aif() != 0) {
        return -1;
    }

    volatile uint32_t *osd = zvrt_reg(OSD0_BASE);
    osd[0x0C / 4U] = 0U;
    osd[0x24 / 4U] = ZVRT_PITCH;
    osd[0x20 / 4U] = frame_pa;
    osd[0x00 / 4U] = 2U;
    for (uint32_t off = 0x28U; off <= 0x44U; off += 4U) {
        osd[off / 4U] = 0U;
    }
    osd[0x2C / 4U] = ZVRT_HEIGHT - 1U;
    for (uint32_t off = 0x50U; off <= 0x5CU; off += 4U) {
        osd[off / 4U] = 0U;
    }
    osd[0x4C / 4U] = 0U;
    osd[0x70 / 4U] = 0U;
    osd[0x48 / 4U] = ZVRT_PITCH;

    uint32_t v = *zvrt_reg(VPH_BASE + 0x42CU);
    *zvrt_reg(VPH_BASE + 0x42CU) = (v & ~0x7FFU) | ZVRT_HEIGHT;
    *zvrt_reg(VPH_BASE + 0x144U) &= ~1U;
    zvrt_dsb();
    osd[0] = 3U;
    zvrt_dsb();

    return 0;
}

int zvrt_display_flip(uint32_t frame_pa, uint32_t wait_ticks) {
    volatile uint32_t *osd = zvrt_reg(OSD0_BASE);
    uint32_t t0 = zvrt_timer_ticks();
    uint32_t spins = 20000000U;
    while (osd[0] != 2U) {
        if ((uint32_t)(zvrt_timer_ticks() - t0) >= wait_ticks || --spins == 0U) {
            return -1;
        }
    }
    osd[0x20 / 4U] = frame_pa;
    zvrt_dsb();
    osd[0] = 3U;
    zvrt_dsb();
    return 0;
}

/* Keep OSD0 refreshing front_pa while waiting, so flip() catches a real 3->2 frame-end. */
void zvrt_display_wait(uint32_t front_pa, uint32_t ticks) {
    (void)front_pa;
    volatile uint32_t *osd = zvrt_reg(OSD0_BASE);
    uint32_t t0 = zvrt_timer_ticks();
    while ((uint32_t)(zvrt_timer_ticks() - t0) < ticks) {
        if (osd[0] == 2U) {
            osd[0] = 3U;
            zvrt_dsb();
        }
    }
}

void zvrt_fill_rect(uint16_t *fb, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint16_t color) {
    if (x >= ZVRT_WIDTH || y >= ZVRT_HEIGHT) {
        return;
    }
    if (x + w > ZVRT_WIDTH) {
        w = ZVRT_WIDTH - x;
    }
    if (y + h > ZVRT_HEIGHT) {
        h = ZVRT_HEIGHT - y;
    }
    for (uint32_t row = 0; row < h; row++) {
        uint16_t *dst = fb + (y + row) * ZVRT_WIDTH + x;
        for (uint32_t col = 0; col < w; col++) {
            dst[col] = color;
        }
    }
}

void zvrt_draw_char(uint16_t *fb, uint32_t x, uint32_t y, char c, uint16_t fg, uint16_t bg, uint32_t scale) {
    if (scale == 0U) {
        scale = 1U;
    }
    uint32_t idx = (uint32_t)(uint8_t)c;
    if (idx < 0x20U || idx > 0x7EU) {
        idx = (uint32_t)'?';
    }
    const uint8_t *glyph = zvrt_font_8x8[idx - 0x20U];
    for (uint32_t gy = 0; gy < 8U; gy++) {
        uint8_t bits = glyph[gy];
        for (uint32_t gx = 0; gx < 8U; gx++) {
            uint16_t color = (bits & (1U << gx)) ? fg : bg;
            if (color != 0U) {
                zvrt_fill_rect(fb, x + gx * scale, y + gy * scale, scale, scale, color);
            }
        }
    }
}

void zvrt_draw_text(uint16_t *fb, uint32_t x, uint32_t y, const char *s, uint16_t fg, uint16_t bg, uint32_t scale) {
    if (scale == 0U) {
        scale = 1U;
    }
    uint32_t cx = x;
    while (*s) {
        if (*s == '\n') {
            cx = x;
            y += 8U * scale;
        } else {
            zvrt_draw_char(fb, cx, y, *s, fg, bg, scale);
            cx += 8U * scale;
        }
        s++;
    }
}

#define INPUT_INVALID   UINT32_MAX

struct key_debounce {
    uint32_t held;
    uint32_t candidate;
};

static struct key_debounce mode_keys, b0_keys, b3_keys;
static uint8_t rear_quad_prev;
static int last_adc[8] = { -1, -1, -1, -1, -1, -1, -1, -1 };

static void adc_enable_controller(uint32_t base, uint32_t init_ch) {
    volatile uint16_t *r = (volatile uint16_t *)(uintptr_t)base;
    r[0x08U / 2U] = 0U;                    /* ADC_MODE = OFF to clear any prior continuous scan */
    zvrt_dsb();
    zvrt_delay_ticks(10U);
    r[0x44U / 2U] = 0xFE03U;               /* ADC_CLKCTRL */
    r[0x00U / 2U] = (uint16_t)(1U << init_ch); /* AIN_SEL */
    r[0x48U / 2U] = 0x2FU;                 /* ADC_WAIT */
    r[0x0CU / 2U] = 0U;                    /* ADC_INT */
    r[0x08U / 2U] = 1U;                    /* ADC_MODE = BOOT */
    zvrt_dsb();
}

static int adc_read_channel(uint32_t base, uint32_t channel) {
    volatile uint16_t *r = (volatile uint16_t *)(uintptr_t)base;
    if (r[0x10U / 2U] & 0x11U) {
        last_adc[channel & 7U] = -1;
        return -1;
    }
    r[0x00U / 2U] = (uint16_t)(1U << channel); /* Select one input in boot mode. */
    zvrt_dsb();
    r[0x04U / 2U] = 1U;                   /* ADC_TRG = START */
    zvrt_dsb();
    zvrt_delay_ticks(50U);                /* Let BUSY assert and conversion settle. */
    uint32_t start = zvrt_timer_ticks();
    uint32_t spins = 10000U;
    while (r[0x10U / 2U] & 0x11U) {
        if ((uint32_t)(zvrt_timer_ticks() - start) >= 200U || --spins == 0U) {
            last_adc[channel & 7U] = -2;
            return -1;
        }
    }
    int val = (int)(r[(0x14U + 4U * channel) / 2U] & 0x3FFU);
    last_adc[channel & 7U] = val;
    return val;
}

int zvrt_adc_last(uint32_t ch) {
    return (ch < 8U) ? last_adc[ch] : -1;
}

static uint32_t decode_b0(uint16_t value) {
    /* Sony backup 0x01120000 selector 0x0c (ADC1 ch 0, B0): Delete, Fn, Custom (C1). */
    if (value <= 0x05BU) return ZVRT_KEY_DELETE;
    if (value >= 0x1B8U && value <= 0x257U) return ZVRT_KEY_FN;
    if (value >= 0x258U && value <= 0x304U) return ZVRT_KEY_C1;
    return 0U;
}

static uint32_t decode_b3(uint16_t value) {
    /* ZV-E10 ADC1 ch 3 (B3, idle 0x3FF): OK (0x000), Left (~0x0D4), Up (~0x15F), Down (~0x1FA), Right (~0x2AD). */
    if (value <= 0x05BU) return ZVRT_KEY_OK;
    if (value <= 0x111U) return ZVRT_KEY_LEFT;
    if (value <= 0x1B7U) return ZVRT_KEY_UP;
    if (value <= 0x257U) return ZVRT_KEY_DOWN;
    if (value <= 0x304U) return ZVRT_KEY_RIGHT;
    return 0U;
}

static uint32_t adc_read_key(uint32_t base, uint32_t channel, uint32_t (*decode)(uint16_t)) {
    int first = adc_read_channel(base, channel);
    if (first < 0) return INPUT_INVALID;
    int second = adc_read_channel(base, channel);
    if (second < 0 || first - second > 12 || second - first > 12) return INPUT_INVALID;
    uint32_t key = decode(first);
    return key == decode(second) ? key : INPUT_INVALID;
}

static uint32_t debounce(struct key_debounce *state, uint32_t sample) {
    if (sample == INPUT_INVALID) {
        state->candidate = state->held;
    } else if (sample == state->candidate) {
        state->held = sample;
    } else {
        state->candidate = sample;
    }
    return state->held;
}

void zvrt_input_init(void) {
    uint32_t g00 = *zvrt_reg(LED_GPIO_ADDR + 0x010U);
    rear_quad_prev = (uint8_t)(g00 & 3U);
    mode_keys.held = mode_keys.candidate = 0U;
    b0_keys.held = b0_keys.candidate = 0U;
    b3_keys.held = b3_keys.candidate = 0U;
    adc_enable_controller(ADC1_BASE, 3U);
}

void zvrt_poll_keys(struct zvrt_keys *keys) {
    uint32_t previous = mode_keys.held | b0_keys.held | b3_keys.held;
    uint32_t b3 = adc_read_key(ADC1_BASE, 3U, decode_b3);
    uint32_t b0 = adc_read_key(ADC1_BASE, 0U, decode_b0);
    uint32_t gpio = *zvrt_reg(LED_GPIO_ADDR + 0x010U);
    uint32_t mode = debounce(&mode_keys, (gpio & 0x400U) ? ZVRT_KEY_MODE : 0U);
    keys->held = mode | debounce(&b0_keys, b0) | debounce(&b3_keys, b3);
    keys->pressed = keys->held & ~previous;
    keys->released = previous & ~keys->held;
}

uint32_t zvrt_read_keys(void) {
    struct zvrt_keys keys;
    zvrt_poll_keys(&keys);
    return keys.held;
}

void zvrt_read_dials(int32_t *top_delta, int32_t *rear_delta) {
    static const int8_t quad_lut[16] = {
        0, -1, 1, 0,
        1, 0, 0, -1,
        -1, 0, 0, 1,
        0, 1, -1, 0
    };
    uint32_t g00 = *zvrt_reg(LED_GPIO_ADDR + 0x010U);
    uint8_t r = (uint8_t)(g00 & 3U);
    if (top_delta) {
        /* Control Wheel rotary ring is routed through FRONT(CA), not G00. */
        *top_delta = 0;
    }
    if (rear_delta) {
        *rear_delta = quad_lut[(rear_quad_prev << 2) | r];
    }
    rear_quad_prev = r;
}

/* SPDX-License-Identifier: GPL-2.0 */
#ifndef ZVRT_RUNTIME_H
#define ZVRT_RUNTIME_H

/* Reserve 16 MiB non-cacheable DMA window: 2 MiB OSD0 display + 14 MiB DMA pool. */
#define ZVRT_DISPLAY_PA   0x25000000
#define ZVRT_DISPLAY_VA   0x85000000
#define ZVRT_DISPLAY_SIZE 0x00200000
#define ZVRT_DMA_NC_PA    0x25200000
#define ZVRT_DMA_NC_VA    0x85200000
#define ZVRT_DMA_NC_SIZE  0x00E00000
#define ZVRT_NC_TOTAL_END 0x26000000

#define ZVRT_MODE_HEAP_VA   0x86000000U
#define ZVRT_MODE_HEAP_SIZE 0x0F000000U /* 240 MiB cacheable mode arena */
/* Reserve the last 48 MiB of the old mode arena for a full-size RAW frame. */
#define ZVRT_STILL_RAW_PA  0x35000000
#define ZVRT_STILL_RAW_END 0x38000000

#ifndef __ASSEMBLER__

#include <stdint.h>
#include <stddef.h>

#define ZVRT_PROBE_OK   0x4F4B5254U
#define ZVRT_PROBE_FAIL 0x4641494CU

#define ZVRT_WIDTH       640U
#define ZVRT_HEIGHT      480U
#define ZVRT_PITCH       1280U
#define ZVRT_FRAME_BYTES 614400U

#define ZVRT_CLIP_ADDR   ((const void *)0x84000000U)

struct zvrt_handoff {
    uint32_t magic;
    uint32_t version;
    uint32_t bytes;
    uint32_t flags;
    uint32_t arena_va;
    uint32_t arena_pa;
    uint32_t arena_bytes;
    uint32_t result;
    uint32_t clean_frame;
    uint32_t frame_bytes;
    uint32_t clip_va;
    uint32_t clip_bytes;
};

static inline volatile uint32_t *zvrt_reg(uint32_t addr) {
    return (volatile uint32_t *)(uintptr_t)addr;
}

static inline void zvrt_dsb(void) {
    __asm__ volatile("dsb sy" ::: "memory");
}

static inline void zvrt_isb(void) {
    __asm__ volatile("isb sy" ::: "memory");
}

uint32_t zvrt_timer_ticks(void);
void zvrt_delay_ticks(uint32_t ticks);
void zvrt_led_set(int on);
__attribute__((noreturn)) void zvrt_report_error(uint32_t code);

void zvrt_dcache_clean(const void *va, uint32_t bytes);
void zvrt_dcache_inv(const void *va, uint32_t bytes);
void *zvrt_alloc(uint32_t bytes, uint32_t align);
void *zvrt_mode_alloc(uint32_t bytes, uint32_t align);
void zvrt_mode_reset(void);
void *zvrt_dma_alloc(uint32_t bytes, uint32_t align);
void zvrt_dma_reset(void);

typedef void (*zvrt_irq_fn)(uint32_t irq, void *ctx);
void zvrt_irq_init(void);
void zvrt_irq_register(uint32_t irq, zvrt_irq_fn fn, void *ctx);
void zvrt_irq_enable(uint32_t irq);
void zvrt_irq_disable(uint32_t irq);
static inline void zvrt_irq_enable_all(void) { __asm__ volatile("cpsie i" ::: "memory"); }
static inline void zvrt_irq_disable_all(void) { __asm__ volatile("cpsid i" ::: "memory"); }

void zvrt_fill_rect(uint16_t *fb, uint32_t x, uint32_t y, uint32_t w, uint32_t h, uint16_t color);
void zvrt_draw_char(uint16_t *fb, uint32_t x, uint32_t y, char c, uint16_t fg, uint16_t bg, uint32_t scale);
void zvrt_draw_text(uint16_t *fb, uint32_t x, uint32_t y, const char *s, uint16_t fg, uint16_t bg, uint32_t scale);

/* ZV-E10 key IDs. GPIO G00 and ADC1 ladders B0/B3 are currently polled. */
#define ZVRT_KEY_UP           (1U << 0)
#define ZVRT_KEY_DOWN         (1U << 1)
#define ZVRT_KEY_LEFT         (1U << 2)
#define ZVRT_KEY_RIGHT        (1U << 3)
#define ZVRT_KEY_OK           (1U << 4)
#define ZVRT_KEY_MENU         (1U << 5)
#define ZVRT_KEY_FN           (1U << 6)
#define ZVRT_KEY_PLAY         (1U << 7)
#define ZVRT_KEY_DELETE       (1U << 8)
#define ZVRT_KEY_REC          (1U << 9)
#define ZVRT_KEY_SHUTTER_HALF (1U << 10)
#define ZVRT_KEY_SHUTTER_FULL (1U << 11)
#define ZVRT_KEY_MODE         (1U << 12)
#define ZVRT_KEY_C1           (1U << 13)

struct zvrt_keys {
    uint32_t held;
    uint32_t pressed;
    uint32_t released;
};

void zvrt_input_init(void);
/* Sample once per display frame. Edges are relative to the preceding poll. */
void zvrt_poll_keys(struct zvrt_keys *keys);
/* Held-only compatibility API. This also advances the input poll. */
uint32_t zvrt_read_keys(void);
void zvrt_read_dials(int32_t *top_delta, int32_t *rear_delta);
int zvrt_adc_last(uint32_t unit);

int zvrt_display_init(uint32_t frame_pa);
/* Return -1 on timeout without changing the current scanout. */
int zvrt_display_flip(uint32_t frame_pa, uint32_t wait_ticks);
void zvrt_display_wait(uint32_t front_pa, uint32_t ticks);

static inline uint16_t *zvrt_ddr0_va(uint32_t pa) {
    return (uint16_t *)(uintptr_t)(pa + 0x60000000U);
}

static inline uint32_t zvrt_ddr0_pa(const void *va) {
    uint32_t addr = (uint32_t)(uintptr_t)va;
    return (addr >= 0x60000000U && addr < 0xA0000000U) ? (addr - 0x60000000U) : addr;
}

#endif /* !__ASSEMBLER__ */
#endif

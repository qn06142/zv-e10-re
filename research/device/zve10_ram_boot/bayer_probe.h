/* SPDX-License-Identifier: GPL-2.0 */
#ifndef ZV_BAYER_PROBE_H
#define ZV_BAYER_PROBE_H

#include "zvrt_runtime.h"

/* Stock mode 0x37 writes through ISP0, then reads the span through ISP1. */
#define BAYER_ISP0_WRITE  0xf3002380U
#define BAYER_ISP1_READ   0xf3102200U
#define BAYER_WRITER_BUSY (1U << 31)

struct bayer_writer_sample {
    uint32_t control, status, current, base, line, gap, rows_minus_one;
};

struct bayer_writer_observation {
    struct bayer_writer_sample last;
    uint32_t address_changes, busy_rises, busy_falls, geometry_changes;
};

static inline struct bayer_writer_sample bayer_read_writer(uint32_t base) {
    volatile uint32_t *reg = zvrt_reg(base);
    return (struct bayer_writer_sample){reg[0], reg[1], reg[4], reg[8], reg[9], reg[10], reg[11]};
}

static inline void bayer_reset_observation(struct bayer_writer_observation *obs, uint32_t base) {
    obs->last = bayer_read_writer(base);
    obs->address_changes = 0U;
    obs->busy_rises = 0U;
    obs->busy_falls = 0U;
    obs->geometry_changes = 0U;
}

static inline void bayer_observe_writer(struct bayer_writer_observation *obs, struct bayer_writer_sample next) {
    const struct bayer_writer_sample *prev = &obs->last;
    obs->address_changes += next.current != prev->current;
    obs->busy_rises += !(prev->status & BAYER_WRITER_BUSY) && (next.status & BAYER_WRITER_BUSY);
    obs->busy_falls += (prev->status & BAYER_WRITER_BUSY) && !(next.status & BAYER_WRITER_BUSY);
    obs->geometry_changes += next.base != prev->base || next.line != prev->line ||
                             next.gap != prev->gap || next.rows_minus_one != prev->rows_minus_one;
    obs->last = next;
}

static inline uint32_t bayer_raw_extent(const struct bayer_writer_sample *s) {
    if (!s->base || !s->line || s->base >= 0x40000000U) {
        return 0U;
    }
    uint64_t stride = (uint64_t)s->line + s->gap;
    uint64_t limit = 0x40000000U - s->base;
    if (stride > limit || s->line > limit) {
        return 0U;
    }
    uint64_t bytes = (uint64_t)s->rows_minus_one * stride + s->line;
    return bytes <= limit ? (uint32_t)bytes : 0U;
}

static inline void bayer_draw_hex_value(uint16_t *frame, uint32_t x, uint32_t y,
                                        const char *label, uint32_t value) {
    static const char hex[] = "0123456789ABCDEF";
    char word[9];
    for (uint32_t i = 0; i < 8U; ++i) {
        word[i] = hex[(value >> (28U - i * 4U)) & 15U];
    }
    word[8] = '\0';
    zvrt_draw_text(frame, x, y, label, 0xffffU, 0, 1);
    zvrt_draw_text(frame, x + 144U, y, word, 0x0fffU, 0, 1);
}

static inline void bayer_draw_writer(uint16_t *frame, uint32_t x, const char *name,
                                     const struct bayer_writer_observation *obs) {
    zvrt_draw_text(frame, x, 64, name, 0xffffU, 0, 2);
    bayer_draw_hex_value(frame, x, 94, "Control", obs->last.control);
    bayer_draw_hex_value(frame, x, 118, "Status", obs->last.status);
    bayer_draw_hex_value(frame, x, 142, "Current address", obs->last.current);
    bayer_draw_hex_value(frame, x, 166, "Programmed base", obs->last.base);
    bayer_draw_hex_value(frame, x, 190, "Geometry +24", obs->last.line);
    bayer_draw_hex_value(frame, x, 214, "Geometry +28", obs->last.gap);
    bayer_draw_hex_value(frame, x, 238, "Geometry +2C", obs->last.rows_minus_one);
    bayer_draw_hex_value(frame, x, 270, "Address changes", obs->address_changes);
    bayer_draw_hex_value(frame, x, 294, "Busy rises", obs->busy_rises);
    bayer_draw_hex_value(frame, x, 318, "Busy falls", obs->busy_falls);
    bayer_draw_hex_value(frame, x, 342, "Geometry changes", obs->geometry_changes);
}

static inline void bayer_draw_probe_screen(uint16_t *frame, const char *title,
                                           const struct bayer_writer_observation *writer,
                                           const struct bayer_writer_observation *reader,
                                           uint32_t polls, const char *note1, const char *note2) {
    zvrt_fill_rect(frame, 0, 0, ZVRT_WIDTH, ZVRT_HEIGHT, 0x002fU);
    zvrt_draw_text(frame, 16, 24, title, 0xffffU, 0, 2);
    bayer_draw_writer(frame, 16, "ISP0 AIF3 write", writer);
    bayer_draw_writer(frame, 336, "ISP1 AIF6 read", reader);
    bayer_draw_hex_value(frame, 16, 382, "RAW span bytes", bayer_raw_extent(&writer->last));
    bayer_draw_hex_value(frame, 336, 382, "Polls", polls);
    zvrt_draw_text(frame, 16, 432, note1, 0xffffU, 0, 1);
    zvrt_draw_text(frame, 16, 450, note2, 0xff0fU, 0, 1);
}

#endif

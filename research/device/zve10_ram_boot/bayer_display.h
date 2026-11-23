/* SPDX-License-Identifier: GPL-2.0 */
#ifndef ZV_BAYER_DISPLAY_H
#define ZV_BAYER_DISPLAY_H

#include "zvrt_runtime.h"

#define BAYER_MAGIC       0x5242565AU /* ZVBR */
#define BAYER_CLIP_LIMIT  (16U * 1024U * 1024U)
#define BAYER_TEST_WIDTH  960U
#define BAYER_TEST_HEIGHT 720U

struct bayer_clip_header {
    uint32_t magic;
    uint16_t width, height;
    uint32_t frames;
    uint32_t reserved;
};

struct bayer_frame {
    const uint16_t *pixels;
    uint32_t width, height;
    uint32_t stride_pixels;
};

struct bayer_source {
    struct bayer_frame frame;
    uint32_t count, index;
};

/* Optional fixture linked into the image as a ZVBR clip. */
extern const uint8_t zvrt_bayer_fixture_start[] __attribute__((weak));
extern const uint8_t zvrt_bayer_fixture_end[] __attribute__((weak));

static inline int bayer_open_clip(struct bayer_source *source, const void *data, uint32_t bytes) {
    if (bytes < sizeof(struct bayer_clip_header) || bytes > BAYER_CLIP_LIMIT ||
        !data || ((uintptr_t)data & 3U)) {
        return 0;
    }

    const struct bayer_clip_header *header = (const struct bayer_clip_header *)data;
    uint32_t width = header->width, height = header->height;
    if (header->magic != BAYER_MAGIC || header->reserved || !header->frames ||
        !width || !height || width > 8192U || height > 8192U ||
        ((width | height) & 1U)) {
        return 0;
    }

    uint32_t payload;
    if (__builtin_mul_overflow(width * height * 2U, header->frames, &payload) ||
        payload != bytes - sizeof(*header)) {
        return 0;
    }

    *source = (struct bayer_source){
        {(const uint16_t *)(header + 1), width, height, width},
        header->frames,
        0U,
    };
    return 1;
}

static inline void bayer_generate_test_pattern(uint16_t *pixels, uint32_t index) {
    uint32_t bar_x = 24U + index * 12U;
    for (uint32_t y = 0; y < BAYER_TEST_HEIGHT; y += 2U) {
        for (uint32_t x = 0; x < BAYER_TEST_WIDTH; x += 2U) {
            uint16_t red = 0x1800U, green = 0x2400U, blue = 0x2C00U;
            if (y >= 72U && y < 456U) {
                red = x < 320U ? 0xE000U : 0x2000U;
                green = x >= 320U && x < 640U ? 0xE000U : 0x2000U;
                blue = x >= 640U ? 0xE000U : 0x2000U;
            } else if (y >= 456U) {
                red = green = blue = (uint16_t)(x << 6);
            }
            if (x >= bar_x && x < bar_x + 48U && y >= 100U && y < 670U) {
                red = green = blue = 0xFFFFU;
            }
            uint16_t *block = pixels + y * BAYER_TEST_WIDTH + x;
            block[0] = red;
            block[1] = green;
            block[BAYER_TEST_WIDTH] = green;
            block[BAYER_TEST_WIDTH + 1U] = blue;
        }
    }
}

static inline struct bayer_frame bayer_acquire_frame(struct bayer_source *source, uint16_t *test_pixels) {
    struct bayer_frame frame = source->frame;
    if (source->count) {
        frame.pixels += source->index * frame.width * frame.height;
        ++source->index;
        if (source->index == source->count) {
            source->index = 0U;
        }
        return frame;
    }

    bayer_generate_test_pattern(test_pixels, source->index);
    ++source->index;
    if (source->index == 70U) {
        source->index = 0U;
    }
    return frame;
}

static inline void bayer_resize_lcd_shifted(uint16_t *output, const struct bayer_frame *frame, uint32_t r_shift) {
    uint16_t xmap[ZVRT_WIDTH];
    uint32_t blocks_x = frame->width / 2U;
    uint32_t blocks_y = frame->height / 2U;
    uint32_t stride = frame->stride_pixels ? frame->stride_pixels : frame->width;
    for (uint32_t x = 0; x < ZVRT_WIDTH; ++x) {
        xmap[x] = (uint16_t)(2U * (((2U * x + 1U) * blocks_x) / (2U * ZVRT_WIDTH)));
    }

    for (uint32_t y = 0; y < ZVRT_HEIGHT; ++y) {
        uint32_t row = 2U * (((2U * y + 1U) * blocks_y) / (2U * ZVRT_HEIGHT));
        const uint16_t *top = frame->pixels + row * stride;
        const uint16_t *bottom = top + stride;
        for (uint32_t x = 0; x < ZVRT_WIDTH; ++x) {
            uint32_t column = xmap[x];
            uint32_t red = top[column] >> r_shift;
            uint32_t green = ((uint32_t)top[column + 1U] + bottom[column]) >> (r_shift + 1U);
            uint32_t blue = bottom[column + 1U] >> r_shift;
            if (red > 15U) red = 15U;
            if (green > 15U) green = 15U;
            if (blue > 15U) blue = 15U;
            *output++ = (uint16_t)((red << 12) | (green << 8) | (blue << 4) | 0xFU);
        }
    }
}

static inline void bayer_resize_lcd(uint16_t *output, const struct bayer_frame *frame) {
    bayer_resize_lcd_shifted(output, frame, 12U);
}

static inline int bayer_has_embedded_fixture(struct bayer_source *source) {
    uintptr_t fixture_start = (uintptr_t)zvrt_bayer_fixture_start;
    uintptr_t fixture_end = (uintptr_t)zvrt_bayer_fixture_end;
    return fixture_start && fixture_end > fixture_start &&
           bayer_open_clip(source, zvrt_bayer_fixture_start, (uint32_t)(fixture_end - fixture_start));
}

static inline int bayer_has_staged_clip(struct bayer_source *source, const struct zvrt_handoff *handoff) {
    return handoff && handoff->bytes >= sizeof(*handoff) &&
           handoff->clip_va == (uint32_t)(uintptr_t)ZVRT_CLIP_ADDR &&
           bayer_open_clip(source, ZVRT_CLIP_ADDR, handoff->clip_bytes);
}

#endif

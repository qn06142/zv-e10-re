/* SPDX-License-Identifier: GPL-2.0 */
/* Bare-metal Bad Apple!! player (1-bit XOR-PackBits ZVBA clip at 0x84000000 -> 640x480 OSD0). */
#include "zvrt_runtime.h"

#define ZVBA_MAGIC 0x4142565AU

struct zvba_header {
    uint32_t magic;
    uint16_t width;
    uint16_t height;
    uint32_t fps;
    uint32_t frame_count;
};

/* 256-entry LUT expanding 8 MSB-first 1-bit pixels into 4 RGBA4444 pixel-pairs. */
static uint32_t bit_lut[256][4];
static uint8_t shadow[ZVRT_WIDTH * ZVRT_HEIGHT / 8U];

static void build_lut(void) {
    for (uint32_t b = 0; b < 256U; b++) {
        for (uint32_t w = 0; w < 4U; w++) {
            uint16_t p0 = (b & (0x80U >> (w * 2U))) ? 0xFFFFU : 0x000FU;
            uint16_t p1 = (b & (0x80U >> (w * 2U + 1U))) ? 0xFFFFU : 0x000FU;
            bit_lut[b][w] = (uint32_t)p0 | ((uint32_t)p1 << 16);
        }
    }
}

static void decode_xor_packbits(const uint8_t *src, uint32_t len, uint8_t *dst, uint32_t dst_len) {
    uint32_t pos = 0;
    uint32_t i = 0;
    while (i < len && pos < dst_len) {
        uint8_t ctrl = src[i++];
        if (ctrl & 0x80U) {
            uint32_t count = (uint32_t)(ctrl & 0x7FU) + 2U;
            uint8_t val = src[i++];
            if (pos + count > dst_len) {
                count = dst_len - pos;
            }
            if (val != 0U) {
                for (uint32_t k = 0; k < count; k++) {
                    dst[pos++] ^= val;
                }
            } else {
                pos += count;
            }
        } else {
            uint32_t count = (uint32_t)ctrl + 1U;
            if (pos + count > dst_len) {
                count = dst_len - pos;
            }
            for (uint32_t k = 0; k < count; k++) {
                dst[pos++] ^= src[i++];
            }
        }
    }
}

static void expand_640x480(const uint8_t *bits, uint32_t *fb32) {
    for (uint32_t i = 0; i < (ZVRT_WIDTH * ZVRT_HEIGHT) / 8U; i++) {
        const uint32_t *q = bit_lut[bits[i]];
        fb32[0] = q[0];
        fb32[1] = q[1];
        fb32[2] = q[2];
        fb32[3] = q[3];
        fb32 += 4;
    }
}

static void expand_320x240_2x(const uint8_t *bits, uint32_t *fb32) {
    const uint32_t row_words = ZVRT_WIDTH / 2U; /* 320 uint32_t per 640-px line */
    for (uint32_t y = 0; y < 240U; y++) {
        uint32_t *line0 = fb32 + (y * 2U) * row_words;
        uint32_t *line1 = line0 + row_words;
        for (uint32_t bx = 0; bx < 40U; bx++) {
            uint8_t b = bits[y * 40U + bx];
            for (uint32_t bit = 0; bit < 8U; bit++) {
                uint16_t px = (b & (0x80U >> bit)) ? 0xFFFFU : 0x000FU;
                uint32_t pair = (uint32_t)px | ((uint32_t)px << 16);
                uint32_t x = bx * 8U + bit;
                line0[x] = pair;
                line1[x] = pair;
            }
        }
    }
}

void rtos_main(struct zvrt_handoff *handoff) {
    const struct zvba_header *hdr = (const struct zvba_header *)ZVRT_CLIP_ADDR;
    if (handoff->clip_bytes < sizeof(*hdr) ||
        hdr->magic != ZVBA_MAGIC ||
        hdr->frame_count == 0U ||
        !((hdr->width == 640U && hdr->height == 480U) ||
          (hdr->width == 320U && hdr->height == 240U))) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(10U);
    }

    uint32_t front_pa = ZVRT_DISPLAY_PA;
    uint32_t back_pa = front_pa + ZVRT_FRAME_BYTES;
    uint32_t *front32 = (uint32_t *)zvrt_ddr0_va(front_pa);
    for (uint32_t i = 0; i < ZVRT_FRAME_BYTES / 4U; i++) {
        front32[i] = 0x000F000FU;
    }
    zvrt_dsb();
    if (zvrt_display_init(front_pa) != 0) {
        handoff->result = ZVRT_PROBE_FAIL;
        zvrt_report_error(8U);
    }

    build_lut();

    uint32_t shadow_bytes = ((uint32_t)hdr->width * (uint32_t)hdr->height) / 8U;
    uint32_t target_fps = (hdr->fps > 0U && hdr->fps <= 50U) ? hdr->fps : 24U;
    int is_320 = (hdr->width == 320U);

    handoff->result = ZVRT_PROBE_OK;

    int led = 0;
    for (;;) {
        const uint8_t *ptr = (const uint8_t *)(hdr + 1);
        const uint8_t *clip_end = (const uint8_t *)ZVRT_CLIP_ADDR + handoff->clip_bytes;
        uint32_t vsync_acc = 0U;
        for (uint32_t i = 0; i < shadow_bytes; i++) {
            shadow[i] = 0U;
        }

        for (uint32_t f = 0; f < hdr->frame_count; f++) {
            if (ptr + 4U > clip_end) {
                break;
            }
            uint32_t payload_bytes = *(const uint32_t *)ptr;
            ptr += 4U;
            if (ptr + payload_bytes > clip_end) {
                break;
            }

            decode_xor_packbits(ptr, payload_bytes, shadow, shadow_bytes);
            ptr += (payload_bytes + 3U) & ~3U;

            uint32_t *fb32 = (uint32_t *)zvrt_ddr0_va(back_pa);
            if (is_320) {
                expand_320x240_2x(shadow, fb32);
            } else {
                expand_640x480(shadow, fb32);
            }
            zvrt_dsb();
            while (zvrt_display_flip(back_pa, 30000U) != 0) {
            }

            uint32_t tmp = front_pa;
            front_pa = back_pa;
            back_pa = tmp;

            if ((f & 15U) == 0U) {
                led ^= 1;
                zvrt_led_set(led);
            }

            /* Pace target_fps against the 50 Hz VSYNC via Bresenham accumulator. */
            vsync_acc += 50U;
            while (vsync_acc > target_fps) {
                vsync_acc -= target_fps;
                if (vsync_acc >= target_fps) {
                    while (zvrt_display_flip(front_pa, 30000U) != 0) {
                    }
                }
            }
        }
    }
}

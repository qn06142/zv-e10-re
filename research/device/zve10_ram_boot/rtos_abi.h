/* SPDX-License-Identifier: GPL-2.0 */
#ifndef ZVE10_RTOS_ABI_H
#define ZVE10_RTOS_ABI_H

#define ZVRT_FILE_MAGIC 0x5452565a
#define ZVRT_HANDOFF_MAGIC 0x4852565a
#define ZVRT_ABI_VERSION 1
#define ZVRT_HEADER_BYTES 32
#define ZVRT_H_SIZE 32
#define ZVRT_H_DISPLAY_SIZE 40
#define ZVRT_H_CLIP_SIZE 48
#define ZVRT_H_MAGIC 0
#define ZVRT_H_VERSION 4
#define ZVRT_H_BYTES 8
#define ZVRT_H_FLAGS 12
#define ZVRT_H_ARENA_VA 16
#define ZVRT_H_ARENA_PA 20
#define ZVRT_H_ARENA_BYTES 24
#define ZVRT_H_RESULT 28
#define ZVRT_OWNED_ARENA 1
#define ZVRT_DISPLAY_REUSE 2
#define ZVRT_CLIP_LOADED 4
#define ZVRT_IMAGE_DISPLAY 1
#define ZVRT_H_CLEAN_FRAME 32
#define ZVRT_H_FRAME_BYTES 36
#define ZVRT_H_CLIP_VA 40
#define ZVRT_H_CLIP_BYTES 44
#define ZVRT_PROBE_OK 0x4f4b5254

#ifndef __ASSEMBLER__
struct zvrt_image_header {
    unsigned int magic;
    unsigned int version;
    unsigned int header_bytes;
    unsigned int image_bytes;
    unsigned int entry_offset;
    unsigned int crc32;
    unsigned int flags;
    unsigned int reserved;
};

struct zvrt_handoff {
    unsigned int magic;
    unsigned int version;
    unsigned int bytes;
    unsigned int flags;
    unsigned int arena_va;
    unsigned int arena_pa;
    unsigned int arena_bytes;
    unsigned int result;
    unsigned int clean_frame;
    unsigned int frame_bytes;
    unsigned int clip_va;
    unsigned int clip_bytes;
};

static inline int zvrt_image_valid(const struct zvrt_image_header *h,
                                  unsigned long maximum)
{
    return h->magic == ZVRT_FILE_MAGIC && h->version == ZVRT_ABI_VERSION &&
           h->header_bytes == ZVRT_HEADER_BYTES && !h->reserved &&
           (h->flags == 0 || h->flags == ZVRT_IMAGE_DISPLAY) &&
           h->image_bytes >= 4 && h->image_bytes <= maximum &&
           !(h->image_bytes & 3) && !(h->entry_offset & 3) &&
           h->entry_offset < h->image_bytes;
}
#endif
#endif

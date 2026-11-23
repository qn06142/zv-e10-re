/* SPDX-License-Identifier: GPL-2.0 */
#include <linux/dma-mapping.h>

#define OSD_WIDTH 640
#ifdef ZVE10_OSD_FULL
#define OSD_HEIGHT 480
#else
#define OSD_HEIGHT 48
#endif
#define OSD_PITCH (OSD_WIDTH * sizeof(u16))
#define OSD_BYTES (OSD_PITCH * OSD_HEIGHT)
#define VPH_PHYS 0xf3440000
#define OSD0 0x1300

static void __iomem *vph;
#ifndef ZVE10_OSD_FULL
static u16 *compare_frame;
#endif
static dma_addr_t compare_dma;

#ifdef ZVE10_OSD_FULL
/* The camera can reject order-8 requests even when several smaller,
 * physically adjacent DMA allocations are available. The controller sees
 * one contiguous bus range, while each allocation keeps its own CPU mapping.
 */
#define OSD_CHUNK_BYTES (64 * 1024)
#define OSD_MAX_CHUNKS 24

struct osd_chunk {
    u16 *pixels;
    dma_addr_t dma;
};

static struct osd_chunk osd_chunks[OSD_MAX_CHUNKS];
static unsigned int osd_chunk_count;
static unsigned int osd_chunk_size;

static int find_osd_chunk(dma_addr_t address)
{
    unsigned int i;

    for (i = 0; i < osd_chunk_count; ++i)
        if (osd_chunks[i].pixels && osd_chunks[i].dma == address)
            return i;
    return -ENOENT;
}

static void free_osd_chunks(void)
{
    unsigned int i;

    for (i = 0; i < osd_chunk_count; ++i)
        if (osd_chunks[i].pixels)
            dma_free_coherent(NULL, osd_chunk_size, osd_chunks[i].pixels,
                              osd_chunks[i].dma);
    osd_chunk_count = 0;
}

static int allocate_full_frame(unsigned int chunk_bytes, unsigned int limit)
{
    dma_addr_t base, address;
    unsigned int i, row, column, first_pixel, offset, pixel, count;
    int index;
    static const u16 bars[] = {
        0xffff, 0xff0f, 0x0fff, 0x0f0f, 0xf0ff, 0xf00f, 0x00ff, 0x000f
    };

    osd_chunk_size = chunk_bytes;
    while (osd_chunk_count < limit) {
        struct osd_chunk *chunk = &osd_chunks[osd_chunk_count];
        chunk->pixels = dma_alloc_coherent(NULL, chunk_bytes, &chunk->dma,
                            GFP_KERNEL | __GFP_NORETRY | __GFP_NOWARN);
        if (!chunk->pixels)
            break;
        if (!chunk->dma || (chunk->dma & 7) ||
            chunk->dma > 0x40000000 - chunk_bytes) {
            dma_free_coherent(NULL, chunk_bytes, chunk->pixels, chunk->dma);
            break;
        }
        ++osd_chunk_count;

        /* A new block may extend a candidate on either end. */
        base = chunk->dma;
        while (base >= chunk_bytes && find_osd_chunk(base - chunk_bytes) >= 0)
            base -= chunk_bytes;
        for (offset = 0; offset < OSD_BYTES; offset += chunk_bytes)
            if (find_osd_chunk(base + offset) < 0)
                break;
        if (offset >= OSD_BYTES) {
            compare_dma = base;
            break;
        }
    }

    if (!compare_dma) {
        free_osd_chunks();
        return -ENOMEM;
    }
    for (i = 0; i < osd_chunk_count; ++i) {
        address = osd_chunks[i].dma;
        if (address < compare_dma || address - compare_dma >= OSD_BYTES) {
            dma_free_coherent(NULL, chunk_bytes, osd_chunks[i].pixels, address);
            osd_chunks[i].pixels = NULL;
        }
    }
    for (offset = 0; offset < OSD_BYTES; offset += chunk_bytes) {
        index = find_osd_chunk(compare_dma + offset);
        if (index < 0) {
            free_osd_chunks();
            return -EINVAL;
        }
        first_pixel = offset / sizeof(u16);
        count = min_t(unsigned int, OSD_BYTES - offset, chunk_bytes) / sizeof(u16);
        for (i = 0; i < count; ++i) {
            pixel = first_pixel + i;
            row = pixel / OSD_WIDTH;
            column = pixel % OSD_WIDTH;
            osd_chunks[index].pixels[i] =
                (row < 8 || row >= OSD_HEIGHT - 8 ||
                 column < 8 || column >= OSD_WIDTH - 8) ?
                0x000f : bars[column / (OSD_WIDTH / ARRAY_SIZE(bars))];
        }
    }
    printk(KERN_INFO "ZVBOOT_STAGE_OSD_FULL DMA=%08x bytes=%u chunk=%u\n",
           (unsigned int)compare_dma, (unsigned int)OSD_BYTES, chunk_bytes);
    wmb();
    return 0;
}
#endif

#ifdef ZVE10_OSD_FIRE
#include "osd_fire_span.h"
#endif

static int prepare_osd_compare(void)
{
#ifdef ZVE10_OSD_FULL
    int result;

    vph = ioremap(VPH_PHYS, 0x7000);
    if (!vph)
        return -ENOMEM;
    result = allocate_full_frame(OSD_BYTES, 1);
    if (result == -ENOMEM)
        result = allocate_full_frame(OSD_CHUNK_BYTES, OSD_MAX_CHUNKS);
#ifdef ZVE10_OSD_FIRE
    if (result == -ENOMEM)
        result = reserve_fire_span(4);
    if (result == -ENOMEM)
        result = reserve_fire_span(2);
    if (result == -ENOMEM)
        result = reserve_fire_span(0);
#endif
    return result;
#else
    static const u16 rgba4444[] = {0xf00f, 0x0f0f, 0x00ff, 0xffff};
    static const u16 rgb565[] = {0xf800, 0x07e0, 0x001f, 0xffff};
    unsigned int x, y, band;

    vph = ioremap(VPH_PHYS, 0x7000);
    if (!vph)
        return -ENOMEM;
    compare_frame = dma_alloc_coherent(NULL, OSD_BYTES, &compare_dma, GFP_KERNEL);
    if (!compare_frame)
        return -ENOMEM;
    if (!compare_dma || (compare_dma & 7) || compare_dma > 0x40000000 - OSD_BYTES)
        return -ERANGE;

    for (y = 0; y < OSD_HEIGHT; ++y) {
        band = y / (OSD_HEIGHT / ARRAY_SIZE(rgba4444));
        for (x = 0; x < OSD_WIDTH; ++x)
            compare_frame[y * OSD_WIDTH + x] =
                x < OSD_WIDTH / 2 ? rgba4444[band] : rgb565[band];
    }
    wmb();
    return 0;
#endif
}

static void release_osd_compare(void)
{
#ifdef ZVE10_OSD_FIRE
    release_fire_span();
#endif
#ifdef ZVE10_OSD_FULL
    free_osd_chunks();
#else
    if (compare_frame)
        dma_free_coherent(NULL, OSD_BYTES, compare_frame, compare_dma);
    compare_frame = NULL;
#endif
    compare_dma = 0;
    if (vph)
        iounmap(vph);
    vph = NULL;
}

static void __iomem *osd_word(unsigned int offset)
{
    return vph + OSD0 + offset;
}

/*
 * Run once after the normal shutdown sequence and SMP stop. Use the panel
 * timing inherited from stock shooting, and the native AIF stop handshake.
 */
static int start_osd_compare(void)
{
    unsigned int offset, attempt, control;

    if (readl(vph + 0x5000) != 0x00010114 || readl(vph + 0x6000) ||
        !(readl(vph + 0x0144) & 2) ||
        (readl(vph + 0x0404) & 1))
        return -ENODEV;

    control = readl(osd_word(0x00));
    writel(readl(osd_word(0x04)) & ~1U, osd_word(0x04));
    writel(control & ~1U, osd_word(0x00));
    writel(readl(osd_word(0x04)) | BIT(30), osd_word(0x04));
    for (attempt = 0; attempt < 80; ++attempt) {
        if (!(readl(osd_word(0x04)) & BIT(31)))
            break;
        udelay(1000);
    }
    writel(readl(osd_word(0x08)) | BIT(31), osd_word(0x08));
    if (attempt == 80)
        return -ETIMEDOUT;

    /* Forward single-row DDR0 geometry from the native OSD0 path. */
    writel(0, osd_word(0x0c));
    writel(OSD_PITCH, osd_word(0x24));
    writel(compare_dma, osd_word(0x20));
    writel((control & ~0x000f0801U) | 2, osd_word(0x00));
    for (offset = 0x28; offset <= 0x44; offset += 4)
        writel(offset == 0x2c ? OSD_HEIGHT - 1 : 0, osd_word(offset));
    for (offset = 0x50; offset <= 0x5c; offset += 4)
        writel(0, osd_word(offset));
    writel(0, osd_word(0x4c));
    writel(OSD_PITCH, osd_word(0x48));
    writel(0, osd_word(0x70));
    /* Native OSD0 height setter 0x806652 -> 0x4913c0. */
    writel((readl(vph + 0x042c) & ~0x7ffU) | OSD_HEIGHT, vph + 0x042c);
    wmb();
    writel(readl(osd_word(0x00)) | 1, osd_word(0x00));

    for (attempt = 0; attempt < 80; ++attempt) {
        unsigned int scan_address = readl(osd_word(0x10));
        if (scan_address >= compare_dma && scan_address - compare_dma < OSD_BYTES)
            return 0;
        udelay(1000);
    }
    return -ENODATA;
}

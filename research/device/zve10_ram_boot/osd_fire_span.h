/* SPDX-License-Identifier: GPL-2.0 */
#include <linux/vmalloc.h>

#define FIRE_SPAN_MAX_BLOCKS 512
#define FIRE_SPAN_SEARCH_BYTES (8 * 1024 * 1024)

struct fire_page_block {
    struct page *page;
    dma_addr_t base;
};

static struct fire_page_block fire_blocks[FIRE_SPAN_MAX_BLOCKS];
static struct page *fire_pages[OSD_BYTES / PAGE_SIZE];
static void *fire_span;
static unsigned int fire_block_count;
static unsigned int fire_block_order;

static int find_fire_block(dma_addr_t base)
{
    unsigned int i;

    for (i = 0; i < fire_block_count; ++i)
        if (fire_blocks[i].page && fire_blocks[i].base == base)
            return i;
    return -ENOENT;
}

static void release_fire_span(void)
{
    unsigned int i;

    if (fire_span) {
        vunmap(fire_span);
        fire_span = NULL;
    }
    for (i = 0; i < fire_block_count; ++i)
        if (fire_blocks[i].page)
            __free_pages(fire_blocks[i].page, fire_block_order);
    fire_block_count = 0;
}

static int map_fire_span(dma_addr_t base, unsigned int block_bytes)
{
    unsigned int i, offset, page, count;
    int block_index;
    void *linear;

    for (offset = 0; offset < OSD_BYTES; offset += block_bytes) {
        block_index = find_fire_block(base + offset);
        if (block_index < 0)
            return -EINVAL;
        count = min_t(unsigned int, OSD_BYTES - offset, block_bytes) / PAGE_SIZE;
        linear = page_address(fire_blocks[block_index].page);
        dmac_flush_range(linear, linear + count * PAGE_SIZE);
        for (page = 0; page < count; ++page)
            fire_pages[offset / PAGE_SIZE + page] =
                nth_page(fire_blocks[block_index].page, page);
    }
    outer_flush_range(base, base + OSD_BYTES);
    fire_span = vmap(fire_pages, ARRAY_SIZE(fire_pages), VM_MAP,
                     pgprot_dmacoherent(PAGE_KERNEL));
    if (!fire_span)
        return -ENOMEM;

    for (i = 0; i < fire_block_count; ++i) {
        if (fire_blocks[i].base < base ||
            fire_blocks[i].base - base >= OSD_BYTES) {
            __free_pages(fire_blocks[i].page, fire_block_order);
            fire_blocks[i].page = NULL;
        }
    }
    compare_dma = base;
    osd_chunk_size = OSD_BYTES;
    printk(KERN_INFO "ZVBOOT_STAGE_FIRE_SPAN DMA=%08x bytes=%u order=%u\n",
           (unsigned int)base, (unsigned int)OSD_BYTES, fire_block_order);
    return 0;
}

/* Reserve pages through Linux before GO, then map only one verified DDR0 run. */
static int reserve_fire_span(unsigned int order)
{
    unsigned int block_bytes = PAGE_SIZE << order;
    unsigned int limit = min_t(unsigned int, FIRE_SPAN_MAX_BLOCKS,
                               FIRE_SPAN_SEARCH_BYTES / block_bytes);
    dma_addr_t base;
    unsigned int offset;
    int result = -ENOMEM;

    fire_block_order = order;
    while (fire_block_count < limit) {
        struct fire_page_block *block = &fire_blocks[fire_block_count];

        block->page = alloc_pages(GFP_KERNEL | __GFP_NORETRY | __GFP_NOWARN, order);
        if (!block->page)
            break;
        block->base = page_to_phys(block->page);
        if (!block->base || block->base > 0x40000000 - block_bytes ||
            !page_address(block->page)) {
            __free_pages(block->page, order);
            break;
        }
        ++fire_block_count;
        base = block->base;
        while (base >= block_bytes && find_fire_block(base - block_bytes) >= 0)
            base -= block_bytes;
        for (offset = 0; offset < OSD_BYTES; offset += block_bytes)
            if (find_fire_block(base + offset) < 0)
                break;
        if (offset >= OSD_BYTES) {
            result = map_fire_span(base, block_bytes);
            if (!result)
                return 0;
            break;
        }
    }
    release_fire_span();
    return result;
}

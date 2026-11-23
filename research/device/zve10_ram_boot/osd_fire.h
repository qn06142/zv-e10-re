/* SPDX-License-Identifier: GPL-2.0 */
#include <mach/time.h>

#define FIRE_WIDTH 80
#define FIRE_HEIGHT 60
#define FIRE_PERIOD (SCHED_TICK_RATE / 10)

static u8 fire_heat[FIRE_HEIGHT][FIRE_WIDTH];
static unsigned int fire_seed = 0x5ad0c0de;
static volatile u32 *fire_parts[OSD_MAX_CHUNKS];

static void spread_fire(void)
{
    unsigned int x, y, heat;
    unsigned int rows = OSD_HEIGHT / 8;

    for (y = 0; y < rows - 1; ++y) {
        for (x = 1; x < FIRE_WIDTH - 1; ++x) {
            heat = (fire_heat[y + 1][x - 1] + 2 * fire_heat[y + 1][x] +
                    fire_heat[y + 1][x + 1]) >> 2;
            fire_seed ^= fire_seed << 13;
            fire_seed ^= fire_seed >> 17;
            fire_seed ^= fire_seed << 5;
            fire_heat[y][x] = heat > 0 && !(fire_seed & 3) ? heat - 1 : heat;
        }
    }
    for (x = 1; x < FIRE_WIDTH - 1; ++x) {
        fire_seed = fire_seed * 1664525U + 1013904223U;
        fire_heat[rows - 1][x] = 11 + (fire_seed >> 29) % 5;
    }
}

static void paint_fire(void)
{
    static const u16 colors[] = {
        0x000f, 0x200f, 0x400f, 0x600f, 0x810f, 0xa10f, 0xc20f, 0xe30f,
        0xf40f, 0xf50f, 0xf70f, 0xf90f, 0xfb1f, 0xfd4f, 0xff9f, 0xffff
    };
    unsigned int row, column, part = 0, offset = 0;
    unsigned int words_per_part = osd_chunk_size / sizeof(u32);

    for (row = 0; row < OSD_HEIGHT; ++row) {
        for (column = 0; column < FIRE_WIDTH; ++column) {
            u32 color = colors[fire_heat[row >> 3][column]];
            volatile u32 *pixels;

            color |= color << 16;
            pixels = fire_parts[part] + offset;
            pixels[0] = color;
            pixels[1] = color;
            pixels[2] = color;
            pixels[3] = color;
            offset += 4;
            if (offset == words_per_part) {
                offset = 0;
                ++part;
            }
        }
    }
    asm volatile("dsb sy" ::: "memory");
}

static int prepare_fire(void)
{
    unsigned int offset, i;
    int index;

    if (fire_span) {
        fire_parts[0] = fire_span;
    } else {
        for (offset = 0; offset < OSD_BYTES; offset += osd_chunk_size) {
            index = find_osd_chunk(compare_dma + offset);
            if (index < 0)
                return -EINVAL;
            fire_parts[offset / osd_chunk_size] = (volatile u32 *)osd_chunks[index].pixels;
        }
    }
    for (i = 0; i < 36; ++i)
        spread_fire();
    paint_fire();
    printk(KERN_INFO "ZVBOOT_STAGE_FIRE 80x%u procedural, 640x%u scanout\n", OSD_HEIGHT / 8, OSD_HEIGHT);
    return 0;
}

/* A timeout leaves the last rendered pixels untouched. */
static int pause_fire_scanout(void)
{
    unsigned int i;
    unsigned long start = read_freerun();

    __raw_writel(__raw_readl(osd_word(0x04)) & ~1U, osd_word(0x04));
    __raw_writel(__raw_readl(osd_word(0x00)) & ~1U, osd_word(0x00));
    __raw_writel(__raw_readl(osd_word(0x04)) | BIT(30), osd_word(0x04));
    asm volatile("dsb sy" ::: "memory");
    for (i = 0; i < 2000000; ++i) {
        if (!(__raw_readl(osd_word(0x04)) & BIT(31))) {
            __raw_writel(__raw_readl(osd_word(0x08)) | BIT(31), osd_word(0x08));
            asm volatile("dsb sy" ::: "memory");
            return 0;
        }
        if (read_freerun() - start >= FIRE_PERIOD)
            break;
    }
    return -ETIMEDOUT;
}

static void run_fire(struct boot_info *ctx)
{
    unsigned int attempts, frame = 0;
    void __iomem *led = (void __iomem *)ctx->gpio;

    for (;;) {
        unsigned long start = read_freerun();

        /* Sustain the current frame until the next animation tick. */
        for (attempts = 0; attempts < 16000000; ++attempts) {
            if (read_freerun() - start >= FIRE_PERIOD)
                break;
            if (__raw_readl(osd_word(0x00)) == 2)
                __raw_writel(3, osd_word(0x00));
        }
        if (attempts == 16000000)
            return;
        spread_fire();
        if (pause_fire_scanout())
            return;
        paint_fire();
        __raw_writel(compare_dma, osd_word(0x20));
        asm volatile("dsb sy" ::: "memory");
        __raw_writel(3, osd_word(0x00));
        asm volatile("dsb sy" ::: "memory");
        ctx->heartbeat = ++frame;
        if (!(frame % 5))
            __raw_writel(1, led + ((frame % 10) ? 0x48 : 0x44));
    }
}

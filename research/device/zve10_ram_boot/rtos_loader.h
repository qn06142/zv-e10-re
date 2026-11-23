/* SPDX-License-Identifier: GPL-2.0 */
#include <linux/crc32.h>
#include <linux/fs.h>
#include <linux/vmalloc.h>

#include "rtos_abi.h"

#define ZVRT_IMAGE_PATH "/log/zve10-ram-boot/rtos.bin"
#define ZVRT_CLIP_PATH "/log/zve10-ram-boot/clip.bin"
#define ZVRT_MAX_IMAGE_BYTES (1024 * 1024)
#define ZVRT_CLIP_MAX_BYTES (16 * 1024 * 1024)
#define ZVRT_ARENA_ORDER 4

static struct zvrt_handoff rtos_handoff;
static void *rtos_image;
static void *rtos_clip;
static unsigned long rtos_arena;

#ifdef ZVE10_RTOS_DISPLAY
#define ZVRT_FRAME_BYTES 614400

static int clean_display_frame(unsigned long pa)
{
    void *frame;

    switch (pa) {
    case 0x1968f000:
    case 0x19725000:
    case 0x197bb000:
    case 0x19851000:
        break;
    default:
        return -ERANGE;
    }
    frame = __va(pa);
    dmac_flush_range(frame, frame + ZVRT_FRAME_BYTES);
    outer_clean_range(pa, pa + ZVRT_FRAME_BYTES);
    dsb();
    return 0;
}
#endif

static int rtos_read_exact(struct file *file, loff_t offset, void *output,
                           unsigned long length)
{
    unsigned long done = 0;
    char *bytes = output;
    int n;

    while (done < length) {
        n = kernel_read(file, offset + done, bytes + done, length - done);
        if (n < 0)
            return n;
        if (!n)
            return -ENOEXEC;
        done += n;
    }
    return 0;
}

static void release_rtos(void)
{
    memset(&rtos_handoff, 0, sizeof(rtos_handoff));
    if (rtos_clip)
        vfree(rtos_clip);
    if (rtos_arena)
        free_pages(rtos_arena, ZVRT_ARENA_ORDER);
    if (rtos_image)
        free_code(NULL, rtos_image);
    rtos_clip = NULL;
    rtos_arena = 0;
    rtos_image = NULL;
}

static int load_optional_clip(void)
{
    struct file *file;
    loff_t size;
    int result;

    file = filp_open(ZVRT_CLIP_PATH, O_RDONLY | O_NOFOLLOW | O_NONBLOCK, 0);
    if (IS_ERR(file)) {
        int err = PTR_ERR(file);
        return err == -ENOENT ? 0 : err;
    }
    result = -ENOEXEC;
    if (!S_ISREG(file->f_path.dentry->d_inode->i_mode))
        goto out;
    size = i_size_read(file->f_path.dentry->d_inode);
    if (size <= 0 || size > ZVRT_CLIP_MAX_BYTES) {
        result = -EFBIG;
        goto out;
    }
    rtos_clip = vmalloc((unsigned long)size);
    if (!rtos_clip) {
        result = -ENOMEM;
        goto out;
    }
    result = rtos_read_exact(file, 0, rtos_clip, (unsigned long)size);
    if (result) {
        vfree(rtos_clip);
        rtos_clip = NULL;
        goto out;
    }
    rtos_handoff.flags |= ZVRT_CLIP_LOADED;
    rtos_handoff.bytes = ZVRT_H_CLIP_SIZE;
    rtos_handoff.clip_va = (unsigned long)rtos_clip;
    rtos_handoff.clip_bytes = (unsigned long)size;
out:
    filp_close(file, NULL);
    return result;
}

static int prepare_rtos(void)
{
    struct zvrt_image_header header;
    struct file *file;
    unsigned long arena_bytes = PAGE_SIZE << ZVRT_ARENA_ORDER;
    unsigned long arena_pa;
    unsigned long region = (unsigned long)&info >> 20;
    int result;
    char extra;

    BUILD_BUG_ON(sizeof(header) != ZVRT_HEADER_BYTES);
    BUILD_BUG_ON(sizeof(rtos_handoff) != ZVRT_H_CLIP_SIZE);
    BUILD_BUG_ON(offsetof(struct zvrt_handoff, clean_frame) != ZVRT_H_CLEAN_FRAME);
    BUILD_BUG_ON(offsetof(struct zvrt_handoff, clip_va) != ZVRT_H_CLIP_VA);
    BUILD_BUG_ON(offsetof(struct boot_info, rtos_entry) != 40);
    BUILD_BUG_ON(offsetof(struct boot_info, rtos_context) != 44);

    file = filp_open(ZVRT_IMAGE_PATH, O_RDONLY | O_NOFOLLOW | O_NONBLOCK, 0);
    if (IS_ERR(file))
        return PTR_ERR(file);

    result = -ENOEXEC;
    if (!S_ISREG(file->f_path.dentry->d_inode->i_mode))
        goto close;

    result = rtos_read_exact(file, 0, &header, sizeof(header));
    if (result)
        goto close;
    result = -ENOEXEC;
    if (!zvrt_image_valid(&header, ZVRT_MAX_IMAGE_BYTES))
        goto close;
    if (i_size_read(file->f_path.dentry->d_inode) !=
        sizeof(header) + header.image_bytes)
        goto close;

    result = -ENOMEM;
    rtos_image = allocate_code(PAGE_ALIGN(header.image_bytes));
    rtos_arena = __get_free_pages(GFP_KERNEL | __GFP_ZERO, ZVRT_ARENA_ORDER);
    if (!rtos_image || !rtos_arena)
        goto close;

    arena_pa = __pa(rtos_arena);
    result = -ERANGE;
    if (((unsigned long)&rtos_handoff >> 20) != region ||
        !arena_pa || arena_pa > 0x40000000 - arena_bytes)
        goto close;

    result = rtos_read_exact(file, sizeof(header), rtos_image, header.image_bytes);
    if (result)
        goto close;
    result = kernel_read(file, sizeof(header) + header.image_bytes, &extra, 1);
    if (result > 0)
        result = -ENOEXEC;
    if (result)
        goto close;
    if ((crc32_le(~0U, rtos_image, header.image_bytes) ^ ~0U) != header.crc32) {
        result = -EBADMSG;
        goto close;
    }

    flush_icache_range((unsigned long)rtos_image,
                       (unsigned long)rtos_image + header.image_bytes);
    rtos_handoff.magic = ZVRT_HANDOFF_MAGIC;
    rtos_handoff.version = ZVRT_ABI_VERSION;
    rtos_handoff.bytes = ZVRT_H_SIZE;
    rtos_handoff.flags = ZVRT_OWNED_ARENA;
    rtos_handoff.arena_va = rtos_arena;
    rtos_handoff.arena_pa = arena_pa;
    rtos_handoff.arena_bytes = arena_bytes;
    if (header.flags == ZVRT_IMAGE_DISPLAY) {
#ifdef ZVE10_RTOS_DISPLAY
        rtos_handoff.flags |= ZVRT_DISPLAY_REUSE;
        rtos_handoff.bytes = ZVRT_H_DISPLAY_SIZE;
        rtos_handoff.clean_frame = (unsigned long)clean_display_frame;
        rtos_handoff.frame_bytes = ZVRT_FRAME_BYTES;
        result = load_optional_clip();
        if (result)
            goto close;
#else
        result = -EOPNOTSUPP;
        goto close;
#endif
    }
    info.rtos_entry = (unsigned long)rtos_image + header.entry_offset;
    info.rtos_context = (unsigned long)&rtos_handoff;
    printk(KERN_INFO "ZVBOOT_STAGE_RTOS bytes=%u arena=%lx size=%lu flags=owned-arena\n",
           header.image_bytes, arena_pa, arena_bytes);
close:
    filp_close(file, NULL);
    return result;
}

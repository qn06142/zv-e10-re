/*
 * Sony CXD90045 (ZV-E10) VPH / OSD0 Display Controller (0xf3440000, VSYNC IRQ 102),
 * ADC0/ADC1 (0xf2406000 / 0xf2407000), and GPIO (0xf2910000).
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_ARM_ZVE10_OSD_H
#define HW_ARM_ZVE10_OSD_H

#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "qemu/log.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "hw/core/irq.h"
#include "hw/core/sysbus.h"
#include "system/address-spaces.h"
#include "ui/console.h"
#include "ui/surface.h"

#define TYPE_ZVE10_OSD "sony-vph-osd0"
OBJECT_DECLARE_SIMPLE_TYPE(Zve10OsdState, ZVE10_OSD)

#define ZVE10_OSD_MMIO_SIZE     0x7000
#define ZVE10_OSD_WIDTH         640
#define ZVE10_OSD_HEIGHT        480
#define ZVE10_OSD_DEFAULT_PITCH (ZVE10_OSD_WIDTH * 2)
#define ZVE10_OSD_VSYNC_NS      (NANOSECONDS_PER_SECOND / 50) /* 50 Hz (20 ms) */

typedef struct Zve10OsdState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq;
    QemuConsole *con;
    QEMUTimer *vsync_timer;

    uint32_t regs[ZVE10_OSD_MMIO_SIZE / 4];
    uint32_t latched_startadrs;
    bool invalidate;
} Zve10OsdState;

static void zve10_osd_reset_regs(Zve10OsdState *s)
{
    memset(s->regs, 0, sizeof(s->regs));
    s->regs[0x0000 / 4] = 0x00000001U;
    s->regs[0x0004 / 4] = 0x00000000U;
    s->regs[0x0144 / 4] = 0x02000232U;
    s->regs[0x0404 / 4] = 0x00000000U;
    s->regs[0x042c / 4] = 0x000001e0U;
    s->regs[0x1300 / 4] = 0x00000002U; /* OSD0_CTRL: enabled, idle (2) */
    s->regs[0x1304 / 4] = 0x01e00500U; /* OSD0_READSIZE: 480 lines, 1280 B/line */
    s->regs[0x130c / 4] = 0x01e00280U; /* 480 << 16 | 640 */
    s->regs[0x1310 / 4] = 0x04a00000U; /* OSD0_CUR_DMA */
    s->regs[0x1318 / 4] = 0x000000ffU;
    s->regs[0x1320 / 4] = 0x04a00000U; /* OSD0_STARTADRS default bootMonitor FB */
    s->regs[0x1324 / 4] = ZVE10_OSD_DEFAULT_PITCH; /* OSD0_LINELEN = 1280 */
    s->regs[0x5000 / 4] = 0x00010114U;
    s->regs[0x6000 / 4] = 0x00000000U;
    s->latched_startadrs = 0x04a00000U;
    s->invalidate = true;
}

static hwaddr zve10_osd_resolve_pa(uint32_t addr)
{
    if (addr >= 0x60000000U && addr < 0xa0000000U) {
        return (hwaddr)(addr - 0x60000000U);
    }
    return (hwaddr)addr;
}

static bool zve10_osd_update_display(void *opaque)
{
    Zve10OsdState *s = ZVE10_OSD(opaque);
    if (!s->con) {
        return true;
    }

    DisplaySurface *surface = qemu_console_surface(s->con);
    if (!surface ||
        surface_width(surface) != ZVE10_OSD_WIDTH ||
        surface_height(surface) != ZVE10_OSD_HEIGHT) {
        qemu_console_resize(s->con, ZVE10_OSD_WIDTH, ZVE10_OSD_HEIGHT);
        surface = qemu_console_surface(s->con);
        if (!surface) {
            return true;
        }
    }

    uint32_t raw_addr = s->latched_startadrs ? s->latched_startadrs : s->regs[0x1320 / 4];
    hwaddr fb_pa = zve10_osd_resolve_pa(raw_addr);
    uint32_t pitch = s->regs[0x1324 / 4];
    if (pitch < ZVE10_OSD_DEFAULT_PITCH || pitch > 4096U) {
        pitch = ZVE10_OSD_DEFAULT_PITCH;
    }

    uint8_t *dst_base = (uint8_t *)surface_data(surface);
    int dst_stride = surface_stride(surface);

    if (fb_pa != 0 && (s->regs[0x1300 / 4] & 0x03U) != 0) {
        uint8_t line_buf[ZVE10_OSD_DEFAULT_PITCH];
        for (int y = 0; y < ZVE10_OSD_HEIGHT; y++) {
            uint32_t *dst_row = (uint32_t *)(dst_base + y * dst_stride);
            if (address_space_read(&address_space_memory,
                                   fb_pa + (hwaddr)y * pitch,
                                   MEMTXATTRS_UNSPECIFIED,
                                   line_buf,
                                   sizeof(line_buf)) == MEMTX_OK) {
                for (int x = 0; x < ZVE10_OSD_WIDTH; x++) {
                    uint16_t px = lduw_le_p(line_buf + x * 2);
                    uint32_t r = ((px >> 12) & 0x0fU) * 17U;
                    uint32_t g = ((px >> 8) & 0x0fU) * 17U;
                    uint32_t b = ((px >> 4) & 0x0fU) * 17U;
                    dst_row[x] = (0xffU << 24) | (r << 16) | (g << 8) | b;
                }
            }
        }
    } else if (s->invalidate) {
        for (int y = 0; y < ZVE10_OSD_HEIGHT; y++) {
            memset(dst_base + y * dst_stride, 0, ZVE10_OSD_WIDTH * sizeof(uint32_t));
        }
    }

    qemu_console_update_full(s->con);
    s->invalidate = false;
    return true;
}

static void zve10_osd_invalidate_display(void *opaque)
{
    Zve10OsdState *s = ZVE10_OSD(opaque);
    s->invalidate = true;
}

static const GraphicHwOps zve10_osd_gfx_ops = {
    .invalidate = zve10_osd_invalidate_display,
    .gfx_update = zve10_osd_update_display,
};

static void zve10_osd_vsync_tick(void *opaque)
{
    Zve10OsdState *s = ZVE10_OSD(opaque);

    if (s->regs[0x1300 / 4] & 0x01U) {
        if (s->regs[0x1320 / 4] != 0) {
            s->latched_startadrs = s->regs[0x1320 / 4];
            s->regs[0x1310 / 4] = s->latched_startadrs;
        }
        /* Transition OSD0_CTRL 3 -> 2 on scanout/VSYNC */
        s->regs[0x1300 / 4] = (s->regs[0x1300 / 4] & ~0x01U) | 0x02U;
        s->invalidate = true;
    }

    if (s->invalidate && s->con) {
        zve10_osd_update_display(s);
    }

    s->regs[0x0004 / 4] |= 0x00000001U;
    if (s->irq) {
        qemu_irq_pulse(s->irq);
    }

    timer_mod(s->vsync_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + ZVE10_OSD_VSYNC_NS);
}

static uint64_t zve10_osd_read(void *opaque, hwaddr off, unsigned size)
{
    Zve10OsdState *s = ZVE10_OSD(opaque);
    if (off >= ZVE10_OSD_MMIO_SIZE) {
        return 0;
    }
    uint32_t value = s->regs[off / 4];
    unsigned shift = (off & 3) * 8;
    uint32_t mask = (size == 4) ? UINT32_MAX : ((1U << (size * 8)) - 1U);
    return (value >> shift) & mask;
}

static void zve10_osd_write(void *opaque, hwaddr off, uint64_t value, unsigned size)
{
    Zve10OsdState *s = ZVE10_OSD(opaque);
    if (off >= ZVE10_OSD_MMIO_SIZE) {
        return;
    }
    unsigned shift = (off & 3) * 8;
    uint32_t mask = ((size == 4) ? UINT32_MAX : ((1U << (size * 8)) - 1U)) << shift;
    uint32_t shifted = ((uint32_t)value << shift) & mask;
    uint32_t reg_idx = off / 4;

    if (reg_idx == (0x0004 / 4)) {
        /* VSYNC status write-1-to-clear */
        s->regs[reg_idx] &= ~shifted;
        return;
    }

    s->regs[reg_idx] = (s->regs[reg_idx] & ~mask) | shifted;

    if (reg_idx == (0x1320 / 4)) {
        s->latched_startadrs = s->regs[0x1320 / 4];
        s->regs[0x1310 / 4] = s->latched_startadrs;
        s->invalidate = true;
    } else if (reg_idx == (0x1300 / 4)) {
        if (s->regs[0x1300 / 4] & 0x01U) {
            if (s->regs[0x1320 / 4] != 0) {
                s->latched_startadrs = s->regs[0x1320 / 4];
                s->regs[0x1310 / 4] = s->latched_startadrs;
            }
            s->invalidate = true;
            zve10_osd_update_display(s);
            /* Complete 3 -> 2 latch transition so polling loops also succeed */
            s->regs[0x1300 / 4] = (s->regs[0x1300 / 4] & ~0x01U) | 0x02U;
        }
    }
}

static const MemoryRegionOps zve10_osd_ops = {
    .read = zve10_osd_read,
    .write = zve10_osd_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
};

static void zve10_osd_realize(DeviceState *dev, Error **errp)
{
    Zve10OsdState *s = ZVE10_OSD(dev);
    zve10_osd_reset_regs(s);
    s->con = qemu_graphic_console_create(dev, 0, &zve10_osd_gfx_ops, s);
    qemu_console_resize(s->con, ZVE10_OSD_WIDTH, ZVE10_OSD_HEIGHT);
    s->vsync_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, zve10_osd_vsync_tick, s);
    timer_mod(s->vsync_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + ZVE10_OSD_VSYNC_NS);
}

static void zve10_osd_reset(DeviceState *dev)
{
    Zve10OsdState *s = ZVE10_OSD(dev);
    zve10_osd_reset_regs(s);
    if (s->vsync_timer) {
        timer_mod(s->vsync_timer,
                  qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + ZVE10_OSD_VSYNC_NS);
    }
}

static void zve10_osd_init(Object *obj)
{
    Zve10OsdState *s = ZVE10_OSD(obj);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq);
    memory_region_init_io(&s->iomem, obj, &zve10_osd_ops, s,
                          TYPE_ZVE10_OSD, ZVE10_OSD_MMIO_SIZE);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->iomem);
}

static void zve10_osd_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    set_bit(DEVICE_CATEGORY_DISPLAY, dc->categories);
    dc->realize = zve10_osd_realize;
    device_class_set_legacy_reset(dc, zve10_osd_reset);
}

static const TypeInfo zve10_osd_info = {
    .name = TYPE_ZVE10_OSD,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Zve10OsdState),
    .instance_init = zve10_osd_init,
    .class_init = zve10_osd_class_init,
};

static void zve10_osd_register_types(void)
{
    type_register_static(&zve10_osd_info);
}

type_init(zve10_osd_register_types)

/*
 * Sony ZV-E10 ADC0 (0xf2406000) / ADC1 (0xf2407000) and GPIO (0xf2910000)
 */
typedef struct Zve10Adc {
    MemoryRegion mmio;
    uint32_t regs[0x1000 / 4];
} Zve10Adc;

static void zve10_adc_reset(Zve10Adc *s)
{
    memset(s->regs, 0, sizeof(s->regs));
    s->regs[0x10 / 4] = 0x00000000U; /* ADC_BUSY = 0 (ready) */
    s->regs[0x14 / 4] = 0x000003f0U; /* ch0 neutral */
    s->regs[0x18 / 4] = 0x00000004U; /* STATUS ready bit 2 */
    s->regs[0x1c / 4] = 0x000003f0U; /* ch2 neutral */
    s->regs[0x20 / 4] = 0x000003f0U; /* ch0 / ch3 neutral (10-bit idle) */
    s->regs[0x24 / 4] = 0x000003f0U; /* ch1 neutral */
    s->regs[0x28 / 4] = 0x000003f0U; /* ch2 neutral */
    s->regs[0x2c / 4] = 0x000003f0U; /* ch3 neutral */
}

static uint64_t zve10_adc_read(void *opaque, hwaddr off, unsigned size)
{
    Zve10Adc *s = opaque;
    if (off >= sizeof(s->regs)) {
        return 0;
    }
    uint32_t value = s->regs[off / 4];
    unsigned shift = (off & 3) * 8;
    uint32_t mask = (size == 4) ? UINT32_MAX : ((1U << (size * 8)) - 1U);
    return (value >> shift) & mask;
}

static void zve10_adc_write(void *opaque, hwaddr off, uint64_t value, unsigned size)
{
    Zve10Adc *s = opaque;
    if (off >= sizeof(s->regs)) {
        return;
    }
    unsigned shift = (off & 3) * 8;
    uint32_t mask = ((size == 4) ? UINT32_MAX : ((1U << (size * 8)) - 1U)) << shift;
    uint32_t shifted = ((uint32_t)value << shift) & mask;
    uint32_t idx = off / 4;

    s->regs[idx] = (s->regs[idx] & ~mask) | shifted;
    if (idx == (0x04 / 4)) {
        /* ADC_TRG: conversion completes immediately */
        s->regs[0x04 / 4] = 0;
        s->regs[0x10 / 4] = 0;
        s->regs[0x18 / 4] |= 0x04U;
    }
}

static const MemoryRegionOps zve10_adc_ops = {
    .read = zve10_adc_read,
    .write = zve10_adc_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
};

typedef struct Zve10Gpio {
    MemoryRegion mmio;
    uint32_t regs[0x1000 / 4];
} Zve10Gpio;

static void zve10_gpio_reset(Zve10Gpio *s)
{
    memset(s->regs, 0, sizeof(s->regs));
    s->regs[0x00 / 4] = 0x00000400U; /* Neutral button state */
    s->regs[0x10 / 4] = 0x00000000U; /* Neutral G00 state */
}

static uint64_t zve10_gpio_read(void *opaque, hwaddr off, unsigned size)
{
    Zve10Gpio *s = opaque;
    if (off >= sizeof(s->regs)) {
        return 0;
    }
    uint32_t value = s->regs[off / 4];
    unsigned shift = (off & 3) * 8;
    uint32_t mask = (size == 4) ? UINT32_MAX : ((1U << (size * 8)) - 1U);
    return (value >> shift) & mask;
}

static void zve10_gpio_write(void *opaque, hwaddr off, uint64_t value, unsigned size)
{
    Zve10Gpio *s = opaque;
    if (off >= sizeof(s->regs)) {
        return;
    }
    unsigned shift = (off & 3) * 8;
    uint32_t mask = ((size == 4) ? UINT32_MAX : ((1U << (size * 8)) - 1U)) << shift;
    uint32_t shifted = ((uint32_t)value << shift) & mask;
    uint32_t idx = off / 4;

    s->regs[idx] = (s->regs[idx] & ~mask) | shifted;
    if (idx == (0x44 / 4)) {
        s->regs[0x40 / 4] |= (uint32_t)value;
    } else if (idx == (0x48 / 4)) {
        s->regs[0x40 / 4] &= ~(uint32_t)value;
    }
}

static const MemoryRegionOps zve10_gpio_ops = {
    .read = zve10_gpio_read,
    .write = zve10_gpio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
};

#endif /* HW_ARM_ZVE10_OSD_H */

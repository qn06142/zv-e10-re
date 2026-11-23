/*
 * Sony CXD90045 (ZV-E10) eMMC Fujitsu f_sdh30 SDHCI controller (0xf0304000, IRQ 227)
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_ARM_ZVE10_EMMC_H
#define HW_ARM_ZVE10_EMMC_H

#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "qemu/log.h"
#include "qapi/error.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-properties.h"
#include "hw/core/qdev-properties-system.h"
#include "hw/core/sysbus.h"
#include "system/address-spaces.h"
#include "system/block-backend.h"
#include "system/blockdev.h"

#define TYPE_ZVE10_EMMC "sony-f-sdh30"
OBJECT_DECLARE_SIMPLE_TYPE(Zve10EmmcState, ZVE10_EMMC)

#define ZVE10_EMMC_MMIO_SIZE    0x1000
#define ZVE10_EMMC_SECTOR_SIZE  512
#define ZVE10_EMMC_BOOT_SIZE    (2 * MiB)

typedef struct Zve10EmmcState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq;
    BlockBackend *blk;

    uint32_t regs[ZVE10_EMMC_MMIO_SIZE / 4];
    uint8_t ext_csd[512];
    uint32_t total_sectors;
    uint32_t rca;
    bool block_addressed;
} Zve10EmmcState;

static void zve10_emmc_update_irq(Zve10EmmcState *s)
{
    uint32_t stat = s->regs[0x30 / 4];
    uint32_t sig = s->regs[0x38 / 4];
    qemu_set_irq(s->irq, (stat & sig) != 0);
}

static void zve10_emmc_set_r2_response(Zve10EmmcState *s,
                                       uint32_t w3, uint32_t w2,
                                       uint32_t w1, uint32_t w0)
{
    /*
     * SDHCI stores bits [127:8] in RESPONSE[3..0] shifted right by 8;
     * emmc.ko resp_shift() shifts left by 8 and sets bit 0 = 1.
     */
    s->regs[0x10 / 4] = (w0 >> 8) | ((w1 & 0xffU) << 24);
    s->regs[0x14 / 4] = (w1 >> 8) | ((w2 & 0xffU) << 24);
    s->regs[0x18 / 4] = (w2 >> 8) | ((w3 & 0xffU) << 24);
    s->regs[0x1c / 4] = (w3 >> 8);
}

static void zve10_emmc_init_ext_csd(Zve10EmmcState *s)
{
    memset(s->ext_csd, 0, sizeof(s->ext_csd));
    s->ext_csd[61] = 0;      /* INI_TIMEOUT_EMU (must be 0 for emmc.ko) */
    s->ext_csd[161] = 1;     /* HPI_MGMT */
    s->ext_csd[175] = 0;     /* ERASE_GROUP_DEF */
    s->ext_csd[179] = 0x08;  /* PARTITION_CONFIG: Boot Part 1 enabled, User access */
    s->ext_csd[183] = 2;     /* BUS_WIDTH: 8-bit */
    s->ext_csd[185] = 2;     /* HS_TIMING: HS200 */
    s->ext_csd[192] = 7;     /* EXT_CSD_REV: v1.7 (eMMC 5.0) */
    s->ext_csd[196] = 0x17;  /* DEVICE_TYPE: HS200 + HS 26/52MHz + DDR */
    s->ext_csd[199] = 1;     /* PART_SWITCH_TIME */
    stl_le_p(&s->ext_csd[212], s->total_sectors);
    s->ext_csd[216] = 1;     /* SLEEP_NOTIFICATION_TIME */
    s->ext_csd[217] = 1;     /* S_A_TIMEOUT */
    s->ext_csd[224] = 1;     /* HC_ERASE_GRP_SIZE (512 KiB = 1024 sectors) */
    s->ext_csd[226] = 16;    /* BOOT_SIZE_MULT (2 MiB) */
    s->ext_csd[231] = 0x40;  /* SEC_FEATURE_SUPPORT */
    s->ext_csd[232] = 1;     /* SEC_TRIM_MULT */
    s->ext_csd[247] = 10;    /* POWER_OFF_LONG_TIME */
    s->ext_csd[248] = 10;    /* GENERIC_CMD6_TIME */
}

static void zve10_emmc_reset_regs(Zve10EmmcState *s)
{
    memset(s->regs, 0, sizeof(s->regs));
    s->regs[0x24 / 4] = 0x01f70000U; /* Card inserted, WP, DAT lines high */
    s->regs[0x28 / 4] = 0x00000030U; /* 8-bit bus width (0x20) + ADMA2 32-bit (0x10) */
    s->regs[0x2c / 4] = 0x000e0003U; /* Internal clk enabled & stable */
    s->regs[0x40 / 4] = 0x05e834b4U; /* CAPABILITIES: bit 19 ADMA2, HS, 3.3V/1.8V */
    s->regs[0x44 / 4] = 0x00008000U; /* CAPABILITIES2: bits 15:14 = 2 */
    s->regs[0xfc / 4] = 0x10020000U; /* Host Controller v3.0 */
    s->regs[0x108 / 4] = 0x00000000U;
    s->regs[0x10c / 4] = 0x00080000U;
    s->regs[0x124 / 4] = 0x01000000U; /* Mode 0 (HS200) for sdhci_emmc_dev_probe */
    s->regs[0x158 / 4] = 0x00000040U;
    s->rca = 1;
    zve10_emmc_init_ext_csd(s);
    zve10_emmc_update_irq(s);
}

static bool zve10_emmc_adma_mem(Zve10EmmcState *s, const uint8_t *buf, uint32_t buf_len)
{
    hwaddr desc_addr = s->regs[0x58 / 4];
    uint32_t offset = 0;

    for (int i = 0; i < 4096; i++) {
        uint8_t desc[8];
        if (address_space_read(&address_space_memory, desc_addr,
                               MEMTXATTRS_UNSPECIFIED, desc, sizeof(desc)) != MEMTX_OK) {
            return false;
        }
        uint16_t attr = lduw_le_p(desc);
        uint32_t len = lduw_le_p(desc + 2);
        uint32_t addr = ldl_le_p(desc + 4);
        if (!(attr & 0x01)) {
            break;
        }
        uint8_t act = (attr >> 4) & 0x03;
        if (act == 2) {
            uint32_t xlen = (len == 0) ? 65536 : len;
            uint32_t chunk = (offset < buf_len) ? MIN(xlen, buf_len - offset) : 0;
            if (chunk > 0) {
                address_space_write(&address_space_memory, addr,
                                    MEMTXATTRS_UNSPECIFIED, buf + offset, chunk);
            }
            if (chunk < xlen) {
                g_autofree uint8_t *zeros = g_malloc0(xlen - chunk);
                address_space_write(&address_space_memory, addr + chunk,
                                    MEMTXATTRS_UNSPECIFIED, zeros, xlen - chunk);
            }
            offset += xlen;
            desc_addr += 8;
        } else if (act == 3) {
            desc_addr = addr;
        } else {
            desc_addr += 8;
        }
        if (attr & 0x02) {
            break;
        }
    }
    return true;
}

static bool zve10_emmc_adma_blk(Zve10EmmcState *s, uint64_t disk_off, bool is_write)
{
    hwaddr desc_addr = s->regs[0x58 / 4];
    uint8_t part_cfg = s->ext_csd[179] & 0x07;
    int64_t disk_len = s->blk ? blk_getlength(s->blk) : 0;

    for (int i = 0; i < 4096; i++) {
        uint8_t desc[8];
        if (address_space_read(&address_space_memory, desc_addr,
                               MEMTXATTRS_UNSPECIFIED, desc, sizeof(desc)) != MEMTX_OK) {
            return false;
        }
        uint16_t attr = lduw_le_p(desc);
        uint32_t len = lduw_le_p(desc + 2);
        uint32_t addr = ldl_le_p(desc + 4);
        if (!(attr & 0x01)) {
            break;
        }
        uint8_t act = (attr >> 4) & 0x03;
        if (act == 2) {
            uint32_t xlen = (len == 0) ? 65536 : len;
            g_autofree uint8_t *tmp = g_malloc0(xlen);

            if (is_write) {
                address_space_read(&address_space_memory, addr,
                                   MEMTXATTRS_UNSPECIFIED, tmp, xlen);
                if (part_cfg == 0 && s->blk && (int64_t)(disk_off + xlen) <= disk_len) {
                    blk_pwrite(s->blk, (int64_t)disk_off, (int64_t)xlen, tmp, 0);
                }
            } else {
                if (part_cfg == 0 && s->blk && (int64_t)disk_off < disk_len) {
                    int64_t avail = MIN((int64_t)xlen, disk_len - (int64_t)disk_off);
                    blk_pread(s->blk, (int64_t)disk_off, avail, tmp, 0);
                }
                address_space_write(&address_space_memory, addr,
                                    MEMTXATTRS_UNSPECIFIED, tmp, xlen);
            }
            disk_off += xlen;
            desc_addr += 8;
        } else if (act == 3) {
            desc_addr = addr;
        } else {
            desc_addr += 8;
        }
        if (attr & 0x02) {
            break;
        }
    }
    return true;
}

static void zve10_emmc_exec_command(Zve10EmmcState *s)
{
    uint16_t cmd_reg = (uint16_t)(s->regs[0x0c / 4] >> 16);
    uint8_t cmd_idx = (cmd_reg >> 8) & 0x3fU;
    uint32_t arg = s->regs[0x08 / 4];
    bool has_data = (cmd_reg & 0x20U) != 0;
    uint32_t r1_done = ((cmd_reg & 0x03U) == 0x03U) ? 0x0003U : 0x0001U;
    uint64_t byte_off = s->block_addressed
        ? (uint64_t)arg * ZVE10_EMMC_SECTOR_SIZE
        : (uint64_t)arg;

    switch (cmd_idx) {
    case 0: /* GO_IDLE_STATE */
        s->regs[0x10 / 4] = 0;
        s->regs[0x30 / 4] |= 0x0001;
        break;
    case 1: /* SEND_OP_COND */
        s->regs[0x10 / 4] = 0xc0ff8080U; /* Ready, High-Capacity Sector Mode */
        s->regs[0x30 / 4] |= 0x0001;
        break;
    case 2: /* ALL_SEND_CID */
    case 10: /* SEND_CID */
        zve10_emmc_set_r2_response(s, 0x1501005aU, 0x56453130U, 0x01010203U, 0x04050601U);
        s->regs[0x30 / 4] |= 0x0001;
        break;
    case 3: /* SET_RELATIVE_ADDR */
        s->rca = (arg >> 16) ? (arg >> 16) : 1;
        s->regs[0x10 / 4] = 0x00000500U;
        s->regs[0x30 / 4] |= 0x0001;
        break;
    case 6: /* SWITCH */ {
        uint8_t access = (arg >> 24) & 0x03U;
        uint8_t index = (arg >> 16) & 0xffU;
        uint8_t value = (arg >> 8) & 0xffU;
        if (access == 3) {
            s->ext_csd[index] = value;
        } else if (access == 1) {
            s->ext_csd[index] |= value;
        } else if (access == 2) {
            s->ext_csd[index] &= ~value;
        }
        s->regs[0x10 / 4] = 0x00000900U; /* TRAN | READY_FOR_DATA */
        s->regs[0x30 / 4] |= r1_done;
        break;
    }
    case 7: /* SELECT_DESELECT_CARD */
        s->regs[0x10 / 4] = 0x00000700U;
        s->regs[0x30 / 4] |= r1_done;
        break;
    case 8: /* SEND_EXT_CSD */
        s->regs[0x10 / 4] = 0x00000900U;
        if (has_data) {
            zve10_emmc_adma_mem(s, s->ext_csd, sizeof(s->ext_csd));
            s->regs[0x30 / 4] |= 0x0003;
        } else {
            s->regs[0x30 / 4] |= 0x0001;
        }
        break;
    case 9: /* SEND_CSD */
        zve10_emmc_set_r2_response(s, 0xd0270132U, 0x0f5903ffU, 0xffffffffU, 0x92404001U);
        s->regs[0x30 / 4] |= 0x0001;
        break;
    case 12: /* STOP_TRANSMISSION */
    case 13: /* SEND_STATUS */
    case 16: /* SET_BLOCKLEN */
    case 23: /* SET_BLOCK_COUNT */
    case 35: /* ERASE_GROUP_START */
    case 36: /* ERASE_GROUP_END */
    case 38: /* ERASE */
        s->regs[0x10 / 4] = 0x00000900U;
        s->regs[0x30 / 4] |= r1_done;
        break;
    case 17: /* READ_SINGLE_BLOCK */
    case 18: /* READ_MULTIPLE_BLOCK */
        s->regs[0x10 / 4] = 0x00000900U;
        if (has_data) {
            zve10_emmc_adma_blk(s, byte_off, false);
        }
        s->regs[0x30 / 4] |= 0x0003;
        break;
    case 24: /* WRITE_BLOCK */
    case 25: /* WRITE_MULTIPLE_BLOCK */
        s->regs[0x10 / 4] = 0x00000900U;
        if (has_data) {
            zve10_emmc_adma_blk(s, byte_off, true);
        }
        s->regs[0x30 / 4] |= 0x0003;
        break;
    case 21: /* SEND_TUNING_BLOCK */ {
        static const uint8_t tuning_pat[128] = {
            0xff, 0x0f, 0xff, 0x00, 0xff, 0xcc, 0xc3, 0xcc,
            0xc3, 0x3c, 0xcc, 0xff, 0xfe, 0xff, 0xfe, 0xef,
            0xff, 0xdf, 0xff, 0xdd, 0xff, 0xfb, 0xff, 0xfb,
            0xbf, 0xff, 0x7f, 0xff, 0x77, 0xf7, 0xbd, 0xef,
            0xff, 0xf0, 0xff, 0xf0, 0x0f, 0xfc, 0xcc, 0x3c,
            0xcc, 0x33, 0xcc, 0xcf, 0xff, 0xef, 0xff, 0xee,
            0xff, 0xfd, 0xff, 0xfd, 0xdf, 0xff, 0xbf, 0xff,
            0xbb, 0xff, 0xf7, 0xff, 0xf7, 0x7f, 0x7b, 0xde,
            0xff, 0x0f, 0xff, 0x00, 0xff, 0xcc, 0xc3, 0xcc,
            0xc3, 0x3c, 0xcc, 0xff, 0xfe, 0xff, 0xfe, 0xef,
            0xff, 0xdf, 0xff, 0xdd, 0xff, 0xfb, 0xff, 0xfb,
            0xbf, 0xff, 0x7f, 0xff, 0x77, 0xf7, 0xbd, 0xef,
            0xff, 0xf0, 0xff, 0xf0, 0x0f, 0xfc, 0xcc, 0x3c,
            0xcc, 0x33, 0xcc, 0xcf, 0xff, 0xef, 0xff, 0xee,
            0xff, 0xfd, 0xff, 0xfd, 0xdf, 0xff, 0xbf, 0xff,
            0xbb, 0xff, 0xf7, 0xff, 0xf7, 0x7f, 0x7b, 0xde,
        };
        s->regs[0x10 / 4] = 0x00000900U;
        if (has_data) {
            zve10_emmc_adma_mem(s, tuning_pat, sizeof(tuning_pat));
        }
        s->regs[0x3c / 4] &= ~(0x0040U << 16); /* Complete EXECUTE_TUNING */
        s->regs[0x3c / 4] |= (0x0080U << 16);  /* Latch SAMPLING_CLOCK_SELECT */
        s->regs[0x30 / 4] |= 0x0023;
        break;
    }
    default:
        qemu_log_mask(LOG_UNIMP, "zve10-emmc: unhandled CMD%u arg=0x%08x\n", cmd_idx, arg);
        s->regs[0x10 / 4] = 0x00000900U;
        s->regs[0x30 / 4] |= 0x0001;
        break;
    }

    zve10_emmc_update_irq(s);
}

static uint64_t zve10_emmc_read(void *opaque, hwaddr off, unsigned size)
{
    Zve10EmmcState *s = opaque;
    if (off >= ZVE10_EMMC_MMIO_SIZE) {
        return 0;
    }
    uint32_t value = s->regs[off / 4];
    unsigned shift = (off & 3) * 8;
    uint32_t mask = (size == 4) ? UINT32_MAX : ((1U << (size * 8)) - 1U);
    return (value >> shift) & mask;
}

static void zve10_emmc_write(void *opaque, hwaddr off, uint64_t value, unsigned size)
{
    Zve10EmmcState *s = opaque;
    if (off >= ZVE10_EMMC_MMIO_SIZE) {
        return;
    }
    unsigned shift = (off & 3) * 8;
    uint32_t mask = ((size == 4) ? UINT32_MAX : ((1U << (size * 8)) - 1U)) << shift;
    uint32_t shifted = ((uint32_t)value << shift) & mask;
    uint32_t reg_idx = off / 4;

    if (reg_idx == (0x30 / 4)) {
        /* INT_STATUS and ERR_INT_STATUS are Write-1-to-Clear */
        s->regs[reg_idx] &= ~shifted;
        zve10_emmc_update_irq(s);
        return;
    }

    s->regs[reg_idx] = (s->regs[reg_idx] & ~mask) | shifted;

    if (reg_idx == (0x2c / 4)) {
        uint32_t v = s->regs[reg_idx];
        if (v & 0x00000001U) {
            v |= 0x00000002U; /* INTERNAL_CLOCK_STABLE */
        } else {
            v &= ~0x00000002U;
        }
        if (v & 0x01000000U) {
            /* SW_RESET_ALL */
            s->regs[reg_idx] = (v & ~0x07000000U);
            s->regs[0x30 / 4] = 0;
            zve10_emmc_update_irq(s);
            return;
        }
        v &= ~0x07000000U; /* All SW_RESET bits self-clear */
        s->regs[reg_idx] = v;
    } else if (reg_idx == (0x3c / 4)) {
        /*
         * HOST_CONTROL2 at +0x3e (bits 31:16 of reg 0x3c): keep EXECUTE_TUNING
         * (0x40) latched when written so start_tuning/stop_tuning polling works.
         */
    } else if (reg_idx == (0x38 / 4)) {
        zve10_emmc_update_irq(s);
    } else if (reg_idx == (0x108 / 4)) {
        s->regs[0x10c / 4] = ((s->regs[0x108 / 4] & 0xffU) << 16) | 0x08U;
    }

    if (off < 0x10 && (off + size) > 0x0e) {
        zve10_emmc_exec_command(s);
    }
}

static const MemoryRegionOps zve10_emmc_ops = {
    .read = zve10_emmc_read,
    .write = zve10_emmc_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
};

static void zve10_emmc_realize(DeviceState *dev, Error **errp)
{
    Zve10EmmcState *s = ZVE10_EMMC(dev);

    if (s->blk) {
        if (blk_supports_write_perm(s->blk)) {
            if (blk_set_perm(s->blk, BLK_PERM_CONSISTENT_READ | BLK_PERM_WRITE,
                             BLK_PERM_ALL, errp) < 0) {
                return;
            }
        } else {
            if (blk_set_perm(s->blk, BLK_PERM_CONSISTENT_READ,
                             BLK_PERM_ALL, errp) < 0) {
                return;
            }
        }
        int64_t len = blk_getlength(s->blk);
        s->total_sectors = (len > 0) ? (uint32_t)(len / ZVE10_EMMC_SECTOR_SIZE) : 0x400000;
    } else {
        s->total_sectors = 0x400000;
    }
    s->block_addressed = true;
    zve10_emmc_reset_regs(s);
}

static void zve10_emmc_reset(DeviceState *dev)
{
    zve10_emmc_reset_regs(ZVE10_EMMC(dev));
}

static const Property zve10_emmc_properties[] = {
    DEFINE_PROP_DRIVE("drive", Zve10EmmcState, blk),
};

static void zve10_emmc_init(Object *obj)
{
    Zve10EmmcState *s = ZVE10_EMMC(obj);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq);
    memory_region_init_io(&s->iomem, obj, &zve10_emmc_ops, s,
                          TYPE_ZVE10_EMMC, ZVE10_EMMC_MMIO_SIZE);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->iomem);
}

static void zve10_emmc_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    dc->realize = zve10_emmc_realize;
    device_class_set_legacy_reset(dc, zve10_emmc_reset);
    device_class_set_props(dc, zve10_emmc_properties);
}

static const TypeInfo zve10_emmc_info = {
    .name = TYPE_ZVE10_EMMC,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Zve10EmmcState),
    .instance_init = zve10_emmc_init,
    .class_init = zve10_emmc_class_init,
};

static void zve10_emmc_register_types(void)
{
    type_register_static(&zve10_emmc_info);
}

type_init(zve10_emmc_register_types)

#endif /* HW_ARM_ZVE10_EMMC_H */

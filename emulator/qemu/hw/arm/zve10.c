/*
 * Sony ZV-E10 (CXD90045) machine model for QEMU 11.1.2.
 *
 * Copyright (c) 2026 pmca-re contributors
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/units.h"
#include "qemu/bswap.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "hw/arm/boot.h"
#include "hw/arm/machines-qom.h"
#include "hw/core/boards.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-properties.h"
#include "hw/core/sysbus.h"
#include "hw/char/pl011.h"
#include "hw/cpu/a9mpcore.h"
#include "hw/misc/unimp.h"
#include "qom/object.h"
#include "system/system.h"
#include "system/address-spaces.h"
#include "system/cpus.h"
#include "system/reset.h"
#include "target/arm/cpu-qom.h"
#include "zve10-emmc.h"
#include "zve10-gpe-init.h"
#include "zve10-osd.h"

#define ZVE10_MACHINE_ID    3497
#define ZVE10_MPCORE_BASE   0xf8000000
#define ZVE10_UART0_BASE    0xf2000000
#define ZVE10_UART0_IRQ     150
#define ZVE10_TIMER_BASE    0xf2403000
#define ZVE10_TIMER_IRQ     153
#define ZVE10_ADC0_BASE     0xf2406000
#define ZVE10_ADC1_BASE     0xf2407000
#define ZVE10_GPIO_BASE     0xf2910000
#define ZVE10_OSD_BASE      0xf3440000
#define ZVE10_OSD_IRQ       102
#define ZVE10_EMMC_BASE     0xf0304000
#define ZVE10_EMMC_IRQ      227
#define ZVE10_NUM_TIMERS    9 /* tick/sched 0..4, Sony UTM 5..8 */
#define ZVE10_RAM_BASE      0x00000000
#define ZVE10_DDR0_MAX      (1 * GiB)
#define ZVE10_DDR1_BASE     0x80000000
#define ZVE10_DDR1_SIZE     (256 * MiB)
#define ZVE10_LOADER_START  0x00000000 /* ATAGS at 0x100 */
#define ZVE10_SMP_LOADER    0xfe000000 /* In eSRAM, untouched by Linux mem_map/kernel */
#define ZVE10_SMP_BOOTREG   0xfe005010 /* CXD900X0_BOOTRAM_VEC + 4 (CPU#1) */

typedef struct Zve10MachineState {
    MachineState parent_obj;
    bool ddr1;
    bool strict_cpu;
    DeviceState *mpcore;
} Zve10MachineState;

#define TYPE_ZVE10_MACHINE MACHINE_TYPE_NAME("zve10")
OBJECT_DECLARE_SIMPLE_TYPE(Zve10MachineState, ZVE10_MACHINE)

static bool zve10_get_ddr1(Object *obj, Error **errp)
{
    return ZVE10_MACHINE(obj)->ddr1;
}

static void zve10_set_ddr1(Object *obj, bool value, Error **errp)
{
    ZVE10_MACHINE(obj)->ddr1 = value;
}

static bool zve10_get_strict_cpu(Object *obj, Error **errp)
{
    return ZVE10_MACHINE(obj)->strict_cpu;
}

static void zve10_set_strict_cpu(Object *obj, bool value, Error **errp)
{
    ZVE10_MACHINE(obj)->strict_cpu = value;
}

static uint64_t sugi_read(void *opaque, hwaddr off, unsigned size)
{
    /* grm_gles polls 0xf3400080 for the Sugilite power-up acknowledge. */
    return off == 0x80 ? 0x15 : 0;
}

static void sugi_write(void *opaque, hwaddr off, uint64_t value, unsigned size)
{
}

static const MemoryRegionOps sugi_ops = {
    .read = sugi_read,
    .write = sugi_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
};

typedef struct Zve10Gpe {
    MemoryRegion mmio;
    uint32_t regs[0x4000 / 4];
    qemu_irq irq;
} Zve10Gpe;

static uint64_t gpe_read(void *opaque, hwaddr off, unsigned size)
{
    Zve10Gpe *s = opaque;
    uint32_t value = s->regs[off / 4];
    return (value >> ((off & 3) * 8)) & (UINT32_MAX >> ((4 - size) * 8));
}

static void gpe_write(void *opaque, hwaddr off, uint64_t value, unsigned size)
{
    Zve10Gpe *s = opaque;
    unsigned shift = (off & 3) * 8;
    uint32_t mask = (UINT32_MAX >> ((4 - size) * 8)) << shift;
    s->regs[off / 4] = (s->regs[off / 4] & ~mask) | ((value << shift) & mask);
    if (off == 0x1000 && value == 0) {
        s->regs[0x34 / 4] &= ~0x80000000u;
        qemu_set_irq(s->irq, s->regs[0x34 / 4] != 0);
    }
    if (off == 0x1800 && value == 4) {
        uint8_t packet[128];
        uint32_t pointer = s->regs[0x1804 / 4];
        if (address_space_read(&address_space_memory, pointer,
                               MEMTXATTRS_UNSPECIFIED, packet, sizeof(packet)) == MEMTX_OK) {
            fprintf(stderr, "ZVE10_GPE_PACKET address=%08x", pointer);
            for (unsigned i = 0; i < sizeof(packet); i += 4) {
                fprintf(stderr, " %08x", ldl_le_p(packet + i));
            }
            fprintf(stderr, "\n");
            uint32_t words[8];
            for (unsigned i = 0; i < ARRAY_SIZE(words); ++i) {
                words[i] = ldl_le_p(packet + i * 4);
            }
            /* Only this captured startup fence completes; general GPU packets need a decoder. */
            if (zve10_gpe_init_packet(words)) {
                s->regs[0x1080 / 4] = words[7];
                s->regs[0x34 / 4] |= 0x80000000u;
                qemu_irq_raise(s->irq);
                fprintf(stderr, "ZVE10_GPE_INIT_FENCE irq=76 token=%08x\n", words[7]);
            }
        }
    }
    fprintf(stderr, "ZVE10_GPE off=%04" HWADDR_PRIx " val=%" PRIx64 " size=%u\n",
            off, value, size);
}

static const MemoryRegionOps gpe_ops = {
    .read = gpe_read,
    .write = gpe_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
};

static void zve10_init(MachineState *machine)
{
    Zve10MachineState *zms = ZVE10_MACHINE(machine);
    MemoryRegion *sysmem = get_system_memory();
    DeviceState *mpcore;
    qemu_irq pic[256 - 32];
    int i;

    if (machine->ram_size > 2 * GiB) {
        error_report("zve10: RAM size %" PRIu64 " exceeds 2 GiB DDR0+DDR1 limit",
                     (uint64_t)machine->ram_size);
        exit(1);
    }

    if (machine->ram_size > ZVE10_DDR0_MAX) {
        MemoryRegion *ddr0 = g_new(MemoryRegion, 1);
        MemoryRegion *ddr1 = g_new(MemoryRegion, 1);

        memory_region_init_alias(ddr0, NULL, "zve10.ddr0",
                                 machine->ram, 0, ZVE10_DDR0_MAX);
        memory_region_add_subregion(sysmem, ZVE10_RAM_BASE, ddr0);

        memory_region_init_alias(ddr1, NULL, "zve10.ddr1",
                                 machine->ram, ZVE10_DDR0_MAX,
                                 machine->ram_size - ZVE10_DDR0_MAX);
        memory_region_add_subregion(sysmem, ZVE10_DDR1_BASE, ddr1);
    } else {
        memory_region_add_subregion(sysmem, ZVE10_RAM_BASE, machine->ram);
        if (zms->ddr1) {
            MemoryRegion *ddr1 = g_new(MemoryRegion, 1);

            memory_region_init_ram(ddr1, NULL, "zve10.ddr1",
                                   ZVE10_DDR1_SIZE, &error_fatal);
            memory_region_add_subregion(sysmem, ZVE10_DDR1_BASE, ddr1);
        }
    }

    /*
     * 32 KiB eSRAM window backing the bootMonitor BOOTRAM work area
     * (0xfe005000..0xfe00501f). ej_head_init writes cxd900x0_secondary_entry
     * to 0xfe005010..0xfe005018 for CPUs 1..3.
     */
    {
        MemoryRegion *esram = g_new(MemoryRegion, 1);

        memory_region_init_ram(esram, NULL, "zve10.esram", 32 * KiB,
                               &error_fatal);
        memory_region_add_subregion_overlap(sysmem, 0xfe000000, esram, 1);
    }

    for (i = 0; i < machine->smp.cpus; i++) {
        Object *cpuobj = object_new(machine->cpu_type);

        object_property_set_bool(cpuobj, "has_el3", false, NULL);
        if (object_property_find(cpuobj, "has_el2")) {
            object_property_set_bool(cpuobj, "has_el2", false, NULL);
        }
        if (object_property_find(cpuobj, "reset-cbar")) {
            object_property_set_int(cpuobj, "reset-cbar", ZVE10_MPCORE_BASE,
                                    &error_abort);
        }
        /* CXD90045 Cortex-A9 uses VFPv3-D16 without NEON (stock CONFIG_VFPD16=y). */
        if (zms->strict_cpu && object_property_find(cpuobj, "neon")) {
            object_property_set_bool(cpuobj, "neon", false, &error_abort);
        }
        if (zms->strict_cpu && object_property_find(cpuobj, "vfp-d32")) {
            object_property_set_bool(cpuobj, "vfp-d32", false, &error_abort);
        }
        qdev_realize(DEVICE(cpuobj), NULL, &error_fatal);
    }

    mpcore = qdev_new(TYPE_A9MPCORE_PRIV);
    zms->mpcore = mpcore;
    qdev_prop_set_uint32(mpcore, "num-cpu", machine->smp.cpus);
    qdev_prop_set_uint32(mpcore, "num-irq", 256);
    sysbus_realize_and_unref(SYS_BUS_DEVICE(mpcore), &error_fatal);
    sysbus_mmio_map(SYS_BUS_DEVICE(mpcore), 0, ZVE10_MPCORE_BASE);

    for (i = 0; i < machine->smp.cpus; i++) {
        CPUState *cs = qemu_get_cpu(i);
        DeviceState *cpudev = DEVICE(cs);

        sysbus_connect_irq(SYS_BUS_DEVICE(mpcore), i,
                           qdev_get_gpio_in(cpudev, ARM_CPU_IRQ));
        sysbus_connect_irq(SYS_BUS_DEVICE(mpcore), i + machine->smp.cpus,
                           qdev_get_gpio_in(cpudev, ARM_CPU_FIQ));
        sysbus_connect_irq(SYS_BUS_DEVICE(mpcore), i + 2 * machine->smp.cpus,
                           qdev_get_gpio_in(cpudev, ARM_CPU_VIRQ));
        sysbus_connect_irq(SYS_BUS_DEVICE(mpcore), i + 3 * machine->smp.cpus,
                           qdev_get_gpio_in(cpudev, ARM_CPU_VFIQ));
    }
    for (i = 0; i < ARRAY_SIZE(pic); i++) {
        pic[i] = qdev_get_gpio_in(mpcore, i);
    }

    /* Synthetic PL181 SD card for zve10-qemu kernel compatibility (real eMMC0 is 0xf0304000 IRQ 227). */
    sysbus_create_varargs("pl181", 0xf1005000, pic[9], pic[10], NULL);

    /* CXD900X0_PL310_BASE */
    sysbus_create_simple("l2x0", ZVE10_MPCORE_BASE + 0x2000, NULL);

    pl011_create(ZVE10_UART0_BASE,
                 g_getenv("ZVE10_NO_UART_IRQ") ? NULL : pic[ZVE10_UART0_IRQ - 32],
                 serial_hd(0));

    for (i = 0; i < ZVE10_NUM_TIMERS; i++) {
        DeviceState *timer = qdev_new("sony-hwtimer");
        SysBusDevice *sbd = SYS_BUS_DEVICE(timer);

        sysbus_realize_and_unref(sbd, &error_fatal);
        sysbus_mmio_map(sbd, 0, ZVE10_TIMER_BASE + i * 0x100);
        sysbus_connect_irq(sbd, 0,
                           g_getenv("ZVE10_NO_TIMER_IRQ") ? NULL : pic[ZVE10_TIMER_IRQ + i - 32]);
    }

    {
        DeviceState *emmc = qdev_new(TYPE_ZVE10_EMMC);
        SysBusDevice *sbd = SYS_BUS_DEVICE(emmc);
        BlockBackend *emmc_blk = blk_by_name("emmc0");
        if (!emmc_blk) {
            DriveInfo *dinfo = drive_get(IF_SD, 0, 0);
            if (dinfo) {
                emmc_blk = blk_by_legacy_dinfo(dinfo);
            }
        }
        if (emmc_blk) {
            qdev_prop_set_drive_err(emmc, "drive", emmc_blk, &error_fatal);
        }
        sysbus_realize_and_unref(sbd, &error_fatal);
        sysbus_mmio_map(sbd, 0, ZVE10_EMMC_BASE);
        sysbus_connect_irq(sbd, 0, pic[ZVE10_EMMC_IRQ - 32]);
    }

    {
        MemoryRegion *sugi = g_new0(MemoryRegion, 1);
        memory_region_init_io(sugi, NULL, &sugi_ops, NULL,
                              "zve10-sugi", 0x1000);
        memory_region_add_subregion_overlap(sysmem, 0xf3400000, sugi, 1);
    }

    {
        Zve10Gpe *gpe = g_new0(Zve10Gpe, 1);
        gpe->irq = pic[76 - 32];
        memory_region_init_io(&gpe->mmio, NULL, &gpe_ops, gpe,
                              "zve10-gpe", 0x4000);
        memory_region_add_subregion_overlap(sysmem, 0xf1000000, &gpe->mmio, 1);
    }

    {
        DeviceState *osd = qdev_new(TYPE_ZVE10_OSD);
        SysBusDevice *sbd = SYS_BUS_DEVICE(osd);

        sysbus_realize_and_unref(sbd, &error_fatal);
        sysbus_mmio_map(sbd, 0, ZVE10_OSD_BASE);
        sysbus_connect_irq(sbd, 0, pic[ZVE10_OSD_IRQ - 32]);
    }

    {
        Zve10Adc *adc0 = g_new0(Zve10Adc, 1);
        Zve10Adc *adc1 = g_new0(Zve10Adc, 1);
        Zve10Gpio *gpio = g_new0(Zve10Gpio, 1);

        zve10_adc_reset(adc0);
        memory_region_init_io(&adc0->mmio, NULL, &zve10_adc_ops, adc0,
                              "zve10-adc0", 0x1000);
        memory_region_add_subregion_overlap(sysmem, ZVE10_ADC0_BASE,
                                            &adc0->mmio, 1);

        zve10_adc_reset(adc1);
        memory_region_init_io(&adc1->mmio, NULL, &zve10_adc_ops, adc1,
                              "zve10-adc1", 0x1000);
        memory_region_add_subregion_overlap(sysmem, ZVE10_ADC1_BASE,
                                            &adc1->mmio, 1);

        zve10_gpio_reset(gpio);
        memory_region_init_io(&gpio->mmio, NULL, &zve10_gpio_ops, gpio,
                              "zve10-gpio", 0x1000);
        memory_region_add_subregion_overlap(sysmem, ZVE10_GPIO_BASE,
                                            &gpio->mmio, 1);
    }

    /* Catch-all SoC backing; real devices mapped at higher priority win. */
    create_unimplemented_device("zve10-soc", 0xf0000000, 0x10000000);

    {
        static struct arm_boot_info binfo;

        binfo.ram_size = MIN(machine->ram_size, ZVE10_DDR0_MAX);
        binfo.loader_start = ZVE10_LOADER_START;
        binfo.board_id = ZVE10_MACHINE_ID;
        binfo.kernel_filename = machine->kernel_filename;
        binfo.kernel_cmdline = machine->kernel_cmdline;
        binfo.initrd_filename = machine->initrd_filename;
        binfo.smp_loader_start = ZVE10_SMP_LOADER;
        binfo.smp_bootreg_addr = ZVE10_SMP_BOOTREG;
        binfo.gic_cpu_if_addr = ZVE10_MPCORE_BASE + 0x100;
        arm_load_kernel(ARM_CPU(first_cpu), machine, &binfo);
    }
}

static void zve10_reset(MachineState *machine, ResetType type)
{
    Zve10MachineState *zms = ZVE10_MACHINE(machine);

    qemu_devices_reset(type);
    if (zms->mpcore) {
        GICState *gic = &A9MPCORE_PRIV(zms->mpcore)->gic;
        /*
         * Stock CXD90045 Linux has CONFIG_MPCORE_GIC_INIT disabled and relies
         * on bootMonitor routing GIC SPIs (32..num_irq-1) to CPU0. Upstream
         * arm_gic resets irq_target[32..] to 0 when num_cpu > 1.
         */
        for (uint32_t i = GIC_INTERNAL; i < gic->num_irq; i++) {
            gic->irq_target[i] = 1;
        }
    }

    /*
     * Stock Sony CXD90045 vmlinux setup_arch() checks VA 0x60103000
     * (PA 0x00103000) for a "kemco" prefixed command-line override before
     * falling back to its compiled-in default cmdline.
     */
    if (machine->kernel_cmdline && machine->kernel_cmdline[0]) {
        uint8_t existing[5] = { 0 };
        address_space_read(&address_space_memory, 0x00103000,
                           MEMTXATTRS_UNSPECIFIED, existing, sizeof(existing));
        if (memcmp(existing, "kemco", 5) != 0) {
            g_autofree char *kemco_cmd = g_strdup_printf("kemco%s",
                                                         machine->kernel_cmdline);
            size_t len = MIN(strlen(kemco_cmd) + 1, (size_t)0x1000);
            address_space_write(&address_space_memory, 0x00103000,
                                MEMTXATTRS_UNSPECIFIED, kemco_cmd, len);
        }
    }
}

static void zve10_instance_init(Object *obj)
{
    Zve10MachineState *zms = ZVE10_MACHINE(obj);
    zms->ddr1 = true;
    zms->strict_cpu = true;
}

static void zve10_class_init(ObjectClass *oc, const void *data)
{
    static const char * const valid_cpu_types[] = {
        ARM_CPU_TYPE_NAME("cortex-a9"),
        NULL
    };
    MachineClass *mc = MACHINE_CLASS(oc);

    mc->desc = "Sony ZV-E10 (CXD90045)";
    mc->init = zve10_init;
    mc->reset = zve10_reset;
    mc->max_cpus = 4;
    mc->default_cpu_type = ARM_CPU_TYPE_NAME("cortex-a9");
    mc->valid_cpu_types = valid_cpu_types;
    mc->default_ram_size = ZVE10_DDR0_MAX;
    mc->default_ram_id = "zve10.ram";
    mc->ignore_memory_transaction_failures = true;

    object_class_property_add_bool(oc, "strict-cpu", zve10_get_strict_cpu, zve10_set_strict_cpu);
    object_class_property_set_description(oc, "strict-cpu",
                                          "Use camera VFPv3-D16/no-NEON profile (default: on)");
    object_class_property_add_bool(oc, "ddr1", zve10_get_ddr1, zve10_set_ddr1);
    object_class_property_set_description(oc, "ddr1",
                                          "Map 256 MiB DDR1 at 0x80000000 (default: on)");
}

static const TypeInfo zve10_info = {
    .name = TYPE_ZVE10_MACHINE,
    .parent = TYPE_MACHINE,
    .instance_size = sizeof(Zve10MachineState),
    .instance_init = zve10_instance_init,
    .class_init = zve10_class_init,
    .interfaces = arm_machine_interfaces,
};

static void zve10_machine_init(void)
{
    type_register_static(&zve10_info);
}
type_init(zve10_machine_init);

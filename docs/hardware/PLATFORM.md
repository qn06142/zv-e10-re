# Platform, register access and ownership

Use [platform.json](data/platform.json) for exact source definitions, expressions and line references. Definitions describe the GPL SoC family; body wiring and live ownership need their own evidence. C preprocessor alternatives that disagree are left unresolved by the builder.

## Address spaces

| Region or object | Address / namespace | Evidence and scope |
| --- | --- | --- |
| Linux-visible RAM resources | 0x00000000–0x3fffffff and 0x80000000–0x8fffffff | Service-session /proc/iomem observation; resource coverage does not establish allocation ownership or safely accessible bytes. |
| Static main I/O window | 0xf0000000, size 0x05000000 | GPL platform.h and core.c static mapping. |
| GPIO / OCTRL pin control | 0xf2910000 / 0xf2912000 | GPL platform.h, regs-gpio.h and regs-octrl.h; channel register base adds ch << 8. |
| Misc/reset | 0xf2915000 | GPL platform.h and regs-misc.h. |
| Clock banks & CRG dividers | 0xf2a00000, 0xf2a10000, 0xf2a20000, 0xf2900000, 0xf2a30000 (CRG +0x1000*(idx+1)) | GPL CLK0–CLK4 definitions and udif/clock.c CRG11 domains. Bank number is not ascending address order. |
| Board watchdog & ADC | 0xf2402000 / 0xf2406000 + 0x1000*ch | GPL platform.h, regs-timer.h, wdt.c and regs-adc.h. |
| DDRC A/B & AVBCKG/BAM | 0xf0104000, 0xf0105000 / 0xf2800000, 0xf2801000 | GPL platform.h, regs-ddrc.h, regs-avbckg.h and regs-bam.h. |
| SRAMC / Sync SRAMC | 0xf9003000 / 0xf9004000 (CS windows 0xfa000000, 0xfc000000) | GPL platform.h, regs-sramc.h and regs-syncsramc.h. |
| GIC CPU / distributor | 0xf8000100 / 0xf8001000 | GPL platform.h. |
| SCU / PL310 | 0xf8000000 / 0xf8002000 | GPL platform.h and pl310.h (AUX_VAL stays conditional on CONFIG_EXCLUSIVE_CACHE). Cache visibility and DMA coherency still require per-path analysis. |
| PCIe I/O & memory apertures | phys 0xbf800000→virt 0xf8800000, phys 0xbfc00000→virt 0xf8c00000 (1 MiB each); mem 0xc0000000–0xe7ffffff, 0xe8000000–0xefffffff | GPL platform.h and core.c static map_desc table. Device BAR mapping and endpoints are separate facts. |
| NAND / AXI RAM windows | 0xf5000000 / 0xf6000000 | GPL declarations; not generic MMIO register blocks. |
| eSRAM window | 0xfe000000, declared size 16 MiB | GPL family definition; core.c maps bank regions uncached unless overridden by `esram=` boot parameter. |
| av-cam reference | load base 0x635c6000 | Offline image provenance; firmware VA = that base + file offset only for this analyzed mapping. |
| DMM handles | opaque IDs | Resolve through the matching producer/allocator contract; not a PA or pointer. |

The Linux RAM resources, header DDR aperture sizes and allocatable RAM are different quantities. In `arch/arm/mach-cxd900x0/memory.h` and `adrs_conv.c`, kernel VA↔PA translations split DDR0 (`0x00000000 + CONFIG_CXD900X0_SIZE_DDR0` mapped at `VA_DDR0 = PAGE_OFFSET`), DDR1 (`0x80000000 + CONFIG_CXD900X0_SIZE_DDR1` mapped at `VA_DDR1`), and eSRAM (`0xfe000000`, identity-mapped); `adrs_conv.c` treats `pa_uc[0..1]` from `parse_memrsv_hook` as the cacheable/noncacheable boundary while `arch_phys_to_noncache` currently returns the standard kernel DDR VA or identity eSRAM address (`PA2NC_ERR = 0` out of range). All 8 `cxd900x0_io_desc[]` static kernel I/O mappings (`core.c`, overridden to `memtype_io` in `cxd900x0_map_io`) are indexed in [platform.json](data/platform.json). Do not use a single global VA-minus-offset assumption across kernel modules, Linux userspace, firmware, PCIe and /dev/stream mappings.

## Register transaction syntax

The analyzed native accessors issue 32-bit ARM loads/stores and BFI field insertion. A typical field has mask ((1 << width)-1) << lsb. Optional casts/shifts of the input are preserved in the accessor data; they must be understood before assigning field units.

GPIO has DIR +0x00, RDATA +0x10, INEN +0x20, FUNC +0x30 and WDATA +0x40 within a channel. OCTRL (`0xf2912000 + (ch << 8)`) follows the same `DATA +0x00 / SET +0x04 / CLR +0x08` convention across `OEN +0x00`, `IEN +0x10`, `DRV1 +0x20`, `DRV2 +0x30`, `PUD1 +0x40` and `PUD2 +0x50` (`regs-octrl.h`). Thus GPIO0 WDATA_SET is 0xf2910044 and WDATA_CLR is 0xf2910048. These are command aliases, not ordinary stored-value mirrors. The existing resident image's bit-0 output has owner-observed LED activity; other pin assignments are not implied.

Clock control uses DATA +0x00, SET +0x04 and CLR +0x08; indexed CLKRST entries are bank + (index << 4). Four UDIF channel declarations (`udif/platform.c`) bind per-channel `hclk` / `dclk` gates in `CLK4`: `sircs` (`IPCLKEN2` bit 2, `IPCLKEN4` bit 16), `i2c0` (`IPCLKEN2` bit 1, `IPCLKEN4` bit 17), `i2c1` (`IPCLKEN2` bit 0, `IPCLKEN4` bit 18) and `ms` (`IPCLKEN0` bit 0, `IPCLKEN5` bit 24). CRG divider control uses the nine `CRG11` bases declared in `udif/clock.c` (`CRG11_00=0xf2a01000` through `CRG11_41=0xf2a32000`, stored in [platform.json](data/platform.json)): `clock.c` writes dividers to `base + 0x100 + (clk << 4)` (`CRG_CRDM(clk)`), then writes `1` to `base + 0x30` (`CRG_CRCDC`), executes `dsb()`, and polls bit 0 clear up to `CRCDC_UPDATE_WAIT = 1000`. Field ownership, clock polarity and safe update ordering must come from each peripheral's init path, not the register name alone.

Misc RSTREQ_SET is 0xf2915044, CLR is 0xf2915048 and STAT is 0xf2915050. GPL masks include EN=0x10, ASSERT=0x01 and CPUCLR=0x100. The source force-reset command is 0x11; that is a programming command, not a reset value. The earlier reset trial restarted, but its exact reset path was not independently observed.

## Interrupt namespaces

GPL GIC identifiers include GPE 76, DMA330 channel IRQs 115–118 and abort 119, XDMAC group bases 189/193, I2C base 199, SIO base 201 and SPI base 113. In addition to the 52 MMIO windows with bound IRQs, `udif/platform.c` defines four interrupt-only channel slots (`SIRCS_OVERRUN` 197, `FUSB_CH0` `usb_vbus` 230, `FUSB_CH1` `usb_id` 231, and `DMA330_ABT` 119), recorded under `udif_irq_only_channels` in [platform.json](data/platform.json). Inspect source formulas for each channel count and offset. Linux IRQ numbers, LiRo counter indices and native callback slots are not interchangeable.

The observed LiRo indices 74/75 rising near 24 Hz have not been bound to a specific GIC line or DMA-completion condition. Native DFE slot numbers and event 0x16 are another namespace.

## Handoff is a state transition

Our handoff calls kernel_restart_prepare and machine_shutdown before entering the resident image. GPL kernel_restart_prepare invokes reboot notifiers and device_shutdown; the generic shutdown path can call bus/driver callbacks. A UDIF shutdown dispatcher also exists. Which display, clock or DMA callbacks ran in the physical trial is unmeasured. An MMIO snapshot from Senser or before shutdown is therefore not a description of the resident-entry state.

CPU0 entering our loop and the other Linux CPUs being parked do not establish complete ownership of peripheral state, DMA or other processors. The resident image inherits MMU/DRAM/device configuration and disables watchdog reset. [Handoff implementation and limits](../../research/device/zve10_ram_boot/README.md).

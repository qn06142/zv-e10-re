# Hardware coverage and next work

The atlas is deliberately incomplete. Structural extraction and instruction verification are counted separately from semantic hardware mapping.

| Subsystem | Address/structure coverage | Required next evidence |
| --- | --- | --- |
| CPU/GIC/cache | GPL bases; privileged entry and LED runtime observed. | Owned exception/IRQ/cache/coherency configuration and peripheral quiescence. |
| Memory | Linux resources, GPL apertures, `cxd900x0_io_desc[]` static MMU mappings, `adrs_conv.c`/`memory.h` DDR0/DDR1/eSRAM rules, DDRC/SRAMC/BAM source defs and DMM software contracts recovered. | Actual per-owner regions, device BAR mappings, reserved memory bounds, cache attributes and DMA buffer lifetime. |
| Clocks/reset/GPIO/watchdog | GPL formulas, OCTRL/ADC/AVBCKG/BAM headers, UDIF per-channel clocks, 9 CRG11 divider domains (`CRCDC` handshake), `CLK4` I2C reset sequence and command masks; LED effect observed. | Live-body gating/pin mux mapping, peripheral reset polarity/transitions beyond `i2c.ko`/`grm_gles.ko`, and reset defaults. |
| Sensor serial control | No validated sensor register map (I2C controller hardware contract now recovered separately). | Sensor identity, control-bus binding (I2C/SPI/SIO), slave address and power/reset/clock/mode transaction. Highest imaging priority. |
| Receiver/DFE/Bayer | RAW readout calls KickFOPD. Six AIF banks have verified buffer programming and status helpers. Fourteen selected installed firmware pages matched. | Active Bayer write bank, physical receiver binding, packing, interrupt delivery and reuse fence. See [FOPD routing](SENSOR_DMA.md). |
| XDMAC / DMA330 | Offline `dmac.ko` & `dma330.ko` instruction contracts recovered: `XDACS` + 9 channel regs + 48B LLI start/ack/shutdown; 60 DMA330 regs + `DMAGO`/`DMAKILL`/`INTCLR` + 4 `.data` PL330 template arrays. | Live-body module hashes, descriptor/CCR bitfield semantics beyond templates, caller cache-coherency fences and sensor/DFE buffer ownership. |
| LCD/graphics | Native field accessors; body-bound pin/profile lookup; six-stage panel sequence and wait helper; six empty graphics APIs checked; offline VPH AIF (`0x39..0x40`), Output 0/1 mixer/top, VDF (`0x15bfb0`), VPH queue `0x6603c4` fan-out (`0x498aa4`), IRQ 102/110 (`0x806294`/`0x806352`) completion callbacks (`0x4b59ec`/`0x4b5a84`), Sugilite (`grm_gles.ko`/`grm_ma.ko`) and `dataflowInfraFramework.so` `"SSOS"`/`"ETRY"` OSD contracts verified; v03 LCD effect failed. | 186-word Senser snapshot shows Output 0 active (`0xf3445000=0x00010114`, `0xf3440144=0x02000233`, `0xf3440404=0`, `0xf3441300=3->2`, `0xf3441310=0x22c99600`, `0xf344131c=0x00002a0b`, `GIC liro-102` at `~50 Hz`). Normal-shooting routing, DRAM pixel layout, write-only `OSD0` `startadrs`, pin electrical role and serial panel commands remain open. See [display](DISPLAY.md) and [reconstruction](DISPLAY_RECONSTRUCTION.md). |
| USB | Linux transport evidence, controller apertures and interrupt-only VBUS/ID UDIF channels (IRQs 230/231). | Independent PHY/controller/endpoint/DMA initialization for the resident runtime. |
| Lens/accessory/serial/audio | GPL serial controllers (`I2C`/`SPI`/`SIO`), firmware vocabulary, and offline `i2c.ko` 13-reg/FIFO/divider/NACK/UIPC (`0x00520250`, `0x00520607`) contract recovered. | Connector wiring, I2C slave addresses/bindings, SIO/SPI contracts, electrical/framing/checksum/ack contracts and attached-device identities. |
| Storage/calibration | Known mounted partitions and controller declarations. | Hardware ownership and transactions only as needed; preserve body-specific calibration and recovery data. |

## Work order

1. Finish the platform resource graph from source: MMIO windows, IRQ namespaces, clocks/reset domains, pin mux and memory/bus translations. Attach exact source and binary identities.
2. Bind native entry points to those resources. Recover typed register fields, units/enums and read/write side effects; distinguish setters, status/acknowledgement and command ports. Unknown fields stay unnamed.
3. Reconstruct complete sensor and DMA transactions, including their prerequisites and completion/reuse behavior. Recover serial register tables and command/descriptor structures from actual producers/consumers, rather than inventing values from image-size tables.
4. Use mode-labelled, read-only observations to compare the stock boot, normal shooting/live view, recording and service states. Unclassified addresses and arbitrary bus scans are not implied by this plan. Any read-clear or clock-gated domain needs a justified capture path.
5. Establish display clocks/routing/update semantics and accessory protocol frames in the same map. Resume hardware writes only when the specific transaction is understood well enough to state what result would support or contradict it.

## Evidence record for each register or protocol

Store address space and owner; physical base and offset; access width and byte order; fields/masks/enums/units; reset value or unknown; mode-specific observations; required values and why; read/write side effects; power/clock/reset prerequisites; sequence/order/barriers; busy/completion/ack/error/timeout; buffer lifetime; source path/line or image identity/file offset; verification method and mocked effects; contradictions/open questions.

The generator cannot supply names, reset values, bus wiring or safe access from an instruction pattern. All native candidates retain read_or_write_permission=false. Definition-only GPL entries need target configuration/body binding. The 332 saved Senser observations and five matched firmware pages are reproducible evidence, not a blanket register allowlist.

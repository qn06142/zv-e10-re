# ZV-E10 hardware atlas

18 November 2026. This is the central map for replacing camera functionality: physical address spaces, register fields, clocks/reset/power, interrupts, sensor acquisition, DMA and accessory protocols. The goal remains Bayer RAW over USB. This is an initial, incomplete hardware manual, not a claim that the entire camera has been mapped.

The owner confirmed full-screen RGBA4444 bars from the resident runtime and a successful run of the separate-image allocator probe. The current display reuse demo stops at its stock buffer guard. The hardware and ownership results are recorded in the session handoff.

For the paused display and Bayer RAW checkpoint, see the [research handoff](HANDOFF.md).

| Subject | Reference |
| --- | --- |
| Physical windows, clocks, reset, GPIO and interrupt namespaces | [Platform](PLATFORM.md) |
| Sensor control, DFE, memory and distinct DMA engines | [Sensor and DMA](SENSOR_DMA.md) |
| End-to-end IMX284 / DFE / SGC0 / SLVS-EC sensor pipeline & a6400 parity | [Sensor pipeline](SENSOR_PIPELINE.md) |
| Electrical/controller protocols versus firmware messages and host transports | [Protocols and accessories](PROTOCOLS.md) |
| Display pipeline and the failed v03 assumption | [Display](DISPLAY.md) |
| Body-bound panel settings, GPIO lookup, six-stage sequence and API limits | [Native LCD reconstruction](DISPLAY_RECONSTRUCTION.md) |
| Evidence requirements and unfilled hardware contracts | [Coverage and next work](COVERAGE.md) |
| Numeric platform definitions and channel windows | [Platform data](data/platform.json) |
| Native bitfield accessors with addresses, masks and input transforms | [Native accessor data](data/native-accessors.json) |
| Curated named registers and command values | [Register contracts](data/register-contracts.json) |
| Offline XDMAC and DMA330 module contracts | [DMA contracts](data/dma-contracts.json) |
| Offline RAW readout and FOPD routing | [FOPD contracts](data/dfe-fopd-contracts.json) |
| Offline I2C controller and CLK4 reset contract | [I2C contract](data/i2c-contract.json) |
| Offline VPH AIF, Output 0/1 and mixer contracts | [VPH/AIF contracts](data/vph-aif-contracts.json) |
| Offline Sugilite GPU, MA and DataflowInfra OSD contracts | [GRM contracts](data/grm-contracts.json) |
| External QEMU findings and emulator boundaries | [Pinned source audit](EXTERNAL_ZVE10_QEMU.md) |
| Local `pmca-re` QEMU 11.1.2 (`-M zve10`) emulator | [QEMU emulator](QEMU_EMULATOR.md) |
| Reproduction and query tools | [Atlas builder](../../research/device/zve10_hardware_map/README.md) |

## What is populated

The platform extraction contains 507 numeric source definitions, 64 UDIF channel MMIO declarations (4 with resolved clocks), 4 interrupt-only UDIF channels, 9 CRG11 clock-divider domains, 8 static kernel I/O MMU mappings, 122 curated register contracts, and 1,245 conservative Thumb read-modify-write accessor candidates touching 495 distinct high-address words. Of those words, 451 are in the 0xf3440000 bank, which includes the display leads. These counts describe extracted access patterns, not 495 understood hardware registers. Addresses in external-memory windows remain unclassified.

Offline kernel-module and firmware contract checks add verified instruction-level descriptions of XDMAC (`dmac.ko`: `XDACS`, 9 channel registers, 48-byte LLI submission and `XDDSD` ack), DMA330 (`dma330.ko`: 60 mapped registers, `DMAGO`/`DMAKILL`/`INTCLR` and 4 `.data` template arrays), I2C (`i2c.ko`: 13 16-bit registers, FIFO/command framing, speed dividers, NACK retry, `CLK4` mode-gated reset and UIPC endpoints), VPH/AIF (`av-cam.bin`: 8 AIF channels `0x39..0x40`, `0xf3441320`/`0xf344134c` 31-bit repeat masking, Output 0/1 banks `0xf3445xxx`/`0xf3446xxx`, mixer `0xf3440144`/`0xf3440184`, top `0xf3440000`/`0xf3440008`), and GRM/Sugilite/DataflowInfra (`grm_gles.ko`, `grm_ma.ko`, `dataflowInfraFramework.so`, `libObj.so`). Live-body module hashes, Output 0 vs Output 1 panel routing, and peripheral wiring remain open.

332 saved word readings retain their Senser-mode provenance. They are not reset values, normal-shooting requirements or initialization recipes. 421 accessor candidates fall entirely within reference pages whose bytes matched the current camera image; other candidates are tied only to the offline reference. [Machine-readable coverage](data/coverage.json).

The GPL platform source comes from Sony's CXD900X0 tree, read from an existing external checkout. QEMU is not this project's work and no emulator result establishes hardware behavior. Source-relative paths and SHA-256 hashes are in platform.json. Relevant firmware code-page matches and saved service observations are [preserved as inputs](../../research/device/zve10_hardware_map/evidence/20261118-code-pages.json). Firmware bytes and private keys are excluded.

## Value and address discipline

Every claim must say which address space it uses: physical MMIO, physical RAM/bus address, Linux virtual address, firmware virtual address, file offset, DMM handle, message ID or interrupt namespace. Numerical similarity is not a translation rule. IO_ADDRESS(x)=x is a board mapping macro, not permission to dereference arbitrary physical RAM from a process.

Keep five value categories separate: documented reset value; mode-specific observed value; programming command/bit mask; inferred field meaning; required runtime value established by a complete transaction. Unknown values remain null. A native RMW instruction pattern does not prove a register has no read-clear, write-one or power-domain side effects.

A usable hardware contract needs its owner and routing, power/clock/reset prerequisites, access width/order, field units/enums, buffer/descriptor layout, start/update sequence, busy/completion/error acknowledgement and shutdown/reuse rules. A passing register-write emulator covers only the instruction behavior it models.

The [external QEMU audit](EXTERNAL_ZVE10_QEMU.md) adds graphics-layout and GPU command leads, plus a separately verified Sony-module clock-up transaction. Emulator stubs, synthetic peripherals, assumed responses and unmatched ELF offsets remain outside real-camera register facts.

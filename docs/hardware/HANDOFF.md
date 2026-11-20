# ZV-E10 hardware research handoff

20 November 2026, Bangkok · Senser LCD path sampled after the stock two-flash result.

**Full-screen RAM scanout works. The separate-image loader works. The demo that reuses a stock OSD buffer stopped before writing pixels.** Senser confirmed an alternate OSD0 framebuffer range that the demo rejects at stage 2.

## Current camera and recovery state

- The stage-coded reuse demo is installed. `boot.ko` and `rtos.bin` both reached READY in Senser, unloaded, and passed on-camera SHA-256 verification. The owner's hardware trial reported **two flashes per group**, which identifies the descriptor, slot or current-address guard. That guard runs before the AIF drain and framebuffer writes. [Loader and display experiment](../imaging/RTOS_ITERATION.md)
- Active `/log/zve10-ram-boot/boot.ko` SHA-256 is `3f6d5570fb77be02d6b3a01f7abfb08b1e620e1659369b5366977b1370b5481f`. Active `/log/zve10-ram-boot/rtos.bin` SHA-256 is `3abcfdd100e95ddf9252526bc8597285c1c6245635702d988c73512c84e4d9ae`. The preceding reuse demo pair is backed up in `/log/zve10-ram-boot/rtos-display-diagnostics`. The separate original loader and drain image are under `/log/zve10-ram-boot/rtos-reuse-demo`.
- To return to stock after GO, power off, disconnect USB, briefly remove and reinsert the battery, then boot normally. The two confirmations in **Setup → Version** are **Up → Down → Left → Right → Up** for **BOOT RDY**, followed by the whole sequence again for **BOOTING**. Leave the trigger untouched for a stock capture. USB Senser remains the staging path and BootROM recovery remains the last fallback. [Runtime and rollback](../../research/device/zve10_ram_boot/README.md) · [Access and recovery](../ACCESS_AND_TOOLS.md)
- The latest hotspot IP supplied by the owner was `192.168.137.98`. Two pinned SSH attempts timed out on port 22 before login. No Version-screen capture or camera write occurred during closeout. The later Senser capture closed successfully and Windows saw the camera return to Mass Storage.

## Hardware results

| Milestone | What the session established |
| --- | --- |
| Display path | v06 showed red, green and blue in the RGBA4444 half of the photographed strip, consistent with RRRRGGGGBBBBAAAA packing. v07 then showed full-screen color on the physical LCD. The successful path is Output 0 / OSD0, 640×480 RGBA4444, 1,280-byte pitch, with inherited panel timing. The runtime refreshes AIF start as consumed requests clear. [Display trials](../../research/device/zve10_ram_boot/DISPLAY.md) |
| Stock display evidence | The expanded Senser capture saved 186 selected 32-bit words and 13 matched firmware slices. Paired live-view SSH observations across a DISP overlay change showed Output 0 / OSD0 active, Output 1 idle and IRQ 102 near 50 Hz. A separate stock capture found four adjacent rotating 614,400-byte OSD0 buffers and a matching callback token. These captures were from Senser or live view. The Version-screen descriptor is still missing. [Display capture](DISPLAY.md) · [Descriptor trace](DISPLAY_RECONSTRUCTION.md) |
| Procedural playback | The v08 fire image was staged with a 640×192 buffer after full-height allocation failed in that boot. No moving-fire result was recorded. Full-height allocation and reserved-page retries later failed staging on the examined boots. v07 remains the hardware-confirmed full-screen static baseline. [Fire and static baselines](../../research/device/zve10_ram_boot/DISPLAY.md) |
| Separate-image loader | Stock Version launches `boot.ko`, which stages an independent `rtos.bin` into executable RAM before GO. The owner confirmed the 16 KiB arena allocator probe via its slow heartbeat. Subsequent image-only swaps reached READY while preserving the loader. The handoff still inherits the stock MMU and device configuration. [RTOS image ABI and build commands](../imaging/RTOS_ITERATION.md) |
| DMA and AIF drain | The first post-GO probe blinked fast. Its controller-specific successor showed four flashes, identifying VPH AIF as the only sampled controller flagged. Applying the primary stop sequence cleared the sampled activity over the following roughly 160 ms window. The owner saw even blinking and photographed a mostly dark LCD with bright lines at the left edge. The probe supplies no frame. This establishes the result for the tested registers and window, while global DMA quiescence and general DDR ownership remain open. [DMA and drain experiments](../imaging/RTOS_ITERATION.md) |
| Stock-buffer reuse demo | The new image validates a live OSD0 descriptor, drains AIF, rechecks idle state, and only then paints and repoints one slot. Offline instruction tests passed for the draw, rejected descriptor and post-drain movement. On hardware the first build showed solid red. The stage-coded successor reported two flashes, stopping at the initial validation. No successful reuse or reclaimed stock buffer was observed. [Stage codes](../imaging/RTOS_ITERATION.md) |

## Senser LCD capture

In Senser, the same primary OSD descriptor at `0x6441b27c` passes the demo's 640×480 geometry, zero-field and callback checks. The secondary descriptor is empty. Output 0 / OSD0 is active and Output 1 is idle. The primary framebuffer starts at `0x22c48000` and ends at `0x22cde000` (exclusive). Both sampled OSD0 current addresses, `0x22c84e80` and `0x22cb1200`, are inside that frame. The installed demo rejects this base at stage 2 because it only allows four stock live-view bases. The following current-address check also excludes the Senser frame. No camera writes occurred. [Senser descriptor and MMIO capture](../../research/device/zve10_hardware_map/evidence/20261120-senser-osd-slots.json)

Use this range for a Senser-specific probe. A write test still requires a Senser launch that quiesces the producer and validates the live descriptor and scanout range after the AIF drain. The stock Version-screen sequence is a separate launch path whose two-flash cause remains unverified.

LCD work has priority. The latest offline audit found that the body-matched primary LCD profile uses type `0x10` and bypasses the generic panel pair-list builders. Continue from the GPIO and timing path for cold initialization. The inherited Senser scanout remains the starting point for the demo. [LCD reconstruction](DISPLAY_RECONSTRUCTION.md)

The read-only Senser timing capture matched the native Output 0 writer with `A=640`, `B=480`, `C=32` and the unadjusted timing branch. The panel port uses GPIO4 bit 26. Two live captures matched all six VPH top words issued after the panel clock switch.

The retained Senser request `[1, 0x1b, 1, 0, 0, 0]` matched at the source, pending and latched records. Firmware inspection traced the upstream path to VPH endpoint `0x006603c4`. The sender packs the six words at message offset `+0x20` with a dirty byte at `+0x1c`. The receiver copies that 28-byte span to the service record beginning at destination offset `+0x20`. Replaying the downstream request reached the panel switch with panel 0, mode `0x1b`, enable 1 and option 0. The first cold-boot request producer, divider initialization and physical pixel-clock frequency remain open. [Timing evidence](../../research/device/zve10_hardware_map/evidence/20261120-senser-lcd-timing.json) · [Request evidence](../../research/device/zve10_hardware_map/evidence/20261120-senser-lcd-request.json)

## Resume from the two-flash result

1. For a Senser demo, establish that the handoff can reach GO with the Senser LCD running. For a Version-screen demo, capture the stock screen over pinned SSH using the current hotspot lease.
2. Capture both Route 1 OSD descriptor slots at firmware VAs `0x6441b27c` and `0x644194d8` and AIF current address `0xf3441310`. Verify the live LiRo mapping against the matched queue-consumer code before reading the descriptors. Compare base, dimensions, pitch, component selector, callback and current-address range with the reuse guards (local checkout: `research/device/zve10_ram_boot/rtos_display.S`). The earlier live-view descriptor used 640×480, callback `0x63733989` and rotating bases `0x1968f000`, `0x19725000`, `0x197bb000`, `0x19851000`.
3. Change the specific guard the new evidence explains. Keep post-drain validation ahead of any framebuffer write. Verify the separate image displays a full frame before adding timed updates. Once updates work, preload a short monochrome clip before GO and expand it into RGBA4444 for the Bad Apple demo. The resident runtime has no filesystem reader after handoff.

## Sources and toolchain

- [Hardware atlas](README.md) and [coverage matrix](COVERAGE.md) index the register map, evidence and open contracts. [Atlas tooling](../../research/device/zve10_hardware_map/README.md) contains reproducible audit commands.
- Use the repo Windows Python virtual environment with Capstone, Unicorn and pyelftools, and MSYS2 UCRT64 ARM GCC/binutils. The prepared Sony GPL kernel headers live in the local external `zve10-qemu` checkout. The external emulator belongs to its authors and no emulator work formed part of this session. [Access and toolchain](../ACCESS_AND_TOOLS.md) · [External source audit](EXTERNAL_ZVE10_QEMU.md)
- The local artifacts, USB install journals and staging scripts are under the task workspace's `work/zve10-rtos-loader` and `work/zve10-osd-compare`. Firmware dumps and private keys remain local.

## Bayer RAW track

The long-term goal remains native Bayer RAW over USB. XDMAC channel 5 / IRQ 194 advanced about 47.6 times/s in live view and 47.3 times/s in 4K24. A completed Bayer buffer, CFA and packing, producer ownership, cache rules and transfer to USB are still unverified. [Sensor and DMA](SENSOR_DMA.md) · [DMA contracts](data/dma-contracts.json)

# chocotan/zve10-qemu hardware-source audit

18 November 2026. Reference project: [chocotan/zve10-qemu](https://github.com/chocotan/zve10-qemu), pinned to remote HEAD 42554a639e005455a1cc492744bd77341e7c41d2. Git access verified the remote head. The existing local checkout was read without builds, runs, edits or camera access. [Source receipt](data/external-zve10-qemu.json) records per-file hashes and commit comparisons. scripts/menu_build.py has pre-existing local changes; the committed version independently contains the same libObj guard discussed below. The other audited files match the pinned commit after line-ending normalization.

The project is useful for boot/platform corroboration and native graphics ABI/layout leads. It explicitly does not model the sensor, lens or imaging processor. Its UI success is not evidence that a real LCD panel, physical pixel clock, sensor or DMA engine was initialized. Its authorship and findings remain external to this project.

## What can enter the map

| Reference finding | Evidence scope | How it is used here |
| --- | --- | --- |
| UART0 0xf2000000 / IRQ150; timer bases 0xf2403000 + n*0x100; MPCore/GIC region 0xf8000000 | Emulator declarations also corroborated by Sony GPL platform definitions. | Keep GPL provenance for the real address declarations; emulator agreement is supporting context. |
| Timer control/clear/compare/read/load at +0/+4/+8/+0xc/+0x10 | Implemented emulator behavior aligns with GPL register offsets. | Useful model to read alongside source. Model clock/timing assumptions do not establish measured camera timing. |
| Sugilite control word at 0xf3400080 and value 0x15 | The emulator returns that value to satisfy a native driver check. Independently checked in our identified Sony grm_gles.ko. | Promote the native source-derived transaction below, not the emulator's unconditional response. |
| GPU packet base modeled at 0xf1000000 with pointer/doorbell/fence behavior | Model reads a packet pointer at +0x1804 when +0x1800 receives 4; it recognizes a narrow startup packet and raises IRQ76 with a completion token. | A packet-decoder lead only. Constants, pointer ranges and token 0x12345678 are not reset defaults or a general GPU submission/completion protocol. |
| Native graphics buffer copy | Adapter accepts a tightly checked 640×480, two-byte-per-pixel layout and converts 8×8 Morton tiles with a vertical flip. | A useful surface-format hypothesis and a route to inspect native bitmap metadata. It does not identify physical LCD scanout. |
| CPU/GPU pointers and metadata | Headless code checks bitmap identity, metadata, physical address and read-lock lifetime; token-like values are not blindly cast to PA. | Reinforces typed addresses and buffer ownership. Match our actual ELF identity before reusing offsets or layouts. |
| Boot RAM publication at 0xfe005010 | Documented emulator SMP bring-up with kernel changes. | Distinguish its patched startup from the stock camera's bootMonitor path. |

## Emulator substitutions excluded from hardware facts

The machine uses a Cortex-A9/A9 MPCore model; that is not evidence that this camera has Cortex-A9 cores. Its 1 GiB default RAM and 32 KiB eSRAM backing are emulator allocations, not physical capacity measurements. A PL181 at 0xf1005000 is explicitly added by the emulator and kernel patch to supply filesystem storage; it must not enter the Sony hardware map as a real SD controller.

The fallback unimplemented device logs reads/writes, returns zero on reads and does not retain writes in the inspected upstream helper. It is not a register implementation or a source of reset values. The machine also ignores failed memory transactions. Emulator boot success therefore cannot validate arbitrary register accessibility.

The DMA stub exports dma330_mem_transfer_async and dmac_mem_transfer_async but returns zero without copying data or establishing a completion fence. The Sugilite power acknowledgement is a constant response. The GPE startup fence accepts one special packet rather than interpreting arbitrary GPU programs. UI drawing/presentation includes a CPU backend and host-readable output path. Those substitutions remain explicitly outside our physical device contracts.

The source headers refer to evidence/gpe-abi, evidence/gpe-type6 and evidence/gpe-type3 reports. Those evidence directories are absent from the inspected checkout. Their claimed capture provenance cannot be independently reviewed from this source package alone.

## Independently recovered Sony graphics clock transaction

The lead was checked against our local grm_gles.ko SHA-256 4e4b99e5e17e170ddc13dc432178299512525debd6fb19512521b38867da7a65. In .text, sugilite_clock_up_internal begins at section offset 0x248. This offset is neither a module load address nor a file offset.

The identified driver performs the following ordered operations:

1. Read/modify/write the low nibble of 0xf28040c4, 0xf28041a8, 0xf28050b8 and 0xf280518c to 6, preserving other bits.
2. Write 0x15 to 0xf3400080.
3. Call __const_udelay with encoded argument 0x1a36e. Wall-clock duration is not asserted here.
4. Write 0x10 to 0xf3400280.
5. Read 0xf3400080 and require exact equality to 0x15; otherwise call __bug_noarg. This is one check, not a polling loop.

The IO helpers directly dereference their address arguments. Reads include DSB SY; writes execute DSB SY and an optional outer_cache callback before the store. The callback's struct offset is recorded without guessing its semantic name. Raw opcodes, literal values and call relocations are checked by extract_graphics_clock.py (local checkout: `research/device/zve10_hardware_map/extract_graphics_clock.py`); the resulting [transaction record](data/graphics-clock-transaction.json) is data, not an executable camera recipe.

The current body's module identity has not been freshly matched to this offline module, and prerequisites/shared clock ownership are not fully recovered. None of these operations were executed for this audit. This transaction initializes part of graphics infrastructure; it is not a panel power/timing/scanout sequence.

## Graphics ABI identity boundary

The committed emulator build guards libObj.so SHA-256 cfdc59b94fa56116e9d99154ca03a2c1aaf6039dd272679b78b0b76e21c722ac. Our local dump is bc0deb2f0e94218752e42ce6f5a3576d7456971eb63fbde705ffbd9b3a7fdeea. These differ. Function offsets such as the bitmap physical-address and read-lock calls are leads, not portable callable addresses. The cause of the identity difference has not been established; it is not assumed to be a particular firmware version or patch.

The present adapter describes a restricted RGBA4444/tiled path and allocates a separate linear output copy. It must not be confused with a native Bayer buffer, a camera scanout PA or a recovered standalone LCD driver. The next useful work is to match the relevant native code/metadata and trace graphics power, buffer submission and completion into real display routing. Sensor/DFE and accessory register mapping still require separate evidence.

## Audited upstream files

- [Machine and MMIO model](https://github.com/chocotan/zve10-qemu/blob/42554a639e005455a1cc492744bd77341e7c41d2/source/qemu/hw/arm/zve10.c)
- [GPU startup fence subset](https://github.com/chocotan/zve10-qemu/blob/42554a639e005455a1cc492744bd77341e7c41d2/source/qemu/hw/arm/zve10-gpe-init.h)
- [DMA stubs](https://github.com/chocotan/zve10-qemu/blob/42554a639e005455a1cc492744bd77341e7c41d2/source/modules/dma330-stub/dma330_stub.c)
- [Present/tile conversion](https://github.com/chocotan/zve10-qemu/blob/42554a639e005455a1cc492744bd77341e7c41d2/source/ui/ui-present.h)
- [Bitmap identity/read-lock checks](https://github.com/chocotan/zve10-qemu/blob/42554a639e005455a1cc492744bd77341e7c41d2/source/ui/ui-headless.h)
- [Kernel changes](https://github.com/chocotan/zve10-qemu/blob/42554a639e005455a1cc492744bd77341e7c41d2/source/kernel/0001-zve10-qemu.patch)

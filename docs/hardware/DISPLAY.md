# Display hardware: current facts and missing semantics

The v03 resident trial failed: the owner saw no LCD change while the access LED continued blinking. This is the current result, superseding the pending-test descriptions. [Installation and owner report](../../research/device/zve10_ram_boot/display-v03-hardware.json).

| Layer | Established | Unknown |
| --- | --- | --- |
| Power/backlight | Owner reported black but backlit LCD during the prior resident runtime. | Panel reset/power state, serial setup, pixel clock and active scan timing after shutdown. |
| Native MMIO word | Original Thumb code accesses 0xf3445108 with three 8-bit fields at 16, 8 and 0, and control bits 25/24. Relevant instruction pages match current camera file pages. | Full field meanings and control semantics, routing to the physical LCD, update/latch domain and required enable order. |
| Component interpretation | Neutral 0x80/0x80 and luma-like values in native callers support a Y/Cb/Cr hypothesis. | A complete hardware register specification or proof that changing that word alone reaches the panel. |
| Adjacent control | Native prefix around file offset 0x4b4b30 invokes 0x807c36, setting bit 0 at 0xf344510c, in addition to the two control bits. | This bit's meaning; it must not simply be called a commit strobe. v03 did not reproduce this complete prefix. |
| Timing | Senser readings included 0xf3445048=0x02800025 and 0xf344505c=0x01df01df. | Complete geometry/porch/polarity/divider interpretation and normal-shooting/post-shutdown values. 640/480-related numbers are leads, not a timing recipe. |
| CPU render path | GRM/DMP and native display/dataflow paths exist. Earlier surface probes failed to identify scanout. | A verified linear framebuffer, source-plane format/stride/address and ownership. No framebuffer absence theorem follows from those failed probes. |
| Shutdown | kernel_restart_prepare calls reboot notifiers and device_shutdown before resident entry. | Actual per-driver callbacks, clock/routing changes and pending display transfers in the tested run. |

The [native corpus](data/native-accessors.json) maps field access patterns, mostly in the 0xf3440000 bank. It leaves semantic names and required/reset values unknown. A service-mode readback does not validate resident-state accessibility or a valid display transaction.

Before another display write, recover the panel clock/reset/power chain, output mux and enable ownership, frame/update boundary, and the exact native transaction that applies a known working image. Then recover a controllable source buffer or a documented test-pattern path. The first write should test a stated hardware contract with an observable result. No new display payload or trial was installed while creating this atlas.

## External graphics leads

The [pinned zve10-qemu audit](EXTERNAL_ZVE10_QEMU.md) exposes a native tiled graphics-buffer lead, identity/read-lock checks and a modeled GPU startup packet. Its guarded libObj identity differs from our dump, and referenced capture reports are absent. A graphics clock-up sequence was independently recovered from an identified Sony module; panel routing, timing and scanout remain unresolved. None of those registers were written for this audit.

## Native panel reconstruction

The [reconstructed configuration and sequence](DISPLAY_RECONSTRUCTION.md) binds the current body to GPIO bank 11/bit 20, a 304-byte selected LCD profile and the analyzed graphics-library identity. A six-stage native sequence and its invocation-count/pending-work wait gate are recovered. Six framebuffer-looking APIs are empty in that library. Pin electrical role, panel transport, output routing and complete scanout initialization remain unresolved. The read-only Senser session installed nothing and wrote no MMIO.

## Offline VPH, AIF, Sugilite and DataflowInfra contracts

The [VPH/AIF offline audit](data/vph-aif-contracts.json) and [GRM/Sugilite/DataflowInfra offline audit](data/grm-contracts.json) verify instruction-level display scanout and graphics paths without camera access:

- **VPH AIF channels (`0xf3441000` / `0xf3441200..0xf3441580`)**: Eight VPH channels (`0x39..0x40`) map YUV0/YUV1 planes 0-1, OSD0 (`0x3b`, `0xf3441300`), OSD1 (`0x3c`, `0xf3441380`), Aux0 (`0x3d`, `0xf3441400`) and Aux1 (`0x40`, `0xf3441480`). `0x41bf98` clears `[ch_base + 0x0c]` even when `flags_byte8 == 0`, uses fill mode when `cfg[5] == 3` (`startadrs = 0xff000000`), and programs non-fill DMA scanout (`cfg[5] != 3`) with bit 11 and bits `19:16` cleared. `0x4b5818` masks physical `rptadrs` (`0xf344134c`) to 31 bits (`phys & 0x7fffffff`, mapping `0xa8200000` to `0x28200000`) while `0xf3441350` (`rpt_ctrl`) depends on BSS state at `0xe57f5c`.
- **Output 0 vs Output 1, mixer and top control**: Output 0 uses `0xf3445000..0xf34456ff` (with mixer enable `0xf3440144` bit 0 YUV / bit 1 OSD and blender/CSC `0xf3445500..0xf3445540`; `display-v03` wrote only `0xf3445108`, omitting `0xf344510c` bit 0 and mixer/top state). Output 0 colorbar (`0x4b3f8c`) maps software modes `3 -> 0x14` and `4 -> 0x13` via `tbb`. Output 1 uses `0xf3446000..0xf34466ff` and mixer `0xf3440184`, with top control/reset bits on `0xf3440000` and `0xf3440008`.
- **GRM / Sugilite / DataflowInfra**: `grm_gles.ko` drives Sugilite GPU registers (`0xf1000000..0xf1001410`, 21 init writes) and clears `0xf3400084`/`0xf3400284` on clock-down; `grm_ma.ko` executes DMA cache flush/invalidate (`dir` `1`/`2`) and UIPC `0x0061003c` messages; `dataflowInfraFramework.so` (`C_DataflowInfra_StdData_OSD` at `0x238dc`/`0x2392c`) serializes `"SSOS"`/`"ETRY"` headers around the `0x94`-byte `PIN_OSD_IMAGE_SIZE_INFO` entry populated by `libObj.so` `0x6fe064` (including `Trans_Type = (flags & 0x10) && bpp == 4`).
- **RTOS VDF consumer, VPH queue and VSYNC completion callbacks**: `VDF::VdfOsdImageSizeProcessor` (`0x15bfb0`) logs `0x4444`/`0x8888` from `Trans_Type` and writes `Sel`/`Trans_Type` to `SubsystemAccessor`. VPH queue `0x006603c4` (`0x498aa4`) fans out 56-byte descriptors to Route 0 (`OSD1`, `0x4b6340`), Route 1 (`OSD0`, `0x4b6298`) or both. VPH IRQs 102 (`0x806294`) and 110 (`0x806352`) update `0xf3440038` bits 9/10 and trigger `0x4b59ec` (`OSD0`) and `0x4b5a84` (`OSD1`) to invoke the latched `[desc + 0x30]` completion callback with `[desc + 0x2c]` in `r1`. In the Senser snapshot below (`0.2198 s` repeat window), `GIC liro-102` advanced by `11` (`~50.0 Hz`) while Output 0 was active (`liro-110` stayed `0`). Physical rear-panel routing, pixel component order in DRAM, write-only `OSD0` DMA `startadrs`/`rpt_ctrl` (`0xf3441320`, `0xf3441350`) and normal-shooting panel state remain open.

## November 19 Senser snapshot

The camera returned 186 selected 32-bit words through its existing `/tmp/busybox devmem` applet. The stock BusyBox lacks that applet. The evidence records the selected addresses, omitted write-only/unindexed addresses, boot ID, firmware hashes and timing. The session used read-form commands only and exited to Mass Storage (`0x0d95`). [Capture receipt](../../research/device/zve10_hardware_map/evidence/20261119-display-senser.json)

| Evidence | Reading in Senser |
| --- | --- |
| Output 0 & top status | Control `0xf3445000 = 0x00010114`, mixer `0xf3440144 = 0x02000233` (YUV0 and OSD0 layer bits set), `0xf3440048 = 0x10010b77` (`bit 10 = 0`), `0xf3440400 = 0x00010000`, `0xf3440404 = 0x00000000` (`bit 0 = 0` -> 2BPP width selector). |
| Output 1 | Control `0xf3446000`, mixer `0xf3440184`, `0xf3440068` and `0xf3440410..0414` all `0`. Color controls `0xf3446100` and `0xf3446104` retained nonzero values. |
| Color path | `0xf3445108 = 0x03008080` and `0xf344510c = 1`. |
| VPH AIF channels | AIF top `0xf3441004 = 0x00000101`. `OSD0` (`0x3b`, `0xf3441300`) read `ctrl = 0x00000003` (then `0x00000002` in repeat samples), `stat = 0x80000000`, `+0x08 = 0x00040012`, `+0x10 = 0x22c99600`, `+0x1c = 0x00002a0b` (`bit 14 = 0`, 8-byte align), `rptadrs = 0`. `YUV1 plane0` (`0xf3441200`) read `ctrl = 2`, `stat = 0x80000000`, `+0x10 = 0x3c78ab00`, `+0x1c = 0x00000b0b`. `OSD1` (`0xf3441380 = 2`, `0xf34413cc = 0x00000500`) had `stat = 0` and `+0x10 = 0`. |
| GPIO and clocks | GPIO bank 11 DIR, RDATA, FUNC and WDATA each showed bit 20 set. The four graphics clock words each held `0x476` and `0xf3400080` held `0x15`. |

Four of five repeated VPH controls (`0xf3440000`, `0xf3441380`, `0xf3445000`, `0xf3446000`) stayed constant across samples `0.2198 s` apart, while `OSD0` control `0xf3441300` dropped from `0x00000003` during the main sweep to `0x00000002` in both repeat samples. Interrupt counters changed, including `GIC liro-102` (`delta = 11` in `0.2198 s`, `~50.0 Hz`, bound at `0xfcc4d0` to VPH handler `0x806294` while Output 0 was active; `liro-110` at `0x806352` did not advance with Output 1 disabled). Compared with November 18, 15 of 89 shared words changed, so one capture cannot serve as a fixed reset or initialization table.

The body files for GRM GLES, GRM MA and DataflowInfra match the audited SHA-256 values. The body `av-cam.bin` differs from the whole reference binary and matches all 13 compared slices (the AIF table and its pointer, AIF core/read helpers, VDF `0x15bfb0`, VPH queue/top/color/mixer/OSD route and VSYNC ISR handlers). The GUI library matches the previously captured installed version. The Senser state favors tracing Output 0 first. A normal-shooting observation tying an owned OSD buffer and output route to the rear LCD is still needed before a resident animation trial.

## Stock live-view comparison over Wi-Fi SSH

The owner changed the rear LCD to minimal OSD with DISP between captures and reported that many overlays disappeared. The initial overlay preset was unrecorded. Both read-only captures used the same boot. Output 0 control stayed at `0xf3445000 = 0x00010114`, its mixer stayed at `0xf3440144 = 0x01000233` with OSD0 enabled, and Output 1 control and mixer stayed zero. The OSD0 width selector stayed at zero (two bytes per pixel). IRQ 102 increased by 83 in 1.64 s before DISP and 84 in 1.67 s after DISP, about 50 Hz in both captures. IRQ 110 stayed at zero. [Capture transcript](../../research/device/zve10_hardware_map/evidence/20261119-display-live-view-ssh.txt)

Output 0 and OSD0 remained active across the visible overlay change, which supports the rear-LCD routing hypothesis in normal shooting. This comparison did not isolate the physical panel output. The OSD0 AIF address word `0xf3441310` varied within each preset, so it cannot identify either preset or serve as a stable framebuffer handle. The next evidence needed for a static RAM frame is the OSD descriptor's format and stride, the owning buffer and its lifetime through completion, and a panel-specific routing observation.

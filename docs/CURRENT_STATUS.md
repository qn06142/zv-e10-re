# ZV-E10 current research status

Updated 28 November 2026. The GUI-triggered bare-metal `ZVOS` runtime (`crt0.S` + `zvrt_runtime.c` + `os_shell.c`) runs on live hardware with platform quiesce, self-owned 1 GiB DDR0 MMU takeover, tear-free uncached 640×480 double-buffered LCD scanout, animated fire, and full 5,258-frame 24 fps Bad Apple!! playback. Current work focuses on bare-metal IMX284 + DFE Bayer RAW acquisition (`cxd90057_hw.h` / `cxd90057_pipeline.h` / `imx284_sensor.h` / `bayer_capture.h` / `senser_bayer_runner.c`) and the standalone QEMU 11.1.2 (`-M zve10`) emulator. See the [hardware handoff](hardware/HANDOFF.md), [Sensor pipeline](hardware/SENSOR_PIPELINE.md), [ZVOS spec](hardware/ZVOS_SPEC.md), and [Bayer handoff](../research/device/zve10_ram_boot/BAYER_HANDOFF.md) for hashes, logs, and open boundaries.

## Project direction

The longer-term goal is native Bayer RAW over USB (and standalone `ZVOS` acquisition). Current work completes hardware register/clock bring-up for the IMX284 sensor and DFE pipeline (`SGC0..3`, SLVS-EC PHY, `RdcW0` / `ISP0` `AIF3`) while expanding `ZVOS` (`os_shell.c`, `bayer_capture.h`) and verifying offline against `av-cam.bin` and QEMU `-M zve10`. Stock boot remains the fallback via battery pull. Start with the [camera overview](CAMERA_OVERVIEW.md).

## Latest checkpoints

| Area | Last evidenced state | Confidence and pending work |
| --- | --- | --- |
| Bare-metal ZVOS runtime | `boot.ko` v3 + `crt0.S` + `zvrt_runtime.c` + `os_shell.c` with uncached `ZVRT_DISPLAY_PA` double-buffering, GIC IRQ dispatch, hardware key ADC/GPIO polling, and 5,258-frame 24 fps Bad Apple!! playback. `verify_os_shell.py` and `verify_bayer_capture.py` pass in Unicorn. | Hardware verified for LCD scanout, quiesce, MMU takeover, and Bad Apple!! playback; `BayerRAW` capture loop hits `ISP0` timeout (`SGC0` inactive) in hardware trials. [Hardware handoff](hardware/HANDOFF.md) · [ZVOS spec](hardware/ZVOS_SPEC.md). |
| Bare-metal Bayer bring-up | Behavioral `CXD90057`/`IMX284` drivers (`cxd90057_hw.h`, `cxd90057_pipeline.h`, `imx284_sensor.h`, `senser_bayer_runner.c`) and `cold-warm-exp-01..35` + `sgc0-factory-passive-01` isolate the Mode-1 stall to `SGC0` start qualification (`0xfc0a1110[16]=0`, `HVcnt=0x3fff3fff`) despite matching 79/80 `SyncSeq` & 64/64 `DFE PLL/CRG` words. Cross-check of a6400 confirms bit-identical `dfe_dat.bin` and shared `IMX284`/`CXD90057` tables. | [Sensor pipeline](hardware/SENSOR_PIPELINE.md) · [Bayer handoff](../research/device/zve10_ram_boot/BAYER_HANDOFF.md) · `SyncTask` (`0x635ce230`) pre-start gate open. |
| QEMU 11.1.2 (`-M zve10`) | Standalone QEMU builds locally (`emulator/`), boots stock `vmlinux.bin` + `initrd.img` to BusyBox `ash`, models OSD0/ADC/GPIO, and displays the adapted Sony menu (`emulator/menu.py`). | M1–M5 automated suite passes; full normal `liro.ko` / live-view / sensor emulation remains open. [QEMU emulator](hardware/QEMU_EMULATOR.md). |
| Permanent UVC demo | The 16 November installation log read back the 2.4p colour-bars pair and producer. The installer returned COLOR_BARS_PERMANENT_PAIR_VERIFIED. | Installed-byte evidence. A later cold-boot readback and new host capture were not collected during consolidation. [Installation log](../research/firmware/evidence/zve10-20261117/demo/install-final.txt). |
| Live VGA candidate | Earlier v4.0 capture delivered 15 complete frames near 2.3 fps, followed by an I/O error and a reported camera crash. | Historical partial capture. It is insufficient to claim stable live video. The later colour-bars installation is the latest recorded permanent UVC checkpoint. |
| 1080p SuperSpeed | The later rebuilt candidate manifest explicitly says hardware_tested=false. It retains chunk staging and corrects earlier registration/table changes. | Offline candidate. Sustained SuperSpeed delivery remains unverified. [Build manifest](../research/firmware/evidence/zve10-20261117/transport/manifest.json). |
| Normal shooting access | Pinned SSH authenticated to root at 192.168.137.152. im.elf and LiRo ran during reported 4K24 recording and later live view. | Hardware observed on 17 November. IP, mode and PIDs are session-specific. [Access guide](ACCESS_AND_TOOLS.md). |
| Device utilities | Existing /tmp/busybox supplied 269 applets. A 25,908-byte ARM register dumper and a trace-reader script were installed under /tmp/zve10-tools. | Register attach/detach tested on a disposable sleep process. Debugging im.elf and reboot persistence remain unverified. [Tool source](../research/device/zve10_diagnostics/README.md). |
| Pipeline timing | SetImgRd intervals 41.629–41.754 ms, with YC::VD_Pre and MEC::VD_Drv near 20.8 ms. | Hardware event cadence. Unique pixel-frame rates and DMA completion semantics remain open. [Trace evidence](../research/firmware/evidence/zve10-20261117/README.md). |
| Bayer acquisition | Offline native dump and DFE callback leads exist. Live traces have not identified a completed, stable Bayer buffer. | No verified continuous Bayer capture. [Claim review](../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md). |
| GUI loader entry | The Version trigger staged and launched a separate RTOS image. The 16 KiB arena allocator probe passed on hardware. | Larger DDR ownership and independent device initialization remain open. [Loader](imaging/RTOS_ITERATION.md) |
| Resident LCD | v07 displayed full-screen RGBA4444 bars over Output 0 / OSD0. The current reuse demo stops at the stock buffer guard. | Static scanout is hardware-confirmed. The next test needs a stock Version-screen descriptor. [Display checkpoint](hardware/HANDOFF.md) |
| Hardware map | GPL platform definitions, 64 channel windows, IRQ bindings, 1,245 conservative native accessor candidates and saved service observations are indexed. | Structural inventory, not a complete register specification. Sensor bus and DMA completion/ownership remain priority gaps. [Atlas](hardware/README.md). |
| QEMU | External project used for Windows build/UI experiments. | Separate provenance. Its results support emulator behavior and do not establish hardware sensor behavior. |

## Corrections carried forward

- v25 yuy2_live_bind accepts a backend for the implemented 640×480 YUY2/NV16/NV12 source path. It does not currently accept packed Bayer. The checked Sony backend source contains simulated extents and a withdrawn IPC model. Its status remains candidate.
- The Bayer tap prototype emits a slot_id/length pair. The existing UpdateVideoBufEvt interface consumes size/physical. The prototype also lacks a real submission call and an ownership/completion handshake.
- USB ioctl 0xf002 checks staging availability. The audited submit path copies through DMA330 into staging, and its timeout path can return success. These are insufficient source-reuse fences.
- Sampled absence of known RAW DMM unit IDs does not establish that Bayer is inaccessible. Exported RawInfo methods do not establish that a live stream is active.
- DFE registration and event 0x16 signaling have offline support. The earlier event bridge audited in the native dump report resolves to RcResize. Sensor output DMA completion still needs its own runtime identification.
- The later RAW gate audit corrects the older native dump report. Gate 0x63d893f4 accepts the tested selector result equal to 9.
- Observations made in service mode, normal shooting, recording and emulation must retain their mode and date. They describe different runtime configurations.

The [claim review](../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md) links the checked sources and captures. Older STATE and HANDOFF entries remain available for provenance.

## Research order after the pause

1. Confirm the current mode, boot identity, firmware readback and available access paths.
2. Use the subsystem overview to choose a single unanswered boundary and define the observation that would resolve it.
3. For the image pipeline, correlate readout, DFE completion, MovItp consumption, YC delivery and recording using operation/frame IDs and buffer metadata.
4. Demonstrate a stable native Bayer source and its lifetime before connecting it to USB.
5. Measure transport completion and sustained frame delivery using the actual negotiated link.

For each resumed run, store the command, mode, raw output, input/build identity and conclusion with limits in a dated evidence directory. Update this page with the resulting checkpoint and link to that evidence.

## Offline package regression correction

On 18 November, the HD package test was changed to compile the current revision 4.6 recipe into an isolated package. Installer guards and the kernel dependency now follow the actual packaged files, all required files have checked sizes/MD5/SHA-256, and a failed rebuild invalidates the prior manifest. The full suite passed 294 tests with 12 fixture-dependent skips and no deselections. [Validation record](archive/HD_PACKAGE_FIX_20261118.json) and [recipe instructions](../research/firmware/yuy2_transport_v43_usb3_hd/README.md).

## Version-screen launch and hardware research, 18–20 November

The Version probe displayed 88.88 on the camera. The input mapper identified the directional events. The first sequence failed on hardware because Center exited the menu and only Up registered reliably. The direction-only sequence Up → Down → Left → Right → Up reached ARMED OK. A returning RAM payload then displayed HELLO. A separate resident runtime held an access-LED heartbeat and the camera booted normally after battery removal.

The rear LCD displayed full-screen RGBA4444 bars through inherited Output 0 / OSD0 scanout. The independent image loader validated a 16 KiB arena on hardware. Later probes identified VPH AIF activity after GO and showed that the tested stop sequence cleared the sampled display activity. The installed stock-buffer reuse demo reported two flashes at its descriptor guard. Read-only Senser captures then mapped a separate stock OSD buffer and traced the mode 0x1b request to the panel switch. Cold LCD bring-up, general DDR ownership, and native Bayer RAW transport remain open. [GUI milestones](ui/README.md) · [Session handoff](hardware/HANDOFF.md)

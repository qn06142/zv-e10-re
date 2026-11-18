# ZV-E10 current research status

Consolidated 18 November 2026. Camera research is paused at the user's request. This page records the latest available checkpoints. No camera query or firmware change was performed for this consolidation. The current powered state and installation need fresh readback when work resumes.

## Project direction

The longer-term goal is native Bayer RAW over USB. The paused investigation aims to understand the camera's complete image pipeline beyond the offline map. The immediate organizational milestone is a shared subsystem map and reproducible evidence. Start with the [camera overview](CAMERA_OVERVIEW.md).

## Latest checkpoints

| Area | Last evidenced state | Confidence and pending work |
| --- | --- | --- |
| Permanent UVC demo | The 16 November installation log read back the 2.4p colour-bars pair and producer. The installer returned COLOR_BARS_PERMANENT_PAIR_VERIFIED. | Installed-byte evidence. A later cold-boot readback and new host capture were not collected during consolidation. [Installation log](../research/firmware/evidence/zve10-20261117/demo/install-final.txt). |
| Live VGA candidate | Earlier v4.0 capture delivered 15 complete frames near 2.3 fps, followed by an I/O error and a reported camera crash. | Historical partial capture. It is insufficient to claim stable live video. The later colour-bars installation is the latest recorded permanent UVC checkpoint. |
| 1080p SuperSpeed | The later rebuilt candidate manifest explicitly says hardware_tested=false. It retains chunk staging and corrects earlier registration/table changes. | Offline candidate. Sustained SuperSpeed delivery remains unverified. [Build manifest](../research/firmware/evidence/zve10-20261117/transport/manifest.json). |
| Normal shooting access | Pinned SSH authenticated to root at 192.168.137.152. im.elf and LiRo ran during reported 4K24 recording and later live view. | Hardware observed on 17 November. IP, mode and PIDs are session-specific. [Access guide](ACCESS_AND_TOOLS.md). |
| Device utilities | Existing /tmp/busybox supplied 269 applets. A 25,908-byte ARM register dumper and a trace-reader script were installed under /tmp/zve10-tools. | Register attach/detach tested on a disposable sleep process. Debugging im.elf and reboot persistence remain unverified. [Tool source](../research/device/zve10_diagnostics/README.md). |
| Pipeline timing | SetImgRd intervals 41.629–41.754 ms, with YC::VD_Pre and MEC::VD_Drv near 20.8 ms. | Hardware event cadence. Unique pixel-frame rates and DMA completion semantics remain open. [Trace evidence](../research/firmware/evidence/zve10-20261117/README.md). |
| Bayer acquisition | Offline native dump and DFE callback leads exist. Live traces have not identified a completed, stable Bayer buffer. | No verified continuous Bayer capture. [Claim review](../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md). |
| RTOS replacement | Owned-buffer hello-world variants were exercised with original loader instructions and mocked services. | Offline experiment, set aside by the user. Physical LCD output and Linux access with LiRo removed remain unresolved. |
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

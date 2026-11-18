# Original User Request

## 2026-10-17T01:37:11Z

Perform rigorous offline reverse engineering and binary analysis of the Sony ZV-E10 (CXD90045) UVC webcam subsystem to isolate the exact bugs in prior patch iterations, and construct a hardened, fully verified patch suite with extensive automated test coverage against the actual firmware binaries.

Working directory: D:\02_Development_And_Projects\pmca-re
Integrity mode: development

## Requirements

### R1. Root-Cause Audit of Previous Failure Modes
Perform instruction-level and data-flow auditing on `libInfraUsbCmn.so`, `libInfraStreamingUsb.so`, and `usbg_video.ko` (from `.local/dumps/trees/` and `.local/dumps/staged/uvc/binaries/`). Determine the precise bugs that broke previous attempts—specifically checking descriptor `wTotalLength` miscalculations, missing format indexes, endpoint max packet constraints, memory allocator exhaustion, and unpatched upstream frame buffer providers.

### R2. Complete UVC & Pipeline Structural Realignment
Reconstruct the full UVC descriptor hierarchy and video pipeline control path. Ensure that all modifications maintain strict compliance with UVC specifications (CS_INTERFACE, VS_FORMAT_MJPEG, VS_FRAME_MJPEG) and that frame dimension modifications match upstream video encoder outputs without register clobbering or stack corruption.

### R3. Multi-Layer Programmatic Verification Suite
Build a comprehensive, adversarial offline verification suite in `tests/test_uvc_patch.py` that executes via pytest. The test suite must independently disassemble, parse, and validate every patched byte against the genuine binary files on disk, ensuring zero tolerance for unverified assumptions or partial implementations.

## Acceptance Criteria

### UVC Descriptor Specification Integrity
- [ ] Class-Specific Video Streaming (CS_INTERFACE) Header `wTotalLength` exactly matches the byte sum of all downstream format and frame descriptors.
- [ ] All frame descriptors define valid width, height, default intervals, and bitrate limits without integer wrap-around or negative values.
- [ ] USB 2.0 High-Speed bulk transfer parameters strictly obey endpoint descriptor limits (512-byte max packet size, valid buffer multiplier).

### Binary & Instruction-Level Guardrails
- [ ] Every modified instruction in `libInfraStreamingUsb.so` and `libInfraUsbCmn.so` is decoded via capstone or automated disassembler and verified to be a valid ARM/Thumb-2 instruction.
- [ ] No callee-saved registers (R4-R11, SP, LR) are clobbered across function prologues/epilogues.
- [ ] All PC-relative literal pool loads and branch targets resolve to valid, aligned code/data addresses within bounds.

### Adversarial Test Enforcement
- [ ] The automated test suite (`pytest tests/test_uvc_patch.py`) runs offline, passes 100%, and explicitly fails if any patch offset, opcode, or descriptor byte is altered or missing.
- [ ] Every claimed patch address and symbol is verified to physically exist in the repository's dump binaries with matching SHA-256 / MD5 hashes.
- [ ] A dedicated test simulates the descriptor parsing logic to guarantee that host operating systems (Windows/Linux/macOS) parse the generated descriptors without rejection.

### Technical Deliverables
- [ ] Comprehensive bug post-mortem documenting exactly why previous patches failed.
- [ ] Completely verified, single-shot patch generator script and patch tables.


## 2026-10-24T02:07:56Z

Diagnostic reverse engineering and log decoder recovery for the Sony ZV-E10 USB webcam experiment. Use many implementer agents with minimal verification agents.

Working directory: D:\02_Development_And_Projects\pmca-re
Previous session workspace: C:\Users\qn061\Documents\Codex\2026-10-22\chec
Integrity mode: development

## Reference Material & Baseline Constraints
- Diagnostics handoff: docs/usb/uvc_yuy2_diagnostics_handoff.md
- State: docs/archive/agents/STATE.md
- Feasibility: docs/usb/uvc_uncompressed_usb2_feasibility.md
- Evidence: C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\usb-debug-20261024-01\camera\app-sequential.log (1,936,183 bytes)
- Firmware binaries / leads: .local/dumps/camera_2025/usr/usr/bin/ulogio.elf, .local/dumps/camera_2025/usr/usr/lib/libosal_ulogio.so, .local/dumps/camera_2025/usr/usr/kmod/osal_ulogio.ko
- Python runtime: D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe -B
- Offline investigation only: do not replay old RAM deployment jobs, flash firmware, or modify persistent partitions.
- Strictly separate 22 October observations (YUY2 advertised, 25-second zero-frame capture timeout) from 24 October observations (USB disappeared, controls unresponsive before capture, followed by manual restart).
- Treat *-after.* files as post-restart snapshots, not live hang state.

## Requirements

### R1. Sony Binary Application-Log Recovery and Decoder
Recover Sony's binary app-sequential.log format using clues from Sony reader/writer binaries (ulogio.elf, libosal_ulogio.so, osal_ulogio.ko). Build a validated decoder script that:
- Preserves byte offsets, record framing, timestamps, subsystem IDs, and event arguments.
- Safely flags and preserves undecoded or corrupted record chunks without crashing.
- Decodes the 1,936,183-byte log capture and determines whether the latest streaming transition was captured prior to the restart.

### R2. Root-Cause Analysis of VideoEsManager::alloc_video_memory Error 4
Trace why VideoEsManager::alloc_video_memory returned generic error 4 when requesting source unit type 0x50f:
- Follow control flow and IPC message/reply handling.
- Differentiate between IPC transport failure, response-status translation, unsupported unit type/configuration, or memory pool exhaustion.
- Do not assume raw RTOS memory exhaustion or equate error 4 with a raw RTOS error without verification.
- Compare original caller initialization, ownership (0x2da), and unit type selection (0x50e vs 0x50f) against the prototype.

### R3. Startup Failure, Cleanup, and Retry Architecture
Analyze the lifecycle gap between the prototype (which latches initialization error permanently) and the stock firmware worker (libInfraStreamingUsb.so VA 0x9700, which ignores producer errors and assumes started state in failure):
- Formulate a bounded failure propagation, cleanup, and retry design adhering to the actual state/semaphore contract.

### R4. Documentation and Traceability
- Document all evidence-backed findings in docs/usb/uvc_yuy2_diagnostics_handoff.md and docs/archive/agents/STATE.md with raw byte offsets and disassembly addresses.
- Define a bounded, verifiable next-step test protocol for future live testing.
- Verify documentation consistency via python -B research/firmware/check_docs.py.

## Acceptance Criteria

### Binary Decoder
- [ ] Standalone decoder script executes cleanly against app-sequential.log via .venv\Scripts\python.exe -B.
- [ ] Decoded output records byte offsets, timestamps, and subsystem markers while retaining unparsed data cleanly.

### Diagnostic Analysis
- [ ] Assembly/decompilation trace explains the return path for generic error 4 on unit type 0x50f.
- [ ] Root cause identified (IPC vs parameter validation vs unit state vs allocator pool).

### Lifecycle & Documentation
- [ ] State/flow specification for startup failure, cleanup, and retry.
- [ ] docs/usb/uvc_yuy2_diagnostics_handoff.md and docs/archive/agents/STATE.md updated; check_docs.py passes with zero errors.


## 2026-10-24T06:11:24Z

This is a single self-contained fix; keep it small and focused.
Investigate why the USB host receives zero frame bytes despite the camera video pipeline successfully generating and accepting frame submissions (180+ successful API submissions in revision 2.1 / 2.2). Focus on offline disassembly and control-flow tracing across `usbg_video.ko`, `libInfraUsbCmn.so`, UVC Probe/Commit negotiation, and endpoint transfer gating.

Working directory: D:\02_Development_And_Projects\pmca-re
Previous session workspace: C:\Users\qn061\Documents\Codex\2026-10-22\chec
Integrity mode: development

## Reference Material & Baseline Constraints
- Session handoff: `docs/archive/sessions/HANDOFF.md`
- Diagnostic handoff: `docs/usb/uvc_yuy2_diagnostics_handoff.md`
- Revision 2.1 live report: `docs/usb/uvc_yuy2_patch_v21.md`
- Revision 2.2 live report: `docs/usb/uvc_yuy2_patch_v22.md`
- Feasibility analysis: `docs/usb/uvc_uncompressed_usb2_feasibility.md`
- Firmware binaries / kernel modules: `.local/dumps/camera_2025/usr/usr/kmod/usbg_video.ko`, `.local/dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so`, `.local/dumps/camera_2025/usr/usr/lib/libInfraStreamingUsb.so`
- Python runtime: `D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe -B`
- Offline investigation only: do not flash firmware, alter persistent camera partitions, or replay deployment jobs.

## Requirements

### R1. UVC Probe/Commit Negotiation and Control Flow Trace
Trace the UVC class control request handling in `libInfraUsbCmn.so` and `usbg_video.ko` for `VS_PROBE_CONTROL` (`0x01`) and `VS_COMMIT_CONTROL` (`0x02`):
- Trace ioctl `0x4008f004` (supply probe info at `0x11ea8`) and `0x4008f005` (supply commit info at `0x11ec0`).
- Determine why runtime PROBE/COMMIT markers were absent in the recovered logs.
- Identify what host control transfer sequence is required before the driver transitions the streaming endpoint to an active transmission state.

### R2. USB Gadget Endpoint & DMA330 Delivery Path Analysis
Trace the frame submission path from `UpdateVideoBufEvt` (ioctl `0x4008f003` at `0x11e90`) into `usbg_video.ko`:
- Follow the 8-byte transfer state handover (`.text+0x0d80` through `.text+0x0e90`), 12-byte UVC payload header assembly (`.text+0x0f24`), and `dma330_mem_transfer_async` invocation (`.text+0x0f70`).
- Determine whether transfers are blocked, dropped, or queued without being committed to the bulk IN endpoint FIFO.
- Identify the exact conditions under which `uvc_transfer_dmac_cb` (`.text+0x06a0`) fires and completes transfers to the host.

### R3. Diagnostic Synthesis & Documentation
- Correlate host DirectShow / FFmpeg exit-124 25-second timeout behavior with the camera-side gadget state machine.
- Document all evidence-backed findings citing exact instruction addresses and data structures in `docs/usb/uvc_yuy2_diagnostics_handoff.md` and `docs/archive/agents/STATE.md`.
- Verify documentation with `python -B research/firmware/check_docs.py`.

## Acceptance Criteria

### Control & Negotiation
- [ ] Complete disassembly trace of `usbg_video.ko` and `libInfraUsbCmn.so` probe/commit control endpoints.
- [ ] Root cause identified for why probe/commit events were unrecorded or bypassed during host streaming activation.

### Endpoint & DMA Delivery
- [ ] Disassembly and control flow trace explaining why 180+ successful API submissions produce zero bytes on the USB bulk endpoint.
- [ ] Concrete gating condition identified (e.g. interface alternate setting, endpoint enable bit, buffer ring synchronization, or header format mismatch).

### Traceability & Consistency
- [ ] Findings and addresses integrated into repository documentation.
- [ ] `check_docs.py` passes with zero broken links or unmatched anchors.


## 2026-10-24T09:08:29Z

Reverse engineer and design a live uncompressed camera frame source from the existing viewfinder/ISP/display pipeline to replace synthetic colour bars in the verified 640×480 YUY2 USB transport on the Sony ZV-E10. Use many implementer agents with minimal verification agents.

Working directory: D:\02_Development_And_Projects\pmca-re
Previous session workspace: C:\Users\qn061\Documents\Codex\2026-10-22\chec
Python runtime: D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe -B
Integrity mode: development

## Reference Material & Baseline Constraints
- Session handoff: `docs/archive/sessions/HANDOFF.md`, `docs/archive/agents/STATE.md`
- Working transport baseline: `docs/usb/uvc_yuy2_patch_v23.md`, `research/firmware/yuy2_transport_v23/`
- Delivery audit: `docs/usb/uvc_yuy2_delivery_audit_20261024.md`
- Historical leads & feasibility: `docs/usb/uvc_uncompressed_usb2_feasibility.md`, `docs/usb/uvc_yuy2_diagnostics_handoff.md`
- Camera dump & disassembly: `.local/outputs/raw-usb-investigation/`, `.local/outputs/offline-uvc-re/`, `.local/dumps/camera_2025/`
- Offline reverse engineering only: do not touch live camera, do not flash firmware, do not reboot camera.
- Do not modify primary agent's concurrent work in `research/firmware/yuy2_transport_v24/` (same-session host-client reopen fix).
- Preserve existing working 640×480 YUY2 USB 2 transport; keep synthetic fallback available in prototype design.

## Requirements

### R1. Candidate Frame Source Survey & Ranking
Trace candidate liveview, viewfinder, display, ISP, and framebuffer interfaces across offline Linux binaries (`libBizFw.so`, `libInfraStreamingUsb.so`), kernel modules (`stream.ko`, `stream2.ko`), and RTOS dumps. Identify and rank concrete frame sources by evidence and access complexity, establishing true representation (e.g., NV12, YUY2, RGB, or Bayer).

### R2. Deep Contract & Metadata Recovery for Best Candidate
For the highest-ranked viable candidate, recover the full operational contract:
- Acquisition/request API and completion/fence synchronization.
- Geometry, plane layout, stride, crop/downscale parameters, and chroma subsampling.
- Memory ownership, CPU virtual vs. physical addressing, cache maintenance, and safe release/return protocol.

### R3. Producer Integration & Conversion Architecture
Design an implementable interface for the YUY2 USB producer:
- Bounded copy and color-space/geometry conversion into the exclusively owned DMM Unit `0x276` source buffer.
- Safe lifecycle, avoiding holding locks across IPC waits, and maintaining coexistence with preview/AF.
- Quantified memory bandwidth and CPU overhead for 640×480 @ 10/30 fps.

### R4. Documentation & Prototype Implementation
- Write `docs/usb/uvc_live_raw_frame_source.md` with source comparisons, handoff table, and exact disassembly citations.
- Implement source-only prototype/interface files under `research/firmware/raw_frame_source/`.
- Validate documentation integrity via `python -B research/firmware/check_docs.py`.

## Acceptance Criteria

### Candidate Ranking & Evaluation
- [ ] Ranked survey of frame source candidates with specific binary hashes, symbols, and VAs.
- [ ] Clear distinction established between processed YUV/RGB and Bayer RAW or JPEG.

### Source Contract Specification
- [ ] Concrete acquire, fence/ready, format/stride, and release call-sequence mapped with disassembled code.
- [ ] Physical vs. virtual memory mapping and cache coherency path documented.

### Integration & Handoff
- [ ] Handoff table documenting dimensions, pixel format, alignment, crop/scale needs, and release ownership.
- [ ] `docs/usb/uvc_live_raw_frame_source.md` created; `check_docs.py` passes with zero broken links or unmatched anchors.


## 2026-10-24T10:12:54Z

URGENT HARDWARE CONSTRAINT FROM USER:
ARM NEON is NOT supported by the Sony ZV-E10 CPU (BIONZ X ARMv7-A core has VFPv3-D16 only, NO NEON SIMD extensions).

Immediately notify the orchestrator (c9c124fc-a8a6-4853-a8dc-1a9215545c5f) and all active workers (m3_arch_worker_1, m4_prototype_worker_1, m4_doc_worker_2):
1. Remove/disable all ARM NEON SIMD instructions (e.g. vld2, vst2, vzip, etc.) across conversion routines to prevent SIGILL (Illegal Instruction) crashes on target hardware.
2. Replace conversion routines in research/firmware/raw_frame_source/ with pure scalar ARMv7-A / Thumb-2 integer operations or standard C loops.
3. Update CPU overhead calculations and documentation in docs/usb/uvc_live_raw_frame_source.md to reflect scalar integer conversion without NEON.
4. Re-verify all conversion kernels with GCC/Unicorn targeting ARMv7-A without NEON (e.g. -mfpu=vfpv3-d16 or no FPU/NEON).


## 2026-10-24T13:42:42Z

Recover and implement the real Sony completed-YC frame acquisition and release backend for the Sony ZV-E10, conforming to `raw_live_ops` and binding to offline revision 2.5 transport while preserving proven USB completion fences, synthetic fallback, and target CPU constraints (four Cortex-A5 cores, VFPv4, no NEON). Use many implementer agents with minimal verification agents.

Working directory: D:\02_Development_And_Projects\pmca-re
Previous session workspace: C:\Users\qn061\Documents\Codex\2026-10-22\chec
Python runtime: D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe -B
Integrity mode: development

## Reference Material & Baseline Constraints
- Live frame implementation & audit: `docs/usb/uvc_live_frame_implementation.md`
- Session handoff: `docs/archive/sessions/HANDOFF.md`
- Working transport baseline: `docs/usb/uvc_yuy2_patch_v24p.md` (working on-camera 2.4p)
- Revision 2.5 offline architecture: `research/firmware/yuy2_transport_v25/README.md`
- Backend interface contract: `research/firmware/raw_frame_source/raw_live_source.h`
- CPU constraints: Four Cortex-A5 cores (part 0xc05, VFPv4, no NEON). Never use NEON instructions or assume Cortex-A9.
- Critical corrections: Do not overwrite `VideoEsManager::get_video_image` body at `0x90c0` (it is the patch activation gate). Do not assume `dumpSdsYccFromHandle` or `VdfCh::getYUVReadStart` is a live streaming subscription.
- Offline only: Do not touch, reboot, or flash the camera. Preserve synthetic fallback.

## Requirements

### R1. Real Consumer Call-Site Tracing & Subscription Recovery
Trace genuine consumers of `C_DataflowInfra_StdData_YC` across saved Linux shared objects (`dataflowInfraFramework.so`, `libBizFw.so`, `libInfraStreamingUsb.so`) and RTOS binaries (`av-cam.bin`). Recover the exact subscription/pin identity, request/completion ABI, stable-frame ownership, physical plane resolution, and lease-return mechanism.

### R2. Representation & Memory Visibility Verification
Establish the authentic pixel order, dimensions, strides, compression, color range/colorimetry, and CPU memory visibility/barriers for the discovered frame source. Clearly delineate confirmed facts from unknowns.

### R3. `raw_live_ops` Backend Implementation & Revision 2.5 Binding
Implement a concrete backend conforming to `raw_live_ops` in `research/firmware/raw_frame_source/`:
- Honor acquisition timeout of $\le 10$ ms.
- Retain the frame lease until release succeeds.
- Enforce the USB completion fence: never acquire or mutate while host `EBUSY` persists; copy into owned Unit `0x276`.
- Bind to revision 2.5 via `yuy2_live_bind`.

### R4. Offline ABI/Ownership Verification & Documentation Updates
- Implement offline test cases testing real compiled structs, ABI calling conventions, and ownership lifecycles with mock services.
- Cite exact binary hashes, mangled symbols, instruction offsets, and call sites.
- Update `docs/usb/uvc_live_frame_implementation.md` and handoff documentation; validate via `python -B research/firmware/check_docs.py`.

## Acceptance Criteria

### Reverse Engineering Trace
- [ ] Genuine consumer call site of completed `C_DataflowInfra_StdData_YC` identified with binary hash, symbol, and instruction VAs.
- [ ] Concrete subscription, ready/fence, and release call sequence documented.

### Implementation & Verification
- [ ] Concrete backend implementing `raw_live_ops` compiled and bound to revision 2.5 without NEON instructions.
- [ ] Offline test suite verifies timeout handling ($\le 10$ ms), error fallback to synthetic bars, and safe lease release.
- [ ] `check_docs.py` passes cleanly across all documentation.


## 2026-10-28T15:01:49Z

Remove all verification agents except for the final victory verifier.

Continue offline reverse engineering of the Sony ZV-E10 live YC frame pipeline to establish the completed-frame delivery, ownership, and format contracts needed for a working live-sensor webcam patch, prioritizing subsystem understanding over another incremental flash.

Working directory: D:\02_Development_And_Projects\pmca-re
Workspace: C:\Users\qn061\Documents\Codex\2026-10-22\chec
Integrity mode: development

## Context & Evidence Baseline

- **Hardware Policy**: HARDWARE TESTING IS PAUSED. Do not access, reboot, flash, roll back, or request mode changes on the camera. It remains on revision 3.3. Service sessions are closed. All work must be strictly offline.
- **Reference Binaries & Modules**:
  - Matched pair: `yuy2_640_v33vga.so` (MD5 `87ddc16bd8e0774926e5eb6d16165d20`), `libInfraStreamingUsb.so` (MD5 `909c4ffadc9e5972b25101529d5f8773`).
  - Kernel module: `dmm.ko` (MD5 `15c8f7807b291c0af3c77fe55848577f`).
- **Primary Live Evidence**:
  - Genuine 4096-byte retained SSYC descriptor: `.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin` (SHA256: `9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c`).
  - 12 ETRY categories present: 0, 1, 2, 6, 4, 5, 18, 12, 16, 10, 22, 23.
  - ImageSizeInfo: `image_attach=1`, `unit_type=0x295`, `unit_handle=0x7f24` (session-transient, never replay), `record/canvas/valid/target=1920x1080`, `unit_data_offset=0`, `yc_compress=1`, `data_site=0`, `data_transfer=1`, `data_placement=1`, `data_content=2`, `data_scan=1`, `strip_width=64`, `yc_bit_depth=0`, `aspect=2`.
- **Known Blockers**:
  - Attached pixel handle rejected by DMM Share: native `-517` (`0xfdfb`), translated status `-5`. Kernel code at relocatable `.text+0x8894..0x88a0` identifies slot serial mismatch.
  - `vga_source_contract` rejects nonzero `data_transfer`, but real descriptor has `data_transfer=1`.
- **Primary Leads**:
  - RTOS VEF metadata builder: `0x6374cdd4`
  - Broader YUVInfo metadata builder: `0x6374ae88`
  - VDF ownership manager vtables: `0x645852c8`, `0x64585300`
  - Ownership share method: `0x63748bec`
  - VDF release path: `0x63728000..0x6372889c`
  - libObj `resize2VGA`: `0x19fd94`
  - libObj paired allocator: `0x206c56`
  - libObj resize helper: `0x19fc88`
  - libBizFw `SdfCh::resizeRotate`: `0x369b4`
  - libBizFw `freeSdsAndYc`: `0x364a1`
  - Kernel `dmm.ko`: Share handler `.text+0x62e4`, Share reference checks `.text+0x884c`, Access-info bookkeeping `.text+0x9238`.

## Requirements

### R1. Producer-to-Consumer Delivery and Completion Path
Trace the real VEF/VDF metadata and pixel ownership transfer from the original builders (`0x6374cdd4`, `0x6374ae88`, `0x645852c8`, `0x63748bec`, `0x63728000..0x6372889c`). Identify actual Linux consumer initialization, subscription callbacks, and event completion mechanics to establish how consumers obtain a fresh, valid metadata/pixel pair without relying on uncoordinated pool scanning.

### R2. DMM Lifetime, Generation Validation, and Safe Cleanup
Map allocation serial, index, state, and ownership transitions across Share/Open/Close/Free and paired SDS/image release using original `dmm.ko` logic. Explain how valid SSYC metadata retained an expired image handle (native `-517` slot serial mismatch vs native `-1`). Trace real callers of `freeSdsAndYc` (`0x364a1`) and prove cleanup semantics (releasing metadata reference without double-freeing or corrupting producer image state).

### R3. SSYC Format, Enums, and Completion Semantics
Trace the captured 12-category SSYC descriptor against original constructors, getters, and consumers. Establish the proven meaning and consumer requirements for `data_transfer=1`, `yc_compress=1`, `data_site=0`, `data_placement=1`, `data_content=2`, `data_scan=1`, `strip_width=64`, and `yc_bit_depth=0`. Identify genuine sequence/timing categories to distinguish frame completion tokens from arbitrary counters.

### R4. SDF Hardware Resize Contract & Consolidated Patch Design
Establish the exact SDF hardware input and output descriptor contracts (`0x19fd94`, `0x206c56`, `0x19fc88`, `0x369b4`), including channel/thread setup, accepted compression/transfer flags, cache/coherency requirements, and ACK/CMP semantics. Produce a consolidated, reviewable patch design addressing delivery, generation, format, and resize together, backed by compiled ARM and host verification.

### R5. Safety, Environment, and Documentation Guards
Maintain strict offline discipline: zero camera interaction, zero hardware flash/reboot commands. Keep proprietary binaries and captures local under `.local/dumps/camera_2025/` (never committed to Git). Update `docs/archive/sessions/HANDOFF.md` and `docs/archive/sessions/YC_SUBSYSTEM_RESEARCH_PLAN.md` with concrete findings, separating proven facts from hypotheses.

## Acceptance Criteria

### Subsystem Architecture & Contracts
- [ ] Evidence-backed call graph and ownership event table documented with concrete instruction addresses for producer generation, delivery, subscription, and release.
- [ ] DMM ownership state machine documented explaining the native `-517` serial mismatch, with proof of whether stale pixel handles permit safe metadata-only cleanup without double-free or producer corruption.
- [ ] SSYC format specification mapping all 12 observed ETRY categories and resolving the `data_transfer=1` blocker against consumer/SDF expectations without arbitrary flag manipulation.
- [ ] SDF hardware resize input/output contract established with explicit ACK/CMP, cache coherency, and cancellation safety rules.

### Verification & Implementation
- [ ] Verification test suite compiles cleanly using `arm-none-eabi-gcc` and host `gcc`.
- [ ] Offline test harness verifies descriptor decoding and contract validation against the genuine retained descriptor `source-ssyc-retained.bin` (SHA256: `9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c`).
- [ ] Consolidated patch implementation updated offline in `research/firmware/yuy2_transport_v33_source_retry/source/` incorporating the resolved contracts.
- [ ] Zero camera interaction executed (no hardware reboot, flashing, roll back, or USB mode changes).
- [ ] `HANDOFF.md` and `YC_SUBSYSTEM_RESEARCH_PLAN.md` updated with comprehensive findings and an explicit, bounded test plan for when hardware testing eventually resumes.

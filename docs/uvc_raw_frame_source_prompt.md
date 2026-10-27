## Current implementation — resolve the Sony backend next

Read `docs/uvc_live_frame_implementation.md` and `research/firmware/yuy2_transport_v25/README.md` first. A tested generic lease/map/convert/release core is implemented and integrated into the offline 2.5 producer candidate. It needs the real completed-YC subscription, ownership and release ABI bound through `yuy2_live_bind`. Do not replace the persistent activation gate with a call to the old JPEG getter, infer format from extent size, or treat VDF status queries as frame leases. Camera still runs permanent 2.4p. Implement the verified backend separately; do not replay deployment jobs or modify camera state as part of offline research.

## Live CPU verification — 24 October 2026

Direct service-shell `/proc/cpuinfo` reports four processors (0–3), ARM implementer `0x41`, part `0xc05` (Cortex-A5), revision 1, hardware ARM-CXD900X0. Features: `swp half thumb fastmult vfp edsp vfpv3 vfpv3d16 tls vfpv4`; **no neon**. Earlier Cortex-A9/NEON assumptions are incorrect for the Linux-visible CPU. VFPv4 is not evidence of NEON. Plan scalar integer conversion/copy; do not execute NEON kernels without new capability evidence. Live feature absence establishes unavailable advertised userspace support, not physical absence independently of kernel configuration. No instruction probe performed. Raw-source report NEON kernels/performance estimates need rework; older A9 compiler tuning does not establish A9 hardware. Evidence: session `outputs/zve10-cpuinfo-neon.log`. Read-only query; no firmware writes.

# Find live uncompressed camera frames for the working USB YUY2 transport

Work offline in `D:\02_Development_And_Projects\pmca-re`.
Session workspace: `C:\Users\qn061\Documents\Codex\2026-10-22\chec`.
Python: `D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe -B`.

## Current transport checkpoint — permanent revision 2.4p

Read `docs/uvc_yuy2_patch_v24p.md` and `research/firmware/yuy2_transport_v24p/README.md` first. Revision 2.4p is persistent and reboot verified, with automatic video-prepare activation. First FFmpeg, same-session reopen, and subsequent OBS passed without mode toggles. The former host-reopen bug described historically below is fixed in this tested sequence. Preserve transport/geometry while investigating source acquisition; do not modify lifecycle or replay camera jobs. Current streaming/producer MD5s: `5fde77e394572ebcf420f8941575f6c4` / `9181ef744955190d04728cf4ef7965c5`; kernel `c1cad400372e26eca729e4b9bc47a237`. Keep synthetic fallback. Raw-source work remains offline-only; 2.3 evidence below is historical, not the current installation.

## Objective

Find and reverse engineer a live camera image source that can replace synthetic bars in our proven 640×480 YUY2 USB transport. Deliver an evidence-backed acquisition/conversion/ownership design and, where supported, a guarded offline prototype. Prioritize live, processed, uncompressed YUV/RGB frames from the existing viewfinder/ISP pipeline. Identify the actual representation; do not confuse uncompressed video with Bayer sensor RAW, JPEG, HDMI output or an encoded recording stream. If only Bayer access is found, quantify the extra demosaic/downscale/conversion work instead of assuming it is YUY2.

## Proven starting point — do not restart the old zero-frame investigation

Revision 2.3 delivers synthetic colour bars/counters over USB 2 to Windows. FFmpeg captured ten 614,400-byte frames with exact bar checks and counters 1–10. The user confirmed OBS displays frames/counters after a camera streaming-mode restart at Custom 640×480 / 10 fps / YUY2. Keep this working transport and its geometry as the initial target. This is not yet live camera footage, and nominal 10 fps is not a sustained throughput measurement.

The matching kernel patch advertises a 614,400-byte frame, 614,412-byte one-header payload and 1,000,000 interval in 100 ns units. It skips the PAL/NTSC interval override and sets EOF. Stock kernel MD5 `5b59c2e62c80683d754955ab5de0467d`; deployed candidate MD5 `c1cad400372e26eca729e4b9bc47a237`, sysfs version `yuy2_640_v23`. Userspace MD5 `bef71344d4d6308e57ab65bdff3283e5`.

There is a separate same-session host-client reopen bug: after FFmpeg exits, later clients can receive no frames until USB Streaming is toggled. The primary agent is working on that lifecycle fix in `research/firmware/yuy2_transport_v24/` (candidate work in progress). Do not modify reconnect handling, kernel negotiation, deployment scripts, or this directory as part of the raw-frame investigation. Report any relevant interactions without merging concurrent work.

## Read first

- `docs/90-session/HANDOFF.md`, `docs/agents/STATE.md` — newest checkpoints override older historical notes.
- `docs/uvc_yuy2_patch_v23.md` — proven deployment, host results, hashes and limitations.
- `docs/uvc_yuy2_delivery_audit_20261024.md` — corrected kernel/probe/packetization findings.
- `docs/uvc_uncompressed_usb2_feasibility.md` and `docs/uvc_yuy2_diagnostics_handoff.md` — source candidates and historical exploration.
- `research/firmware/yuy2_transport_v23/` — reproducible producer, kernel patch and ARM verification.
- Local `outputs/yuy2-640-v23/deployment/camera-after-tests/` — 57 camera files / 9,231,531 bytes, hash verified; `app-decoded.txt` has 111,319 clean application records. `captured-01.yuy2` and `first-frame.png` are actual host-delivered synthetic frames.
- `outputs/raw-usb-investigation/` and `outputs/offline-uvc-re/` — saved disassembly and interface analysis.

## Source and transport constraints

The producer exclusively allocates configured DMM type `0x276` → extent `0x333`, capacity `0x320000` (3,276,800 bytes). Live physical address was `0x15b00000`; these are observed values, not fixed future addresses. `/dev/stream` mapping supplies the producer's CPU view. A successful allocation/mapping is reserved for the module lifetime and rebound to current VideoEsManager instances. Uncertain source reuse is prohibited until driver readiness succeeds. Do not borrow or write existing unknown-owner buffers.

Kernel staging uses type `0x50e`, extent `0x589`, 1,843,200 bytes split into two 921,600-byte halves. Type `0x50f` is AUDIO and unsuitable. `alloc_video_memory(self, unit_type, u16 *handle, u32 *physical, u32 *capacity)` takes a configured type, not a byte size. `UpdateVideoBufEvt` takes an eight-byte by-value `{u32 size, u32 physical}` event. The kernel copies pixels using DMA330 into staging after its UVC header. This DMA is transport staging; it does not acquire a live sensor image. Device `write()` is a stub; do not propose it as a replacement transport.

Never assume a source is packed YUY2 because it is called YUV. Establish stride, crop, planes, chroma order/subsampling, physical versus CPU addresses, cache policy and buffer lifetime. A live source buffer must stay valid while copied and be released through its real owner. Prefer a bounded copy/conversion into our exclusively owned source first; a zero-copy design requires a proved fence/release contract. Preserve 640×480 YUY2 host output for the first source substitution.

## Investigation and deliverables

1. Trace candidate liveview/viewfinder/display/ISP/framebuffer APIs in offline Linux libraries, kernel modules and RTOS binaries. Search exports, callers, strings, IPC definitions and DMM allocation owners; rank concrete source candidates by evidence and access cost. Follow both `/dev/stream` and `/dev/stream2` only where disassembly supports a usable frame API.
2. For the best candidate, identify acquire/request, completion/fence, format/plane/stride metadata, CPU mapping/cache maintenance and release. Cite binary hash, symbol, section-relative instruction offsets and data-layout evidence. Separate observed structures, deductions and unknowns.
3. Produce a handoff table covering source dimensions/rate, pixel format, buffer size/alignment, crop/scale/conversion needs, frame readiness, ownership/release and coexistence with preview/AF. Quantify CPU copies and memory bandwidth at the initial geometry. Do not promise higher resolution or USB 3 throughput.
4. Supply an implementable interface to the producer: acquire a complete frame, safely convert/copy it into our owned YUY2 source only when reusable, submit through existing transport, and release the camera frame at the correct point. Keep acquisition/conversion work bounded and avoid holding manager locks across new IPC waits. Identify how streaming mode affects availability of the liveview source.
5. Write `docs/uvc_live_raw_frame_source.md` and source-only investigation/prototype files under `research/firmware/raw_frame_source/`. Preserve generated artifacts under a new session output directory. Provide meaningful offline ABI/conversion/ownership checks if implementing code; do not label mocked services as live proof. Run `python -B research/firmware/check_docs.py`.

## Scope and evidence discipline

This task is offline reverse engineering. Do not access, reboot, flash, unload modules on, or replay jobs against the camera; do not alter persistent partitions. Do not modify the primary agent's USB lifecycle candidate. Keep synthetic fallback available in any source prototype. Report concrete missing evidence and the smallest eventual read-only/live test needed to resolve it.

Old “110 MB physically transmitted” and “Windows necessarily discards every frame because EOF is absent” claims were unsupported. UVC 1.1 makes EOF optional; API success counters alone are not delivery proof. The actual verified FFmpeg raw frames and user-observed OBS preview establish delivery for revision 2.3. Do not reintroduce those retracted assertions or claim a live image source until its frames are demonstrated.

Return a concise result with the best source, exact evidence, a practical producer integration plan, files changed, tests run and unresolved risks. If no viable source is proven, deliver the ranked trace and precise missing acquisition contract rather than inventing an API.

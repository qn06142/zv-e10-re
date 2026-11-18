# Revision 4.2: chunked full-HD UVC fix

30 October 2026. 4.2 files installed/readback verified; postboot persistence verified. Full-HD hardware capture NOT verified.

## Failure evidence recovered

4.1 activation failed on camera, and the user reported that MSC also failed until restarting. Recovered outputs/hd-v41/diagnostic-01/runtime.log (682 bytes), DMM units/maps/dmesg, original kikilog.dat and AccessLog.dat/.bak. The native allocation succeeded with physical0x30000000 and size0x3f4800; SOURCE_READY/SOURCE_REBOUND were logged. No vga.log existed, and no successful SDF call/frame submission is recorded. The failure is before demonstrated frame production; its exact native wait/fault PC is not established. Do not label0x30000000 an invalid physical address: it was returned by native allocation, and DMM has multiple address roots.

The4.1 staging alias selected a different allocator branch based on capacity alone. A structural parser now follows80-byte root/table headers and20-byte extent records. Extent0x589 belongs under root0x4ec, while extent0x1ba appears under conditional tables0x30/0x2. Unit0x127/extent0x165 is under0x2f with alternative parent paths. Configured capacity did not certify the new staging pool's live compatibility. This is a strong reason to remove that dependency, not proof of the precise native activation failure.

During diagnosis, the4.0 wrapper/config restoration and reboot completed before the user's message prohibiting restoration arrived. No restoration actions were taken after that instruction. 4.2 installation has no automatic restore action and does not write DmmConfig.bin. Saved pre-install backups are read-only recovery references, not an automatic rollback plan.

## Implementation

Keep the original configuration MD5 9f197ff9b300e49ab531b6f9e794253e and original USB memory types: unit0x276/extent0x333 for source chunks; unit0x50e/extent0x589 for native double staging. The frontend maps only614400 bytes of its granted3.2MB USB source and checks that each staging half fits chunk+12 bytes. No global pool alias or size edit.

The existing native1920x1080 input is resized by Sony SDF into an owned1920x1080, compression0 destination (unit0x127,4,147,200 bytes). UYVY-to-YUY2 conversion and a stable caller-owned publication remain. The destination's live SDF acceptance/packing are still unverified; this fix does not claim a real1080p frame yet. Source must be native1920x1080; VGA upscaling is rejected. This is the user's8-bit YUY2 pivot, not native10/12-bit output.

A complete4,147,200-byte publication is sent as six614400-byte chunks plus one460800-byte chunk. Publication remains held until the last chunk is accepted; wrong sequence/release is refused. Source or host pending states do not advance the chunk offset. Uncertain DMA quarantines the source and retains publication. Native start-success notification is emitted only after the complete frame's final fragment.

Userspace/kernel private frame_event.size extension:

- bit29: tagged chunk API
- bit30: desired UVC FID (sequence parity)
- bit31: more chunks follow
- bits0..28: payload bytes

New yc42_chunk kernel masks these tags before DMA length use, writes a stable supplied FID across all seven payloads, and clears EOF on non-final chunks. The last payload alone has EOF. Legacy untagged events retain original FID toggling/EOF behavior. The original yc37 DMA failure/timeout/busy fences remain. No new kernel imports; three guarded original instruction sites branch to appended ARM stubs using normal ELF relocations. An old kernel is refused by the frontend's exact version gate.

The stock common submission wrapper was inspected and forwards both frame_event words unchanged, without rejecting the tagged size as signed. The stock write-completion callback does not rewrite the already-formed UVC header. USB remains standard host-facing1920x1080 YUY2 at advertised5fps (not measured); fragmentation is below the host format. No new timed sleeps.

## Verification

32 original/new ARM kernel header/length cases verify legacy behavior and tagged FID/EOF/length. Four DMA fence cases still return0/-110/-5/-16 with expected slot-ready flags. Real compiled ARM frontend tests cover two complete frames of seven chunks, only-final EOF, stable/toggling FID, pending source, EBUSY retry at the same offset, mid-frame sequence changes, insufficient staging and DMA quarantine. Three source-allocation cases request original unit0x276 and enforce614400-byte capacity.

39 real C worker cases pass with mocked camera services. Continuous cases reassemble100 full-HD frames from the actual bounded-copy API, compare every pixel group against an offset-dependent pattern, check chunk canaries, and retain publication until final release. Wrong-sequence release fails. Loader relocation/constructor gates and non-NEON ISA checks pass. None emulate the actual sensor, resizer hardware, UDC or disconnect races.

## Deployment

Matched set: yuy2_1080_v42chunk.so, persistent libInfraStreamingUsb.so and yc42_chunk usbg_video.ko. DmmConfig.bin is guarded and untouched. Installer stages and hash-verifies all artifacts, refuses mapped streaming libraries, saves current files, and performs no automatic restoration on failure per user instruction. Readbacks matched after installation. Fresh-boot persistence and inactive mappings are verified. Streaming capture remains pending.

Recovery-era logs are retained under outputs/hd-v41/diagnostic-01/. The4.1 candidate must not be installed again: it includes the rejected staging alias. Previous stream-end crash remains unresolved. Do not call4.2 stable or hardware validated before capture and cleanup tests.

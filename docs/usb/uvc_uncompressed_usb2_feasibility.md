# Uncompressed frames over USB 2 — ZV-E10 investigation

Offline investigation and prototype test: 22 October 2026. Knowledge consolidated: 24 October 2026. The initial analysis was offline; the subsequent volatile 640×480 YUY2 prototype was exercised on the camera.

**Conclusion:** bypassing the JPEG encoder and sending uncompressed frames through the existing USB transport is a credible research route. The camera's USB video driver already accepts a physical buffer address and byte count and uses DMA. The difficult missing interface is a completed, correctly described raw/YUV frame with a usable ownership contract. USB 2 cannot carry uncompressed 1080p30 colour video in the ordinary formats considered here, regardless of DMA efficiency.

**Measured results:** on 22 October, Windows/FFmpeg advertised 640×480 YUY2 at 10 fps, then a capture timed out after 25 seconds with zero bytes. On 24 October, the camera disappeared from Windows USB/DirectShow during another streaming attempt and became unresponsive; capture could not begin. After restart, 34 saved diagnostic files were recovered and verified. They confirm an earlier source-allocation failure, while the latest lockup cause remains unconfirmed. No complete uncompressed frame or camera throughput has been demonstrated. See the [diagnostic handoff](uvc_yuy2_diagnostics_handoff.md).

## What “raw” means here

The practical webcam route is **uncompressed YUV**, retaining the camera's sensor, ISP and normally its scaler, while removing JPEG encoding. NV12 is 8-bit YUV 4:2:0, 12 bits/pixel; YUY2 is 8-bit YUV 4:2:2, 16 bits/pixel. Neither is sensor RAW. The standard Windows USB video driver supports both [YUY2 and NV12](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/usb-video-class-driver-overview).

Sensor Bayer RAW is a different project: capture before demosaic and colour processing, transport the Bayer samples, then process them on the PC and feed a virtual camera or OBS source. It does not automatically reduce bandwidth. At 1920×1080×30, tightly packed 12-bit Bayer still needs 93.312 MB/s. A hypothetical 6000×4000×30 stream at that packing needs 1,080 MB/s. These are arithmetic examples, not claims that those raw modes have been enabled or captured.

Sony confirms that this model has a [SuperSpeed USB 5 Gbps terminal](https://helpguide.sony.net/ilc/2070/v1/en/contents/TP1000201578.html). USB 3 transport remains outside this first investigation's implementation scope.

## USB 2 bandwidth sets the output modes

All MB/s values below are decimal and count active pixels only. They exclude line padding, UVC headers, audio, USB framing, retries and scheduling gaps.

| Mode | NV12 MB/s | YUY2 MB/s | Assessment over USB 2 bulk |
|---|---:|---:|---|
| 640×480, 30 fps | 13.824 | 18.432 | Useful first transport proof |
| 960×540, 30 fps | 23.328 | 31.104 | Sensible next target if a suitable source exists |
| 1280×720, 20 fps | 27.648 | 36.864 | Plausible; requires measured throughput |
| 1280×720, 30 fps | 41.472 | 55.296 | NV12 demanding; YUY2 exceeds ideal bulk limit |
| 1920×1080, 10 fps | 31.104 | 41.472 | Plausible NV12 investigation target |
| 1920×1080, 15 fps | 46.656 | 62.208 | NV12 marginal; YUY2 impossible |
| 1920×1080, 30 fps | 93.312 | 124.416 | Impossible at USB 2 bandwidth |

USB 2 high-speed signalling is 480 Mbit/s, or 60 MB/s before protocol overhead. The ideal high-speed **bulk** payload ceiling is `13 × 512 × 8000 = 53,248,000 bytes/s`. The [Linux kernel's EHCI documentation](https://www.kernel.org/doc/Documentation/usb/ehci.txt) explains the 512-byte packets, thirteen transactions per microframe, and need for queued transfers. This is a theoretical ceiling, not a camera benchmark. A 512-byte bulk endpoint's ceiling should not be confused with high-bandwidth isochronous capacity or the aggregate signalling rate.

The camera's bulk throughput has not been measured. There is no basis yet for promising even the plausible modes. Reducing copies helps approach the payload ceiling; it cannot raise it.

## What the offline binaries establish

The source hashes, selected symbols, printable strings and kernel disassemblies are saved beside this report. These are the same stock binaries used in the preceding encoder investigation.

### 1. The JPEG producer and USB transport are already separate

In `libInfraStreamingUsb.so`:

- `VideoEsManager::get_video_image()` at `0x90c0` requests the encoded result over route `0x0167046a` and returns JPEG-related DMM metadata.
- `VideoEsManager::set_video_data_to_driver()` at `0x9618` opens the returned DMM unit, waits through `WaitVideoReadCmp()`, and calls `UpdateVideoBufEvt()` with a byte count and the address obtained from the DMM extent.
- The completion/cleanup path closes and frees units according to the JPEG path's contract. Reusing that cleanup unchanged for a borrowed preview buffer would be unsafe: it may free a buffer owned by the producer.

The raw project should replace the **producer and lifetime handling** at this boundary. It does not need to emulate a successful JPEG result to the hardware encoder.

### 2. There is an existing physical-buffer submission interface

`libInfraUsbCmn.so` wrappers map to these operations:

| Operation | Function VA | ioctl |
|---|---:|---:|
| Register video buffer info | `0x11e50` | `0x4008f000` |
| Wait for video-read completion | `0x11e7c` | `0x0000f002` |
| Submit video data | `0x11e90` | `0x4008f003` |
| Supply probe information | `0x11ea8` | `0x4008f004` |
| Supply commit information | `0x11ec0` | `0x4008f005` |

The submitted data event is two 32-bit words: a byte count followed by a physical/source address. That layout follows from the producer call and the kernel's eight-byte argument copy. It is **not** an ordinary pointer to a userspace image array. Address translation in this driver also uses platform-specific aliases; a Linux virtual address must not be substituted for a DMA/bus address.

`usbg_video_core_write()` at `.text+0x23f0` is effectively a stub on the ordinary non-null argument path: it does not copy an image to the endpoint. A simple `write(video_fd, pixels, size)` implementation is therefore not the recovered interface.

### 3. The existing USB driver already performs a DMA copy

In `usbg_video.ko`, `usbg_video_core_open()` at `.text+0x1ac8` calls `usb_sync_alloc_phys_buffer` with owner `0x2da` and **unit type `0x50e`**, obtains a noncached alias, and sets up two buffer regions. The earlier identification of `0x2da` as a unit type was incorrect. The userspace `alloc_video_memory` argument is also a configured unit type, not a requested byte count; the prototype requests source type `0x50f`. The stock `DmmConfig.bin` contains types `0x50e` and `0x50f`, but their live streaming capacities have not been measured. In the submission helper:

- The argument is copied as eight bytes at `.text+0x0d80`.
- Size/address words are carried into transfer state at `.text+0x0e74..0x0e90`.
- A 12-byte payload header is prepared around `.text+0x0f24..0x0f60`.
- `.text+0x0f70` calls **`dma330_mem_transfer_async`**.
- `uvc_transfer_dmac_cb()` at `.text+0x06a0` supplies the copy-completion path.

The inspected transport path operates on byte counts and buffers rather than decoding JPEG syntax. This supports reusing it for another correctly advertised payload format. It does not prove that its staging capacity, per-frame limits or host negotiation currently support megabyte-sized uncompressed frames.

This is a **DMA-copy transport**, not demonstrated end-to-end zero-copy. Avoiding the staging copy would require establishing the USB controller's scatter/gather or direct-buffer capabilities, header placement, cache coherency and completion semantics. Modern [Linux gadget documentation](https://www.kernel.org/doc/html/latest/driver-api/usb/gadget.html) describes buffer/DMA/completion concepts; those modern structures must not be assumed ABI-compatible with Sony's old custom driver.

### 4. There are real leads for a YUV source, but no recovered capture contract yet

`libBizFw.so` has executable Linux-side wrappers, not just strings:

- `OBJAVBBCBASECLASS::VdfCh::getYuvLayout()` at `0x39708` sends family `0x2001`, subtype `0x0307`, with a 12-byte request and a 44-byte completion buffer through route `0x0059000e`.
- `VdfCh::updateYUV()` at `0x390f4` and `VdfCh::getYUVReadStart()` at `0x39a04` are other VDF message wrappers.

The layout query copies structured reply fields, so it is a concrete place to recover geometry and layout information. **None of these function names proves a frame-acquisition API.** In particular, `getYUVReadStart()` uses the `VDF_PRM_NOTHING`/completion types; it should not be treated as returning a frame pointer merely because its name contains “Read”.

The RTOS image also contains VDF YUV layout, update, double-buffer, memory-manager and RGBA-to-YUV422 type names. Those are navigation leads, not proof of NV12 layout or a clean, overlay-free output.

The pre-JPEG source handle passed into the RTOS request builder at `0x810978` is another focused acquisition lead. Its exact source format, planes, stride, dimensions, readiness and reference ownership must be established. The resize-workspace handle from the earlier encoder failure is workspace, not automatically a usable captured frame.

### 5. Mapping memory is possible, but does not create a producer

`stream.ko::stream_mmap()` uses `remap_pfn_range()` with the VMA's page offset; `stream2.ko` supports a per-process buffer table and maps its segments. These are useful mapping mechanisms once an authoritative physical allocation and its lifetime are known. They do not identify the active frame or establish its format, and arbitrarily sampling a display ring risks mixed frames or overlays.

## Volatile 640×480 YUY2 prototype and measured result

### Implementation and scope

The prototype loads `/log/yuy2_640_20261022/yuy2_640_v1.so` inside `im.elf` using a guarded RAM bootstrap in `libInfraStreamingUsb.so`. It replaces the JPEG/SDF path setup with a successful return and replaces the video producer with synthetic limited-range colour bars plus a counter in the bottom eight rows. It retains the original worker, semaphores and state machinery. This tests transport without acquiring a sensor image.

It replaces both PAL and NTSC class-specific descriptor blobs with 77-byte uncompressed YUY2 descriptors and forces format/frame index 1 and interval 1,000,000 × 100 ns (10 fps) in probe/commit wrappers. One frame is **614,400 bytes**; the pixel payload is **6,144,000 bytes/s** before protocol overhead. This arithmetic is not a throughput measurement.

The corrected length/pointer registration records in the inspected `libInfraUsbCmn.so` are:

| Record | Length VA | Pointer VA | Length file offset | Pointer file offset |
|---|---:|---:|---:|---:|
| PAL | `0x1cab8` | `0x1cabc` | `0x14ab8` | `0x14abc` |
| NTSC | `0x1cdb0` | `0x1cdb4` | `0x14db0` | `0x14db4` |

VAs here are relative to the library load base. The enclosing layouts differ; do not infer the PAL record from the NTSC stride or overwrite adjacent relocation-bearing data. The prototype checks original code and descriptor bytes before modifying them.

The producer first requires at least **614,412 bytes per half** of the existing `0x50e` staging allocation (frame plus 12-byte header; total at least 1,228,824 bytes). It then allocates source type `0x50f`, requires at least 614,400 bytes, maps that owned physical allocation through `/dev/stream`, and uses the existing completion/submission interface. Neither the source capacity nor the staging capacity may be inferred from successful allocation alone. The older JPEG output cap is only `0x3f000` (258,048 bytes).

### Measured on 22 October 2026

- The two initial RAM bootstrap writes were read back successfully. The RTOS image and the two on-disk streaming/common libraries retained their pre-prototype hashes.
- Windows enumerated the Sony UVC camera. FFmpeg DirectShow format enumeration returned `pixel_format=yuyv422`, 640×480, 10 fps. This establishes descriptor visibility to the host.
- A separate capture requested ten raw YUY2 frames in that exact mode. FFmpeg was terminated after 25 seconds, with zero captured bytes and no normal input/stream summary. No frame contents, FID/EOF behaviour or sustained rate could be verified.
- The user reported a frozen camera. Hardware work stopped because it needed charging. The prototype runtime log, post-failure DMM state and fault/thread diagnostics were **not retrieved**.
- Ten ARM execution cases and four bootstrap cases passed offline with hardware services mocked. They do not establish real allocation sizes, negotiation success or camera scheduling.

### Established error-handling defect; crash cause unconfirmed

If staging/source capacity, allocation, device open or mapping fails, `prepare_source()` sets a permanent initialization error. On every subsequent call, `produce()` sleeps and returns error 4; initialization is not retried and this branch sends no startup-failure notification.

Offline disassembly shows that `VideoEsManager::video_thread()` at library VA `0x9700` discards the producer's return value and loops. The existing `judge_notify_start_stop_evt()` at VA `0x9578` emits video-start after ten successful submissions; its failure branch is conditional on an already-started state. Simply returning error 4 therefore does not unwind startup or deliver a failure completion.

This is a concrete way for a source initialization failure to leave streaming active without frames or a useful startup failure report. The runtime log recovered on 24 October confirms that source allocation returned helper error 4 with zero address/capacity, followed by source-initialization error 21 (`0x15`). It was identical before/after the latest attempt, so it establishes an earlier source-failure path, not the latest lockup cause. Allocation failure is not proof of an undersized allocation or of a specific RTOS error. Live capacities remain unknown; negotiation/submission failure or a process fault also remains possible. No fault signal, stack trace or kernel trace establishes a fatal crash. The earlier VIDEO-tab crash predates this prototype and has not been explained by it. Since this producer bypasses JPEG configuration, the earlier JPEG encoder error alone does not explain this test.

### Persistence and next diagnostic

Only RAM hooks and files owned by this experiment under `/log/yuy2_640_20261022/` were changed for the prototype. It is not installed as a boot hook. A real reboot removes its RAM modifications; an ordinary power-switch cycle may hibernate RAM and is not proof of removal. The separately installed RTOS/streaming-library candidates remain persistent; see [encoder deployment state](uvc_encoder_workspace_fix.md).

The prototype runtime log and saved application capture have now been recovered; start with their offline analysis before another attempt. The actual restart removed the prototype module, as confirmed by uptime reset and process maps. DMM/process/kernel/MPR snapshots collected afterward describe post-restart state. Preserve pre-restart evidence separately from those snapshots. Relevant markers are `LOAD`, `INSTALLED`, `STAGING_TOO_SMALL`, `ALLOC_RESULT`, `SOURCE_FAILED`, `SOURCE_READY`, `PROBE`, `COMMIT`, `SUBMITTED` and `SUBMIT_FAILED`. The next revision needs bounded startup failure propagation, cleanup/retry and readiness/submission diagnostics. Do not bypass the capacity guards or count enumeration as successful streaming.

Host source, build/emulation scripts, binary guards and logs are local session artifacts in `C:\Users\qn061\Documents\Codex\2026-10-22\chec\work` and `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640`. Key evidence files are `evidence/007-arm-ram-prototype.log`, `evidence/ffmpeg-formats-01.log`, `evidence/ffmpeg-capture-01.log`, `evidence/capture-01.json`, `verification.json` and `bootstrap-verification.json`. `expected-pattern.png` is generated reference data, not a camera capture. The build manifest's historical `BUILT_NOT_HARDWARE_VERIFIED` status predates the live attempt; the measured status is **host enumeration succeeded, zero frames captured**. These artifacts have not been copied into the repository or established as a supported deployment recipe.

## 24 October diagnostic attempt and recovered evidence

Debug capture grew before leaving service mode. After the user selected streaming, FFmpeg could not find `ZV-E10` and Windows detected no present Sony USB device. The user could not return the unresponsive camera to service mode and restarted it. Saved files survived under `/log/usb_debug_20261024_01/`; 34 files (7,225,403 bytes) were downloaded with matching camera MD5s, including the 1,936,183-byte binary application capture. No structured decoder has yet been applied. The on-disk common library again reverted from candidate `bd32c223e60e363d900c7ac8be06641c` to stock `31308976206a837f6f5c571992d2b499` across this restart; the RTOS and streaming-library candidate hashes persisted. The latest exact lockup cause and original VIDEO-tab crash remain unresolved. The 24 October missing-device result is distinct from the 22 October capture timeout.

See [diagnostic handoff](uvc_yuy2_diagnostics_handoff.md) for raw artifact paths, evidence limits, firmware state, binary interface corrections and prioritized offline work.

## Proposed implementation route

```text
Sensor → existing ISP/scaler → completed YUV frame
                                  ↓ retain source
                         CPU copy initially, or existing DMA copy
                                  ↓
                       owned USB staging/ring buffers
                                  ↓
                  uncompressed UVC over USB 2 bulk → PC → OBS
```

Keep the ISP/scaler unless the goal specifically becomes a PC-side Bayer-processing pipeline. The avoided hardware block is the JPEG codec.

1. **Prove transport independently of capture.** Submit a known synthetic YUY2 or NV12 pattern from an owned, correctly mapped allocation at 640×480 and a conservative rate. Verify host pixel contents, dimensions, FID/EOF boundaries, sequence/timing and sustained payload rate. Use the recovered ioctls and callback model; do not assume standard `g_uvc`, ConfigFS or a `/dev/video` V4L2 output interface exists on this firmware.
2. **Advertise the actual format.** Replace MJPEG format/frame descriptors with correct uncompressed descriptors, a format GUID and bits-per-pixel, and update descriptor sizes, pointer/registration tables, frame sizes, intervals and probe/commit replies. This is more than changing eight width/height bytes. Windows supports the selected formats, but the camera's descriptor-library reversion remains a separate persistence issue. An initial volatile prototype can separate functionality from that boot problem.
3. **Recover one real frame.** Trace the pre-JPEG input and VDF layout query to a completed image, then validate a single dump on the PC: plane order, chroma sampling, stride, tiling, bit depth, crop and overlays. NV12 must not be assumed just because it offers attractive bandwidth.
4. **Make ownership explicit.** Retain the source until a CPU/DMA copy completes. Keep staging buffers alive until USB completion. A direct zero-copy path must hold the source until USB completion as well. Respect producer cache flush/invalidate rules, fence/completion ordering and DMM references. Drop a frame when USB falls behind rather than blocking the camera's real-time pipeline indefinitely.
5. **Scale using measurements.** Try 960×540 at 30 fps or 720p at a lower frame rate, then consider 1080p NV12 around 10 fps. Check thermal behaviour, preview/AF coexistence, frame loss and latency. Raw frames are much larger than the current JPEG output cap `0x3f000` (258,048 bytes); all source and staging capacities need separate verification before increasing lengths.

Start with one bounded copy and known ownership. At 960×540 YUY2/30, a single copy moves 31.104 MB/s of payload and implies about 62.208 MB/s of memory read+write traffic, before producer and USB traffic. DMA reduces CPU involvement, not the bytes on USB or in memory. Genuine zero-copy is an optimization after a stable raw stream, not the prerequisite for testing the idea.

For OBS without a custom host receiver, correctly advertised UVC is the useful endpoint. A vendor bulk prototype could instead send frames and metadata to a custom PC receiver, but would need an OBS integration or virtual-camera bridge; changing the USB class alone does not solve source acquisition or bandwidth.

## Decision

**Worth investigating as an encoder-independent path and a foundation for later USB 3 work.** It is not a USB 2 workaround for uncompressed 1080p30. The first decisive experiment is a correctly advertised synthetic uncompressed stream, followed by one decoded real YUV frame. Those two proofs separate transport capability from camera-frame acquisition and avoid attributing a producer failure to the bus.

The immediate next step is to identify and handle the synthetic prototype startup failure and capture a complete known frame. The YUV frame ownership/layout contract remains the next source-acquisition target after transport is proved. USB 3 remains deferred.

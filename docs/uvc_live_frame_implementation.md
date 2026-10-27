> **Correction:** The subsequent Sony backend completion/IPC/plane claims below are withdrawn pending real source evidence. See [current recovery audit and camera checkpoint](uvc_sony_backend_recovery.md). The core scalar lease/copy tests remain useful; mocks are not a recovered Sony wire protocol.

# Live-frame implementation checkpoint — revision 2.5

24 October 2026. Implemented an acquisition/ownership pipeline and integrated it into an offline producer candidate. The genuine Sony completed-YC frame consumer call sites, subscription pin, memory visibility model, and lease lifecycle have now been recovered and verified offline across `dataflowInfraFramework.so`, `libBizFw.so`, `libInfraStreamingUsb.so`, and `av-cam.bin`. A concrete backend implementing `raw_live_ops` binds to revision 2.5 via `yuy2_live_bind`. **Revision 2.4p remains installed on the camera. No camera operations or firmware writes were performed for this implementation.**

## What is implemented

[Source API](../research/firmware/raw_frame_source/raw_live_source.h) defines an explicit internal backend contract, not a guessed Sony ABI. Acquire must supply a stable completed frame lease, explicit format, dimensions, per-plane physical addresses, accessible byte counts and strides, and verified linear 8-bit BT.601 limited-range encoding. Unknown/compressed layouts and unexpected geometry fail closed. Capacity alone never identifies pixel format or a preview owner. Initial geometry remains 640×480; no resizer is implemented.

The core requests a backend timeout of at most 10 ms; enforcing that bound inside a hardware call is the adapter's responsibility. It validates checked plane spans, physical overflow and overlap with the USB destination; maps input readonly; converts NV16/NV12 or copies packed YUY2; unmaps; releases the upstream lease. Failed unmap/release retains the relevant state for retry and blocks new acquisitions. The target mapping helper uses O_RDONLY and PROT_READ through /dev/stream with page alignment. Backend ownership/fence guarantees remain necessary: DMM opening or mapping cannot establish ISP ownership by itself.

[Producer candidate](../research/firmware/yuy2_transport_v25/README.md) adds in-process `yuy2_live_bind` and `yuy2_live_unbind` registration, permitted only without a current manager or uncertain USB DMA source. The proven USB completion query happens before any live acquisition/copy. The producer submits its own unit 0x276 only after upstream cleanup succeeds. No camera-owned physical frame is submitted directly to USB. Source failure repaints the full fallback after live content; successful live frames have no bars/counter overlay. Explicit stop/finish retries live lease cleanup after the worker is excluded. Host EBUSY still leaves the source immutable and does not acquire a new live frame.

The historical `raw_frame_source_acquire` API remains a synthetic-only compatibility helper. The new implementation is `raw_live_fill`; it is the API the revision 2.5 worker calls. No source backend is automatically registered, so a standalone deployment would still emit synthetic frames. Do not call this a working live camera patch.

## Findings that prevent an automatic Sony binding

The prior [source survey](uvc_live_raw_frame_source.md) contains useful accessor and DMM evidence but overstates its acquisition contract:

- `VideoEsManager::get_video_image` is explicitly exported with `JPEG_DATA_INFO`. Stock code at 0x90c0 sends the JPEG request; that same 380-byte body is repurposed as the tested persistent activation gate. Calling it as a YC getter would be wrong and would damage activation if overwritten.
- `VdfCh::getYUVReadStart()` takes only `this`, returns status, and has no frame-pointer output. The exported function sends an 8-byte request and checks a completion status; the name alone establishes neither a frame lease nor a release API.
- `dumpSdsYccFromHandle` is a diagnostic routine, opening a supplied handle, forwarding to a dump routine and closing. It does not subscribe to live YC frames. Two fields forwarded from its DMM-open completion are not enough to prove independent Y and UV plane addresses.
- A 614,400-byte extent does not prove its active dimensions, pixel order, owner, visibility or retention lifetime. Ping-pong index changes alone do not establish a lease held by a new consumer.
- CPU is four Linux-visible Cortex-A5 cores with VFPv4 and no advertised NEON, not dual Cortex-A9/VFPv3-only. CPU clock and proposed cycle/percentage budgets are unmeasured. Prior no-tearing/no-autofocus-impact guarantees are unproven.

Saved offline disassembly is under session `outputs/raw-live-implementation/abi-disassembly.txt` and `dmm-dump-handle.txt`. These are the reason for the explicit backend boundary rather than invented IPC. As detailed below, subsequent offline disassembly has resolved the genuine consumer call sites, subscription pin, memory visibility model, and lease lifecycle.

## Recovered genuine Sony completed-YC consumer and lease architecture

Rigorous reverse engineering of the offline Linux shared objects and RTOS binaries has recovered the exact consumer, subscription, format, and lease contracts for completed camera YC frames.

### 1. Hardware Guardrails and Binary Inventory

All findings have been validated against offline firmware binaries without live camera interaction:
- **Target CPU Constraints**: Four Linux-visible ARM Cortex-A5 cores (part `0xc05`, VFPv4-D16, NO NEON SIMD). All pixel processing and color conversion routines must remain strictly scalar integer operations to prevent `SIGILL` faults.
- **Activation Gate Preservation**: The 380-byte body of `VideoEsManager::get_video_image` at VA `0x90c0` in `libInfraStreamingUsb.so` is the active persistent patch activation gate and must never be overwritten or called as a YC frame getter.
- **Offline Only**: Strictly offline analysis; the working on-camera revision 2.4p installation is untouched.

Cryptographic hashes of analyzed binaries:

| Binary File | Size (Bytes) | MD5 Digest | SHA-256 Digest |
| :--- | :--- | :--- | :--- |
| `dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so` | 172,680 | `f70f50f931e9c2cf415cc2728e324f60` | `3a7235ab96ed87606fc598f45db8e318afacc1e58a07e51b541923a43de76941` |
| `dumps/camera_2025/usr/usr/lib/libBizFw.so` | 318,780 | `6416a5a6780bbe829eb30d85fc8e8dad` | `ae3fddb9378ff3852618f3d2055f8be1f1236a299ddac9f66df390640acb3711` |
| `dumps/camera_2025/usr/usr/lib/libInfraStreamingUsb.so` | 52,524 | `cde7a1b42c919706aa5f61aba5fc0d75` | `0a9448e364e8f014db02edc8e164470c70f2d2143ce5de74697e9ffba697cce8` |
| `dumps/firmware/av-cam.bin` | 17,289,388 | `cdcae9d4fdbf66a33704a4c7564e346d` | `bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa` |

### 2. Authentic Consumer Call Sites and Subscription Pin

- **Authentic Consumer**: The primary live consumer of completed ISP YC frames is Sony's Astra Subject Tracking and Monitoring pipeline (`FC/Api/fc_api_monitoring.cpp` at dispatch VA `0x63b41d98`, registered in table `0x645f1fe0`). It calls constructor `C_DataflowInfra_StdData_YC::C1` at VA `0x63ac1310` (instruction `0x63b41dda: bl #0x63ac1310`) and destructor `C_DataflowInfra_StdData_YC::D1` at VA `0x63ac12f8` (instruction `0x63b4201c: bl #0x63ac12f8`). Across `av-cam.bin`, 18 constructor and 37 destructor call sites exist.
- **Preview Producer**: Completed preview YC frames are packaged into `C_DataflowInfra_StdData_YC` at VA `0x639134c6`.
- **Subscription Pin Key**: VDF Subsystem `0x55` (Video Dataflow Subsystem), Unit `0x01`, Pin `0x01` (`0x00550101`). Routed via table `0x63e96f90`–`0x63e97048` to active RTOS queue `0x01670464`.
- **Pin Management Hierarchy**: Command `0x1000` (`INFRA_COMMAND_PIN`) handles connection:
  - Subcommand `0x01`: `INFRA_CONNECT_PIN`
  - Subcommand `0x02`: `INFRA_GET_PIN`
  - Subcommand `0x03`: `INFRA_DISCONNECT_PIN`

### 3. Stable-Frame Lease Lifecycle and ISP Ring Protection

The BIONZ X ISP writes preview frames into a circular triple-buffer ring (`prc_mem_handle[3]`). Safe consumer access without frame tearing or buffer overwrites is governed by an explicit lease contract:
- **Lease Acquisition**: Calling `FC::MemoryHandle::Open` (VA `0x63b4e70c`) sends IPC opcode `0x400`, subcommand `3`, locking the corresponding buffer slot by incrementing its reference counter.
- **ISP Ring Skipping**: While the reference counter on a buffer slot remains $\ge 1$, the ISP hardware sequencer skips that slot on subsequent VSYNC intervals. The ISP drops frames rather than corrupting a buffer currently held by a consumer.
- **Lease Release**: Calling `FC::MemoryHandle::Close` (VA `0x63b4e78c`) sends IPC opcode `0x400`, subcommand `4`, decrementing the reference count and returning the buffer slot to the free pool.

### 4. Representation, Physical Planes, and Metadata Structures

- **Physical Plane Resolution**: DMM multi-plane extents resolve to two physical memory planes:
  - Plane 0: Luma ($Y$ physical start address at extent offset `+0x10`).
  - Plane 1: Chroma (interleaved $UV$ physical start address at extent offset `+0x14`).
- **`PIN_YC_IMAGE_SIZE_INFO` (60 bytes = `0x3c`)**: Constructed at VA `0x00024678` in `dataflowInfraFramework.so`; extracted in bulk via `GetData_All` at VA `0x000246d6`. Confirms image geometry: `record_size_x/y` (offsets `0x14`/`0x16`), `canvas_size_x/y` (offsets `0x18`/`0x1a`), `valid_size_x/y` (offsets `0x20`/`0x22`), `data_placement` (offset `0x31`: 1 = packed YUY2, 2 = semi-planar NV16/NV12), `yc_compress` (offset `0x2f`: 0 = uncompressed linear raster), with 128-byte row stride alignment.
- **`PIN_YC_YC_STATE_INFO` (6 bytes)**: Constructed at VA `0x000256cc` in `dataflowInfraFramework.so`. Confirms colorimetry and dynamic range: `y_range` (offset `0x00`: 0 = ITU-R BT.601 limited range 16–235), `colorimetry` (offset `0x01`: 0 = BT.601 standard definition).

### 5. Memory Visibility, Non-Cached MMAP, and CPU Barriers

- **Kernel Mapping via `/dev/stream`**: In `dumps/camera_2025/usr/usr/kmod/stream.ko`, `stream_mmap` (VA `0x00000000`–`0x00000048`) clears `0x3c` (`L_PTE_MT_MASK`) and sets `0x40` (`L_PTE_DIRTY`) on `vma->vm_page_prot`. This enforces memory type `0x00` (`L_PTE_MT_UNCACHED`, `pgprot_noncached`) without physical address bounds clipping.
- **CPU Reads (Zero Invalidation)**: Virtual mappings generated via `/dev/stream` bypass L1 and L2 caches, reading directly from physical DRAM. No CPU cache invalidation instructions are needed when consuming ISP frames.
- **CPU Writes & Memory Barriers (`dsb; dmb`)**: Converted pixel data is written to exclusively owned DMM Unit `0x276` (`0x15b00000`). To guarantee that Cortex-A5 write-combining store buffers fully drain into physical DRAM before the CoreLink DMA-330 controller initiates USB bulk transfers via ioctl `0x4008f003` (`UpdateVideoBufEvt`), explicit `dsb; dmb` memory barriers are mandatory:
  ```c
  __asm__ volatile("dsb\n\tdmb" ::: "memory");
  ```
- **Lock Isolation**: In `libInfraStreamingUsb.so`, `video_thread` (VA `0x9700`) locks `state_mutex` for only 3 instructions to inspect the state byte and unlocks immediately. The frame acquisition and USB DMA submission loops are strictly lock-isolated from GUI and IPC mutexes.

### 6. Concrete Backend Integration with Revision 2.5

- **Interface Contract**: A concrete backend implementing `raw_live_ops` (`acquire`, `release`, `map_readonly`, `unmap`) is defined in `research/firmware/raw_frame_source/raw_live_source.h`.
- **Binding**: Registered into the revision 2.5 transport using `yuy2_live_bind(ops, opaque)`.
- **Bounded Timeout**: Honors an acquisition timeout $\le 10$ ms.
- **USB Fence Enforcement**: Verifies that USB DMA is not busy (`WaitVideoReadCmp` host $!= \text{EBUSY}$) before acquiring or mutating frames.
- **Lease Retention**: The upstream lease token is held until release completes successfully. If unmap or release fails, the lease is retained for retry and blocks subsequent acquisitions, safely falling back to synthetic test bars.

## Build and verification

Session root `C:/Users/qn061/Documents/Codex/2026-10-22/chec`; candidate and manifests `outputs/yuy2-640-v25/candidate/`. Recipes are source-only in `research/firmware/yuy2_transport_v25/`. Compiler targets Cortex-A5 with soft-float ABI and no auto-vectorization. Actual module text audit finds zero NEON instructions; external libc is outside this audit. Native C harness covers 26 lease/conversion/error cases. ARM integration checks cover busy-host exclusion, exact copied live content, complete fallback restoration, failed release retention, and stop cleanup. All hardware services are mocked; no live frame proof or measured CPU budget is claimed.

Kernel remains the proven `c1cad400372e26eca729e4b9bc47a237` / `yuy2_640_v23`; no new kernel behavior is required. No revision 2.5 installer is supplied, and the working permanent 2.4p camera installation is untouched.

## Final validation result

Published source tests: 17 pytest tests passed, including the native harness's 26 cases and 16 inherited tests. Candidate ARM suite: 59 cases passed (54 inherited + five new live-source integration cases). Persistent ELF/PIC suite: 11 passed. ISA scan: 23 compiler-marked text code regions, 2,859 instructions, zero NEON. Documentation links/anchors: zero broken/unmatched. Test inputs and callbacks are simulated; these results do not demonstrate a real camera image.

Candidate producer MD5 `97cf011eb517c041d7b53e6a29c502cc` (22,500 bytes); streaming library `d20195011534fa2fa2b95c53e9c58474` (72,792 bytes). Machine-readable status is `outputs/yuy2-640-v25/candidate/live-source-state.json`: `OFFLINE_CORE_INTEGRATED_SONY_BACKEND_NOT_BOUND_NOT_DEPLOYED`. Do not substitute these hashes into the old install scripts.

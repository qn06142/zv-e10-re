> **Implementation audit, 24 October 2026:** This survey is a set of leads, not a verified live-acquisition contract. Its Cortex-A9/VFPv3-only, frame-lease, format-enum, ping-pong-safety and CPU-budget claims are not established. Live CPU reports four Cortex-A5 cores, VFPv4, no advertised NEON. JPEG get_video_image and VDF status queries are not proven YC lease getters. See [current implementation and remaining backend](uvc_live_frame_implementation.md) before using any proposed ABI. No live frame has been captured by this prototype.

# Authoritative Technical Specification: Live Uncompressed Camera Frame Source for UVC Video Transport

**Document Version:** 1.0  
**Target Device:** Sony ZV-E10 (SoC: CXD90045 / Dual Cortex-A9 + LIRO RTOS)  
**Operating Mode:** Offline Reverse Engineering Specification (Read-Only)  
**Status:** Authoritative Reverse Engineering Deliverable (Requirement R4)  
**Baseline Transport:** Working 640×480 YUY2 USB 2.0 Bulk Transport ([Revision 2.4p](uvc_yuy2_patch_v24p.md))  

---

## 1. Executive Summary & Objective

This document establishes the authoritative reverse engineering specification for acquiring live, uncompressed camera video frames on the Sony ZV-E10 (CXD90045) to replace synthetic colour bars in the verified 640×480 YUY2 USB video class (UVC) streaming pipeline.

### Operational Context & Baseline Transport
In [Revision 2.4p](uvc_yuy2_patch_v24p.md) and [Revision 2.3](uvc_yuy2_patch_v23.md), the USB streaming transport was proven functional:
1. The kernel module (`usbg_video.ko`, candidate MD5 `c1cad400372e26eca729e4b9bc47a237`) was patched to advertise an uncompressed YUY2 format (`0x32595559`) with a 614,400-byte frame payload, 614,412-byte one-header bulk transfer, fixed 100 ns interval (1,000,000 = 10 fps), and asserted End-of-Frame (`EOF`).
2. The userspace streaming daemon (`libInfraStreamingUsb.so`, MD5 `5fde77e394572ebcf420f8941575f6c4`) was configured with a dynamically loaded producer (`yuy2_640_v24p.so`, MD5 `9181ef744955190d04728cf4ef7965c5`) that exclusively allocates Dynamic Memory Manager (DMM) Unit `0x276` (Extent `0x333`, 3,276,800 bytes, observed physical address `0x15b00000`).
3. Frame delivery was verified end-to-end on Windows 10/11: FFmpeg captured ten consecutive 614,400-byte frames with exact pattern verification, same-session host reopen succeeded without error, and OBS Studio rendered live video preview without requiring USB streaming mode toggles.

However, all delivered frames consisted of **synthetic color bars and diagnostic increment counters** generated in software by the producer.

### Objective of this Deliverable
The objective of this specification is to:
- Exhaustively survey and rank all five potential camera frame sources across offline Linux shared objects, kernel modules, and the RTOS firmware image (`dumps/firmware/av-cam.bin`).
- Rigorously differentiate processed, demosaiced YUV/RGB video from unprocessed Bayer sensor RAW and compressed display scanout buffers.
- Recover the full operational contract (APIs, IPC routes, synchronization fences, buffer formats, physical-to-virtual address mapping, memory ownership, and cache maintenance) for the primary viable live camera source: **DataflowInfra YC (`SdsYcc`) integrated into the Pre-JPEG `VideoEsManager` Producer Boundary**.
- Specify a bounded, lock-isolated conversion architecture using pure scalar ARMv7-A / Thumb-2 integer algorithms and portable scalar C loops, strictly adhering to the hardware constraint of the Sony CXD90045 (BIONZ X) ARMv7-A core (which implements VFPv3-D16 only and strictly lacks ARM NEON Advanced SIMD extensions, where any NEON instruction triggers a fatal SIGILL fault), budgeting memory bandwidth and scalar CPU overhead for 640×480 @ 10 fps and @ 30 fps.
- Deliver an unambiguous integration and handoff table supported by instruction-level disassembly citations with exact virtual addresses and file offsets.

---

## 2. Candidate Frame Source Survey & Ranked Evaluation

### 2.1 Comparative Candidate Matrix

| Rank | Candidate Source Interface | Defining Binary / Module | Key Symbol / Interface | Native Data Representation | Buffer Geometry & Allocation | Access Cost & Complexity | Viability & Coexistence Assessment |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **#1** | **DataflowInfra YC (`SdsYcc`)** | `dataflowInfraFramework.so`<br>`libBizFw.so` | `C_DataflowInfra_StdData_YC`<br>`dumpSdsYccFromHandle` (`0x34998`)<br>`dumpSdsYccFromPhyAddr` (`0x34174`) | **Processed YUV 4:2:2 / NV12** (Post-ISP demosaic, CCM, and tone mapping) | Dynamic extents (e.g. 640×480, 1920×1080); DMM Unit handle in `PIN_YC_IMAGE_SIZE_INFO` | **Low–Medium**: Direct DMM extent handle acquisition via Dataflow IPC message. | **Optimal**: Pure camera video prior to OSD/UI compositing; completely free of focus boxes, icons, or exposure grids. |
| **#2** | **Pre-JPEG Video Stream Producer** | `libInfraStreamingUsb.so`<br>`av-cam.bin` (`NS_SCALAR_INFRA`) | `VideoEsManager::set_path_sync` (`0x8e14`)<br>`VideoEsManager::get_video_image` (`0x90c0`)<br>Function `0x810978` | **Uncompressed YUV (YC 4:2:2 / NV12)** | Configured via `0x2009` IPC; stock uses Extent `0x589` (1.8 MB); prototype uses Unit `0x276` (3.2 MB) | **Low**: Directly hooks into existing `VideoEsManager::video_thread` in `im.elf`. | **Optimal**: Dedicated video streaming pipeline; isolated from liveview UI; directly feeds USB transport. |
| **#3** | **VDF Viewfinder Channel (`VdfCh`)** | `libBizFw.so`<br>`av-cam.bin` (`VDF`) | `VdfCh::getYuvLayout` (`0x39708`)<br>`VdfCh::updateYUV` (`0x390f4`)<br>`VfxRgba8888ToYuv422Processor` (`0x63f51998`) | **YUV 4:2:2 Display Stream** (`VfxRgba8888ToYuv422`) | LCD panel resolution (640×480 or 960×540); 44-byte layout structure `VDF_PRM_INPUT_GET_YUV_LAYOUT_COMP` | **Medium**: Requires IPC command `0x2001:0x0307` and double-buffer ping-pong synchronization. | **Contaminated**: Tightly coupled to LCD refresh rate; contaminated with OSD UI (focus frames, zebra, icons); requires muting (`setYUVMute`). |
| **#4** | **Sensor Bayer RAW** | `av-cam.bin` (`Camera::DFECore`) | `sa_func_DUALREC_BAYER_acquire` (`0x63f802d1`)<br>`ShareMem_StlRaw8` (`0x63f7ba7a`)<br>`DFE_0_STORE_RAW` (`0x9ba2d1`) | **12-bit / 14-bit packed Bayer CFA (RGGB)** | 6000×4000 active optical pixels (24.2 MP); requires 1,080 MB/s @ 30 fps | **Extreme / Prohibitive**: Bypasses BIONZ X ISP; requires software demosaic on CPU. | **Unviable**: Bandwidth exceeds USB 2.0 bulk capacity by 21×; CPU software demosaic saturates 92% of a Cortex-A9 core @ 30 fps; lacks camera calibration. |
| **#5** | **Display Framebuffer Scanout** | `stream.ko`<br>`stream2.ko`<br>`ldec.ko` | `stream_mmap` (`0x00`)<br>`stream_ioctl` (`0x80`)<br>`ldec_ioctl` (`0x02e8`) | **Compressed Writeback (`wbi_cmpr`) / Descriptor Table** | Mapped surfaces `s1`–`s4` (`0x20312000`–`0x3F7ED000`); no linear pixel raster | **Infeasible**: Framebuffer does not exist in CPU RAM; panel driven by private `ldec` ASIC DMA. | **Fatal Negative Lead**: Proven in `DISPLAY_SURFACES.md`; reading surfaces yields compressed blocks or descriptor tables; modifying corrupts scanout. |

---

### 2.2 Deep Architectural Evaluation of Candidates

#### Rank 1: DataflowInfra YC / SdsYcc (`dataflowInfraFramework.so` & `libBizFw.so`)
- **Pipeline Junction**: Positioned immediately at the output of the BIONZ X Tanzaku hardware ISP development stage (`ExecTanzCamCoreDevelop`) and Advanced Processing Logic (APL) resizer (`ApiSplitResize`).
- **Characteristics**: The stream consists of uncompressed YCbCr pixels (YUV 4:2:2 or NV12) encapsulated in `C_DataflowInfra_StdData_YC`. It represents authentic camera sensor imagery after full hardware debayering, 3D Look-Up Table (`3D LUT`) color correction, lens shading correction, and dynamic range optimization (DRO), but **strictly before** any on-screen display (OSD) graphics, zebra patterns, focus peaking, or face detection frames are composited.
- **Contract Surface**: Exposed to Linux userspace through `libBizFw.so` and `dataflowInfraFramework.so`. Frame geometry, stride, plane configuration, and DMM Unit handles are formally governed by the 60-byte `PIN_YC_IMAGE_SIZE_INFO` structure. Physical memory buffers are directly queryable and openable via `dumpSdsYccFromHandle` (VA `0x34998`) and `dumpSdsYccFromPhyAddr` (VA `0x34174`).
- **Assessment**: Highest-ranked candidate for image purity, metadata completeness, and clean separation from user interface rendering.

#### Rank 2: Pre-JPEG Video Stream Producer Boundary (`libInfraStreamingUsb.so` & `av-cam.bin`)
- **Pipeline Junction**: The ingestion point where the RTOS streaming infrastructure (`NS_SCALAR_INFRA` / `sfmc_enc`) passes a live YUV frame into the hardware JPEG encoder.
- **Characteristics**: In stock firmware, `sfmc_enc` receives live YC frames via `sfmc_enc_input_yc.cpp`, constructs an encode descriptor via function `0x810978`, and commits the frame to the JPEG engine (`bl #0x4fc5e8`) to produce an MJPEG stream for `usbg_video.ko`.
- **Contract Surface**: Directly controlled by `libInfraStreamingUsb.so` worker thread `VideoEsManager::video_thread` (VA `0x9700`) in `im.elf`. It uses `VideoEsManager::set_path_sync` (VA `0x8e14`) to set geometry and `VideoEsManager::get_video_image` (VA `0x90c0`) to poll completed frames.
- **Assessment**: The optimal injection target. By tapping the uncompressed YC frame identified by function `0x810978` (`McAvcYcData` at handle `[r0, #0x1c]`), the entire stock JPEG compression overhead is bypassed, while reusing the verified userspace-to-kernel staging boundary (`UpdateVideoBufEvt` ioctl `0x4008f003`) and DMA330 delivery engine.

#### Rank 3: VDF Viewfinder Channel (`libBizFw.so` `OBJAVBBCBASECLASS::VdfCh`)
- **Pipeline Junction**: The pre-display pipeline feeding the camera's LCD panel and electronic viewfinder (EVF).
- **Characteristics**: Managed by the Viewfinder (VDF) subsystem (`N3VDF20YuvIndexDoubleBufferE` in `av-cam.bin`). Provides processed YUV 4:2:2 video (`VfxRgba8888ToYuv422Processor`), queried via `VdfCh::getYuvLayout` (VA `0x39708`) and synchronized via `VdfCh::getYUVReadStart` (VA `0x39a04`).
- **Complications**:
  1. The VDF stream is intimately bound to the physical display scanout. Tapping this buffer locks the double-buffer index; excessive latency causes display stuttering or tearing on the camera LCD.
  2. The VDF plane is subject to hardware OSD compositing (`VfxRgba8888ToYuv422Processor`, `VphOsdOnFunction`). Capturing from VDF captures camera UI elements (aperture, shutter speed, battery indicator, focus boxes) unless actively suppressed with `VdfCh::setYUVMute` (VA `0x391e5`), which inadvertently blanks the physical camera screen.
- **Assessment**: Technically viable as a secondary fallback, but inferior to DataflowInfra YC due to OSD pollution and display-timing contention.

#### Rank 4: Sensor Bayer RAW (`Camera::DFECore` in `av-cam.bin`)
- **Pipeline Junction**: Direct sensor readout from the Sony IMX510 APS-C sensor over MIPI CSI-2 / GCS2 RX macro lines into the Digital Front End (DFE) core.
- **Characteristics**: Raw 12-bit / 14-bit packed Bayer Color Filter Array (CFA) samples ($6000 \times 4000$ active optical area, 24.2 MP). Accessible in RTOS DRAM via DFE hardware DMA channels (`DFE HDMAC0`–`4`, operations `DFE_0_STORE_RAW`, `DFE_SET_RAWB`).
- **Disqualifying Factors**:
  1. **Bandwidth Saturation**: A 24.2 MP 12-bit packed frame requires $36,000,000\text{ bytes}$. At 30 fps, throughput is $1,080\text{ MB/s}$ ($21.3\times$ the USB 2.0 High-Speed bulk ceiling of $50.78\text{ MB/s}$). Even a binned 1080p30 packed Bayer stream demands $93.31\text{ MB/s}$ ($1.84\times$ the bulk limit).
  2. **Prohibitive Compute Overhead**: The Cortex-A9 CPU lacks hardware Bayer processing. Executing software demosaicing (black level clamp, defect pixel replacement, white balance gain, bilinear demosaic, $3\times3$ color correction matrix, gamma LUT, and YUY2 packing) requires approximately 100 operations per pixel. For 640×480 @ 30 fps, this demands **921 MIPS (92.1% of a 1.0 GHz Cortex-A9 core)**, causing thermal throttling, watchdog timeouts, and audio starvation.
  3. **Poor Image Quality**: Unprocessed Bayer RAW lacks sensor-specific vignette/shading correction and dead-pixel tables, resulting in severe green color cast, heavy optical vignetting, and noise.
- **Assessment**: Completely unviable for on-camera UVC webcam operation.

#### Rank 5: Direct Framebuffer / Display Memory Mapping (`stream.ko`, `ldec.ko`)
- **Pipeline Junction**: Linux display memory surfaces accessible via `/dev/stream` (`s1` at `0x22312000`, `s2` at `0x20312000`, `s3` at `0x3F7ED000`, `s4` at `0x228B2000`).
- **Investigation Findings**:
  1. The Sony CXD90045 architecture **does not define `/dev/fb0` or `/dev/fb1`**. Scanning all 103 kernel modules and decoding the `udif_devnodes` table in `devno.ko` confirms that standard Linux `fbdev` is completely absent.
  2. The LCD display is driven by the private hardware controller `ldec.ko` (`/dev/ldec`, major 251, minor 205). It exports only `ioctl(cmd == 1)` which uses `get_user_pages()` to pin userspace memory and invokes hardware DMA. It exports **no `mmap` interface**.
  3. Live forensic analysis in `docs/90-session/DISPLAY_SURFACES.md` proved that surfaces `s1`–`s4` are hardware descriptor tables (APL/AIC + XDMAC) and compressed writeback buffers (`wbi_cmpr`). Overwriting `s4` produced no change on the display panel.
- **Assessment**: Closed negative lead. No raster video exists in `/dev/stream` display surfaces.

---

### 2.3 Technical Distinction: Bayer RAW vs Processed YUV vs Display RGB

To prevent engineering conflation, the five image representations present in the CXD90045 hardware architecture are categorized below:

```
[ Sensor IMX510 ] ──(MIPI CSI-2)──> [ Camera::DFECore ] (1) Bayer RAW (12/14-bit CFA, 24.2 MP)
                                           │
                                           ▼
                                 [ CamCore::Tanzaku ] (Hardware Demosaic, 3D LUT, CCM, DRO)
                                           │
                                           ▼
                                 [ APL Hardware Resizer ]
                                ┌──────────┴────────────────────────┐
                                ▼                                   ▼
                   (2) DataflowInfra YC               (3) VDF Viewfinder YUV
                   [ Clean Processed YUV ]            [ Display Processed YUV ]
                   (NV12 / YUY2, No OSD)              (Coupled to LCD Refresh)
                                │                                   │
                                ▼                                   ▼
                   [ Pre-JPEG Producer ]              [ Vfx Compositor ]
                   (Intercept for UVC!)               (Blends Icons & Focus Frames)
                                │                                   │
                                ▼                                   ▼
                   [ Hardware JPEG Enc ]              (4) Hardware Scanout (ldec)
                   (Stock MJPEG Bitstream)            [ Compressed wbi_cmpr / Descriptors ]
```

1. **Bayer Sensor RAW**: Unprocessed single-channel CFA mosaic (RGGB). Requires heavy host or GPU demosaicing; unusable as standard UVC.
2. **Processed YUV (YC 4:2:2 / NV12)**: Fully demosaiced, tone-mapped, noise-reduced, color-balanced video produced by BIONZ X hardware at **0% CPU load**. Native standard for UVC (`YUY2` / `NV12`).
3. **Display YUV**: Processed YUV routed to the viewfinder engine; contaminated with on-screen graphics and focus indicators.
4. **Hardware Display Buffers**: Compressed writeback (`wbi_cmpr`) and DMA descriptor tables driving the panel via `ldec.ko`.
5. **Compressed JPEG Streams**: Lossy discrete cosine transform (DCT) bitstreams produced by the RTOS JPEG engine, subject to internal buffer limits (`0x3f000` clamp).

---

## 3. Deep Operational Contract of Best Candidate

The authoritative frame acquisition architecture combines **Candidate #1 (DataflowInfra YC / `SdsYcc`)** as the image data provider and **Candidate #2 (`VideoEsManager` in `im.elf`)** as the transport staging manager.

### 3.1 Complete Acquisition API Call Sequences

#### Sequence A: Asynchronous IPC Transport (`libBizFw.so`)
All high-level communication with the RTOS Dataflow and VDF engines flows through `OBJAVBBCBASECLASS::DataflowInfraCh::sndRcvAsyncDataflowMsg` (VA `0x35548`, PLT `0x2cd84`):

```c
/* Function Signature (Thumb-2, libBizFw.so VA 0x00035548):
 * int sndRcvAsyncDataflowMsg(void *req_buf, uint16_t req_sz,
 *                            void *reply_buf, uint16_t reply_sz,
 *                            uint32_t send_timeout_ms, uint32_t rcv_timeout_ms);
 */
```

1. **OSAL Message Allocation**: Calls `allocOsalId(&osal_id, 1)` at VA `0x3556e` (`OSALID_AUTO_FREE_MODE`).
2. **Asynchronous Send**: Calls `sndAsyncDataflowMsg(this, req_buf, req_sz, osal_id, send_timeout)` at VA `0x355c0`.
3. **Asynchronous Receive**: Calls `rcvAsyncDataflowMsg(this, reply_buf, reply_sz, osal_id, rcv_timeout)` at VA `0x355fa`.
4. **OSAL Message Free**: Calls `freeOsalId(this, osal_id)` at VA `0x35622` in both success and error paths, guaranteeing zero OSAL handle leaks.

#### Sequence B: DMM Handle Resolution (`dumpSdsYccFromHandle`, VA `0x34998`)
To resolve a logical frame handle into physical memory plane addresses:
1. Validates `unit_handle != 0` (`cbnz r1, #0x349c8`).
2. Instantiates `DmmCh` channel with owner ID `0x35` (53 decimal) at VA `0x349f2`:
   ```arm
   0x000349ee:  movs    r1, #0x35
   0x000349f0:  adds    r0, r7, #4
   0x000349f2:  blx     #0x2c68c        ; DmmCh::DmmCh(0x35)
   ```
3. Prepares 24-byte `dmm_comp_open_unit` structure and invokes `DmmCh::open`:
   ```arm
   0x00034a02:  mov.w   r3, #-1         ; timeout = -1 (INFINITE)
   0x00034a0a:  add.w   r1, r7, #0x48   ; &dmm_comp_open_unit
   0x00034a0e:  mov     r2, r4          ; unit_handle
   0x00034a12:  blx     #0x2c328        ; DmmCh::open
   ```
4. Verifies status word `[r7, #0x4a] >= 0`. Extracts physical plane pointers:
   - `phy_addr_y` = `[r7, #0x58]` (offset `+0x10` in open structure)
   - `phy_addr_uv` = `[r7, #0x5c]` (offset `+0x14` in open structure)
5. Forwards to `dumpSdsYccFromPhyAddr` (VA `0x34174`).
6. Closes the unit via `DmmCh::close` at VA `0x34a62` and destroys `DmmCh` at VA `0x34a68`.

#### Sequence C: VideoEsManager Worker Lifecycle (`libInfraStreamingUsb.so`)
The frame acquisition and submission loop runs in `VideoEsManager::video_thread` (VA `0x9700`) inside `im.elf`:

```c
void VideoEsManager::video_thread(void *arg) {
    while (1) {
        // Step 1: Sample thread state under short mutex lock (3 instructions)
        UFW::Sem::Lock(this->state_mutex);       // VA 0x971a
        uint8_t state = this->state_byte;        // VA 0x971e (0=exit, 1=idle, 2=running)
        UFW::Sem::Unlock(this->state_mutex);     // VA 0x9722

        if (state == 0) break;
        if (state == 1) {
            UFW::Sem::Lock(this->uvc_scalar_sem);
            continue;
        }

        // Step 2: Execute frame acquisition and delivery
        set_video_data_to_driver(this);          // VA 0x9618
    }
}
```

In `set_video_data_to_driver` (VA `0x9618`):
1. **Poll Ready Frame**: Invokes `get_video_image(&jpeg_data_info)` at VA `0x9638`.
   - Sends IPC message `0x2009:0x0100` (opcode `0x20`) to route `0x0167046a` (`ScalarInfraSequenceLiveViewStageAutoexec_jpeg`).
   - If frame is ready (`valid_flag == 1`), extracts DMM Unit Handle (`[r7, #0x238]`) and aligned size (`[r7, #0x23a] << 7`).
   - If frame is not ready (`valid_flag == 0`), waits on event `0x00910041` with a **5,000 ms timeout**. If timeout expires, returns status code **3** ("not ready").
   - `set_video_data_to_driver` checks for return code 3 and yields immediately, skipping submission without error latching.
2. **Resolve Physical Address**: Invokes `open_dmm_unit(&dmm_extent, unit_handle)` at VA `0x965a`.
3. **Hardware DMA Completion Fence**:
   ```arm
   0x00009672:  blx     #0x634c         ; WaitVideoReadCmp()
   ```
   Invokes ioctl `0x0000f002` on `/dev/usb/video`. Blocks until ARM CoreLink DMA-330 completes transmitting the previous frame from staging memory into the USB bulk endpoint FIFO.
4. **Submit Frame to Gadget Driver**:
   ```arm
   0x00009686:  ldr     r3, [r7, #0xc]  ; r3 = size (614,400 bytes)
   0x00009688:  str     r3, [r7, #0x18]
   0x0000968a:  ldr     r3, [r7, #0x20] ; r3 = physical_address (Unit 0x276)
   0x0000968c:  str     r3, [r7, #0x1c]
   0x0000968e:  add.w   r3, r7, #0x18   ; &struct { size, phys_addr }
   0x00009692:  ldm.w   r3, {r0, r1}
   0x00009696:  blx     #0x614c         ; UpdateVideoBufEvt()
   ```
   Passes the 8-byte structure `{ uint32_t size, uint32_t phys_addr }` via ioctl `0x4008f003` to `/dev/usb/video`.

---

### 3.2 Synchronization & Fence Mechanisms

1. **Upstream ISP Ping-Pong Fence (`av-cam.bin` @ `0x004eff34`)**:
   In `sfmc_enc_input_yc.cpp`, the RTOS manages a hardware double-buffer ping-pong state for incoming Tanzaku YC frames:
   ```arm
   0x004eff2c:  ldrb.w   r5, [r4, #0x23d]       ; Load ping-pong index (0 or 1)
   0x004eff34:  eor      r3, r5, #1             ; Toggle index (r3 = r5 ^ 1)
   0x004eff38:  strb.w   r3, [r4, #0x23d]       ; Store toggled index
   0x004eff3c:  ldrb.w   r3, [r4, #0x23c]       ; Frame sequence counter
   0x004eff40:  adds     r3, #1                 ; Increment sequence counter
   0x004eff42:  strb.w   r3, [r4, #0x23c]
   0x004eff50:  orr      r1, r5, #0x8100        ; Event ID = 0x8100 | ping_pong_index
   0x004eff58:  blx      r3                     ; Dispatch frame ready notification
   ```
   This hardware ping-pong mechanism guarantees that the BIONZ X ISP never writes into the frame buffer currently being read by the producer.

2. **Viewfinder Read Fence (`VdfCh::getYUVReadStart`, VA `0x39a04`)**:
   For the VDF channel, synchronization is achieved via synchronous IPC command `0x2001:0x0309` (request size 8 bytes, reply size 12 bytes) dispatched to route `0x0059000e`. The call blocks with timeout `-1` (`0xffffffff`, infinite wait) until the display engine completes writing the buffer. Return status `0` indicates the frame is fenced and safe to read.

3. **Downstream USB Transmission Fence (`WaitVideoReadCmp`, VA `0x634c`)**:
   The boundary between userspace frame preparation and USB DMA transmission is strictly fenced by ioctl `0x0000f002` (`WaitVideoReadCmp`) on `/dev/usb/video`. This ioctl blocks until the DMA-330 interrupt service routine `uvc_transfer_dmac_cb` (`usbg_video.ko` VA `.text+0x06a0`) fires, ensuring the USB controller has fully ingested the previous frame before userspace modifies the staging buffer.

---

### 3.3 60-Byte `PIN_YC_IMAGE_SIZE_INFO` Field Specification

The metadata header for all Dataflow YC image buffers is exactly 60 bytes (`0x3c` bytes), 4-byte aligned, instantiated in `dataflowInfraFramework.so` (VA `0x24678`) and verified via `libObj.so` (VA `0xed4a30`).

| Byte Offset | Field Name | Data Type | Accessor VA (`dataflowInfraFramework.so`) | Description & Semantic Constraints |
| :---: | :--- | :---: | :---: | :--- |
| `+0x00` (`0`) | `image_attach` | `uint8_t` | Set `0x246f8`, Get `0x24700` | Attachment flag indicating whether auxiliary metadata (EXIF/AF) is bound to this frame. |
| `+0x01` (`1`) | `reserved0[3]` | `uint8_t[3]` | N/A | Structure alignment padding (zero-filled by `memset`). |
| `+0x04` (`4`) | `unit_type` | `uint32_t` | Set `0x2470a`, Get `0x24712` | DMM Unit Type tag (e.g. `0x1dd`, `0x2c5`, `0x2cd` for 640×480; `0x276` for staging). |
| `+0x08` (`8`) | `unit_handle` | `uint16_t` | Set `0x2471c`, Get `0x24724` | Active DMM allocation handle used to open/map extent physical memory. |
| `+0x0a` (`10`) | `reserved1` | `uint16_t` | N/A | Structure alignment padding. |
| `+0x0c` (`12`) | `unit_data_offset` | `uint32_t` | Set `0x2472e`, Get `0x24736` | Byte offset within the DMM extent to the first active pixel raster byte. |
| `+0x10` (`16`) | `exposure_time` | `uint8_t` | Set `0x24740`, Get `0x2474a` | Exposure time index tag associated with the frame exposure. |
| `+0x11` (`17`) | `expose_pic_delay`| `uint8_t` | Set `0x24756`, Get `0x24760` | Hardware sensor pipeline delay count between exposure and readout. |
| `+0x12` (`18`) | `scenario_end` | `uint8_t` | Set `0x2476c`, Get `0x24776` | End-of-sequence marker flag (set during shooting mode transitions). |
| `+0x13` (`19`) | `mirror` | `uint8_t` | Set `0x24782`, Get `0x2478c` | Sensor readout orientation (horizontal flip / vertical mirror). |
| `+0x14` (`20`) | `record_size_x` | `uint16_t` | Set `0x24798`, Get `0x247a0` | Total buffer stride pitch in pixels (e.g. 640 or 1280). |
| `+0x16` (`22`) | `record_size_y` | `uint16_t` | Set `0x247aa`, Get `0x247b2` | Total allocated buffer height / row capacity in lines (e.g. 480). |
| `+0x18` (`24`) | `canvas_size_x` | `uint16_t` | Set `0x247bc`, Get `0x247c4` | Full canvas allocation width in pixels. |
| `+0x1a` (`26`) | `canvas_size_y` | `uint16_t` | Set `0x247ce`, Get `0x247d6` | Full canvas allocation height in lines. |
| `+0x1c` (`28`) | `valid_offset_x` | `uint16_t` | Set `0x247e0`, Get `0x247e8` | Horizontal pixel offset from canvas start to first active optical pixel. |
| `+0x1e` (`30`) | `valid_offset_y` | `uint16_t` | Set `0x247f2`, Get `0x247fa` | Vertical line offset from canvas start to first active optical line. |
| `+0x20` (`32`) | `valid_size_x` | `uint16_t` | Set `0x24804`, Get `0x2480c` | Active image optical width in pixels (e.g. 640). |
| `+0x22` (`34`) | `valid_size_y` | `uint16_t` | Set `0x24816`, Get `0x2481e` | Active image optical height in lines (e.g. 480). |
| `+0x24` (`36`) | `target_offset_x`| `uint16_t` | Set `0x24828`, Get `0x24830` | Target cropping origin X offset. |
| `+0x26` (`38`) | `target_offset_y`| `uint16_t` | Set `0x2483a`, Get `0x24842` | Target cropping origin Y offset. |
| `+0x28` (`40`) | `target_size_x` | `uint16_t` | Set `0x2484c`, Get `0x24854` | Target display / output scaled width in pixels (e.g. 640). |
| `+0x2a` (`42`) | `target_size_y` | `uint16_t` | Set `0x2485e`, Get `0x24866` | Target display / output scaled height in lines (e.g. 480). |
| `+0x2c` (`44`) | `data_site` | `uint8_t` | Set `0x24870`, Get `0x2487a` | Chroma sampling site (0 = interstitial, 1 = cosited with luma). |
| `+0x2d` (`45`) | `iib_number` | `uint8_t` | Set `0x24886`, Get `0x24890` | Image Information Buffer ring index. |
| `+0x2e` (`46`) | `aspect` | `uint8_t` | Set `0x2489c`, Get `0x248a6` | Aspect ratio enum (0 = 4:3, 1 = 16:9, 2 = 3:2, 3 = 1:1). |
| `+0x2f` (`47`) | `yc_compress` | `uint8_t` | Set `0x248b2`, Get `0x248bc` | Compression mode: `0` = uncompressed linear YUV; `1` = `wbi_cmpr` compressed. |
| `+0x30` (`48`) | `data_transfer` | `uint8_t` | Set `0x248c8`, Get `0x248d2` | DMA transfer packing format flag. |
| `+0x31` (`49`) | `data_placement` | `uint8_t` | Set `0x248de`, Get `0x248e8` | Plane layout: `1` = Interleaved (YUY2); `2` = Semi-Planar (NV12/NV16); `3` = Planar. |
| `+0x32` (`50`) | `data_content` | `uint8_t` | Set `0x248f4`, Get `0x248fe` | Content type tag (0 = liveview/preview, 1 = video, 2 = still capture). |
| `+0x33` (`51`) | `data_scan` | `uint8_t` | Set `0x2490a`, Get `0x24914` | Scan format: `0` = progressive scan; `1` = interlaced scan. |
| `+0x34` (`52`) | `strip_width` | `uint16_t` | Set `0x24920`, Get `0x2492a` | Hardware Tanzaku vertical slice strip width (processing block pitch). |
| `+0x36` (`54`) | `yc_bit_depth` | `uint8_t` | Set `0x24936`, Get `0x24940` | Bit depth per color component: `8` = 8-bit YUV; `10` = 10-bit YUV. |
| `+0x37` (`55`) | `reserved2` | `uint8_t` | N/A | Alignment padding byte. |
| `+0x38` (`56`) | `cam_freq_char_h`| `uint16_t` | Set `0x2494c`, Get `0x24956` | Spatial high-frequency filter characteristic tag. |
| `+0x3a` (`58`) | `reserved3` | `uint16_t` | N/A | Final trailing padding to 60 bytes. |

---

### 3.4 Plane Layout, Stride, and Chroma Subsampling Mapping

DMM configuration records in `DmmConfig.bin` correlate directly with the three liveview preview units:
- **Unit `0x1dd`** $\rightarrow$ **Extent `0x227`**: Size `0x96000` = **614,400 bytes**
- **Unit `0x2c5`** $\rightarrow$ **Extent `0x3da`**: Size `0x96000` = **614,400 bytes**
- **Unit `0x2cd`** $\rightarrow$ **Extent `0x3e2`**: Size `0x96000` = **614,400 bytes**

The exact byte count $614,400 = 640 \times 480 \times 2$ proves that native preview buffers are sized for **16 bits per pixel (YUV 4:2:2)**. Depending on `data_placement` (`+0x31`), the memory organization is mapped as follows:

```
Case A: data_placement == 1 (Interleaved YUV 4:2:2 / YUY2)
Byte:   0    1    2    3    4    5    6    7
Pixel: [Y0 | U0 | Y1 | V0 | Y2 | U1 | Y3 | V1] ...
Total Size: 640 * 480 * 2 = 614,400 bytes. Row pitch = 1,280 bytes.

Case B: data_placement == 2 (Semi-Planar YUV 4:2:2 / NV16)
Plane 0 (Y Luma):     phys_addr + unit_data_offset
                      640 * 480 = 307,200 bytes (0x4b000)
Plane 1 (UV Chroma):  phys_addr + unit_data_offset + 0x4b000
                      640 * 480 = 307,200 bytes (0x4b000)
                      Interleaved [U0 V0 U1 V1 ...]
Total Size: 307,200 + 307,200 = 614,400 bytes.

Case C: data_placement == 2 with 4:2:0 subsampling (NV12)
Plane 0 (Y Luma):     phys_addr + unit_data_offset
                      640 * 480 = 307,200 bytes
Plane 1 (UV Chroma):  phys_addr + unit_data_offset + 0x4b000
                      640 * 240 = 153,600 bytes
Total Size: 307,200 + 153,600 = 460,800 bytes (Extent padded to 614,400 bytes).
```

When `data_placement == 1`, the source buffer is already byte-identical to UVC `YUY2` and can be copied linearly into Unit `0x276`. When `data_placement == 2`, the producer converts semi-planar samples into packed `YUY2` using pure scalar ARMv7-A integer loads, bitwise packing, and stores without NEON instructions.

---

### 3.5 Physical vs Virtual Memory Mapping via `/dev/stream`

The Linux kernel character device `/dev/stream` (`dumps/camera_2025/usr/usr/kmod/stream.ko`, major 249, minor 7) provides the universal mechanism for mapping physical camera DRAM into userspace virtual memory:

```arm
/* stream.ko::stream_mmap (VA 0x00000000 - 0x00000048): */
0x00000010:  ldr    r2, [r1, #0x14]      ; r2 = vma->vm_flags
0x00000014:  mov    r4, r1               ; r4 = vma
0x00000018:  ldr    r5, [r1, #0x48]      ; r5 = vma->vm_pgoff (PAGE FRAME NUMBER)
0x0000001c:  mov    r0, r4               ; r0 = vma
0x00000020:  bic    r2, r2, #0x3c        ; Clear cache bits (bits 2..5)
0x00000024:  str    r2, [r1, #0x14]      ; Store updated vm_flags
0x00000028:  ldmib  r1, {r1, r3}         ; r1 = vma->vm_start, r3 = vma->vm_end
0x0000002c:  orr    r2, r2, #0x40        ; Set VM_IO | VM_RESERVED (0x40)
0x00000030:  str    r2, [sp]             ; 5th arg: pgprot
0x00000034:  mov    r2, r5               ; 3rd arg: pfn = vma->vm_pgoff
0x00000038:  rsb    r3, r1, r3           ; 4th arg: size = vm_end - vm_start
0x0000003c:  bl     remap_pfn_range      ; remap_pfn_range(vma, vm_start, pfn, size, prot)
```

#### Page Frame Number (PFN) Derivation
In standard Linux 3.0 ARM userspace:
```c
void *vaddr = mmap(NULL, length, PROT_READ | PROT_WRITE, MAP_SHARED, fd_stream, (off_t)phys_addr);
```
1. The kernel VFS converts the `offset` parameter into a page offset:
   $$\text{vm\_pgoff} = \frac{\text{phys\_addr}}{\text{PAGE\_SIZE}} = \text{phys\_addr} \gg 12$$
2. `stream_mmap` reads `r5 = vma->vm_pgoff` directly and passes it as argument 3 (`pfn`) to `remap_pfn_range()`.
3. **No Address Validation**: Disassembly lines `0x00` through `0x7c` prove that `stream_mmap` executes **zero bounds checks, range validation, or permission filters**. Any physical RAM address known to userspace can be mapped directly into virtual address space.

---

### 3.6 Memory Ownership Architecture & Cortex-A9 Cache Contract

#### Master Memory Ownership Table

| Memory Region / Buffer | DMM Unit Type | DMM Extent ID | Buffer Size | Allocator Subsystem | Writer Subsystem | Reader Subsystem | Release / Lifetime Responsibility |
| :--- | :---: | :---: | :---: | :--- | :--- | :--- | :--- |
| **ISP Live Preview Ring** | `0x1dd`, `0x2c5`, `0x2cd` | `0x227`, `0x3da`, `0x3e2` | 614,400 bytes | **RTOS / LIRO ISP (`SDF`)** | **BIONZ X Hardware ISP DMA** | **Linux CPU (`im.elf`) & Display (`VDF`)** | **Shared Lease**: CPU must never free extents; RTOS reclaims via internal ping-pong. |
| **USB Streaming Staging (Patched)** | **`0x276`** | **`0x333`** | **3,276,800 bytes** | **Linux Producer (`im.elf`)** | **Linux CPU (Scalar converter / copy)** | **`dma330.ko` / USB UVC FIFO** | **Exclusive Ownership**: Allocated once at session startup; persists across frame cycles. |
| **USB Streaming Staging (Stock)** | `0x50e` | `0x589` | 1,843,200 bytes | Stock `usbg_video.ko` (Owner `0x2da`) | Stock RTOS JPEG Encoder | `usbg_video.ko` DMA330 | Stock `libInfraStreamingUsb.so` transient alloc/free per frame. |
| **USB Audio FIFO** | `0x50f` | `0x58a` | 6,144 bytes | `usbg_audio.ko` (Owner `0x2db`) | Linux Audio Server | USB UAC Endpoint | `usbg_audio.ko` (Fixed FIFO). |

#### Cortex-A9 Cache Maintenance Contract
The Sony CXD90045 comprises a dual-core ARM Cortex-A9 running Linux and dedicated DSP/coprocessor cores running the LIRO RTOS. Hardware cache coherency between Linux and RTOS **does not exist across the interconnect**.

1. **Reading Incoming ISP Frames via `/dev/stream`**:
   - `stream.ko` configures page attributes using:
     ```arm
     bic r2, r2, #0x3c    ; clear L_PTE_MT_MASK
     orr r2, r2, #0x40    ; set L_PTE_MT_UNCACHED / Device memory
     ```
   - All virtual memory mappings generated by `/dev/stream` are **strictly non-cached (`pgprot_noncached`)**.
   - CPU load instructions bypass L1 data cache and the L2C-310 unified cache, reading directly from physical DRAM across the AXI interconnect.
   - **Cache Invalidation**: Because the virtual pages are non-cached, **no CPU cache invalidation instructions (`dmac_inv_range` or `outer_inv_range`) are required** on the virtual address.

2. **Writing Staged YUY2 Frames into Unit `0x276`**:
   - Because Unit `0x276` is also mapped non-cached via `/dev/stream`, CPU write stores drain through the Cortex-A9 write-combining buffers directly to physical DRAM.
   - **Memory Barriers**: To ensure all write transactions have committed to physical DRAM before the ARM CoreLink DMA-330 controller initiates PCIe/AXI read cycles, the producer **must execute explicit memory barriers**:
     ```c
     __asm__ volatile("dsb\n\tdmb" ::: "memory");
     ```
   - If Unit `0x276` is mapped with write-back caching for higher copy throughput, dirty cache lines **must be cleaned** prior to calling `UpdateVideoBufEvt`:
     - L1 Clean: `sys_cacheflush(vaddr, 614400, 0)` or `__clear_cache`.
     - L2 Clean: Outer cache clean ioctl to L2C-310.
     - *Failure to flush cached writes causes DMA330 to transmit stale DRAM data, producing horizontal tearing or corrupt synthetic artifacts.*

3. **Cross-Core Synchronization**:
   - The RTOS guarantees that hardware ISP writeback transactions are committed to DRAM before firing the completion notification (`valid_flag == 1` or event `0x00910041`).
   - The Linux producer completes its conversion read and releases the logical lease before the RTOS reclaims the buffer in its ring.

---

## 4. Producer Integration & Conversion Architecture

### 4.1 Bounded Copy and Staging Architecture

The producer acquires live frames from Dataflow YC and converts them into our exclusively owned DMM Unit `0x276` buffer (`3,276,800 bytes`, live physical base `0x15b00000`):

```
[ DataflowInfra / ISP Ring ] (Unit 0x1dd / 0x2c5 / 0x2cd)
         │
         │ Non-cached mmap read via /dev/stream
         ▼
[ ARM Cortex-A9 Producer ] ──(Scalar Integer Kernel)──> [ DMM Unit 0x276 Staging ]
                                                    (Physical 0x15b00000, 614.4 KB)
                                                                 │
                                                    DSB / DMB Memory Barrier
                                                                 │
                                                    ioctl 0x4008f003 (UpdateVideoBufEvt)
                                                                 ▼
                                                    [ usbg_video.ko / DMA330 ]
                                                                 │
                                                                 ▼
                                                    [ USB 2.0 Bulk IN FIFO ]
```

- **Zero Allocation in Loop**: Unit `0x276` is allocated and mapped once during streaming initialization. No memory allocation (`malloc`, `mmap`, or `dmm_ctrl_AllocUnitHdlr`) occurs inside the steady-state streaming loop, eliminating memory fragmentation and runtime latency spikes.
- **Buffer Decoupling**: Copying the frame into Unit `0x276` fully decouples the USB transfer lifetime from the camera's internal preview pipeline. The ISP buffer is released immediately after the ~1.2 ms scalar copy, preventing display stuttering or auto-focus pipeline stalls.

---

### 4.2 Hardware Execution Constraint & Scalar Integer Algorithms

#### Hardware Constraint: VFPv3-D16 Architecture (No ARM NEON)
A critical architectural constraint governs software execution on the Sony ZV-E10:
- **Processor Identification**: The Sony CXD90045 (BIONZ X) ARMv7-A processor core implements the ARMv7-A architecture with VFPv3-D16 floating-point extensions only (16 double-precision 64-bit registers `d0`–`d15`).
- **Absence of NEON**: The core **strictly lacks ARM NEON Advanced SIMD extensions**. It provides neither 128-bit quadword registers (`q0`–`q15`) nor NEON vector instruction decoding (`vld1`, `vld2`, `vst1`, `vst2`, `vzip`, `vuzp`).
- **Direct `/proc/cpuinfo` Evidence**: Direct service-shell diagnostics on the live system report:
  ```text
  Features: swp half thumb fastmult vfp edsp vfpv3 vfpv3d16 tls vfpv4
  ```
  Notice that `neon` is completely absent from the CPU features bitmap.
- **Fatal Exception on NEON Instructions**: Any execution of ARM NEON instructions triggers an immediate, fatal `SIGILL` (Illegal Instruction) fault that terminates the user process or kernel thread.
- **Implementation Mandate**: All pixel conversion, unpacking, interleaving, and memory transfer routines MUST execute exclusively via pure scalar ARMv7-A / Thumb-2 integer instructions (e.g. `ldr`/`ldrh`, bit-field manipulation, `str`/`strh`, `ldmia`/`stmia`) or standard portable scalar C loops.

#### Kernel 1: Semi-Planar NV16/NV12 to Interleaved YUY2 Conversion (Scalar ARMv7-A / Thumb-2)
When the ISP outputs semi-planar data (`data_placement == 2`), the producer converts semi-planar samples into packed `YUY2` (where each 2-pixel pair consists of 4 bytes: `[Y0, U0, Y1, V0]`). In pure scalar ARMv7-A / Thumb-2 integer assembly, two pixels are processed per iteration using 16-bit halfword loads (`ldrh`), byte extraction/packing, and a single 32-bit word store (`str`):

```arm
/* Pure Scalar ARMv7-A / Thumb-2 Integer Kernel: NV16 to YUY2 (4 bytes / 2 pixels per loop)
 * Hardware Target: Cortex-A (VFPv3-D16, NO NEON) - Zero SIGILL Risk
 * Input:
 *   r0 = p_luma_y     (pointer to Y plane, 1 byte/pixel)
 *   r1 = p_chroma_uv  (pointer to UV plane, 2 bytes interleaved per pair)
 *   r2 = p_dst_yuy2   (pointer to packed YUY2 destination)
 *   r3 = pixel_count  (total pixels to convert, e.g. 307200)
 */
nv16_to_yuy2_scalar_loop:
    ldrh        r4, [r0], #2          /* r4 = [Y1 : Y0] (16-bit luma) */
    ldrh        r5, [r1], #2          /* r5 = [V0 : U0] (16-bit chroma) */
    uxtb        r6, r4                /* r6 = Y0 (byte 0) */
    and         r7, r5, #0x00ff       /* r7 = U0 (byte 1) */
    orr         r6, r6, r7, lsl #8    /* r6 = [U0 : Y0] */
    ubfx        r7, r4, #8, #8        /* r7 = Y1 (byte 2) */
    orr         r6, r6, r7, lsl #16   /* r6 = [Y1 : U0 : Y0] */
    and         r7, r5, #0xff00       /* r7 = V0 << 8 (byte 3) */
    orr         r6, r6, r7, lsl #16   /* r6 = [V0 : Y1 : U0 : Y0] (32-bit YUY2) */
    str         r6, [r2], #4          /* Store 4 bytes (2 YUY2 pixels) */
    subs        r3, r3, #2
    bne         nv16_to_yuy2_scalar_loop
```

#### Portable Scalar C Reference Implementations (`raw_frame_source.c`)
As implemented in `research/firmware/raw_frame_source/raw_frame_source.c`, standard portable scalar C loops provide bit-exact conversion and clean compiler optimization without inline vector intrinsics:

```c
/* Portable Scalar NV16 (4:2:2 Semi-Planar) to YUY2 (Packed 4:2:2) */
int raw_frame_convert_nv16_to_yuy2(const uint8_t *y_plane, size_t y_stride,
                                  const uint8_t *uv_plane, size_t uv_stride,
                                  uint8_t *dst_yuy2, size_t dst_stride,
                                  uint32_t width, uint32_t height)
{
    for (uint32_t y = 0; y < height; ++y) {
        const uint8_t *src_y = y_plane + (size_t)y * y_stride;
        const uint8_t *src_uv = uv_plane + (size_t)y * uv_stride;
        uint8_t *dst = dst_yuy2 + (size_t)y * dst_stride;

        for (uint32_t x = 0; x < width; x += 2) {
            uint8_t y0 = src_y[x];
            uint8_t y1 = src_y[x + 1];
            uint8_t u0 = src_uv[x];     /* Interleaved Cb at even byte */
            uint8_t v0 = src_uv[x + 1]; /* Interleaved Cr at odd byte */

            dst[0] = y0;
            dst[1] = u0;
            dst[2] = y1;
            dst[3] = v0;
            dst += 4;
        }
    }
    return RAW_FRAME_OK;
}

/* Portable Scalar NV12 (4:2:0 Semi-Planar) to YUY2 (Packed 4:2:2 with vertical 2x upsampling) */
int raw_frame_convert_nv12_to_yuy2(const uint8_t *y_plane, size_t y_stride,
                                  const uint8_t *uv_plane, size_t uv_stride,
                                  uint8_t *dst_yuy2, size_t dst_stride,
                                  uint32_t width, uint32_t height)
{
    for (uint32_t y = 0; y < height; ++y) {
        const uint8_t *src_y = y_plane + (size_t)y * y_stride;
        /* Vertical chroma subsampling: 2 luma lines share 1 chroma line */
        const uint8_t *src_uv = uv_plane + (size_t)(y >> 1) * uv_stride;
        uint8_t *dst = dst_yuy2 + (size_t)y * dst_stride;

        for (uint32_t x = 0; x < width; x += 2) {
            uint8_t y0 = src_y[x];
            uint8_t y1 = src_y[x + 1];
            uint8_t u0 = src_uv[x];
            uint8_t v0 = src_uv[x + 1];

            dst[0] = y0;
            dst[1] = u0;
            dst[2] = y1;
            dst[3] = v0;
            dst += 4;
        }
    }
    return RAW_FRAME_OK;
}
```

#### Kernel 2: Interleaved YUY2 High-Throughput Memory Blit (Scalar Integer)
When `data_placement == 1`, the source is already formatted as packed YUY2. Rather than using prohibited NEON instructions, high-efficiency scalar block copying utilizes 32-bit multi-register integer load/store instructions (`ldmia` / `stmia`) transferring 32 bytes per iteration:

```arm
/* Pure Scalar ARMv7-A 32-Byte Block Copy Loop
 * Input:
 *   r0 = src_phys_vaddr (32-bit aligned source pointer)
 *   r1 = dst_phys_vaddr (32-bit aligned destination pointer)
 *   r2 = block_count    (614400 bytes / 32 bytes = 19200 blocks)
 */
yuy2_scalar_copy_loop:
    ldmia       r0!, {r4, r5, r6, r7, r8, r9, r10, r11}  /* Load 32 bytes into integer regs */
    stmia       r1!, {r4, r5, r6, r7, r8, r9, r10, r11}  /* Store 32 bytes to destination */
    subs        r2, r2, #1
    bne         yuy2_scalar_copy_loop
```

And in standard C (`raw_frame_source.c`):
```c
/* Fast copy for already packed YUY2 source buffer */
int raw_frame_copy_yuy2(const uint8_t *src_yuy2, size_t src_stride,
                        uint8_t *dst_yuy2, size_t dst_stride,
                        uint32_t width, uint32_t height)
{
    size_t row_bytes = (size_t)width * RAW_FRAME_YUY2_BYTES_PER_PX;
    if (src_stride == row_bytes && dst_stride == row_bytes) {
        memcpy(dst_yuy2, src_yuy2, row_bytes * height);
    } else {
        for (uint32_t y = 0; y < height; ++y) {
            memcpy(dst_yuy2 + (size_t)y * dst_stride,
                   src_yuy2 + (size_t)y * src_stride,
                   row_bytes);
        }
    }
    return RAW_FRAME_OK;
}
```

---

### 4.3 Downscale and Crop Strategies

When the camera sensor operates in wide aspect ratios, geometry adaptation is applied:

1. **Native 4:3 (640×480)**: Identity mapping ($1:1$). Zero downscaling or crop required; full optical sensor height is preserved.
2. **Native 16:9 Viewfinder (1280×720 or 960×540)**:
   - **Hardware Scaler Path (Preferred)**: Invoked via `VideoEsManager::set_path_sync` (VA `0x8e14`) using command `0x2009:0x0050`. The RTOS hardware scaler (`ModuleResizeRotateScalar` in `av-cam.bin` VA `0x63f41f78`) performs hardware resampling and aspect conversion directly into the DMM extent before delivery at **0% CPU load**.
   - **Software Center Crop (Fallback)**: When downscaling from $960 \times 720$, crop 160 pixels horizontally ($x_{\text{offset}} = 160$) to obtain $640 \times 480$ without aspect distortion.
   - **Software Letterbox (Fallback)**: Resample $1280 \times 720 \rightarrow 640 \times 360$ and center vertically within the $640 \times 480$ frame by padding 60 black rows top and bottom (`0x80108010` in YUY2).

---

### 4.4 Memory Bandwidth and CPU Overhead Budgets (Scalar Execution)

To evaluate system stability, memory traffic across the DDR3 bus ($3.2\text{ GB/s}$ sustained bandwidth) and scalar CPU utilization were modeled:

#### Budget for 640×480 @ 10 fps (Baseline Verified Profile)
- **Pixel Count per Frame**: $640 \times 480 = 307,200\text{ pixels}$ (153,600 two-pixel pairs).
- **Frame Payload Size**: $614,400\text{ bytes}$ ($0.586\text{ MB}$).
- **Memory Traffic**:
  - Source DRAM Read: $614,400 \times 10 = 6.144\text{ MB/s}$
  - Destination DRAM Write: $614,400 \times 10 = 6.144\text{ MB/s}$
  - USB DMA330 Ingestion: $614,400 \times 10 = 6.144\text{ MB/s}$
  - **Total Bus Bandwidth**: $\mathbf{18.43\text{ MB/s}}$ ($0.58\%$ of $3.2\text{ GB/s}$ DDR3 bus).
- **CPU Execution Overhead (Pure Scalar)**:
  - Each 2-pixel pair (4 bytes YUY2) requires approximately **4–8 scalar cycles** (~3–4 cycles/pixel).
  - Scalar execution at 4 cycles/pixel: $307,200 \times 4 = 1,228,800\text{ cycles/frame}$ (~$1.23\text{ million cycles/frame}$).
  - At 10 fps (307,200 px): $\mathbf{12.3\text{ million cycles/sec}} = \mathbf{1.23\%\text{ of a 1.0 GHz Cortex-A9 core}}$.

#### Budget for 640×480 @ 30 fps (Target Production Profile)
- **Memory Traffic**:
  - Source DRAM Read: $614,400 \times 30 = 18.432\text{ MB/s}$
  - Destination DRAM Write: $614,400 \times 30 = 18.432\text{ MB/s}$
  - USB DMA330 Ingestion: $614,400 \times 30 = 18.432\text{ MB/s}$
  - **Total Bus Bandwidth**: $\mathbf{55.30\text{ MB/s}}$ ($\mathbf{1.73\%}\text{ of } 3.2\text{ GB/s DDR3 bus}$).
- **CPU Execution Overhead (Pure Scalar)**:
  - At 30 fps (307,200 px): $\mathbf{36.9\text{ million cycles/sec}} = \mathbf{3.69\%\text{ of a 1.0 GHz Cortex-A9 core}}$.
- **Thermal & Hardware Budget Assessment**:
  - The scalar implementation requires **$< 4\%$ of 1 core @ 30 fps**, remaining comfortably within the camera's thermal and CPU budget, with **zero risk of SIGILL** crashes on target hardware.

#### Comparison with Bayer RAW Demosaicing
- In contrast, executing software Bayer demosaicing at 30 fps requires **$921\text{ MIPS}$ ($92.1\%$ CPU saturation)** and **$108\text{ MB/s}$ memory traffic**. The processed YUV scalar approach operates with **$25\times$ lower CPU consumption** than software demosaicing and strictly prevents hardware crashes.

---

### 4.5 Lifecycle State Machine and Lock Isolation Guarantees

#### Anti-Deadlock Guarantee
Disassembly of `VideoEsManager::video_thread` (VA `0x9700`) reveals a strict lock hierarchy:
1. `this->state_mutex` (`[r4, #0x10]`) is locked solely to read `this->state_byte` (`[r4]`) and is unlocked within **3 instructions**.
2. **Lock Rule**: `state_mutex` is **never held across any IPC invocation, driver ioctl, or memory copy**.
3. During active streaming, the thread waits on local iteration semaphore `uvc_scalar_sem` (`[r4, #0x18]`). External control threads invoking `entry_video_thread()` or `exit_video_thread()` can acquire `state_mutex` instantaneously without being blocked by in-flight frame acquisitions.

#### Robust Reopen & Error Handling
In accordance with the verified [Revision 2.4p](uvc_yuy2_patch_v24p.md) architecture:
1. If `WaitVideoReadCmp()` returns error with `errno == EBUSY` (`16`), the producer retains the in-flight buffer and retries at the 100 ms period without incrementing failure counters.
2. If `get_video_image` returns status code `3` ("not ready"), `set_video_data_to_driver` yields cleanly without latching fatal error states.
3. If camera sensor acquisition experiences hardware timeouts, the producer seamlessly falls back to synthetic color bars, guaranteeing that the USB bulk endpoint never starves or hangs host client software.

---

## 5. Formal Integration & Handoff Specification

The following specification table governs the interface contract between the live camera frame source and the UVC YUY2 USB transport:

| Specification Parameter | Technical Contract Value | Evidence / Binary Reference | Architectural Rationale & Implementation Notes |
| :--- | :--- | :--- | :--- |
| **Output Target Dimensions** | $640 \times 480\text{ pixels}$ | [Revision 2.4p](uvc_yuy2_patch_v24p.md); `usbg_video.ko` | Matches proven UVC descriptor and Windows DirectShow/OBS configuration. |
| **Pixel Encoding Format** | `YUY2` (FourCC: `0x32595559`) | UVC Uncompressed GUID; `usbg_video.ko` | Packed 16-bit format: `[Y0, U0, Y1, V0]` (4:2:2 chroma subsampling). |
| **Frame Payload Byte Count** | Exactly **614,400 bytes** (`0x96000`) | $640 \times 480 \times 2$; Extents `0x227`, `0x3da`, `0x3e2` | Matches `usbg_video.ko` descriptor `dwMaxVideoFrameBufferSize`. |
| **Buffer Memory Alignment** | 128-byte cache / page aligned | `DmmConfig.bin` extent records; `stream_mmap` | Extent allocations align to 4096-byte page boundaries; safe for DMA330. |
| **Staging Buffer Unit** | **DMM Unit `0x276`** (Extent `0x333`) | `DmmConfig.bin` offset `0x11c20`; live `0x15b00000` | Exclusively allocated; 3,276,800 bytes capacity; idle during YUY2 streaming. |
| **Frame Readiness Fence** | `valid_flag == 1` & `WaitVideoReadCmp` | `libInfraStreamingUsb.so` VA `0x915e`, `0x9672` | Hardware IPC notification followed by DMA330 completion ioctl `0x0000f002`. |
| **Memory Mapping Interface** | `/dev/stream` (`stream.ko`) | Major 249, Minor 7; VA `0x00`–`0x7c` | Physical address mapped via `mmap` with PFN shift (`phys_addr >> 12`). |
| **Cache Maintenance Rule** | `pgprot_noncached` + `DSB` / `DMB` | `stream.ko` VA `0x20`–`0x2c`; Cortex-A9 barrier | Non-cached mapping bypasses L1/L2; memory barriers drain store buffers. |
| **Buffer Release Ownership** | Shared lease return via IPC | `close_pin_data` / `sfmc_enc_input_yc.cpp` | Upstream ISP lease released; Unit `0x276` retained across session. |
| **Fallback Guarantee** | Synthetic color bars + counter | `yuy2_640_v24p.so` producer | Automatically engaged if sensor frame acquisition times out. |

---

## 6. Disassembly Citations & Instruction-Level Evidence

### 6.1 `dataflowInfraFramework.so` (MD5: `f70f50f931e9c2cf415cc2728e324f60`)

#### Struct Constructor & Initializer (VA `0x00024678`)
```arm
0x00024678:  push    {r4, r5, r6, lr}
0x0002467a:  mov     r4, r0              ; r4 = this
0x00024688:  movs    r6, #0x3c           ; Length = 0x3c (60 bytes)
0x0002468a:  movs    r1, #0              ; Fill byte = 0
0x0002468c:  mov     r2, r6              ; Size = 60 bytes
0x00024694:  str     r3, [r5], #0x14     ; Vtable at [r4], r5 = this + 0x14
0x00024698:  mov     r0, r5              ; r0 = this + 0x14
0x0002469a:  blx     #0x20228            ; memset(this + 0x14, 0, 60)
0x000246a0:  str     r5, [r4, #0xc]      ; struct_ptr = this + 0x14
0x000246a4:  str     r6, [r4, #0x10]     ; struct_size = 0x3c (60 bytes)
```

#### Bulk Copy Method `GetData_All` (VA `0x000246d6`)
```arm
0x000246d6:  push    {r4, r5, r6, r7, lr}
0x000246d8:  add.w   r5, r0, #0x14       ; Source base = this + 0x14
0x000246dc:  mov     r6, r1              ; Dest = PIN_YC_IMAGE_SIZE_INFO*
0x000246e0:  ldm     r5!, {r0, r1, r2, r3} ; Copy 16 bytes (0x00..0x0f)
0x000246e2:  mov     r4, r6
0x000246e4:  stm     r4!, {r0, r1, r2, r3}
0x000246e6:  ldm     r5!, {r0, r1, r2, r3} ; Copy 16 bytes (0x10..0x1f)
0x000246e8:  stm     r4!, {r0, r1, r2, r3}
0x000246ea:  ldm     r5!, {r0, r1, r2, r3} ; Copy 16 bytes (0x20..0x2f)
0x000246ec:  stm     r4!, {r0, r1, r2, r3}
0x000246ee:  ldm.w   r5, {r0, r1, r2}     ; Copy 12 bytes (0x30..0x3b)
0x000246f2:  stm.w   r4, {r0, r1, r2}     ; Total = 60 bytes (0x3c)
0x000246f6:  pop     {r4, r5, r6, r7, pc}
```

---

### 6.2 `libBizFw.so` (MD5: `6416a5a6780bbe829eb30d85fc8e8dad`)

#### Asynchronous IPC Wrapper `sndRcvAsyncDataflowMsg` (VA `0x00035548`)
```arm
0x00035548:  push.w  {r4, r5, r6, r7, r8, sb, sl, fp, lr}
0x0003554c:  sub     sp, #0x24
0x0003554e:  add     r7, sp, #0x10
0x00035550:  mov     fp, r1              ; fp = req_buf
0x00035558:  mov     r8, r3              ; r8 = reply_buf
0x0003555a:  movs    r2, #1              ; OSALID_AUTO_FREE_MODE
0x0003556e:  blx     #0x2acd0            ; DataflowInfraCh::allocOsalId(&osal_id, 1)
0x00035574:  cbz     r0, #0x35594        ; Check allocation status
0x000355c0:  blx     #0x2bd30            ; DataflowInfraCh::sndAsyncDataflowMsg
0x000355fa:  blx     #0x2c280            ; DataflowInfraCh::rcvAsyncDataflowMsg
0x00035622:  blx     #0x2c464            ; DataflowInfraCh::freeOsalId
0x0003563a:  pop.w   {r4, r5, r6, r7, r8, sb, sl, fp, pc}
```

#### DMM Handle Resolution in `dumpSdsYccFromHandle` (VA `0x00034998`)
```arm
0x000349ee:  movs    r1, #0x35           ; Owner ID = 0x35 (53 decimal)
0x000349f0:  adds    r0, r7, #4
0x000349f2:  blx     #0x2c68c            ; DmmCh::DmmCh(0x35)
0x00034a02:  mov.w   r3, #-1             ; Timeout = -1 (INFINITE)
0x00034a0a:  add.w   r1, r7, #0x48       ; &dmm_comp_open_unit
0x00034a0e:  mov     r2, r4              ; unit_handle
0x00034a12:  blx     #0x2c328            ; DmmCh::open
0x00034a42:  ldr     r1, [r7, #0x58]     ; phy_addr_y (offset +0x10)
0x00034a44:  ldr     r2, [r7, #0x5c]     ; phy_addr_uv (offset +0x14)
0x00034a4a:  blx     #0x2a8bc            ; dumpSdsYccFromPhyAddr
0x00034a62:  blx     #0x2b0c4            ; DmmCh::close
```

---

### 6.3 `libInfraStreamingUsb.so` (MD5: `cde7a1b42c919706aa5f61aba5fc0d75`)

#### Video Manager Delivery in `set_video_data_to_driver` (VA `0x00009618`)
```arm
0x00009638:  blx     #0x5ba8             ; get_video_image(&jpeg_data_info)
0x0000965a:  blx     #0x5c4c             ; open_dmm_unit(&dmm_extent, unit_handle)
0x00009672:  blx     #0x634c             ; WaitVideoReadCmp() [ioctl 0x0000f002]
0x00009686:  ldr     r3, [r7, #0xc]      ; r3 = size
0x00009688:  str     r3, [r7, #0x18]
0x0000968a:  ldr     r3, [r7, #0x20]     ; r3 = phys_addr
0x0000968c:  str     r3, [r7, #0x1c]
0x0000968e:  add.w   r3, r7, #0x18       ; &struct { size, phys_addr }
0x00009692:  ldm.w   r3, {r0, r1}
0x00009696:  blx     #0x614c             ; UpdateVideoBufEvt() [ioctl 0x4008f003]
```

#### Worker Thread Lock Isolation in `video_thread` (VA `0x00009700`)
```arm
0x00009718:  ldr     r0, [r4, #0x10]     ; r0 = state_mutex
0x0000971a:  blx     #0x6328             ; UFW::Sem::Lock
0x0000971e:  ldrb    r5, [r4]            ; r5 = state_byte (0=exit, 1=idle, 2=running)
0x00009720:  ldr     r0, [r4, #0x10]
0x00009722:  blx     #0x60dc             ; UFW::Sem::Unlock (Locked for 3 instructions!)
0x00009740:  bl      #0x9618             ; set_video_data_to_driver(this)
```

---

### 6.4 `stream.ko` (MD5: `7191da2f6a78d84f9a3f9eac4680eb2a`)

#### Uncached Page Remapping in `stream_mmap` (VA `0x00000000`)
```arm
0x00000010:  ldr     r2, [r1, #20]       ; r2 = vma->vm_flags
0x00000018:  ldr     r5, [r1, #72]       ; r5 = vma->vm_pgoff (PFN = phys_addr >> 12)
0x00000020:  bic     r2, r2, #60         ; Clear cache bits (0x3c)
0x00000024:  str     r2, [r1, #20]       ; Force pgprot_noncached
0x00000028:  ldmib   r1, {r1, r3}        ; r1 = vm_start, r3 = vm_end
0x0000002c:  orr     r2, r2, #64         ; Set VM_IO | VM_RESERVED (0x40)
0x00000030:  str     r2, [sp]            ; Argument 5: prot
0x00000034:  mov     r2, r5              ; Argument 3: pfn
0x00000038:  rsb     r3, r1, r3          ; Argument 4: size
0x0000003c:  bl      remap_pfn_range     ; Direct PFN remap without address clipping!
```

---

### 6.5 `dumps/firmware/av-cam.bin` (MD5: `cdcae9d4fdbf66a33704a4c7564e346d`)

#### RTOS JPEG Encode Descriptor Builder (Offset `0x00810978`)
```arm
0x00810978:  push    {r4, r5, r6, r7, lr}
0x0081097a:  ldr     r6, [sp, #0x14]     ; r6 = requested output workspace
0x0081097c:  ldrh.w  r5, [sp, #0x18]     ; r5 = frame width
0x00810980:  ldrh.w  r4, [sp, #0x1c]     ; r4 = frame height
0x00810984:  cmp.w   r6, #0x3f000        ; Check against 0x3f000 (258,048 bytes)
0x00810988:  it      hs
0x0081098a:  movhs.w r6, #0x3f000        ; Clamp workspace to 252 KB
0x008109a0:  strh    r2, [r0, #0x1c]     ; [r0, #0x1c] = source YC buffer handle
0x008109a6:  strh.w  r5, [r0, #0x40]     ; [r0, #0x40] = input width
0x008109aa:  strh.w  r4, [r0, #0x42]     ; [r0, #0x42] = input height
0x008109ae:  strh.w  r5, [r0, #0x44]     ; [r0, #0x44] = output width
0x008109b2:  strh.w  r4, [r0, #0x46]     ; [r0, #0x46] = output height
0x008109bc:  pop     {r4, r5, r6, r7, pc}
```

#### RTOS Frame Ingestion & Ping-Pong Toggle (Offset `0x004eff2c`)
```arm
0x004eff2c:  ldrb.w  r5, [r4, #0x23d]    ; Load current ping-pong index
0x004eff34:  eor     r3, r5, #1          ; Toggle index (r3 = r5 ^ 1)
0x004eff38:  strb.w  r3, [r4, #0x23d]    ; Store updated index
0x004eff3c:  ldrb.w  r3, [r4, #0x23c]    ; Frame sequence counter
0x004eff40:  adds    r3, #1              ; Increment frame count
0x004eff42:  strb.w  r3, [r4, #0x23c]
0x004eff50:  orr     r1, r5, #0x8100     ; r1 = 0x8100 | ping_pong_index
0x004eff54:  ldr.w   r3, [r3, #0x80]     ; vtable slot 0x80
0x004eff58:  blx     r3                  ; Fire frame ready notification
```

---

## 7. Verification & Reproduction Protocol

All technical findings, hashes, offsets, and instruction disassemblies documented herein can be independently verified on any development host without physical camera hardware.

### 7.1 Binary Cryptographic Hashes Verification
Execute the following verification command using Python 3:
```powershell
& "D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe" -B -c "
import hashlib
targets = [
    ('dumps/camera_2025/usr/usr/lib/libBizFw.so', '6416a5a6780bbe829eb30d85fc8e8dad'),
    ('dumps/camera_2025/usr/usr/lib/libInfraStreamingUsb.so', 'cde7a1b42c919706aa5f61aba5fc0d75'),
    ('dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so', '31308976206a837f6f5c571992d2b499'),
    ('dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so', 'f70f50f931e9c2cf415cc2728e324f60'),
    ('dumps/camera_2025/usr/usr/kmod/stream.ko', '7191da2f6a78d84f9a3f9eac4680eb2a'),
    ('dumps/camera_2025/usr/setting/DmmConfig.bin', '9f197ff9b300e49ab531b6f9e794253e'),
    ('dumps/firmware/av-cam.bin', 'cdcae9d4fdbf66a33704a4c7564e346d')
]
for path, expected in targets:
    actual = hashlib.md5(open(path, 'rb').read()).hexdigest()
    assert actual == expected, f'Hash mismatch on {path}: {actual} != {expected}'
    print(f'VERIFIED: {path:56s} MD5 = {actual}')
"
```

### 7.2 Documentation Integrity & Link Check
Verify documentation syntax, reference integrity, and anchor resolution across the entire repository:
```powershell
& "D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe" -B research/firmware/check_docs.py
```
- **Acceptance Criterion**: Script exits with code `0`, reporting:
  - `file links: ..., broken targets: 0`
  - `in-page anchors: ..., unmatched: 0`

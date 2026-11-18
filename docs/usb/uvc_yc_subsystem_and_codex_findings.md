> Evidence update, 18 November 2026. Read this synthesis with the [current status](../CURRENT_STATUS.md) and [hook claim review](../../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md). It includes historical layout and throughput assertions whose hardware scope remains unresolved. The live evidence currently establishes timing markers and DMM activity. The latest candidate manifest has hardware_tested=false.

# LiveView YC Subsystem Architecture and Codex Reverse Engineering Synthesis

**Authoritative offline synthesis** consolidating the comprehensive YC video pipeline reverse engineering and hardware evidence from `C:\Users\qn061\Documents\Codex\2026-10-22\chec` into `pmca-re`.

---

## 1. Executive Summary & The Architectural Pivot

### 1.1 "LiveView Is Not Raw"
A critical architectural boundary was established during reverse engineering:
- **Intuition / Common Assumption:** That intercepting the continuous LiveView video stream (`ReadExeLv`, `Utl>DfeAcqSet`, or resizer callbacks) would yield raw Bayer sensor frames.
- **Hardware & Software Reality:** **LiveView is demosaiced, color-processed YC (YCbCr / YUV, 4:2:2 or 4:2:0) video**, NOT sensor Bayer raw data.
- **The Processing Flow:**
  $$\text{Sensor Readout} \longrightarrow \text{DFE} \longrightarrow \text{MovItp (ISP Demosaicing)} \longrightarrow \mathbf{YC\text{ domain}} \longrightarrow \text{SDF / Resizers} \longrightarrow \text{Display / HDMI / UVC}$$
  In movie and LiveView modes, the BIONZ X hardware ISP runs `MovItp` (`calcMovBayerSetParam`, `YC: job_YC_MovItp_CalcParam_Sync`) to demosaic Bayer sensor data directly into the YC domain. All downstream LiveView modules (autoframing, EVF/LCD rendering, HDMI out, UVC gadget driver, `RcResize`, `SdfCh`) operate strictly on **YC framebuffers** (`StdData_YC` / `ImageSizeInfo`), never Bayer pixels.

### 1.2 Separation of Video Deliverables
1. **Uncompressed LiveView Video (YC / YUY2):**
   - High-quality, demosaiced, processed YUV video.
   - Ideal for UVC webcam streaming, external recording, and live preview.
   - Full 1080p YUY2 @ 24/30 fps (95–119 MB/s) and 1280p 3:2 Open Gate YUY2 @ 24 fps (112.5 MB/s) fit natively over USB 3.0 SuperSpeed (~380 MB/s usable) with zero chunking.
2. **Sensor Bayer RAW Video / Frames:**
   - Undemosaiced, true sensor Bayer data with native CFA pattern and bit depth (10/12/14-bit).
   - Exists strictly in:
     - Still capture pipeline: `Wai>GetMmIdtRaw` (Unit `0x20500`), `AllocMem_Raw_Snr` (`0x638d9ff4`), `Capture_MemOpen` (`0x63d8a42a`), `Stg>ReadEndBase` (`0x638f4018`), and `MemAreaMSDebug_RAW` (`0x6390897c`), dumping via endpoint `0x012802f1` to Linux `CameraOnDemandSaver.so`.
     - Burst continuous still drive (up to 11 fps).
     - Direct pre-demosaic DFE hardware interception (requiring tapping DFE buffers before `MovItp` execution).

---

## 2. The Live YC Delivery Pipeline Architecture

### 2.1 Subsystem Overview

```
+-----------------------------------------------------------------------------------+
|                            RTOS PRODUCER (av-cam.bin)                             |
|  1. BIONZ X ISP DMA writes YC frame into DRAM (triple-buffer ring slot N)         |
|  2. RDV Allocator (0x637545ec) allocates Unit 0x295 (handle = H_pixel)            |
|  3. VEF / YUVInfo Builder (0x6374cdd4 / 0x6374ae88) constructs ImageSizeInfo       |
|  4. Inlined out_pin0_send (0x6374c5ba):                                           |
|     Calls VDF Ownership Manager +0x00 (share_yc_mem at 0x63748bec)                |
|     -> Issues DMM Command 2 (allocShare) targeting consumer queue                 |
|  5. Pin::Send (0x6374c5e6) posts 52-byte _MSG_PIN_SEND (opcode 0x0102)            |
+-----------------------------------------------------------------------------------+
                                         |
                                         | 52-byte _MSG_PIN_SEND (sds_unit at +0x2c)
                                         v
+-----------------------------------------------------------------------------------+
|                        LINUX CONSUMER (dataflow / libObj)                         |
|  1. Receives _MSG_PIN_SEND on subscribed queue (e.g. 0x0059000e via YC pin)       |
|  2. Opens SDS handle via DmmCh::open (0x360a5)                                    |
|  3. Maps SSYC container with AvbbcPhycMem; parses C_DataflowInfra_StdData_YC      |
|  4. Reads ImageSizeInfo: unitType = 0x295, unitHandle = H_pixel                    |
|  5. Opens pre-shared H_pixel via DmmCh::open (DMM Command 5)                      |
|     -> SERIAL MATCHES because lease is active and held by producer!               |
|  6. Consumes pixels / submits to SDF resizeRotate (0x369b5) / USB DMA             |
|  7. Closes pixel mapping via DmmCh::close (0x361ad)                               |
|  8. Acknowledges completion: calls DataflowInfraPin::SendComp(0) (0x21fc5)        |
|     -> Emits 44-byte _MSG_PIN_SEND_COMP (opcode 0x8102, status = 0 at +0x28)      |
+-----------------------------------------------------------------------------------+
                                         |
                                         | 44-byte _MSG_PIN_SEND_COMP
                                         v
+-----------------------------------------------------------------------------------+
|                            RTOS PRODUCER (av-cam.bin)                             |
|  1. Receives _MSG_PIN_SEND_COMP in VdfInputReleasePinAndMem::Execute (0x6372808c) |
|  2. Dispatches Ownership Manager +0x04 (free_handle) / +0x18 (free pin unit)     |
|  3. Decrements buffer slot reference count in ISP ring sequencer                  |
|  4. Buffer slot N is now free to be overwritten by new sensor frames              |
+-----------------------------------------------------------------------------------+
```

### 2.2 Wire Protocols & Handshake Messages
Defined in `dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so` and `av-cam.bin`:

#### 1. Frame Delivery: `_MSG_PIN_SEND` (52 Bytes, Opcode `0x0102`)
- `+0x00` (2B): Category ID = `0x1000`
- `+0x02` (2B): Opcode = `0x0102` (`PIN_SEND`)
- `+0x04` (2B): Packet Size = `0x0034` (52 bytes)
- `+0x06` (2B): Protocol Version = `0x0001`
- `+0x08` (16B): Output `PIN_PROPERTY` (`data_type`, `direction`, `index`, `queue_id`)
- `+0x18` (16B): Input `PIN_PROPERTY`
- `+0x28` (4B): Opaque transaction tag
- `+0x2C` (2B): SDS Metadata Unit Handle (`uint16_t`)
- `+0x2E` (2B): Reserved / alignment padding

#### 2. Completion Acknowledgment: `_MSG_PIN_SEND_COMP` (44 Bytes, Opcode `0x8102`)
- `+0x00` (2B): Category ID = `0x1000`
- `+0x02` (2B): Opcode = `0x8102` (`PIN_SEND_COMP`)
- `+0x04` (2B): Packet Size = `0x002c` (44 bytes)
- `+0x06` (2B): Protocol Version = `0x0001`
- `+0x08` (16B): Output `PIN_PROPERTY`
- `+0x18` (16B): Input `PIN_PROPERTY`
- `+0x28` (4B): Completion Status (`int32_t`: `0` = SUCCESS)

#### 3. Frame Release Command: `VdfInputReleasePinAndMem::Execute` (`0x6372808c`)
- Registered on vtable `0x645823f8` with selector **`0x2001/0x050a`**.
- It is **not** identical to `SystemCmdPinSendComp` (`0x64585008`, selector `0x1000/0x8102`), whose Execute routine at `0x63cfaa16` is a two-instruction return-zero leaf.

---

## 3. Dynamic Memory Manager (DMM) & Handle Lifetimes

### 3.1 16-Bit Handle Architecture & Slot Cycling
In `dmm.ko`, 16-bit handles encode both physical slot index and a temporal generation counter:

```
 15  14          10 9                                0
+---+--------------+----------------------------------+
|IDX|  GEN SERIAL  |         SLOT INDEX [9:0]         |
|10 |   (5 bits)   |            (10 bits)             |
+---+--------------+----------------------------------+
```
- **Slot Index** (11 bits, `0..1407`, limit `0x580`):
  $$\text{slot\_index} = (\text{handle} \ \& \ \text{0x3ff}) \ | \ ((\text{handle} \gg 15) \ll 10)$$
- **Generation Serial** (5 bits, range `1..31`):
  $$\text{serial} = (\text{handle} \gg 10) \ \& \ \text{0x1f}$$
- On each allocation (`dmm_unit_ctrl_Alloc` at `.text+0x9bc0`), the slot's serial cycles strictly from 1 to 31 ($1 \to 2 \dots \to 30 \to 31 \to 1$). Serial 0 is reserved.

### 3.2 Root Cause of Native Error `-517` (`0xfdfb`)
In early naive prototypes (Revision 3.3):
- Code scanned memory pools for SDS descriptors (unit type `0x000e0b00`) instead of listening for `_MSG_PIN_SEND` events.
- It found descriptor `0x8cc9` pointing to pixel handle `0x7f24` (slot 804, serial 31).
- By the time `DmmCh::allocShare(0x7f24)` was called, the camera ISP ring sequencer had already finished writing slot 804, retired it, and re-allocated it for a subsequent frame, bumping slot 804's serial from 31 to 1.
- In `dmm.ko` `.text+0x8898`:
  ```armasm
  ldr  r2, [r5, #0xb23] ; read current entry->slot_serial
  cmp  r2, r0           ; compare with handle serial
  movwne r0, #0xfdfb    ; MISMATCH -> RETURN NATIVE -517 (0xfdfb)!
  ```
- **Conclusion:** Polling DRAM pools captures stale / orphaned descriptors. Event-driven pin delivery is mandatory so `Share`/`Open` occurs while the producer's lease is active.

### 3.3 Safe Metadata-Only Cleanup Contract
- SDS metadata units (type `0x000e0b00`) and pixel image units (type `0x295`) have separate entries in `dmm.ko`.
- When pixel `Share` fails (e.g. stale serial `-517`), the consumer holds **0 references** and **0 open counts** on the pixel handle.
- The consumer must execute:
  1. `DmmCh::close(sds_handle)`
  2. `DmmCh::free(sds_handle)`
  3. **Omit** calling `free` on the pixel handle.
- This ensures 0 descriptor leaks, 0 double-frees, and 0 kernel panics. Never call `freeSdsAndYc` on borrowed frames!

---

## 4. Real Source Metadata: The SSYC Container

### 4.1 Header & 12 Observed Categories
Captured authentic descriptor: `outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin` (4096 bytes, SHA256 `9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c`).
Magic: `0x43595353` ("SSYC"), Version: 1, Capacity: 4096 B, Entries: 12.

| Index | Cat ID | Hex | C++ RTTI Class Name | Data Off | Size (B) | Functional & Hardware Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **0** | 0 | `0x00` | `C_DataflowInfra_Entry_ImageSizeInfo` | `0x040` | 64 | Geometry, buffer handle, compression, DMA status |
| **1** | 1 | `0x01` | `C_DataflowInfra_Entry_YcStateInfo` | `0x0a0` | 32 | Colorimetry (BT.709 `0x0005`), scan mode |
| **2** | 2 | `0x02` | `C_DataflowInfra_Entry_ImageOutTimInfo` | `0x0e0` | 32 | **Hardware frame completion sync** (`id = 0x7600`, `createTime = 0x1979`) |
| **3** | 6 | `0x06` | `C_DataflowInfra_Entry_MovieQualityInfo` | `0x120` | 224 | Gyro telemetry, EIS vectors, exposure compensation |
| **4** | 4 | `0x04` | `C_DataflowInfra_Entry_FaceInfo` | `0x220` | 256 | Face detection & Eye AF bounding boxes |
| **5** | 5 | `0x05` | `C_DataflowInfra_Entry_CameraInfo` | `0x340` | 800 | Lens telemetry, aperture, shutter speed, ISO gain |
| **6** | 18 | `0x12` | `C_DataflowInfra_Entry_FocusInfo` | `0x680` | 256 | Autofocus tracking window coordinates |
| **7** | 12 | `0x0c` | `C_DataflowInfra_Entry_DisplayInfo` | `0x7a0` | 32 | EVF / LCD on-screen display crop and orientation |
| **8** | 16 | `0x10` | `C_DataflowInfra_Entry_LineoutRecTriggerInfo`| `0x7e0` | 32 | HDMI / external recorder trigger state |
| **9** | 10 | `0x0a` | `C_DataflowInfra_Entry_TcubInfo` | `0x820` | 92 | **Wall-clock RTC synchronization** (BCD timestamp) |
| **10** | 22 | `0x16` | `C_DataflowInfra_Entry_RemoteInfo` | `0x89c` | 760 | PC Remote / Imaging Edge tethering coordinates |
| **11** | 23 | `0x17` | `C_DataflowInfra_Entry_IactiveCutOutInfo`| `0xbb4` | 28 | Intelligent Active SteadyShot EIS cutout offset |

### 4.2 Category 0 (`ImageSizeInfo`) Critical Flags
- **`data_transfer` (`+0x2e`):** Set to **`1`** by RTOS upon hardware DMA completion. Early test code falsely filtered out `data_transfer != 0`. Consumers must accept `data_transfer == 1`.
- **`yc_compress` (`+0x2f`):** Mandatory **`1`** for 1080p sensor frames in DMM unit `0x295` ($1920\times1080\times1 = 2,073,600$ bytes). 1 byte/pixel indicates VPH hardware compression.
- **`strip_width` (`+0x32`):** `64` (pixels per DMA strip).

---

## 5. Scaler/Decompressor/Formatter (SDF) Hardware Contract

### 5.1 Architecture & IPC Interface
The BIONZ X hardware scaler/decompressor is controlled by userland via `OBJAVBBCBASECLASS::SdfCh` (`libBizFw.so` `0x36680`):
- 68-byte command packet (`0x2000/0x0003` `RESIZE_ROTATE`) submitted to RTOS queue `0x00560010`.
- Two-stage IPC: 16-byte ACK token, followed by 24-byte CMP completion token.
- **Critical finding:** SDK return 0 can accompany an ACK rejection or non-zero CMP payload. The caller must inspect `ack_param[8]` and `cmp_param[8]`.

### 5.2 1-Pass Decompress and Downscale
`WrapSrotateStart` (`0x63cc8a7c`) accepts a 1080p compressed input (`yc_compress = 1`, 2,073,600 bytes) and outputs an uncompressed YUY2 destination (`yc_compress = 0`, 614,400 bytes) in a **single hardware DMA pass**.

---

## 6. Physical Hardware Evolution in Codex Workspace (`2026-10-22/chec`)

Between 22 October and 31 October 2026, progressive iterations were tested on the physical ZV-E10:

```
[Rev 2.4p]  Permanent synthetic color bars / counters in OBS / FFmpeg over USB 2.0
     |
[Rev 3.3]  DMM pool scanning attempted -> Native -517 serial mismatch (orphaned descriptor)
     |
[Rev 3.4]  Event-driven VDF delivery connected; shutdown crash when USB Streaming turned off
     |
[Rev 3.9]  First recognizable LIVE CAMERA VIDEO in OBS (~1 fps)! Stalled on no-image frames
     |
[Rev 4.0]  No-image handling verified; unpaced benchmark; removed all timed sleeps
     |
[Rev 4.1]  Attempted direct 1080p uncompressed YUY2; failed due to DMM staging pool alias
     |
[Rev 4.2]  Chunked 1080p YUY2 (7 chunks/frame) at 5 fps over USB 2.0; SDF CMP 11 entry error
     |
[USB 3.0]  DWC3 controller discovered! 380 MB/s bandwidth eliminates USB 2.0 chunking entirely!
```

### Key Hardware Test Highlights:
- **Revision 3.9:** Proved that live sensor frames can be captured, decompressed via SDF, and displayed in OBS on the host PC!
- **Revision 4.0:** Discovered the "no-image" metadata frame (`ImageAttach=0`, `handle=0`). Sony RTOS produces these during preview state transitions. Rev 4.0 cleanly acknowledged and freed them without stalling the pipeline.
- **Revision 4.2:** Proved that under USB 2.0, streaming full 1080p uncompressed YUY2 (4.15 MB/frame) required complex 7-chunk segmentation (six 614,400 B + one 460,800 B chunks) via private `frame_event.size` flags (bit 31 = more chunks, bit 30 = FID, bit 29 = tagged chunk API).

---

## 7. The USB 3.0 Breakthrough: Eliminating Chunking

### 7.1 Bandwidth & Delivery Comparison

| Transport Mode | Frame Format | Resolution | Framerate | Required Bandwidth | USB 2.0 (40 MB/s) Feasibility | USB 3.0 (380 MB/s) Feasibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **VGA YUY2** | Uncompressed YUY2 | $640\times480$ | 30 fps | 18.43 MB/s | Compatible (Rev 3.9) | Compatible (4.8% bus) |
| **1080p YUY2** | Chunked YUY2 (7 chunks) | $1920\times1080$ | 5 fps | 20.74 MB/s | Compatible (Rev 4.2) | Obsolete |
| **1080p YUY2** | Uncompressed YUY2 | $1920\times1080$ | 24 fps | 99.53 MB/s | **Impossible** (>2.5x bus) | **Native Pass** (26.2% bus) |
| **1080p YUY2** | Uncompressed YUY2 | $1920\times1080$ | 30 fps | 124.42 MB/s | **Impossible** (>3.1x bus) | **Native Pass** (32.7% bus) |
| **1280p OpenGate** | Uncompressed YUY2 | $1920\times1280$ | 24 fps | 117.96 MB/s | **Impossible** (>2.9x bus) | **Native Pass** (31.0% bus) |

### 7.2 Native SuperSpeed Infrastructure in Firmware
- **Hardware Controller:** Synopsys DesignWare USB 3.0 (`dwc3-gadget` at `0x60108000` in `vmlinux.bin`).
- **Negotiated Speed Reporting:** Kernel driver `usb_otgcore` ioctl `0x8001e30b` reports `3` for SuperSpeed.
- **Speed Mapping:** `libInfraUsbCmn.so` table `0x1280c` maps speed `3` to `CUSB_SPEED_SUPER` (`0x2`).
- **SuperSpeed Descriptors:** Set 3 at `0x1cca0` provides Bulk IN Endpoint `0x81` with `wMaxPacketSize = 1024` and `bMaxBurst = 2` at `0x1cce8`.

With USB 3.0 SuperSpeed active, the entire chunking complexity of Rev 4.2 is eliminated: full 1080p and 1280p Open Gate YUY2 frames stream directly in standard single-buffer UVC frames at $\ge 24\text{ fps}$.

---

## 8. Cross-Reference Index

- **Source Code Decoders & Protocol Implementations:**
  - `research/firmware/raw_frame_source/verified_yc/sony_yc_metadata.h/.c`: 31-field SSYC decoder.
  - `research/firmware/raw_frame_source/verified_yc/sony_yc_pin_wire.h/.c`: 52-byte SEND and 44-byte COMPLETE framing.
  - `research/firmware/raw_frame_source/verified_yc/sony_yc_sds.h/.c`: SSYC container navigation.
- **Verification Scripts:**
  - `research/firmware/raw_frame_source/verified_yc/verify_pin_protocol.py`
  - `research/firmware/raw_frame_source/verified_yc/verify_individual_getters.py`
  - `research/firmware/raw_frame_source/verified_yc/verify_metadata_decoder.py`
  - `research/firmware/raw_frame_source/verified_yc/verify_preview_geometry.py`
  - `research/firmware/raw_frame_source/verified_yc/verify_preview_update.py`
- **Related Topic Documents:**
  - [04-messaging.md](../reference/04-messaging.md): IPC messaging and OSAL queues.
  - [05-formats.md](../reference/05-formats.md): Container formats and metadata.
  - [08-camera-interfaces.md](../reference/08-camera-interfaces.md): USB modes and camera interfaces.
  - [uvc_yc_source_recovery_20261025.md](uvc_yc_source_recovery_20261025.md): Initial YC metadata recovery.
  - [uvc_yc_live_source_20261026.md](uvc_yc_live_source_20261026.md): Preview geometry tables and update handlers.
  - [90-session/YC_SUBSYSTEM_RESEARCH_PLAN.md](../archive/sessions/YC_SUBSYSTEM_RESEARCH_PLAN.md): Detailed 5-part subsystem plan.
  - [90-session/HANDOFF.md](../archive/sessions/HANDOFF.md): Master chronological session handoff ledger.

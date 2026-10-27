# YUY2 USB Diagnostics & Architecture Handoff — 24 October 2026

**Physical recovery status:** 34 camera files, 7,225,403 bytes, each matching its on-camera MD5. Raw evidence files reside in `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\usb-debug-20261024-01\camera`; transfer verification is recorded in `transfer-result.json` and `recovery-summary.json`.

---

## 1. Sequence and Measured Results: Strict Separation of Observations

To prevent conflation of experimental results, the observations from the 22 October and 24 October sessions must be strictly distinguished:

### 1.1 22 October 2026: Mode Negotiation & Zero-Frame Capture Timeout
- **Test Objective:** Validate synthetic 640×480 YUY2 at 10 fps via the in-memory RAM prototype (`yuy2_640.so`).
- **Observed Behavior:**
  - The camera remained fully responsive and enumerated normally as a USB Video Class (UVC) device on Windows.
  - FFmpeg successfully probed and recognized DirectShow media format `rawvideo` / `yuyv422` at 640×480, 10 fps (`outputs/yuy2-640/evidence/ffmpeg-formats-01.log`).
  - Upon issuing a 10-frame capture command (`ffmpeg-capture-01.log`), the host application waited 25 seconds for video bulk transfers.
  - **Result:** Exact 25-second timeout with **zero frames (0 bytes) received**.
  - **Mechanism (Now Established):** The prototype failed source allocation, latched `init_error = 21`, and entered an infinite 10 Hz error loop where return code 4 was discarded by the worker thread. No start completion event was ever dispatched to the state machine or host.

### 1.2 24 October 2026: Streaming Transition, USB Disappearance & Unresponsive Controls
- **Test Objective:** Capture high-resolution binary application logs (`app-sequential.log`) across the service-mode to USB streaming transition to isolate the allocation and streaming failure.
- **Observed Behavior:**
  - Sequential capture for subsystem 131 was armed into `/log/usb_debug_20261024_01/app-sequential.log`.
  - Log file growth was verified from 504,783 bytes (5048.062s uptime) to 508,944 bytes (5049.379s uptime) while navigating service mode.
  - The user manually switched the camera from Service Mode to USB Streaming.
  - **Result:** Windows detected **no Sony USB device**; FFmpeg reported that the `ZV-E10` DirectShow device was not found (`outputs/usb-debug-20261024-01/ffmpeg-devices.log`). This session **never reached a frame-capture attempt**. It was **not** a 25-second zero-frame timeout.
  - Physical camera controls and dial buttons became completely unresponsive. The camera would not return to service mode or respond to commands over USB, necessitating a manual battery/power restart.

### 1.3 Post-Restart Artifact Scope (`*-after.*` Snapshots)
- Following manual power restart, service access was restored, and 34 diagnostic files were extracted and checksum-verified.
- **Uptime Baseline:** System uptime reset from **5,049.03 seconds** before the attempt to **53.57 seconds** after restart.
- **RAM State:** The RAM-injected YUY2 prototype module was wiped from memory; `/proc/157/maps` showed the module absent.
- **Scope Constraint:** All files designated `*-after.*` (e.g. `dmm-after.txt`, `kmod-after.txt`, `proc-maps-after.txt`, `threads-after.txt`) represent **post-restart snapshots** taken at 53.57s uptime. They do **not** represent the live hang state or active allocations at the moment of the crash.
- **Persistent Firmware State:** RTOS hash (`90096db2c76148f4f9db5d104e5c608c`) and streaming library hash (`19461091c07aa6900829defb0060fcd6`) remained intact; common descriptor library reverted to stock (`31308976206a837f6f5c571992d2b499`).

---

## 2. Requirement 1 (R1): Sony Application-Log Binary Framing & Capture Recovery

Disassembly of `dumps/camera_2025/usr/usr/kmod/osal_ulogio.ko` (at `__ulogio_seqcap_thread_entry` VA `0x29b0` and `ulogio_lbm_record` VA `0x1b98`) and `dumps/camera_2025/usr/usr/bin/ulogio.elf` establishes the exact file framing, timestamp mathematics, and sequential record structure of `app-sequential.log` (1,936,183 bytes).

### 2.1 The ulogio On-Disk Record Format
The sequential logging kernel thread extracts records directly from kernel ring buffers and flushes them to disk via `ulogio_file_write()` with `O_WRONLY | O_CREAT | O_TRUNC`. The file contains **no overarching container header, no file magic, and no trailing checksums**.

Every record begins immediately with a fixed 16-byte packed header:

```c
#pragma pack(push, 1)
typedef struct ulogio_record_hdr {
    uint32_t payload_len;   /* [0x00] Byte length of record payload (0 to 28 bytes) */
    uint16_t subsys_id;     /* [0x04] OSAL Subsystem ID (0x0083 = 131: Sony APP)    */
    uint16_t area_id;       /* [0x06] Component / Channel ID (1 to 14)              */
    uint64_t timestamp_us;  /* [0x08] Monotonic microsecond clock since boot       */
    uint8_t  payload[];     /* [0x10] Variable-length binary payload bytes          */
} ulogio_record_hdr_t;
#pragma pack(pop)
```

- **Framing Rule:** Record length on disk is strictly `sizeof(ulogio_record_hdr_t) + payload_len` (`16 + payload_len` bytes).
- **Alignment:** Zero inter-record padding bytes, zero word-alignment padding, and zero record delimiters. The subsequent record begins strictly at `offset + 16 + payload_len`.

### 2.2 Monotonic Microsecond Timestamp Mathematics
In `osal_ulogio.ko` function `ulogio_print` (VA `0x145c`–`0x1524`):
- The 64-bit integer timestamp field is multiplied by fixed-point reciprocal constant $M = \text{0x431bde82d7b634db}$ ($4,835,703,278,458,516,699$) and shifted right by 82 bits:
  $$\text{Seconds} = \left\lfloor \frac{T \times 4,835,703,278,458,516,699}{2^{82}} \right\rfloor = \left\lfloor \frac{T}{1,000,000} \right\rfloor$$
- Microseconds are derived by `mls r0, r3, ip, r0`:
  $$\text{Microseconds} = T - (\text{Seconds} \times 1,000,000)$$
- **Conclusion:** `timestamp_us` is an exact, monotonic 64-bit microsecond counter starting from hardware boot.

### 2.3 Record Population & Subsystem 131 Inventory
Programmatic parsing of the entire 1,936,183-byte `app-sequential.log` using struct format `<IHHQ` parses **exactly 61,997 records** with **100.000% completeness**:
- **Total file size:** 1,936,183 bytes.
- **Parsed byte count:** 1,936,183 bytes (**0 slack bytes, 0 unparsed bytes, 0 corrupted headers**).
- **Subsystems present:** **100% Subsystem 131 (`0x0083`)**. Zero records from other subsystems were captured.
- **Component ID (Area) Distribution:**
  - CID 1 (14 B payload): 551 records (UI and dispatch actions)
  - CID 2 (7 B payload): 627 records
  - CID 3 (12 B payload): 1,863 records (4 records with 0 B)
  - CID 4 (18 B payload): 17,466 records (Streaming worker state & telemetry)
  - CID 5 (20 B payload): 390 records (`DataflowInfraLog` errors)
  - CID 6 (20 B payload): 230 records (`DataflowInfraLog` errors)
  - CID 7 (6 B payload): 2,230 records
  - CID 8 (21 B payload): 4,577 records (1 record with 0 B)
  - CID 9 (16 B payload): 338 records
  - CID 10 (28 B payload): 7,177 records (ASCII tags: `camera Model loaded.`, `ERROR`, `SetPJT`, `Lock`, `modelID`)
  - CID 11 (12 B payload): 1,874 records (3 records with 0 B)
  - CID 12 (28 B payload): 2,365 records (Performance markers: `[PERF]ISO`)
  - CID 14 (8 B payload): 22,309 records (Two 32-bit state words)

### 2.4 Dual-Phase Structure of `app-sequential.log`
The file exhibits two distinct operational phases:
1. **Phase 1: Initial In-Memory Ring Buffer Dump (Offsets `0x000000` to `0x079f0e`, Bytes 0 to 499,470, Records 0 to 15,364)**:
   - When command `lstart 131` was executed, `osal_ulogio.ko` sequentially flushed the 13 circular buffers residing in RAM across separate memory blocks.
   - Starting timestamps reflect when each circular buffer previously wrapped in memory (e.g., CID 5 starts at 2,251.309s; CID 14 starts at 5,026.613s).
   - All 13 ring buffers end synchronously at uptime ~5047.4s.
2. **Phase 2: Live Sequential Chronological Event Streaming (Offsets `0x079f0e` to `0x1d8b1f`, Bytes 499,470 to 1,936,183, Records 15,365 to 61,997)**:
   - Beginning at timestamp **5047.881s**, all 13 components are interleaved chronologically in real time as events occur.

### 2.5 Baseline Alignment and Post-Service Mode Streaming Capture
Verification of known diagnostics milestones against exact byte offsets in `app-sequential.log`:
- **Baseline Offset 504,783 (`0x07b3cf`)**: Aligns with record 15,450 (CID 4, timestamp `5,048,062,345 us` = **5048.062s uptime**), captured while navigating service mode.
- **Baseline Offset 508,944 (`0x07c410`)**: Aligns with record 15,569 (CID 4, timestamp `5,049,378,556 us` = **5049.379s uptime**, growth of exactly 4,161 bytes), recording the exit from service mode.
- **Post-Service Mode Streaming Span:**
  - The log did not truncate upon leaving service mode. It recorded an additional **46,428 records (1,427,239 bytes)**.
  - Final record 61,996 ends at byte 1,936,183 at timestamp `5,224,050,061 us` = **5224.050s uptime**.
  - **Capture Duration Post-Service Mode:** $5224.050 - 5049.379 = \mathbf{174.672\text{ seconds}}$ (~2 minutes 55 seconds).

### 2.6 Critical Event Markers and Failure Sequence in app-sequential.log
Between 5049.378s and 5224.050s, the log captures the complete streaming transition and lockup progression:
1. **Service Mode Exit (5049.378s, Records 15569–15571)**: Records state transition payload words `00a3000100002200fff6...`.
2. **Model Load & Twin Errors (5064.719s – 5064.721s, Offsets `0x0baa5e` – `0x0bad60`)**:
   - Record 23286 (5064.7198s, offset `0x0baa5e`): CID 10 string: `camera Model loaded.`
   - Record 23293 (5064.7200s, offset `0x0bab6a`): CID 10 string: `ActionSetStatusChang`
   - **Record 23305 (5064.7214s, offset `0x0bad34`)**: CID 10 string: `ERROR` (payload: `06000e027700000008000000...4552524f52000000`)
   - **Record 23306 (5064.7214s, offset `0x0bad60`)**: CID 10 string: `ERROR` (payload: `06000e026401000000000000...4552524f52000000`)
3. **Pipeline Reconfiguration & Display Mute (5212s – 5220s)**:
   - Records 59341–59458 (5212.741s): Zoom/Liveview parameters (`ZmLvSp1` – `ZmLvMSp8`).
   - Records 59393–59435 (5212.752s): Frame geometry (`ViewFrm1`, `ViewFrm2`, `ViewReso`, `DispFFok`).
   - Records 61308–61348 (5219.919s): Video mute commands (`ActionSetYuvUiMute`, `YUV_RELD`, `ActionSetOneTouchPla`).
4. **Power Interruption (5224.050s)**: Log terminates at record 61,996 when manual power-cycle interrupted execution.

---

## 3. Requirement 2 (R2): Root-Cause Analysis of `VideoEsManager::alloc_video_memory` Error 4

In the preserved prototype runtime log (`prototype-runtime-before.log` / `after.log`), lines 3–4 recorded:
```text
YUY2 ALLOC_RESULT 00000004 00000000 00000000
YUY2 SOURCE_FAILED 00000015 00000000 00000000
```
Full binary disassembly of `libInfraStreamingUsb.so`, `dmm.ko`, and configuration analysis of `DmmConfig.bin` isolates the complete execution chain.

### 3.1 Client-Side Control Flow & Error 4 Synthesis (VA 0x94f4 – 0x9572)
In `dumps/camera_2025/usr/usr/lib/libInfraStreamingUsb.so`, symbol `VideoEsManager::alloc_video_memory(unsigned int unit_type, unsigned short *handle, unsigned int *phys, unsigned int *cap)`:
- **VA `0x9506`–`0x951a`:** Prepares a 24-byte IPC request packet `req`:
  - `req[0..1] = 1` (Command 1: `dmm_ctrl_AllocUnitNewHdlr`)
  - `req[4..7] = unit_type` (`0x50f`)
  - `req[12..15] = 0xffffffff`
  - `req[22..23] = 1` (Open mode flag)
- **VA `0x9528`:** Calls `VideoEsManager::send_recv_msg(0x0061003c, req, 24, resp, 24)`.
- **VA `0x952e`:** Evaluates IPC transport return code:
  - If transport fails ($r_0 \neq 0$), branches to VA `0x9530`, logs event `0x1d5` (Subsystem `0x92`), and returns `4`.
  - In our run, transport succeeded ($r_0 == 0$), branching to VA `0x953a`.
- **VA `0x953a`–`0x9556` (The Fatal Branch):**
  ```arm
  0x953a: ldrsh.w r0, [r7, #2]    ; r0 = (int16_t) resp[2..3] (Server Status Code)
  0x953e: cbz     r0, #0x955a     ; If resp[2..3] == 0 (SUCCESS), branch to unpack
  0x9540: movs    r0, #0x92       ; Subsystem 0x92
  0x9542: movs    r1, #0x10       ; Priority ERROR
  0x9544: movw    r2, #0x1db      ; Event 0x1db (475: DMM_SERVER_ERR)
  0x9548: bl      #0x8a64         ; Log error
  0x954c: ldrh    r1, [r7, #2]    ; r1 = raw server status code
  0x954e: movs    r0, #0x93       ; Log secondary code
  0x9550: mov     r2, r6
  0x9552: bl      #0x8a64
  0x9556: movs    r0, #4          ; *** SYNTHETIC ERROR CODE 4 RETURNED ***
  0x9558: b       #0x956c
  ```
- **Finding:** Return code `4` is a **synthetic client error code** generated at instruction VA `0x9556`. It is executed when the DMM kernel module returns any non-zero value in response status field `resp[2..3]`.

### 3.2 DMM Configuration and Semantic Identity of Unit Type 0x50f
Inspection of `dumps/camera_2025/usr/setting/DmmConfig.bin`:
- **Unit Table Entries (File offsets `0x13094`–`0x130c4`)**:
  - `0x13094`: Unit Type `0x050e` $\rightarrow$ Extent ID `0x0589`
  - `0x130a4`: Unit Type `0x050f` $\rightarrow$ Extent ID `0x058a`
  - `0x130b4`: Unit Type `0x0510` $\rightarrow$ Extent ID `0x058b`
- **Extent Table Entries (File offsets `0x1da4`–`0x1de0`)**:
  - `Extent 0x0589` (Unit `0x50e`): Size `0x001c2000` = **1,843,200 bytes (1,800 KB = 1.758 MiB)**, Pool `0x0c`.
  - `Extent 0x058a` (Unit `0x50f`): Size `0x00001800` = **6,144 bytes (6.0 KB)**, Pool `0x0c`.
  - `Extent 0x058b` (Unit `0x510`): Size `0x00018000` = **98,304 bytes (96.0 KB)**, Pool `0x0b`.

### 3.3 Kernel-Side Rejection in dmm.ko: Extent Collision & Ownership Mismatch
Inspection of `dumps/camera_2025/usr/usr/kmod/dmm.ko` (at `dmm_ctrl_SyncMsg` VA `0x6e74` and `dmm_ctrl_AllocUnitNewHdlr` VA `0x645c`):
- When the composite USB gadget initializes in streaming mode, both USB Audio (`usbg_audio.ko`) and USB Video (`usbg_video.ko`) are configured.
- In `usbg_audio.ko` function `usbg_audio_core_open` (VA `0x126c`):
  ```arm
  0x126c: movw r0, #0x2db     ; Owner ID 0x2db = usbg_audio
  0x1274: movw r1, #0x50f     ; Unit Type 0x50f
  0x1280: bl   usb_sync_alloc_phys_buffer
  ```
  `usbg_audio.ko` opens first and allocates unit `0x50f` (Extent `0x58a`), setting its reference count to 1 and locking it as the **6,144-byte USB Audio (UAC) isochronous PCM FIFO buffer**.
- When prototype `yuy2_640.c` calls `alloc_video_memory(0x50f)` from `VideoEsManager` (Subsystem `0x2d9`):
  1. `dmm_unit_ctrl_Alloc` in `dmm.ko` looks up unit `0x50f` (Extent `0x58a`).
  2. Because Extent `0x58a` is a single-instance extent already allocated by `usbg_audio.ko`, line VA `0xa880` (`cmp r3, #0; bne #0xa920`) detects that the extent is busy, triggering error **`-0x201` (`0xfdff`: extent collision / resource in use)**.
  3. Furthermore, rule check at VA `0xa864` (`tst r1, r3`) restricts Extent `0x58a` to audio owner `0x2db`, rejecting caller `0x2d9` with rule mismatch **`-0x6401`**.
  4. At VA `0x6698`, `dmm_ctrl_AllocUnitNewHdlr` translates these internal error codes via helper `0x5294` into status code **`-1` (`0xffff`)**, storing it into `resp[2..3]`.
  5. `VideoEsManager::alloc_video_memory` reads `resp[2..3] == -1 != 0`, logs `0x1db`, and returns synthetic error code **`4`**.

### 3.4 Authentic Stock Pipeline vs. Prototype Architectural Divergence
- **Stock Driver `usbg_video.ko`**: Function `usbg_video_core_open` (VA `0x1b10`) calls:
  `usb_sync_alloc_phys_buffer(owner=0x2da, unit_type=0x50e, &handle, &phys, &cap)`
  allocating the legitimate **1,843,200-byte USB Video double staging buffer** ($2 \times 921,600$ bytes).
- **Stock Daemon `VideoEsManager`**: Does **NOT** call `alloc_video_memory` to allocate frame data. In stock firmware, `VideoEsManager::get_video_image()` (VA `0x90c0`) sends asynchronous command `0x2009` over route `0x0167046a` to the hardware RTOS encoder. The hardware encoder writes frames into its own managed memory pool and delivers ready handles to `VideoEsManager::set_video_data_to_driver()`.
- **Prototype `yuy2_640.c` Error**: The prototype mistakenly assumed `alloc_video_memory` was a general frame allocator and requested unit `0x50f`, which is a 6 KB audio buffer owned by `usbg_audio.ko`.

### 3.5 Categorical Differentiation of Failure Modes
- **(a) IPC Transport Failure:** **Negative**. `send_recv_msg` cleanly dispatched and received messages via queue `0x0061003c`.
- **(b) Raw RTOS Kernel Error:** **Negative**. Return code 4 is created in user space at `libInfraStreamingUsb.so` VA `0x9556`.
- **(c) Memory Pool Exhaustion:** **Negative**. Pool `0x0c` has ample capacity (1.8 MB staging buffer was intact).
- **(d) Unit Type Conflict & Rule Rejection:** **Affirmative & Established**. Unit type `0x50f` is an audio buffer with capacity 6,144 bytes, already owned by `usbg_audio.ko` (Owner `0x2db`).

---

## 4. Requirement 3 (R3): Streaming Lifecycle Gaps and Bounded Recovery Architecture

Analysis of `VideoEsManager::video_thread` (VA `0x9700`), `judge_notify_start_stop_evt` (VA `0x9578`), and `StateMachine` (VA `0x8800`–`0x8956`) reveals the exact causal mechanism behind the 22 October 25-second timeout and 24 October system lockup.

### 4.1 Stock Worker Thread Return Code Discard (VA 0x9700)
In `dumps/camera_2025/usr/usr/lib/libInfraStreamingUsb.so`, `VideoEsManager::video_thread(void*)`:
```arm
0x973c: ldr  r0, [r4, #0x18]     ; r0 = this->uvc_scalar_sem
0x973e: blx  #0x6328             ; UFW::Sem::Lock(uvc_scalar_sem)
0x9742: mov  r0, r4              ; r0 = this
0x9744: mov  r1, r4              ; r1 = info
0x9746: blx  #0x6340             ; VideoEsManager::set_video_data_to_driver(this)
0x974a: ldr  r0, [r4, #0x18]     ; *** FATAL: r0 (return code) overwritten with semaphore! ***
0x974c: blx  #0x60dc             ; UFW::Sem::Unlock(uvc_scalar_sem)
0x9750: b    #0x9718             ; Unconditional loop back to header!
```
- At VA `0x9746`, `set_video_data_to_driver` (or any replacement hook) returns its error code in `r0`.
- At VA `0x974a`, `r0` is immediately clobbered by loading `uvc_scalar_sem`.
- **Fatal Defect:** The worker thread **unconditionally discards the producer return code**. It performs zero error handling and loops continuously at 10 Hz as long as `m_state == 2`.

### 4.2 Start Notifier Gate and Error Silencing (VA 0x9578)
In `VideoEsManager::judge_notify_start_stop_evt(VideoEsManager::VIDEO_MGR_INFO*, bool)`:
- **Success Branch (VA `0x959a`–`0x95d6`):**
  - Increments `info->consecutive_count` at VA `0x95a6`.
  - At VA `0x95a8`: `cmp r3, #0xa`.
  - **Requirement:** Streaming start is **only declared after 10 consecutive successful frames**. Only then does VA `0x95ae` call `SendEvtStreamingMain(9)` (`MSGID_START_VIDEO_DRIVER_CMP`) and set `info->is_started = 1`.
- **Failure Branch (VA `0x95d8`–`0x9614`):**
  - At VA `0x95d8`: `cmp r6, #1; bne #0x9614`.
  - **Fatal Defect:** Instruction `bne #0x9614` verifies that `is_started == 1`. During startup, `is_started` is `0`. Consequently, **all errors occurring before 10 successful frames are submitted are silently discarded**. No event is dispatched to `StreamingMain`.

### 4.3 StateMachine Asynchronous Deadlock (VA 0x8800, VA 0x894d)
In `StateMachine` (`libInfraStreamingUsb.so`):
- When host initiates streaming, `Ready::funcConnectCmd` (VA `0x7aa8`) saves caller reply token in `[StateMachine + 0x18]` (`m_asyncReplyEndpoint`) and transitions to state `Starting`.
- In `Starting::funcStartVideoDriverCmp` (VA `0x8800`):
  Dispatches `sendCompMsg(m_asyncReplyEndpoint, {0x2003, 0})` to notify caller of success and transitions to `Started`.
- In `Starting::funcStopVideoDriverCmp` (VA `0x894d`):
  An empty stub that logs a message, returns 0, does **not** notify `m_asyncReplyEndpoint`, and does **not** transition state.
- **Deadlock Result:** When allocation fails during startup, Event 9 is never dispatched, `m_asyncReplyEndpoint` never receives completion `0x2003`, and `StateMachine` is permanently trapped in `Starting`. Upper camera management remains blocked on `0x2003`, causing host timeouts and deadlocking camera UI controls.

### 4.4 Prototype 1-Shot Latching Deficiencies (`yuy2_640.c`)
In `yuy2_640.c` (lines 223–231):
- `attempted = 1` is latched permanently on the first execution. When `prepare_source()` returns error 21, `init_error = 21` is latched.
- Subsequent iterations take line 228 (`if(init_error || !pixels...){usleep(100000); return 4;}`).
- The prototype never retries, never calls `judge()`, releases no resources, and returns 4 in a tight loop.

### 4.5 Bounded Recovery & Cleanup Architecture Specification
To guarantee clean error termination without deadlocks:
1. **Bounded Retry Policy (Producer Layer):**
   - Configured with `MAX_INIT_RETRIES = 5` and `RETRY_DELAY_US = 150000` (bounded 750 ms retry window).
   - Absorbs transient timing jitter during USB interface switching.
2. **Resource Cleanup Contract (`cleanup_source`):**
   - On retry exhaustion or error: invoke `munmap()` on any active memory mapping and call `dealloc_unit(self, &handle)`.
3. **Semaphore Contract Adherence:**
   - Adhere to `uvc_status_sem` (`[self + 0x10]`): acquire lock, set `VideoEsManager::m_state = 1` (PAUSED), and release lock. This halts `video_thread` cleanly without spinning.
4. **Active StateMachine Error Unwinding:**
   - If `StateMachine::m_currState` is `Starting` and `m_asyncReplyEndpoint != 0`:
     - Dispatch `sendCompMsg(m_asyncReplyEndpoint, {0x2003, ERR_ALLOC_FAILED})`.
     - Clear `[StateMachine + 0x18] = 0`.
     - Transition `StateMachine` back to `Ready` (`[StateMachine + 0x08]`).

---

## 5. Bounded Next-Step Test Protocol for Future Live Testing

When live testing resumes, execution must adhere to the following sequenced, verifiable protocol:

### Step 1: Pre-Flight Hardware Link & Descriptor Verification
1. Verify camera physical connection via `research/device/zve10_retry.py "ls -l /usr/lib"`.
2. Inspect on-disk binary hashes:
   - Verify `libInfraUsbCmn.so` has valid descriptor patch bytes and matching MD5.
   - Verify `libInfraStreamingUsb.so` and `av-cam.bin` hashes match expected candidates.
3. Confirm that USB high-speed bulk endpoints (512-byte packets) and interface descriptors are cleanly registered.

### Step 2: Staging Memory & Buffer Geometry Verification
1. Query `dmm` and `usbg_video.ko` staging buffers:
   - Confirm driver staging unit `0x50e` (Extent `0x589`) is allocated with capacity $\ge 1,843,200$ bytes.
   - Confirm each double-buffer half ($\ge 921,600$ bytes) exceeds required 640×480 YUY2 frame size ($614,400 + 12 = 614,412$ bytes).

### Step 3: Legitimate Video Frame Memory Acquisition
1. **Prohibition:** Under no circumstances request unit type `0x50f` for video data.
2. **Acquisition Route:**
   - Route A (Synthetic Test): Allocate a dedicated, legitimate video frame buffer or utilize pre-allocated staging memory without colliding with audio extents.
   - Route B (Hardware YUV): Intercept the hardware encoder pipeline or route completed DMM unit handles from the camera ISP.

### Step 4: Decoupled Audio and Video Gadget Initialization
1. Ensure composite USB configuration properly isolates USB Audio Class (`usbg_audio.ko`, unit `0x50f`, owner `0x2db`) from USB Video Class (`usbg_video.ko`, unit `0x50e`, owner `0x2da`).
2. Verify that audio driver buffer acquisition does not block video streaming startup.

### Step 5: Controlled Live Stream Execution & Telemetry Capture
1. Arm sequential logging for subsystem 131 with bounded capture size.
2. Launch host capture with a strictly bounded FFmpeg invocation (e.g. timeout 10 seconds, max 10 frames).
3. If frames do not arrive within 3 seconds, trigger bounded producer unwinding, transition `m_state = 1`, and notify `m_asyncReplyEndpoint` with error code to prevent camera control freeze.

---

## 6. Verification and Reproducibility Matrix

All findings documented above are verified against genuine repository binaries and data:

| Claim | Verification Command | Expected Output |
|---|---|---|
| R1: Record Framing & Integrity | `python -B -c "import struct; data=open(r'C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\usb-debug-20261024-01\camera\app-sequential.log','rb').read(); pos, cnt = 0, 0; while pos < len(data): plen, sid, aid, ts = struct.unpack('<IHHQ', data[pos:pos+16]); pos += 16 + plen; cnt += 1; assert pos == 1936183 and cnt == 61997; print('VERIFIED')"` | `VERIFIED` |
| R1: Uptime & Timestamps | Record 15,450 (offset 504,783) = 5048.062s; Record 15,569 (offset 508,944) = 5049.379s; Record 61,996 = 5224.050s | Verified exact to microsecond |
| R2: Error 4 Synthesis | Capstone disassembly of `libInfraStreamingUsb.so` VA `0x94f4`–`0x9572`: `ldrsh.w r0, [r7, #2]`, `movs r0, #4` at `0x9556` | Verified exact instructions |
| R2: Unit 0x50f is Audio Extent 0x58a | `struct.unpack_from('<4I', open('dumps/camera_2025/usr/setting/DmmConfig.bin','rb').read(), 0x130a4)` | Extent `0x58a`, size 6,144 bytes |
| R2: usbg_audio.ko Ownership | Disassembly of `usbg_audio_core_open` VA `0x126c`: `movw r0, #0x2db`, `movw r1, #0x50f` | Verified exact instructions |
| R3: Worker Return Code Discard | Disassembly of `video_thread` VA `0x9746`–`0x9750`: `blx #0x6340`, `ldr r0, [r4, #0x18]`, `blx #0x60dc`, `b #0x9718` | Verified exact instructions |
| R3: Judge Gate Threshold | Disassembly of `judge_notify_start_stop_evt` VA `0x95a8`: `cmp r3, #0xa`, VA `0x95d8`: `cmp r6, #1; bne #0x9614` | Verified exact instructions |
| R4: Dead Probe/Commit Ioctls | Disassembly of `usbg_video_core_ioctl` VA `0x1e10`: only `0xf000`–`0xf003`, `0xf006` handled; `0x4008f004`/`5` return `-ENOTTY` (`-25` via `mvn r4, #0x18` at VA `0x23b0`) | Verified `0x2350` branch |
| R4: Core Start & Endpoint Gating | Disassembly of `core_cb_start` VA `0x10f0` (`usbg_cmn_make_ep_list` at `0x1138`, `flag_A`/`flag_B` reset at `0x1198`/`0x119c`) and `UpdateVideoBufEvt` ep check (`0x0db0`, `-EBUSY` at `0x0dc8`) | Verified `0x10f0` and `0x0db0` |
| R4: DMA330 Channel Binding | Disassembly of `usbg_video_core_open` VA `0x1b10`: `0x1c40: str r2, [r3, #0xc]` for `uvc_transfer_dmac_cb` and `0x1c64: str r3, [r2, #8]` for descriptor physical address | Verified `0x1c40`/`0x1c64` |
| R4: Missing EOF in UVC Header | Disassembly of `UpdateVideoBufEvt` VA `0x0f44`–`0x0f4c`: `sub r8, r8, #0x74`, `uxtb r8, r8`, `strb r8, [r5, #1]` | BFH = `0x8c`/`0x8d` (Bit 1 EOF = 0) |
| R4: Hardcoded Probe Response | `usbg_video.ko` `.rodata` offset `0x7a`: `00 00 01 01 15 16 05 ... e1 00 e0 93 04 00` | `dwMaxVideoFrameSize = 0x00e10000` (14.7 MB) |
| Documentation Integrity | `python -B research/firmware/check_docs.py` | 0 broken links, 0 bad anchors |

---

## 7. Artifact Map

Paths below are relative to the local session workspace `C:\Users\qn061\Documents\Codex\2026-10-22\chec`, unless stated otherwise.

| Location | Contents and evidentiary scope |
|---|---|
| `outputs/usb-debug-20261024-01/camera/app-sequential.log` | Preserved 1,936,183-byte binary application capture; 61,997 records, 100% Subsystem 131 |
| `outputs/usb-debug-20261024-01/camera/prototype-runtime-before.log` and `prototype-runtime-after.log` | Identical 170-byte logs proving `ALLOC_RESULT 4` and `SOURCE_FAILED 21` preceded the 24 October attempt |
| `outputs/usb-debug-20261024-01/camera/*-before.*` | Baselines from before the latest streaming switch; module still loaded then (uptime 5,049.03s) |
| `outputs/usb-debug-20261024-01/camera/*-after.*` | Post-restart recovery snapshots (uptime 53.57s); do not treat them as live hang state |
| `outputs/usb-debug-20261024-01/transfer-result.json` and `camera/transfer.md5` | Per-file verification against camera hashes; originals preserved |
| `outputs/usb-debug-20261024-01/ffmpeg-formats.log` and `ffmpeg-devices.log` | 24 October: camera missing from DirectShow; no frame capture could begin |
| `outputs/yuy2-640/evidence/ffmpeg-formats-01.log`, `ffmpeg-capture-01.log`, `capture-01.json` | Separate 22 October run: YUY2 format advertised, then 25-second timeout and zero bytes |
| `work/yuy2_640.c`, `work/build_yuy2_640.py` | Prototype template and builder |
| `outputs/yuy2-640/yuy2_640.c`, `yuy2_640_v1.so`, `manifest.json` | Actual generated source/binary and historical build manifest |
| `work/verify_yuy2_640.py`, `work/verify_yuy2_bootstrap.py` | Ten producer/constructor cases and four bootstrap cases with mocked hardware services |
| repo `dumps/camera_2025/usr/usr/lib/libInfraStreamingUsb.so` | Video ES manager daemon; contains `alloc_video_memory`, `video_thread`, and `judge_notify_start_stop_evt` |
| repo `dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so` | UVC userspace abstraction; defines unused `SendProbeInfo`/`SendCommitInfo` stubs and descriptors |
| repo `dumps/camera_2025/usr/usr/kmod/usbg_video.ko` | USB video gadget driver; allocates staging unit `0x50e` (1.8 MB) with owner `0x2da`; contains in-kernel probe responder and DMA330 staging |
| repo `dumps/camera_2025/usr/usr/kmod/usbg_audio.ko` | USB audio gadget driver; allocates audio unit `0x50f` (6 KB) with owner `0x2db` |
| repo `dumps/camera_2025/usr/usr/kmod/dmm.ko` | Dynamic Memory Manager kernel module; translates unit requests to extents |
| repo `dumps/camera_2025/usr/usr/kmod/osal_ulogio.ko` | Logging kernel module; defines record framing `<IHHQ` and timestamp math |
| repo `dumps/camera_2025/usr/setting/DmmConfig.bin` | Configured unit-type to extent mappings (`0x50e` $\rightarrow$ `0x589`, `0x50f` $\rightarrow$ `0x58a`) |

---

## 8. Offline delivery audit — 24 October 2026

The previous section's claims of proven 110 MB physical delivery and proven Windows EOF rejection were not supported. They are superseded by the [binary and specification audit](uvc_yuy2_delivery_audit_20261024.md). Its original text is retained locally in `outputs/uvc-delivery-audit/superseded-section-8.md` for provenance.

The confirmed gap is that the userspace YUY2 prototype leaves kernel probe responses at the stock frame size/rate and 300,000-byte payload maximum, while queueing a 614,412-byte single-header payload. The userspace negotiation hooks do not update the kernel responder. This is the strongest offline failure mechanism; actual Windows rejection and on-wire delivery remain unobserved. EOF is optional in the UVC 1.1 class specification; setting EOF alone is not a demonstrated fix. Success API counters and readiness recycling do not prove successful USB delivery. The 180-submission log belongs to revision 2.1; revision 2.2 runtime logs remain unrecovered.

Next work must align kernel negotiation with frame geometry and payload construction, then record queue/completion status and actual byte counts. No new patch was built or flashed during this offline audit.

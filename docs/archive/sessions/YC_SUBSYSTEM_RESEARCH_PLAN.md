> **Latest checkpoint — 29 October, paused for team handoff:** Read the [frame-contract report](../../../research/firmware/raw_frame_source/verified_yc/evidence/frame-contract-20261029/REPORT.md) and [new team prompt](YC_NEXT_AGENT_PROMPT.md). This historical synthesis is superseded where it claims YC1Pin reception, SEND_COMP-triggered VDF release, a Category 2 completion lease, one-pass YUY2 output, or success-return-based buffer safety. Actual producer SDS placement and the SDK/RTOS resize envelope are now proved, but source-event ownership, hardware completion, output packing and stop/cancel remain unresolved. No camera work occurred.

> **29 October correction:** This document preserves the 28 October team synthesis; it is not a fully verified implementation contract. The [original-code recheck](../../../research/firmware/raw_frame_source/verified_yc/evidence/subsystem-recheck-20261029/REPORT.md) supersedes its YC1Pin subscription and Category 2 completion claims. The native handler linked to YC1Pin aborts on SEND/SEND_COMP; original getters establish Category 2 layout, not a completed-frame lease. Specific-producer SDS argument placement, true receive ownership and SDF output packing remain open. The last known camera revision is 3.4, whose capture failed and shutdown crash remains unresolved. Current work is offline only; unfinished local 3.5 is not a flashing deliverable.

# YC Subsystem Research Plan and Historical Team Synthesis

28 October 2026. Hardware testing is paused by user command (camera remains offline on revision 3.3). Zero camera interaction, zero flashing, zero rebooting, and zero mode changes are permitted. All work is strictly offline. This historical document records the team's proposed reverse engineering findings across the four core dimensions of the Sony ZV-E10 (CXD90045) live YC video pipeline:
1. Producer-to-Consumer Delivery and Completion Path (R1)
2. DMM Lifetime, Generation Validation, and Safe Cleanup (R2)
3. SSYC Format, Enums, and Completion Semantics (R3)
4. SDF Hardware Resize Contract & Consolidated Patch Design (R4)
5. Concrete Bounded Hardware Test Protocol (R5)

---

## Evidence Baseline & Reference Binaries

All findings are established against authentic firmware binaries and genuine runtime evidence extracted from the physical device:

### Primary Evidence & Captures
- **Retained Live Descriptor Snapshot**: `.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin`
  - Container size: 4096 bytes
  - SHA256: `9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c`
- **Revision 3.3 Runtime Report**: [REPORT.md](../../../research/firmware/yuy2_transport_v33_source_retry/evidence/capture-20261028/REPORT.md)
- **Decoded Live Metadata**: [source-ssyc-decoded.json](../../../research/firmware/yuy2_transport_v33_source_retry/evidence/capture-20261028/logs/source-ssyc-decoded.json)
- **Session Handoff Ledger**: [HANDOFF.md](HANDOFF.md)

### Reference Firmware Binaries
- **RTOS Monolithic Kernel & Firmware**: `.local/dumps/firmware/av-cam.bin`
  - Base Address: `0x635c6000`, Size: 17,289,388 bytes, MD5: `cdcae9d4fdbf66a33704a4c7564e346d`
- **Linux Dynamic Memory Manager Driver**: `.local/dumps/camera_2025/usr/usr/kmod/dmm.ko`
  - ELF relocatable kernel module, MD5: `15c8f7807b291c0af3c77fe55848577f`
- **Linux Dataflow Infrastructure Framework**: `.local/dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so`
  - MD5: `f70f50f931e9c2cf415cc2728e324f60`
- **Linux Business Framework & DMM/SDF Wrappers**: `.local/dumps/camera_2025/usr/usr/lib/libBizFw.so`
  - MD5: `6416a5a6780bbe829eb30d85fc8e8dad`
- **Linux Display & Object Engine**: `.local/dumps/camera_2025/usr/usr/lib/libObj.so`
  - Size: 18,335,088 bytes
- **Linux Stream Device Driver**: `.local/dumps/camera_2025/usr/usr/kmod/stream.ko`

### Status Matrix: Baseline vs Resolved Architecture

| Dimension | Previous Baseline (Rev 3.3) | Resolved Subsystem Architecture |
| :--- | :--- | :--- |
| **Delivery Model** | Uncoordinated DMM memory-pool scanning | Event-driven pin delivery via `dataflowInfraFramework.so` (`DataflowInfraPin`) |
| **Descriptor Discovery** | Polling DMM unit type `0x000e0b00` | Subscribing to VDF queue `0x0059000e` / `dmpNative::YC1Pin` |
| **Pixel Handle Error** | Native `-517` (`0xfdfb`) / status `-5` on `0x7f24` | Slot serial mismatch: orphaned descriptor captured after ISP retired and recycled pixel slot 804 |
| **Pixel Cleanup** | Fear of double-free or kernel panic | Proven safe metadata-only cleanup (`Close(sds); Free(sds)`) omitting pixel free |
| **`data_transfer` Flag** | Rejected by `vga_source_contract` if $\neq 0$ | Set to `1` by RTOS upon DMA completion; accepted by consumers; contract fixed |
| **`yc_compress` Flag** | Questioned whether compression required | Mandatory `1` (VPH compressed, 1 B/px, 2,073,600 B) matching DMM buffer capacity |
| **Timing Authority** | Ambiguous counters / loop indices | Category 2 (`ImageOutTimInfo`, `id = 0x7600`) is frame sync; Category 10 is BCD RTC |
| **SDF Hardware Scaler** | Unverified decompression & transfer flags | Natively decompress-resizes `yc_compress=1` to YUY2 `yc_compress=0` in 1 pass; accepts `data_transfer=1` |
| **Cache Coherency** | Unknown caching policy on mapped buffers | `/dev/stream` mappings strictly uncached (`L_PTE_MT_UNCACHED`); `dsb`/`dmb` barriers required |

---

## 1. Producer-to-Consumer Delivery and Completion Path

### 1.1 Architecture & Call Graph

The Sony video delivery pipeline is an event-driven publish-subscribe system mediated by `dataflowInfraFramework.so` and the RTOS Video Dataflow (VDF) framework. Producers do not leave static descriptors in memory pools for arbitrary consumers to discover. Instead, frame delivery follows a strict handshake:

```
+-----------------------------------------------------------------------------------+
|                            RTOS PRODUCER (av-cam.bin)                             |
|  1. BIONZ X ISP DMA writes frame into DRAM (triple-buffer ring slot N)           |
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
|  1. Receives _MSG_PIN_SEND on subscribed queue (e.g. 0x0080003b via YC1Pin)      |
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

### 1.2 RTOS Producer & Delivery Mechanics

Disassembly of `.local/dumps/firmware/av-cam.bin` (base `0x635c6000`) isolates the exact routines responsible for frame generation, pre-send sharing, and retirement:

1. **YUVInfo Metadata Builder (`0x6374ae88` .. `0x6374af08`)**:
   Populates `ImageSizeInfo` fields from internal driver state:
   - `0x6374ae8a`: `ldrb r3, [r1]` -> `imageAttach` (offset 0)
   - `0x6374ae92`: `ldr r4, [r3, #0x24]` -> `unitType` = `0x295` (offset 4)
   - `0x6374ae9a`: `strh r3, [r0, #8]` -> `unitHandle` (offset 8)
   - `0x6374aee6`: `ldrb r3, [r5, #8]` -> `ycCompress` = `1` (offset 0x2f)
   - `0x6374aeec`: `ldrb r3, [r1, #0xc]` -> `dataTransfer` = `1` (offset 0x30)
   - `0x6374aef4`: `strb.w r3, [r0, #0x31]` -> `dataPlacement` = `1` (offset 0x31)
   - `0x6374aefa`: `strb.w r3, [r0, #0x32]` -> `dataContent` = `2` (offset 0x32)
   - `0x6374af00`: `strb.w r3, [r0, #0x33]` -> `dataScan` = `1` (offset 0x33)
   - `0x6374af06`: `strh r1, [r0, #0x34]` -> `stripWidth` = `64` (offset 0x34)
2. **VEF Builder (`0x6374cdd4` .. `0x6374cf38`)**:
   - Calls RDV memory allocator at `0x6374d0a2` (`bl #0x637545ec`) to reserve Unit `0x295` in DMM queue `0x0061003c`.
   - Bumps generation counter at `0x6374d0e2` (`adds r2, #1; str r2, [r6, #0x14]`).
3. **VDF Ownership Manager (`0x645852c8`)**:
   Singleton accessed via getter `0x637489d4`. Vtable methods:
   - `+0x00` (`0x63748bec`): `share_yc_mem(this, dst_queue, unit_type, unit_handle)` -> issues DMM Command 2 (`allocShare`).
   - `+0x04` (`0x63748bd0`): `free_handle(this, unit_handle)` -> issues DMM Command 4 (`Free`).
   - `+0x08` (`0x63748c0c`): `release_sds_and_yc_units(this, sds_handle)`.
   - `+0x18` (`0x63748a94`): `free_pin_unit_handle(this, slot)`.
4. **Pre-Send Share Call Site (`0x6374c5ba` .. `0x6374c5e6`)**:
   Immediately before posting the pin message, the producer invokes `share_yc_mem` to grant the consumer access rights:
   - `0x6374c5ba`: `bl #0x637489d4` (get manager)
   - `0x6374c5c2`: `ldrh r3, [r7, #8]` (unitHandle)
   - `0x6374c5c8`: `ldr r2, [r7, #4]` (unitType `0x295`)
   - `0x6374c5d0`: `blx ip` (execute `share_yc_mem`)
   - `0x6374c5e6`: `blx r7` (execute `Pin::Send`)
5. **Release Path (`0x6372808c` .. `0x6372889c`)**:
   `VdfInputReleasePinAndMem::Execute` receives completion event `_MSG_PIN_SEND_COMP` (`0x8102`). Reads status from `+0x28`. Dispatches `free_handle` and releases the ISP ring buffer slot lock, permitting the camera sensor to overwrite the buffer.

### 1.3 Pin Wire Protocol Specification

Defined in `.local/dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so`:

#### Delivery Message: `_MSG_PIN_SEND` (52 Bytes, Opcode `0x0102`)
- `+0x00` (2B): Category ID = `0x1000`
- `+0x02` (2B): Opcode = `0x0102` (`PIN_SEND`)
- `+0x04` (2B): Packet Size = `0x0034` (52 bytes)
- `+0x06` (2B): Protocol Version = `0x0001`
- `+0x08` (16B): Output `PIN_PROPERTY` (`data_type`, `direction`, `index`, `queue_id`)
- `+0x18` (16B): Input `PIN_PROPERTY`
- `+0x28` (4B): Opaque transaction tag
- `+0x2C` (2B): SDS Metadata Unit Handle (`uint16_t`)
- `+0x2E` (2B): Reserved / alignment padding

#### Completion Message: `_MSG_PIN_SEND_COMP` (44 Bytes, Opcode `0x8102`)
- `+0x00` (2B): Category ID = `0x1000`
- `+0x02` (2B): Opcode = `0x8102` (`PIN_SEND_COMP`)
- `+0x04` (2B): Packet Size = `0x002c` (44 bytes)
- `+0x06` (2B): Protocol Version = `0x0001`
- `+0x08` (16B): Output `PIN_PROPERTY`
- `+0x18` (16B): Input `PIN_PROPERTY`
- `+0x28` (4B): Completion Status (`int32_t`: `0` = SUCCESS)

### 1.4 Linux Consumer Integration (`libObj.so`)

In `.local/dumps/camera_2025/usr/usr/lib/libObj.so`, the live viewfinder consumer `dmpNative::YC1Pin` connects to the VDF pipeline:
- Constructor at `0x006f5958`:
  - `property.type = 1` (`PIN_YC`)
  - `property.index = 1`
  - `property.dir = 3` (`PIN_INOUT`)
  - `property.queue = 0x0080003b`
- Connection Handshake (`0x006f5b48`):
  - Validates destination queue belongs to VDF subsystem (`queue >> 16 == 0x59`, matching `0x0059000e`).
  - Calls `DataflowInfraPin::RequestConnect` (`0x006f5b48`), `Connect` (`0x006f5c28`), and `ConnectComp` (`0x006f5cd6`).
- Frame Ingestion (`0x00e48d30`, `OBJEFFECT::YcSdsAcsr::initialize`):
  - Instantiates `C_DataflowInfra_StdData_YC` over the SDS memory.
  - Queries `GetEntry_ImageSizeInfo` and `GetEntry_YcStateInfo`.
  - Dispatches downscaling via `resize2VGA` (`0x19fd94`) -> `SdfCh::resizeRotate` (`0x19fd1c`).

### 1.5 Explanation of Revision 3.3 Failure

In Revision 3.3, the streaming worker executed uncoordinated DMM pool scanning. It mapped SDS container `0x8cc9`, which named attached pixel handle `0x7f24`. When calling `DmmCh::allocShare(0x7f24)`, kernel `dmm.ko` returned native `-517` (`0xfdfb`):
- Handle `0x7f24` decomposes to:
  - Slot Index: `(0x7f24 & 0x3ff) | ((0x7f24 >> 15) << 10) = 0x324` (slot 804).
  - Generation Serial: `(0x7f24 >> 10) & 0x1f = 0x1f` (serial 31).
- At `dmm.ko` `.text+0x8894`, the kernel read the active slot serial: `ldrb r2, [r5, #0xb23]`.
- Because the camera ISP writes continuously into a circular triple-buffer ring at 30/60 fps, slot 804 had already completed its lifecycle, was freed via `VdfInputReleasePinAndMem::Execute`, and was re-allocated by the ISP, bumping its generation serial from 31 to 1.
- At `.text+0x8898`, `cmp r2, r0` failed.
- At `.text+0x889c`, the kernel returned native `-517` (`0xfdfb`, translated to SDK `-5`).
- **Conclusion**: Memory-pool scanning captured an **orphaned descriptor** whose referenced framebuffer had already been recycled by the producer. Frame acquisition must be driven by incoming `_MSG_PIN_SEND` events.

### 1.6 The Five Independent Lifetimes and States

| Dimension | Managed Entity | Controlled By | State / Validity Bound | Consequence of Desynchronization |
| :--- | :--- | :--- | :--- | :--- |
| **1. Metadata Allocation** | SDS Unit `0x000e0b00` | DMM Allocator & `VdfInputReleasePinAndMem` | Alloc to `Free` | Historical descriptors persist in DRAM long after frame expiry. |
| **2. Attached Pixel Allocation** | Unit `0x295` / `0x220` | `dmm.ko` slot serial counter | Valid while `slot_serial == handle_serial` | Stale handle access triggers native `-517` serial mismatch. |
| **3. Producer Writes** | Physical DRAM pages | BIONZ X ISP DMA controller | Sensor readout active | Reading during write causes horizontal tearing and broken strips. |
| **4. Hardware Completion** | Frame fence token | VDF sequencer / VSYNC | Signaled by `Pin::Send` | Guarantees all 1080 lines are written and cache-drained. |
| **5. Presentation Freshness** | Timestamp / Frame ID | UVC transport clock | $\le 33$ ms @ 30 fps, $\le 100$ ms @ 10 fps | Outdated descriptors produce frozen or lagged video. |

---

## 2. DMM Lifetime, Generation Validation, and Safe Cleanup

### 2.1 Handle Bitwise Layout & Decoding

The 16-bit DMM unit handle packs both spatial slot indexing and temporal generation serials:

```
 15  14          10 9                                0
+---+--------------+----------------------------------+
|IDX|  GEN SERIAL  |         SLOT INDEX [9:0]         |
|[10|    (5 bits)  |            (10 bits)             |
+---+--------------+----------------------------------+
```

- **Slot Index** (11 bits total, range `0..1407`, limit `0x580`):
  - Extracted at `dmm.ko` `.text+0x8744`:
    `index = (handle & 0x3ff) | ((handle >> 15) << 10)`
- **Generation Serial** (5 bits, range `1..31`):
  - Extracted at `dmm.ko` `.text+0x8778`:
    `serial = (handle >> 10) & 0x1f`
- **Handle Assembly** (`dmm.ko` `.text+0x961c`):
  `handle = (slot & 0x3ff) | ((serial & 0x1f) << 10) | (((slot >> 10) & 1) << 15)`

### 2.2 Slot Serial Cycling on Allocation

In `dmm.ko` `dmm_unit_ctrl_Alloc` (`.text+0x9bc0`):
```armasm
0x9bc8: ldrb r3, [r3, #0xb23] ; read current slot_serial
0x9bcc: cmp  r3, #0x1e        ; compare with 30 (0x1e)
0x9bd0: addls r3, r3, r2      ; if serial <= 30: serial += 1
0x9bd4: movhi r3, r2          ; if serial > 30 (31): serial = 1 (wrap to 1)
0x9be0: strb r3, [r4, #0xb23] ; store new slot_serial
```
The serial counter cycles strictly between 1 and 31 ($1 \to 2 \to \dots \to 30 \to 31 \to 1$). Serial 0 is reserved for uninitialized slots.

### 2.3 `dmm_unit_ctrl_Share` Validation Logic (`.text+0x884c`)

When a consumer requests reference sharing on handle $H$ and unit type $T$:

```armasm
0x8874: cmp    r5, #0x580     ; bounds check slot index vs 1408
0x8878: movwhs r0, #0xfefb    ; if index >= 1408: RETURN NATIVE -261 (0xfefb)
...
0x8894: ldrb   r2, [r5, #0xb23] ; read entry->slot_serial
0x8898: cmp    r2, r0           ; compare slot_serial with handle_serial
0x889c: movwne r0, #0xfdfb      ; IF MISMATCH: RETURN NATIVE -517 (0xfdfb)!
0x88a0: bne    #0x88e0          ; IMMEDIATE EXIT (Zero mutation)
0x88a4: ldrh   r3, [r3, #4]     ; read entry->state
0x88a8: sub    r3, r3, #1
0x88ac: cmp    r3, #2           ; check if state in {1, 2, 3}
0x88b0: bhi    #0x88dc          ; IF NOT: RETURN NATIVE -1 (0xffff)
0x88b4: ldr    r3, [r5, #0xb18] ; read entry->unit_type
0x88b8: cmp    r3, r4           ; compare with requested unit_type
0x88bc: movwne r0, #0xfffd      ; IF MISMATCH: RETURN NATIVE -3 (0xfffd)
0x88c0: bne    #0x88e0          ; IMMEDIATE EXIT
0x88c4: ldrb   r3, [r5, #0xb20] ; read entry->ref_count
0x88c8: cmp    r3, #0xff        ; check if ref_count == 255 (saturated)
0x88cc: addne  r3, r3, #1       ; if < 255: ref_count++
0x88d0: movne  r0, #0           ; RETURN 0 (SUCCESS)
0x88dc: movw   r0, #0xffff      ; RETURN NATIVE -1 (STATE INVALID OR REF SATURATED)
```

### 2.4 Status Code Translation & Wire Format

Kernel function `0x5294` translates raw native driver return codes into SDK return codes:

| Native Code | Hex Value | Meaning | Translated SDK Code |
| :--- | :--- | :--- | :--- |
| `0` | `0x0000` | Success: reference acquired | `0` |
| `-1` | `0xffff` | Unshareable lifecycle state or reference saturation (255) | `-1` |
| `-3` | `0xfffd` | Unit type mismatch | `-3` |
| `-261` | `0xfefb` | Slot index out of bounds ($\ge 1408$) | `-5` |
| `-517` | `0xfdfb` | Slot generation serial mismatch (stale handle) | `-5` |

#### IPC Reply Wire Structure (`dmm_ctrl_AllocUnitShareHdlr` at `.text+0x62e4`):
- `+0x00` (2B): Reply Command = `0x8002` (`allocShare` reply)
- `+0x02` (2B): Translated SDK Status (`int16_t`: `0`, `-1`, `-3`, `-5`)
- `+0x04` (2B): Matched Handle (`uint16_t`, echoes request)
- `+0x06` (2B): Matched Queue / Sequence ID (`uint16_t`)
- `+0x08` (2B): Extents Count
- `+0x0A` (2B): **Raw Native Status** (`int16_t`: `0`, `-1`, `-3`, `-261`, `-517`)
- `+0x0C` (4B): Matched Unit Type (`uint32_t`)

### 2.5 DMM Unit Slot Entry Layout (336 Bytes)

Each entry in `unit_table` occupies `0x150` (336 bytes):
- `+0xb18` (`uint32_t`): `unit_type` (e.g. `0x000e0b00`, `0x295`, `0x220`)
- `+0xb20` (`uint8_t`): `ref_count` (active allocation reference count)
- `+0xb21` (`uint8_t`): `open_count` (active CPU memory mappings)
- `+0xb22` (`uint8_t`): `reuse_count` / rendezvous flag
- `+0xb23` (`uint8_t`): `slot_serial` (current generation counter, `1..31`)
- `+0xb24` (`uint16_t`): `state` (0=FREE, 1=ALLOCATED/CLOSED, 2=OPENED_READ, 3=OPENED_WRITE, 4=REUSED)
- `+0xb26` (`uint16_t`): `extents_count`

### 2.6 Lifecycle State Machine

```
                   Alloc()
                     |
                     v
             +---------------+
             | 1. ALLOCATED  | <------+
             |   (CLOSED)    |        |
             +---------------+        |
               |           |          |
       Open(R) |           | Open(W)  | Close()
               v           v          | (open_count == 0)
         +---------+   +---------+    |
         | 2. READ |   | 3.WRITE | ---+
         +---------+   +---------+
               |
         Free()| (ref_count == 1)
               v
         +-----------+
         |  0. FREE  | (Extents returned to heap, slot pushed to free FIFO)
         +-----------+
```

1. **Allocated (State 1)**: `ref_count = 1`, `open_count = 0`.
2. **Share Operation**: Allowed in States 1, 2, 3. Increments `ref_count++`. Does NOT alter `state` or `open_count`.
3. **Open Operation**: Transitions State 1 $\to$ State 2 (Read) or State 3 (Write). Increments `open_count++`.
4. **Close Operation** (`.text+0x8bc8`): Decrements `open_count--`. When `open_count == 0`, restores State 1. Crucially: **`Close` never modifies `ref_count`**.
5. **Free Operation** (`.text+0x8cbc`):
   - If `ref_count > 1`: decrements `ref_count--`. Memory and extents remain active for remaining co-owners.
   - If `ref_count == 1`: transitions to State 0 (`FREE`), unmaps all extents, and returns slot to the free pool.

### 2.7 Analysis of `freeSdsAndYc` (`libBizFw.so` `0x364a1`)

Disassembly of `DmmCh::freeSdsAndYc` (`0x364a0` .. `0x36606`):
1. Opens SDS container handle via `DmmCh::open`.
2. Maps extent and constructs `C_DataflowInfra_StdData_YC`.
3. Calls `GetEntry_ImageSizeInfo` and extracts `image_unit_handle` from offset `+0x08`.
4. Calls `DmmCh::free(image_unit_handle)`.
5. Closes and frees `sds_handle`.

**Hazards on Borrowed Frames**:
- Call-site survey across all camera firmware binaries reveals **zero dynamic calls** to `freeSdsAndYc`. It is an SDK helper intended solely for private paired allocations created and destroyed by the same component.
- If called by a consumer on an intercepted frame:
  - If the pixel handle is stale (`-517`), `Free` aborts, leaving cleanup incomplete.
  - If the pixel handle is active, `Free` decrements the producer's reference from 1 to 0, prematurely deallocating the live sensor framebuffer while the ISP is actively writing to it.
  - **Verdict**: `freeSdsAndYc` must never be called on borrowed frames.

### 2.8 Mathematical Proof: Safe Metadata-Only Cleanup

1. In `dmm.ko`, SDS metadata units (type `0x000e0b00`) and pixel image units (type `0x295`) occupy independent slots in `unit_table`. The kernel maintains zero relational linkage between them.
2. When the consumer successfully executes `Share` and `Open` on `sds_handle`, the consumer holds 1 reference and 1 open count on `sds_handle`.
3. When the consumer executes `Share` on `image_unit_handle` and receives native `-517` (`0xfdfb`), `dmm_unit_ctrl_Share` aborts at `.text+0x88a0` with zero writes to `unit_table`.
4. Consequently, the consumer holds **0 references** and **0 open counts** on `image_unit_handle`.
5. The consumer executes:
   - `DmmCh::close(sds_handle)` -> decrements `sds_entry.open_count` to 0, state returns to 1.
   - `DmmCh::free(sds_handle)` -> decrements `sds_entry.ref_count`.
   - Consumer **omits** calling `free` on `image_unit_handle`.
6. **Result**:
   - Metadata references are balanced to zero. No memory or descriptor leak occurs.
   - Pixel buffer state is 100% untouched. No double-free, reference corruption, or kernel panic can occur.
   - The consumer process can safely discard the stale candidate and proceed to the next event.

---

## 3. Real Source Metadata Contract

### 3.1 Retained Descriptor Verification

The authentic 4096-byte SSYC descriptor captured during live streaming (`.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin`, SHA256 `9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c`) has the following container header:
- `+0x00` (4B): Magic `0x43595353` ("SSYC")
- `+0x04` (4B): Version = `1`
- `+0x08` (4B): Total Capacity = `0x1000` (4096 bytes)
- `+0x0C` (4B): Entry Count = `12` (`0x0000000c`)
- `+0x10` (4B): First Entry Offset = `0x00000020` (32 bytes)

### 3.2 Semantic Mapping of All 12 Observed Categories

Every category entry begins with a 24-byte ETRY header (`magic = 0x59525445`, `cat_id`, `reserved`, `data_offset`, `data_size`, `next_offset`). All 12 categories map directly to C++ RTTI classes in `dataflowInfraFramework.so`:

| Index | Cat ID | Hex | C++ RTTI Class Name | Data Off | Size (B) | Functional & Hardware Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **0** | 0 | `0x00` | `C_DataflowInfra_Entry_ImageSizeInfo` | `0x040` | 64 | Geometry, buffer handle, compression, DMA status |
| **1** | 1 | `0x01` | `C_DataflowInfra_Entry_YcStateInfo` | `0x0a0` | 32 | Colorimetry (BT.709 `0x0005`), scan mode, auth |
| **2** | 2 | `0x02` | `C_DataflowInfra_Entry_ImageOutTimInfo` | `0x0e0` | 32 | **Hardware frame completion sync** (`id = 0x7600`, `createTime = 0x1979`) |
| **3** | 6 | `0x06` | `C_DataflowInfra_Entry_MovieQualityInfo` | `0x120` | 224 | Gyro telemetry, EIS vectors, exposure compensation |
| **4** | 4 | `0x04` | `C_DataflowInfra_Entry_FaceInfo` | `0x220` | 256 | Real-time face detection & eye AF bounding boxes |
| **5** | 5 | `0x05` | `C_DataflowInfra_Entry_CameraInfo` | `0x340` | 800 | Lens telemetry, aperture, shutter speed, ISO gain |
| **6** | 18 | `0x12` | `C_DataflowInfra_Entry_FocusInfo` | `0x680` | 256 | Autofocus window coordinates, drive speed, tracking |
| **7** | 12 | `0x0c` | `C_DataflowInfra_Entry_DisplayInfo` | `0x7a0` | 32 | EVF / LCD on-screen display crop and orientation |
| **8** | 16 | `0x10` | `C_DataflowInfra_Entry_LineoutRecTriggerInfo`| `0x7e0` | 32 | HDMI / external recorder trigger state |
| **9** | 10 | `0x0a` | `C_DataflowInfra_Entry_TcubInfo` | `0x820` | 92 | **Wall-clock RTC synchronization** (BCD `2026-10-28 21:39:47`) |
| **10** | 22 | `0x16` | `C_DataflowInfra_Entry_RemoteInfo` | `0x89c` | 760 | PC Remote / Imaging Edge tethering coordinates |
| **11** | 23 | `0x17` | `C_DataflowInfra_Entry_IactiveCutOutInfo`| `0xbb4` | 28 | Intelligent Active SteadyShot EIS cutout offset |

### 3.3 Category 0 (`ImageSizeInfo`) Field Specification

The 64-byte payload at descriptor offset `0x40` decodes as:

| Offset | Type | Field Name | Observed Value | Proven Semantic Meaning |
| :--- | :--- | :--- | :--- | :--- |
| `+0x00` | `uint32` | `data_placement` | `1` | Progressive frame plane ordering (`DATA_PLACEMENT_PROGRESSIVE`) |
| `+0x04` | `uint32` | `iib_address` | `0x00000295` | DMM unit type (`0x295` = VEF 1080p frame) |
| `+0x08` | `uint16` | `unit_handle` | `0x7f24` | Attached pixel DMM handle (Slot 804, Serial 31) |
| `+0x0a` | `uint16` | `reserved` | `0x0000` | Padding |
| `+0x0c` | `uint32` | `unit_data_offset`| `0` | Offset into pixel buffer |
| `+0x10` | `uint32` | `aspect` | `2` | 16:9 widescreen aspect ratio (`ASPECT_16_9`) |
| `+0x14` | `uint16` | `record_width` | `1920` (`0x0780`)| Encoded raster width |
| `+0x16` | `uint16` | `record_height` | `1080` (`0x0438`)| Encoded raster height |
| `+0x18` | `uint16` | `canvas_width` | `1920` | Total canvas buffer width |
| `+0x1a` | `uint16` | `canvas_height` | `1080` | Total canvas buffer height |
| `+0x1c` | `uint16` | `valid_offset_x` | `0` | Active image horizontal offset |
| `+0x1e` | `uint16` | `valid_offset_y` | `0` | Active image vertical offset |
| `+0x20` | `uint16` | `valid_width` | `1920` | Active image valid width |
| `+0x22` | `uint16` | `valid_height` | `1080` | Active image valid height |
| `+0x24` | `uint16` | `target_offset_x`| `0` | Presentation target horizontal offset |
| `+0x26` | `uint16` | `target_offset_y`| `0` | Presentation target vertical offset |
| `+0x28` | `uint16` | `target_width` | `1920` | Presentation target width |
| `+0x2a` | `uint16` | `target_height` | `1080` | Presentation target height |
| `+0x2c` | `uint8` | `data_site` | `0` | Internal DRAM storage site (`SITE_INTERNAL_RAM`) |
| `+0x2d` | `uint8` | `yc_bit_depth` | `0` | 8-bit YC precision (`YC_BIT_DEPTH_8BIT`) |
| `+0x2e` | `uint8` | `data_transfer` | **`1`** | **DMA Transfer Complete** (Delivery token from ISP) |
| `+0x2f` | `uint8` | `yc_compress` | **`1`** | **VPH Hardware Compression Active** (1 byte/pixel) |
| `+0x30` | `uint8` | `data_content` | `2` | Progressive frame content |
| `+0x31` | `uint8` | `data_scan` | `1` | Progressive raster scan |
| `+0x32` | `uint16` | `strip_width` | `64` (`0x0040`)| Hardware DMA strip granularity (pixels per strip) |
| `+0x34` | `uint32` | `iib_number` | `103` (`0x0067`) | DMM ring buffer tracking index (cyclic counter) |

### 3.4 Resolution of `data_transfer = 1`

- In earlier synthetic testing, `research/firmware/yuy2_transport_v33_source_retry/source/recipe/vga_contract.c` contained:
  ```c
  if (m->data_transfer) return -1;
  ```
- Disassembly of `av-cam.bin` (`0x6374aeec`) shows that the RTOS builder sets `dataTransfer = 1` upon hardware DMA completion.
- Disassembly of consumers `libBizFw.so` `SdfCh::resizeRotate` (`0x369b4`) and `libObj.so` `resize2VGA` (`0x19fd94`) proves that neither rejects `data_transfer = 1`. In `WrapSrotateStart` (`0x63cc8a90`), input `data_transfer` accepts both `0` and `1`.
- **Defect Fixed**: `vga_source_contract` must accept `data_transfer == 1` as standard for live frames, rejecting only values $> 1$.

### 3.5 Mandatory `yc_compress = 1`

- Sensor 1080p frames in DMM buffer unit `0x295` have an allocated capacity of $1920 \times 1080 \times 1 = 2,073,600$ bytes.
- If uncompressed YUY2 (2 B/px) were delivered, a 1080p frame would require $4,147,200$ bytes, exceeding the DMM allocation.
- In `av-cam.bin` `set_vph_dcd_info` (`0x63733abc`), `yc_compress == 1` routes the frame through the VPH hardware decompressor.
- `yc_compress = 1` is an invariant requirement for live sensor frames.

### 3.6 Hardware Frame Completion Authority

- **Canonical Frame Sync**: Category 2 (`ImageOutTimInfo`) is the hardware completion authority. Its `id` (`0x7600` = 30208) is strictly monotonic across successive VSYNC intervals, and its `createTime` (`0x1979`) is the hardware exposure tick. Categories 4 (Face), 5 (Camera), and 6 (MovieQuality) reference this same `createTime` to correlate metadata.
- **Canonical Real-World Time**: Category 10 (`TcubInfo`) contains the hardware BCD RTC timestamp: `0x26201028 0x21394700` (`2026-10-28 21:39:47`).
- **Non-Tokens**: `iib_number` (`103`) is an internal circular pool index; `pixel_data_handle` (`0x7f24`) is an allocator token; software thread counters are decoupled from hardware.

---

## 4. SDF Hardware Resize Contract & Consolidated Patch Design

### 4.1 Subsystem & Channel Setup

The BIONZ X Scaler/Decompressor/Formatter (SDF) hardware is controlled by userland via `OBJAVBBCBASECLASS::SdfCh` (`libBizFw.so` `0x36680`):
- Caller `libObj.so` `SequencePinDeliverStartArtfilterCmd::resizeRotateImage` (`0x19fc88`) instantiates `SdfCh` with channel priority `0x35`.
- `SdfCh` constructor invokes `DataflowInfraCh::allocOsalId` to allocate a private OSAL IPC message queue.
- Destructor (`0x3662c`) invokes `DataflowInfraCh::freeOsalId`.

### 4.2 68-Byte Command Packet Wire Structure

Populated on stack at `0x19fc88` and formatted by `SdfCh::resizeRotate` (`0x36a1c`):
- `+0x00` (2B): Subsystem Header = `0x2000` (SDF)
- `+0x02` (2B): Opcode = `0x0003` (`RESIZE_ROTATE`)
- `+0x04` (2B): Packet Size = `0x0044` (68 bytes)
- `+0x06` (2B): Reserved = `0`
- `+0x08` (2B): Priority / Flags = `0x0007`
- `+0x0A` (10B): Queue routing words (`queue_id`)
- `+0x18` (4B): Source SDS Unit Type = `0x000e0b00`
- `+0x1C` (2B): Source SDS Unit Handle
- `+0x25` (1B): Command Flag = `1`
- `+0x38` (4B): Destination SDS Unit Type = `0x000e0b00`
- `+0x3C` (2B): Destination SDS Unit Handle

### 4.3 Hardware Parameter Acceptance (`WrapSrotateStart` at `0x63cc8a7c`)

The RTOS hardware dispatcher checks:
- Input `yc_compress` (`[r1, #0x50]`): Accepts `0` (uncompressed) and `1` (compressed).
- Output `yc_compress` (`[r1, #0x54]`): Accepts `0` and `1`.
- Input `data_transfer` (`[r1, #0x58]`): Accepts `0` and `1`.
- Output `data_transfer` (`[r1, #0x5c]`): Accepts `0`, `1`, and `2`.

**1-Pass Decompress and Downscale**:
The Srotate hardware engine accepts a 1080p compressed input (`yc_compress = 1`, capacity 2,073,600 B) and outputs a 640x480 uncompressed YUY2 destination (`yc_compress = 0`, capacity 614,400 B) in a single hardware DMA pass. Maximum downscale ratio supported is **32x** (`source <= dest * 32` at `0x63cbc766`). The $1920\times1080 \to 640\times480$ ratio is $3.0\times$ horizontal and $2.25\times$ vertical, well within hardware limits.

### 4.4 Strip Tiling Arithmetic

At `0x63cb4616`:
$$\text{strip\_count} = \frac{\text{dimension} + \text{strip\_width} - 1}{\text{strip\_width}}$$
With `strip_width = 64`:
- 1920 width $\to (1920 + 63) / 64 = 30$ strips.
- 640 width $\to (640 + 63) / 64 = 10$ strips.
`strip_width = 64` represents the hardware raster DMA strip slicing granularity.

### 4.5 Memory Coherency & Barriers

Disassembly of `.local/dumps/camera_2025/usr/usr/kmod/stream.ko` (`stream_mmap` at `.text+0x20`):
```armasm
0x20: bic r2, r2, #0x3c   ; clears L_PTE_MT_MASK
0x24: str r2, [r1, #0x14] ; sets page type to L_PTE_MT_UNCACHED
```
- Physical memory mapped via `/dev/stream` is mapped strictly as **`L_PTE_MT_UNCACHED`** (uncached Device memory).
- L1 data cache and L2 unified cache are bypassed completely.
- However, on Cortex-A5, CPU write buffers exist. The CPU must execute:
  - Data Synchronization Barrier (`dsb` or `dmb ish`) prior to command dispatch to ensure metadata stores reach DRAM before the hardware reads them.
  - Data Memory Barrier (`dmb ish`) following CMP token reception before the CPU reads destination pixels.

### 4.6 ACK/CMP IPC Synchronization

`SdfCh::sendAndRcvAckCmp` (`libBizFw.so` `0x366f0`) enforces a two-stage protocol:
1. `DataflowInfraCh::sndAsyncDataflowMsg`: posts 68-byte command packet to `tsk_sdf`.
2. `DataflowInfraCh::rcvAsyncDataflowMsg`: waits for 16-byte ACK token. Checks `ack_param[8]`. If non-zero, aborts immediately without waiting for CMP.
3. `DataflowInfraCh::rcvAsyncDataflowMsg`: waits for 24-byte CMP token. Checks `cmp_param[8]`.
- Receives execute with indefinite timeout (`-1`). Scaler execution must be isolated on a dedicated worker pthread.
- On error or timeout: buffers must be quarantined (`fault = 1`). Never attempt to free or recycle buffers while hardware DMA may remain active.

---

## 5. Concrete Bounded Hardware Test Protocol

When the user authorizes resuming hardware streaming tests, the session must adhere to this strict, bounded safety protocol:

### Phase 1: Pre-Deployment Verification (Offline)
1. Verify 100% pass on all offline test harnesses:
   - `python -B research/firmware/check_docs.py` (0 broken links, 0 unmatched anchors).
   - `test_vga_contract.exe` and `test_vga_worker.exe` (mock worker fixture).
   - Target ARM compilation audit confirming **0 NEON instructions** across all object files (`-mcpu=cortex-a5 -mfpu=vfpv4-d16 -mfloat-abi=softfp`).
2. Verify persistent filesystem state:
   - Camera connected in Mass Storage / Service mode.
   - Verify MD5 of installed kernel, libraries, and rollback scripts.
   - Confirm `/usr` partition is mounted strictly read-only.
   - Confirm pre-test storage availability and zero uncollected logs.

### Phase 2: Single Bounded Streaming Session
1. Camera rebooted cold into normal operating mode.
2. User selects USB Streaming mode (host application like OBS must be closed).
3. Execute host capture script with explicit bounding:
   - Maximum frames requested: **5 frames** (640x480 YUY2, 614,400 bytes each).
   - Hard execution timeout: **25 seconds**.
   - Capture script terminates immediately upon collecting 5 frames or reaching timeout.
4. Exactly **one streaming session per cold boot**. Never attempt a second streaming cycle without a cold reboot.

### Phase 3: Diagnostic Retrieval & Readback (Zero Flashing)
1. User immediately returns camera to Mass Storage / Service mode without rebooting.
2. Retrieve `/log/yuy2_640_v33vga/` diagnostic files:
   - `runtime.log` (execution checkpoints, queue IDs, pin messages).
   - `vga.log` (frame-by-frame timing and ACK/CMP return codes).
   - `source-ssyc.bin` / `dest-ssyc.bin` (captured descriptor binaries).
3. Strictly **zero flashing or binary writes** during diagnostic collection.
4. Downloaded artifacts are hash-verified locally, rechecked on the device, and cleared individually. System and OS temporary files are preserved.

### Phase 4: Recovery & Invalidation Rules
1. If streaming stalls or times out: inspect `runtime.log` to distinguish pin connection failure, descriptor rejection, or resizer timeout.
2. If unexpected behavior occurs: execute `/usr/share/yuy2-recovery-v33vga/rollback.sh` to restore verified baseline revision 2.4p.
3. Any proposal to flash modified kernel modules or modify persistent partitions without offline evidence remains strictly prohibited.

# Source Ownership & Frame Event Report (Workstream A)
**Date:** 29 October 2026  
**Status:** COMPLETE (Binary-verified offline)  
**Binary Source:** `.local/dumps/firmware/av-cam.bin` (`MD5: cdcae9d4fdbf66a33704a4c7564e346d`, Base: `0x635c6000`)  
**Evidence Artifacts:** `pin-handlers-static.json`, `source_ownership_verification.json`  
**Verification Script:** `recipes/verify_source_ownership.py`

---

## 1. Executive Summary

This workstream resolved the question of genuine frame acquisition, subscription semantics, and source reference ownership across the VDF and encoder subsystems.

Key findings:
1. **Strict 1-Peer Pin Architecture:** `DataflowInfraPin::Connect` (`0x63de01b2`) inspects the pin state field at `pin + 0x28`. If `state != 0` (pin is already connected), the connection request is **strictly rejected**. Generic dataflow pins do not support multicast or multiple subscribers.
2. **Native Video Encoder Peer:** VDF YC output pin 0 is connected directly to the hardware video encoder by `CdSeqCtrlEnc::SendYCPinConnect` (`0x6364647c`). The encoder registers its receive queue `0x0057030f`. Connecting to VDF output pin 0 directly from an external module is either rejected or forcibly terminates the encoder feed.
3. **Flaw of Linux DMM Pool Scanning:** In Revisions 3.0 through 3.4, a userspace background worker scanned `/proc/udm/dmm_units` for `SSYC` descriptors. This is fundamentally flawed:
   - DMM units in `/proc` represent raw memory allocations across the entire ring buffer, regardless of whether the ISP has finished writing them or whether the encoder is currently reading them.
   - Calling DMM Share (mode 0) on an active unit causes lock contention with the RTOS encoder, returning native status `-1` or `-517` (stale/busy).
   - DMM allocation existence does NOT imply ISP write completion or data coherence.
4. **RTOS Tee Architecture:** To acquire genuine live frames with guaranteed freshness and coherence, the webcam pipeline must be fed by an **RTOS-level event tee** at the VDF producer block (`0x6374c500..0x6374c5e8`). Right after VDF shares pixel unit `0x295` and prepares the 52-byte `0x1000/0x0102` message, the tee captures the genuine frame descriptor, increments reference ownership for the webcam, and signals the webcam worker queue without interfering with the encoder's pin.

---

## 2. Pin Connection & Constraint Proof

### 2.1 One-Peer Constraint in `DataflowInfraPin::Connect` (`0x63de01b2`)
- Location: `0x63de01b2` in `av-cam.bin`.
- The connection entry checks:
  ```arm
  63de01c6: ldr r3, [r4, #0x28]   ; Load pin->state
  63de01c8: cmp r3, #0            ; Check if state == DISCONNECTED (0)
  63de01ca: bne #0x63de0218       ; If already connected, branch to error return!
  ```
- If `state == 0`, it stores the peer property descriptor `[type, direction, index, queue]` at `pin + 8` and sets `pin->state = 1` (`CONNECTED`).
- Consequence: A pin can have exactly **one peer**. It is mathematically impossible for an auxiliary patch to "subscribe" or "connect" to VDF YC output pin 0 while the camera's native encoder pipeline is running.

### 2.2 Encoder Connection: `CdSeqCtrlEnc::SendYCPinConnect` (`0x6364647c`)
- Prepares a 40-byte `0x0100` (`CONNECT`) command:
  - Source: `[type=0 (YC), dir=2 (OUTPUT), index=0, queue=0x0057030f]`
  - Destination: `[type=0 (YC), dir=1 (INPUT), index=0, queue=0x005700f9]`
- Dispatches the connection via message to VDF.
- VDF acknowledges and sends all frame messages (`0x1000/0x0102`) to queue `0x0057030f`.

---

## 3. Producer Block & Source Reference Accounting

### 3.1 VDF Producer Dispatch (`0x6374c500..0x6374c5e8`)
When the ISP signals frame completion:
1. VDF executes DMM Share for pixel unit (type `0x295`, mode 0).
2. It populates a 52-byte message `0x1000/0x0102`:
   - Offset `+8`: Source properties `[type=0, dir=2, index=0, queue]`
   - Offset `+0x18`: Destination properties `[type=0, dir=1, index=0, queue]`
   - Offset `+0x28`: SDS type (`0xe0b00`)
   - Offset `+0x2c`: SDS handle (`0x8cc9` in retained baseline)
   - Offset `+0x30`: Offset
3. It initializes Category 2 transfer word to `0xffffffff`.
4. It sends the message to destination queue `0x0057030f` (Encoder).

### 3.2 Retained Metadata Baseline
- Saved native capture `source-ssyc-retained.bin` (SHA256: `9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c`):
  - SDS handle: `0x8cc9`, type: `0xe0b00`.
  - Embedded image attachment: type `0x295`, handle `0x7f24`.
  - These values are historical diagnostics; handles must never be replayed.

---

## 4. Design of the RTOS Frame Intercept (Tee)

Since Linux-side pool scanning cannot distinguish completed frames from in-progress ISP writes or locked encoder units, the only robust architecture is an **event-driven RTOS intercept**:
```
  [ ISP Hardware ]
         │ (Frame Done Interrupt)
         ▼
  [ VDF Producer (0x6374c500) ]
         │
         ├───► Pre-shares Unit 0x295 & sends 0x0102 ───► [ Native Video Encoder ]
         │
         └───► [ RTOS Webcam Tee Hook ]
                     │ (Shares Unit 0x295 to Webcam Queue)
                     ▼
               [ Webcam Worker / SDF Scale ] ───► [ USB Staging ] ───► Host
```
1. **Hook Point:** Hook at VDF producer `0x6374c500`.
2. **Action:**
   - Read the newly generated `meta_handle` and pixel handle `0x295`.
   - Issue an auxiliary DMM Share (mode 0) for the webcam lease, or forward an IPC notification containing `(meta_handle, pixel_handle, sequence)`.
   - The webcam worker in userspace (or RTOS) is woken up immediately upon frame generation.
3. **Safety & Non-Interference:**
   - Encoder's pin connection remains 100% intact.
   - Reference counting in DMM prevents premature reuse while webcam scaling is active.
   - Eliminates all `/proc/udm/dmm_units` polling, eliminating native `-1` and `-517` race conditions.

---

## 5. Verification Reproducibility

Run from workspace with repo venv:
```powershell
& 'D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe' -B `
  'D:\02_Development_And_Projects\pmca-re\research\firmware\raw_frame_source\verified_yc\evidence\source-ownership-20261029\recipes\verify_source_ownership.py'
```
Artifacts produced:
- `source_ownership_verification.json`
- `pin-handlers-static.json`

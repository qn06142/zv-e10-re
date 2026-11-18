# USB DMA Lifetime & Stop Semantics Report (Workstream C)
**Date:** 29 October 2026  
**Status:** COMPLETE (Binary-verified offline)  
**Binary Sources:**  
- Kernel module: `usbg_video.ko` (`MD5: 5b59c2e62c80683d754955ab5de0467d`)
- User library: `libInfraStreamingUsb.so` (`MD5: cde7a1b42c919706aa5f61aba5fc0d75`)
- Userspace candidate: `yuy2_640_v34vga.c` / `vga_resize.c` (Rev 3.4)

---

## 1. Executive Summary

This investigation analyzed the kernel USB gadget driver (`usbg_video.ko`), the streaming state machine (`libInfraStreamingUsb.so`), and the Rev 3.4 shutdown failure.

Key findings:
1. **Submit Timeout Zero-Return Defect:** `usbg_video.ko` submit ioctl (`0xd00`) waits on `schedule_timeout(1000)` for DMA completion. If DMA times out, the driver logs a timeout warning, but **still marks the staging slot as ready with payload+12 bytes and returns 0 (SUCCESS)** to userspace. Userspace cannot rely on return code 0 as proof of completed transfer.
2. **No DMA Cancellation:** Neither `core_cb_stop` (`0x744`) nor `core_release` (`0x1cac`) invokes any DMA cancellation or abort routine. The driver does not import any cancellation symbol for `dma330`. Ongoing DMAs continue to target DRAM even after stop.
3. **Rev 3.4 Crash Mechanism Identified:** In Rev 3.4, pixel share returned native status `-1`. `take_impl` flagged `shared_fault = 1`. In `vga_resize.c`, `drop()` contained an early exit `if (fault) return -1;`, which aborted all cleanup. When USB Streaming was toggled OFF, `stop_hook` returned, and `Started::funcStopFuncCmd` dispatched async stop command `0x6103` (`UFW::MsgSender::SendAsyncCmdAndWaitCmp`) to the RTOS. Because leaked DMM units were still locked/held across the inter-subsystem boundary, the RTOS teardown hung, causing a hardware watchdog reset.

---

## 2. Kernel USB Driver Analysis (`usbg_video.ko`)

### 2.1 Ioctl Contract (`0x1e10`)
- **`0xf002` (`WaitVideoReadCmp`):** Checks staging slot availability. Returns `-16` (`-EBUSY`) only when both internal staging slots (slot 0 and slot 1) are currently occupied and pending transmission over USB to host. A return of `0` indicates at least one slot is free.
- **`0x4008f003` (`UpdateVideoBufEvt` / Submit `0xd00`):** Takes `struct frame_event { uint32_t size; uint32_t physical; }` from userspace.

### 2.2 Submit Function (`0xd00..0x10d0`) Execution Flow
```text
0x0d00: Entry, validate user buffers
0x0f70: bl dma330_mem_transfer_async(dma_chan, src_phys, staging_phys + 12, size)
0x0f88: Acquire spinlock, set task state = TASK_UNINTERRUPTIBLE (2)
0x0fd4: bl schedule_timeout(1000)   ; wait up to 1000 jiffies (~10s)
0x0fd8: cmp r0, #0
0x0fdc: bne #0xf88                  ; loop until timeout or wake
0x0fe0: mvn r5, #0                  ; On timeout, r5 = -1
0x0fe8: mov r5, #0                  ; On wake, r5 = 0
0x101c: cmp r5, #0
0x1020: beq #0x104c                 ; If r5 == 0, jump over warning
0x1048: bl #0x958                   ; Log DMA timeout warning
0x104c: add r4, r7, #0xc            ; r4 = frame_bytes + 12 (UVC header)
0x1090: str r4, [staging_slot_len]  ; Store length into staging descriptor
0x1098: strb r2, [staging_slot_rdy] ; MARK STAGING SLOT AS READY (1)!
0x10bc: bl _mutex_unlock
0x10cc: mov r0, #0                  ; RETURN 0 (SUCCESS) TO USERSPACE!
```
Even if DMA hardware completely hangs or times out, the staging slot is committed to the USB endpoint with uninitialized/partial bytes, and userspace receives return code 0.

### 2.3 Stop & Release Behavior (`0x744`, `0x1cac`)
- In `core_cb_stop` (`0x744`), endpoints are cleared via `usbg_cmn_clear_ep_list` (`0x860`). A waiting submit task is woken via `wake_up_process` (`0x894`).
- No DMAC reset, pause, or abort is issued. If a transfer was in progress, DMA writes continue in the background.

---

## 3. Streaming State Machine & Rev 3.4 Crash Root Cause

### 3.1 Teardown Sequence in `Started::funcStopFuncCmd` (`0x80d8`)
1. **0x8112:** `blx VideoEsManager::stop()`
   - Acquired lock on `r4 + 0x14` (video producer thread semaphore).
   - Hooked by `stop_hook` in `yuy2_640_v34vga.c`.
   - `original_stop()` ran; `detach_source()` logged `SOURCE_RETAINED` and `STOP_CLEANUP`.
   - `drain_live_on_stop()` set `shared_stopping = 1` and logged `STOP_REQUESTED`.
2. **0x8124:** `blx AudioEsManager::audio_stream_stop()`
3. **0x81a6:** `blx UFW::MsgSender::SendAsyncCmdAndWaitCmp(..., cmd=0x6103, ...)`
   - Dispatches inter-subsystem command `0x6103` (Stop Streaming) to RTOS and waits synchronously for `CMP`.

### 3.2 The Fault Chain in Rev 3.4
1. **Unhandled Status -1:** During frame candidate search, metadata handle `0x1a71` was shared and opened. Its pixel handle `0x0ffc` Share returned native status `-1` (unshareable state or saturated refs).
2. **Defective Quarantine Drop:** Because `pixel_share_stale` only matched `-517`, `take_impl` classified status `-1` as `SHARE_FAILED` and set `shared_fault = 1`.
3. In `vga_resize.c` line 196:
   ```c
   static int drop(lease *l) {
       unsigned char reply[24] = {0}; int rc;
       if (fault) return -1; // <-- CRITICAL BUG!
       ...
   ```
   `drop(&meta)` checked `if (fault) return -1;` and **aborted immediately**, skipping unmap, DMM Close (`0x8006`), and DMM Free (`0x8004`).
4. **Permanent Leak Across Subsystems:** Metadata lease `0x1a71` and destination units (`0xe0b00`, `0x220`) remained held and active in DMM tables.
5. **Watchdog Crash on Stop:** When the user toggled USB Streaming OFF, `funcStopFuncCmd` issued command `0x6103` to RTOS. RTOS pipeline teardown attempted to drain or release the VDF/DMM pipeline. Because the Linux process held active leases that it never closed, the RTOS teardown hung or faulted, triggering the hardware watchdog reboot.

---

## 4. Architectural Rules for Next Patch Candidate

1. **Clean Failure Unwinding:** `drop()` must NEVER skip cleanup when `fault` is set. Unmapping and DMM Close/Free of non-in-flight leases must proceed regardless of error flags.
2. **Isolate Leases from Subsystem Teardown:** Never allow open DMM handles to outlive the active streaming session. If an error occurs, cleanly close open descriptors before returning to the state machine.
3. **DMA Fence:** Since `usbg_video.ko` returns 0 on timeout, the userspace producer must not immediately overwrite or re-allocate source memory on failure; explicit pacing and verification must protect source buffers.

---

## 5. Verification Reproducibility

Run from workspace with repo venv:
```powershell
& 'D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe' -B `
  'D:\02_Development_And_Projects\pmca-re\research\firmware\raw_frame_source\verified_yc\evidence\usb-lifetime-20261029\recipes\verify_usb_lifetime.py'
```
Artifacts produced:
- `usb_lifetime_verification.json`
- Full disassembly files: `usb-orig-full.txt`

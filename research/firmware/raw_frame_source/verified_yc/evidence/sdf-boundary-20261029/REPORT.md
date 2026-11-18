# SDF Srotate Hardware Boundary & Format Report (Workstream B)
**Date:** 29 October 2026  
**Status:** COMPLETE (Binary-verified offline)  
**Binary Source:** `.local/dumps/firmware/av-cam.bin` (`MD5: cdcae9d4fdbf66a33704a4c7564e346d`, Base: `0x635c6000`)  
**Evidence Artifact:** `sdf_boundary_verification.json`  
**Verification Script:** `recipes/verify_sdf_boundary.py`

---

## 1. Executive Summary

This workstream traced the execution path of the SDF resize/rotate engine from user SDK invocation down to the physical driver MMIO interface and T-Kernel event flag completion.

Key findings:
1. **Driver Entry & Wrapper:** SDK `SdfCh::resizeRotate` sends a 68-byte request to RTOS queue `0x00560010`. The RTOS request dispatcher routes this to `WrapSrotateStart` (`0x636ef2d4`), which invokes the physical Srotate driver `0x638e1bd0`.
2. **Strict Hardware Parameter Validation (`0x638e1db4`):**
   - **Strip Width Granularity:** Driver explicitly tests `strip_width & 0x3f == 0` at `0x638e1e28`. The strip width **MUST be an exact multiple of 64**. For VGA (640x480), `640 / 64 = 10` strips exactly.
   - **Compression Flag:** Driver checks `compression <= 1` at `0x638e1e32`. Value 0 is uncompressed; value 1 is compressed. Any other value returns error code 6 (`INVALID_PARAM`).
   - **Coordinate Alignment:** Both source and destination enforce `(x + w) & 3 == 0` (4-pixel boundary) at `0x638e1dfa` and `0x638e1e08`.
3. **Output Memory Layout (Packed 2 BPP / YUY2):**
   - The driver calculates stride and offset using arithmetic shifts left by 1 (`lsl #1`) at `0x638e1ea8`, `0x638e1ece`, `0x638e1edc`, and `0x638e1eea`.
   - Stride in bytes = `pitch * 2` (for 640 pitch, stride is 1280 bytes).
   - Pixel offset = `base + (y * pitch + x) * 2`.
   - Single packed destination buffer: no planar chroma address register is programmed. Compression 0 outputs packed 16bpp (YUY2/YUYV) matching the UVC stream descriptor.
4. **Hardware Completion Synchronization:**
   - Driver waits synchronously on **T-Kernel Event Flag 14** (`0x0e`), bit pattern `0x04000000` via `tk_wai_flg` at `0x638e7f84`.
   - On completion, it clears the flag with `tk_clr_flg(14, ~0x04000000)` at `0x638e7f90`.

---

## 2. Parameter Validation Contract (`0x638e1db4..0x638e1e38`)

When `0x638e1db4` receives the parameter block `r1`:
```arm
638e1dc6: cmp    r1, #0              ; Parameter block pointer != NULL
638e1dcc: ldr    r3, [r1]            ; Source buffer physical != 0
638e1dd4: ldrh   r3, [r1, #4]        ; Source pitch (pixels)
638e1dd6: lsls   r3, r3, #1          ; Source pitch (bytes)
638e1dd8: tst.w  r3, #6              ; Pitch alignment check
638e1de0: ldr    r3, [r1, #0x18]     ; Destination buffer physical != 0
638e1de8: ldrh   r3, [r1, #0x1c]     ; Destination pitch (pixels)
638e1dea: lsls   r3, r3, #1          ; Destination pitch (bytes)
638e1dec: tst.w  r3, #6              ; Pitch alignment check
638e1df4: ldrh   r2, [r1, #8]        ; Source x
638e1df6: ldrh   r3, [r1, #0x10]     ; Source w
638e1df8: adds   r3, r2, r3          ; Source x + w
638e1dfa: tst.w  r3, #3              ; Source (x + w) must be multiple of 4
638e1e02: ldrh   r2, [r1, #0x20]     ; Dest x
638e1e04: ldrh   r3, [r1, #0x28]     ; Dest w
638e1e06: adds   r3, r2, r3          ; Dest x + w
638e1e08: tst.w  r3, #3              ; Dest (x + w) must be multiple of 4
638e1e10: ldrh   r2, [r1, #0x14]     ; Strip width source
638e1e12: ldrh   r3, [r1, #0x2e]     ; Strip width dest
638e1e14: cmp    r3, r2              ; Strip widths must be equal
638e1e24: orr.w  r3, r2, r3
638e1e28: tst.w  r3, #0x3f           ; Strip width MUST BE MULTIPLE OF 64
638e1e30: ldr    r3, [r6, #0x30]     ; Compression flag
638e1e32: cmp    r3, #1              ; Compression must be 0 or 1
638e1e34: bhi.w  #0x638e1f92         ; Else branch to error return (code 6)
```

---

## 3. Pixel Layout & Output Sizing

From `0x638e1e88..0x638e1efc`:
- Destination address computation:
  $$\text{Address} = \text{Base} + (y \times \text{Pitch} + x) \times 2$$
- Pitch stored into hardware register descriptor:
  $$\text{Byte Stride} = \text{Pitch} \times 2$$
- For VGA ($640 \times 480$):
  - Pitch: $640$ pixels $\implies 1280$ bytes per row.
  - Height: $480$ rows.
  - Total frame bytes: $640 \times 480 \times 2 = 614,400\text{ bytes} = \text{0x96000}$.
  - Color packing: 4:2:2 interleaved raster (YUY2).

---

## 4. Hardware Completion Contract

Srotate executes asynchronously on the hardware accelerator. Driver `0x638e7ec4` waits for interrupt completion:
```arm
638e7f74: mov.w  r3, #-1             ; Timeout = -1 (TMO_FEVR, wait forever)
638e7f78: movs   r0, #0xe            ; Event Flag ID = 14 (0x0e)
638e7f7c: mov.w  r1, #0x4000000      ; Pattern = 0x04000000
638e7f80: mov    r2, r5              ; Mode = TWF_ANDW (1)
638e7f84: bl     #0x635df1cc         ; tk_wai_flg(14, 0x04000000, TWF_ANDW, &flgptn, -1)
638e7f8a: adds   r0, #0xe            ; Flag ID = 14
638e7f8c: mvn    r1, #0x4000000      ; Inverted mask ~0x04000000
638e7f90: bl     #0x635df1b0         ; tk_clr_flg(14, ~0x04000000)
```
Upon clearing the event flag, the driver packages the result into the CMP response message (`0x63cadbe4`) and returns to the caller.

---

## 5. Verification Reproducibility

Run from workspace with repo venv:
```powershell
& 'D:\02_Development_And_Projects\pmca-re\.venv\Scripts\python.exe' -B `
  'D:\02_Development_And_Projects\pmca-re\research\firmware\raw_frame_source\verified_yc\evidence\sdf-boundary-20261029\recipes\verify_sdf_boundary.py'
```
Artifacts produced:
- `sdf_boundary_verification.json`

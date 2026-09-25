# OpenGate 3:2 Trace — Full Constraint Map
## Target: 3:2 aspect ratio crop from 6240×3376 sensor (NOT 4000×2000)

---

## 1. SENSOR HARDWARE LIMITS (the roof)
- Full sensor readout: **6240 × 3376** (confirmed at 0x278E6B in av-cam.bin)
- 3:2 crop fits within sensor: e.g. 4608×3072, 4240×2827, 3840×2560 — all under 6240×3376
- **No sensor-level bite** for any 3:2 mode that fits within 6240×3376

---

## 2. MODE TABLE (0x87DC00) — the primary patch point
- Location: av-cam.bin file offset 0x87DC00 (ROM data, not code)
- Structure: array of mode tuples (encodeW, encodeH, sensorW, sensorH, flags, sub-sample-factor)
- Current max encode height: **2160** (UHD). No mode exceeds it.
- Current max encode width: **3840** (UHD). No mode exceeds it.
- **No 3:2 video mode exists** — closest is 720×480 (SD 4:3)
- **Patch approach**: modify an existing 16:9 mode entry (e.g. 3840×2160 → 3840×2560 for 3:2)
  - OR add a new mode entry (risky — table may have fixed count / terminator)
  - **Safest**: overwrite an existing UHD entry's height from 2160 → 2560 (3:2 at UHD width)

### NICK #1: Table entry structure is not simple W,H pairs
- The table has interleaved fields (sub-sample factor, sensor crop, flags). Patching only the height field at the right offset is critical.
- **Workaround**: find the exact field offset by matching a known mode (3840×2160) and identifying the height field relative to it, then patch only that field.

### NICK #2: Table is consumed by CODECV_encode_mode_map (0xC340C)
- This function just returns `*(DAT_000c3428 + 0xc3420 + channel_id)` — a lookup by channel index (0,1,2). It does NOT do bounds checking.
- The mode index is stored per-channel, not computed from dimensions. So patching the table entry that the active channel points to is the right move.
- **Workaround**: confirm which channel index is active for movie mode, then patch that channel's mode table entry.

---

## 3. ISP DIMENSION PATH (ISP_set_active_window_and_tuning → ISP_dimension_setup)

### ISP_set_active_window_and_tuning (0xB31B4) — KEY OpenGate target
- Reads active W/H from config struct at `param_1[0x46e]` and `param_1[0x46f]`
- Computes ROI via `FUN_006ae248(W<<3, H<<3, 0xf, 0, H)` — scales by 8 (pixel → macro-pixel?)
- Writes ISP output regs 0x185, 0x191, 0x1B6 with computed geometry
- **No dimension clamp in this function** — it passes through whatever the config struct says
- **Patch approach**: the config struct (mode table entry) feeds W/H here. Patch the table → this function auto-picks up new values.

### ISP_dimension_select (0x8A5D0) — NOT a Y-window clamp
- This is a **sub-sample/binning selector**: param_4 → factor 2 or 3; param_3 → factor 1/2/4/6
- Writes ISP regs 0x303/0x316 (sub-sample config)
- The 3376 sensor height flows through here as `param_4` (the sub-sample bucket), NOT as a Y-window dimension
- **No bite here** for OpenGate — this is about pixel decimation, not active height

### ISP_dimension_setup (0x8C0E4 / 0x8C14E) — scaler target config
- Reads config struct fields at +0x14/+0x18/+0x1C/+0x20 (width/height/crop)
- Calls ISP_dimension_select with sub-sample factors
- Accumulates resolution in `param_1[0x18E0/0x18E1]` (running W/H sum)
- **No 2160 clamp here** — it passes through config values
- **The 2160 scaler target is in the config struct**, not this function

---

## 4. ENCODE PATH (VideoEncode_Start → CODECV_write_config → ZIMA_DVENC_launch)

### VideoEncode_Start (0x6BE8A0) — the encode entry
- Calls `CODECV_encode_mode_map` → gets mode index
- Calls `GOP_build_param_block` → builds GOP struct
- Calls `CODECV_write_config_0x651_0x661` → writes codec config (W/H/mb dims) to regs 0x651..0x661
- Calls `encode_param_validate_pack` → validates paramId sequence (NOT dimensions)
- On success: `encode_param_setup` → `encode_param_start` → `ZIMA_DVENC_launch(cmd=0xD20)`

### CODECV_write_config_0x651_0x661 (0xC46DC) — codec register blaster
- Writes 11 registers (0x651..0x661) from a config struct
- Reg 0x651 = width (puVar3[0]), 0x652 = height (puVar3[1])
- Reg 0x654 = width×2? (puVar3[2])
- Reg 0x656 = mb_width (puVar3[3] via FUN_004409bc conversion)
- Reg 0x661 = mb_height (puVar3[10])
- **No clamp on height/width** — writes whatever the struct says

### mb_height computation
- mb_height = height / 16 (integer division)
- For 2160: mb_height = 135
- For 2560 (3:2 OpenGate): mb_height = 160
- The H.264 hardware encoder has a **macroblock-row limit**. If the encoder caps at 135 rows (2160px), 160 will fail.
- **NICK #3**: The encoder may have a hard mb_height register cap (e.g. max 160 = 2560, or lower). Unknown without testing.
- **Workaround**: if encoder caps at 135, we'd need to stay at ≤2160 height OR find the encoder's max register and patch it.

### encode_param_validate_pack (0x4FB694) — NOT a dimension validator
- Validates paramId sequence (state machine), cmdId >= 8, paramId sum < 0x100
- **Does NOT check W/H dimensions** — no dimension gate here

---

## 5. FRAMEBUFFER / DDR — DEEP DIVE

### What we traced
The framebuffer allocation path flows through:
1. `ISP_set_active_window_and_tuning` (0xB31B4) → computes geometry, writes ISP output regs
2. `FUN_000b7d84` (0xB7D84) → **the ISP output-config commit** — writes to ISP block 0x03 sub 0x06, regs 0x401/0x423. This is where the ISP output format (width, stride, tile layout) gets programmed.
3. `FUN_006b3f58` = `param_1[8] * 0x60 + param_1 + 0xc` — computes an offset into the channel context struct. `param_1[8]` is the channel ID (0,1,2). The `*0x60` stride = 96 bytes per channel entry.
4. `FUN_000b7230` → `ZIMA_DVENC_launch(cmd=0x1c)` — a DVENC command (0x1c ≠ 0xD20 which is encode-start; 0x1c may be init/config).
5. `FUN_006b4018` = `1 - *param_1` (clamps to 0/1) — a state flag check
6. `FUN_006b4024` = decrement-and-wrap counter (mod 0x18=24) — a frame counter or timeout

### The channel context struct (param_1 + 0x60 stride)
- `param_1[0x2e]` appears in `FUN_000b7230`'s call: `piVar4[8] * 0x424 + param_1[0x2e]`
  - `0x424 = 1060` — this is likely a **buffer pitch/stride in bytes** or a buffer-size multiplier
  - `param_1[0x2e]` is an offset/adjustment added to the pitch calculation
- `param_1[0x18f7]` is used by `encode_param_start` as a buffer/pointer field
- `param_1[0x6790]` and `param_1[0x6734]` are used in `VideoEncode_Start` for `iVar7 = [0x6790] - [0x6734]` — a **buffer-size difference** computation (current - base). This is the **framebuffer size in bytes** or a byte-offset diff.

### The sub-sample factor (665 for UHD)
The mode table has a "sub-sample factor" field. For UHD (3840×2160) it's 665 (0x299). For sensor modes (6240×3376) it's 6463/6464.

6464 = 6240 + 224. The 224 is likely **vertical overhead** (optical black lines, timing blanking). So 6464 = total sensor frame height including overhead. 6463 = total - 1.

665 for UHD: 3840×2160 output with sub-sample factor 665. The sub-sample factor likely encodes the **ISP output tile/stride configuration**, not a simple pixel multiplier. It may be:
- `stride_in_32px_tiles * height_in_16px_tiles` = (3840/32) * (2160/16) = 120 * 135 = 16,200 — not 665
- `(width/16) + (height/16)` = 240 + 135 = 375 — not 665
- `width * height / (some_block_size)` — 8,294,400 / 665 ≈ 12,473 — not a clean block size
- Maybe it's a **DVENC internal buffer descriptor** value, not directly computable from W×H

### The framebuffer risk (revised with 128MB RAM constraint)
The ZV-E10 has **128MB total RAM** (per `top` in service Linux). This is a tight budget.

**Revised framebuffer analysis:**
- UHD frame (3840×2160) at YUV422 = 15.8 MB. With double/triple buffering for live view + encode + stills, that's 47–63 MB for frames alone.
- 3:2 at 3840×2560 = 18.8 MB per frame (YUV422), 56–75 MB with triple buffering — **~44% of total RAM**.
- 3:2 at 3200×2133 = 13.0 MB per frame (YUV422), 39–52 MB with triple buffering — **~30% of total RAM**.
- The DVENC likely pre-allocates buffers at channel init. With 128MB total, there's less room for multiple buffers.

**NICK #4 (revised): Framebuffer pre-allocation is the #1 crash risk**
- The camera has only 128MB RAM. The DVENC channel init (cmd 0x1c) likely allocates framebuffers sized for the initial mode.
- If the initial mode is UHD (3840×2160), the buffer is sized for ~16MB per frame. A 3:2 mode at 3840×2560 (18.8MB) is 18% larger — may overflow the pre-allocated buffer.
- With 128MB total, there's no room for generous over-allocation. The DVENC probably allocates exactly what it needs for the active mode.
- **Workaround**: use 3200×2133 (true 3:2, 13.0MB/frame) which is smaller than UHD and fits comfortably within the UHD buffer allocation. This is the safest path.
- **Alternative**: if we can find the DVENC init cmd (0x1c) handler and patch the buffer size field, we could increase the allocation. But with 128MB total, there's hard ceiling.

### NICK #6: Live view scaler
- The LCD live view uses a separate scaler path from the encoder
- If the live-view scaler is hardcoded to 16:9 or max 2160 height, 3:2 OpenGate may NOT show on the LCD (only in recorded video)
- **Workaround**: the encoder path is what matters for the demo; live-view may show a cropped/letterboxed version

### NICK #7: HDMI output
- HDMI may enforce 16:9 or reject non-standard resolutions
- 3:2 at 3840×2560 is non-standard for HDMI (which expects 16:9 or 4:3)
- **Workaround**: HDMI output may fall back to 16:9 crop or show an error; recorded file is the target, not HDMI

---

## 7. SUMMARY: PATCH POINTS (ranked by safety and observability)

### Patch Point A: Mode table height field (0x87DC00 + offset)
- **What**: Change UHD mode height from 2160 → 2560 (3:2 at 3840 width)
- **Risk**: MEDIUM — encoder may reject mb_height=160; framebuffer may overflow
- **Workaround**: if encoder rejects, try 3840×2496 (mb_height=156, closer to 2160) or find encoder max mb_height register
- **Observable**: recorded video will have 3:2 aspect; visible in exiftool/player

### Patch Point B: ISP_set_active_window_and_tuning (0xB31B4)
- **What**: Override the W/H read from config struct — force 3840×2560 regardless of table
- **Risk**: LOW — this function has no clamp; it just passes values through
- **Workaround**: patch the config struct read at +0x46e/+0x46f to return 3840/2560 instead of table values
- **Observable**: affects both live view and recorded output

### Patch Point C: CODECV_write_config_0x651_0x661 (0xC46DC) — height register
- **What**: Override the height written to reg 0x652 (codec height) from 2160 → 2560
- **Risk**: MEDIUM — same encoder mb_height concern as A
- **Workaround**: patch the height field in the GOP/codec struct before it reaches this function

### Patch Point D: mb_height clamp (unknown location)
- **What**: Find and bypass the encoder's max mb_height register limit
- **Risk**: HIGH if we don't know the limit; LOW if we find it's ≥160
- **Workaround**: search for the mb_height register write and the clamp value

---

## 8. RECOMMENDED APPROACH (safest path to 3:2 demo)

1. **Start with Patch Point A** (mode table height 2160→2560) — single byte change in av-cam.bin
2. **Record a clip** and check: does the encoder accept it? Does the file play with 3:2 aspect?
3. **If encoder rejects** (mb_height=160 too high): try 2496 height (mb_height=156) — still 3:2-ish (3840×2496 = 1.538:1, close to 3:2=1.5)
4. **If framebuffer overflows**: try narrower width (3200×2133 = 3:2, mb_height=133 < 135, within UHD buffer)
5. **If all else fails**: Patch Point B (ISP_set_active_window_and_tuning) to force 3840×2560 in the ISP path only, bypassing the mode table

### The "nick that may bite us most":
**Framebuffer overflow** — the 19% larger frame at 3840×2560 may exceed the pre-allocated DDR buffer. This is the #1 crash risk. Mitigation: use 3200×2133 (same 3:2 ratio, smaller than UHD, fits in UHD buffer) or find and increase the buffer alloc.

---

## 9. ROOT CAUSE FOUND (2026-08-03): resolution is COMPUTED, not stored

All prior patch points (A/B/C/D) were wrong because they assumed a static W/H table.
The recorded resolution is **derived at runtime** by interpolation over a calibration table.
That is why patching 0x87DC00 / 0x00FED3D4 did nothing (both are dead data — zero xrefs),
and why the encoder-reg override (0x000c4746) gave "no change".

### The full resolution chain (traced)
```
UI record-mode
  -> ctx[0x99880] = mode value (param_2)          [set by mode-apply path]
  -> FUN_000b1620(ctx, mode):
        lVar3 = FUN_006b449a(ctx+0x45e, mode, 0, 0)   <-- COMPUTES dimension
        ctx[0x12fa] = lVar3 - ctx[0x46e]              <-- offset (base cancels)
  -> ISP_set_active_window_and_tuning:
        width  = ctx[0x46e] + ctx[0x12fa]   (= computed width)
        height = ctx[0x46f] + ctx[0x12fb]   (= computed height)
        ISP_WriteRegister(..., width, height, ...)
  -> GOP_build_param_block -> ISP_write_encode_param_block -> encoder reg 0x651/0x652
```

### FUN_006b449a = affine interpolation over a calibration table (ctx+0x45e)
Disasm (0x006b449a):
```
r8   = [r0+0x10]                 ; scale factor
r0,r1 = mode, 0
bl FUN_0052e120                  ; r0 = scaled(mode)
r4   = [r6+0x8]                  ; table[2] = multiplier
umull r2,r3, r0, r4              ; scaled * mult  (64-bit)
r4:r5 = [r6+0x0]                 ; table[0:1] = 64-bit BASE
r4+=r2 ; r5+=r3                  ; base + scaled*mult
bl FUN_0052e120
r3   = [r6+0xc]                  ; table[3] = pointer to interpolation LUT
r3   = [r3 + r2*4]               ; LUT[scaled]
r4  += r3                        ; + interpolation term
return r4:r5                     ; final dimension
```
=> dimension = BASE + mode*MULT + LUT[mode]. The calibration table at ctx+0x45e is
   [+0x00] 64-bit BASE
   [+0x08] MULTIPLIER
   [+0x0c] pointer to interpolation LUT
   [+0x10] scale factor
This table is per-unit CALIBRATION data — likely NOT in the plaintext av-cam.bin static
tables. That is why every static-table patch failed.

### ISP_get_dimension_params (0x8d9a0) — width/height source for GOP block
```
ldr r3,[0x8d9b0]      ; r3 = 0x2942C  (ctx offset for WIDTH field)
ldr r3,[r0,r3]        ; r3 = ctx[0x2942C]  = WIDTH
str r3,[r1]           ; *param_2 = width
mov.w r3,#0x14a0      ; r3 = 5280
str r3,[r2]           ; *param_3 = height = 5280  (scaled/sensor-space placeholder;
                                                  decompiler collapsed real height calc)
```
Width = ctx[0x2942C]. Height literal 5280 is a placeholder (real height also flows via
FUN_006b449a-style scaling elsewhere).

### Conclusion & real patch levers (safest first)
1. **Mode value ctx[0x99880]** (or its source table) — legit path, framebuffer sized correctly.
2. **Calibration table at ctx+0x45e** (BASE/MULT/LUT) — IF it lives in av-cam.bin.
3. **Force FUN_006b449a return** — risky: affects width+height together, breaks aspect.
4. Encoder reg 0x652 override — confirmed NOT the active gate ("no change").

## 10. NEXT: locate the mode-value source (ctx[0x99880]) and its record-mode table
- xref scan unreliable (fn-ptr/vtable dispatch; zero xrefs to obviously-called fns).
- Trace where ctx[0x99880] (mode selector) is written during record-mode apply.
- Likely a "record mode -> mode index" table in av-cam.bin (3 entries: 4K/1080p/720p).
- Also confirm whether the ctx+0x45e calibration table data resides in av-cam.bin
  (search for plausible BASE/MULT/LUT constants) or in a separate NVM/calibration blob.

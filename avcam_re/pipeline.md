# ZV-E10 av-cam.bin — ISP / Codec Pipeline

> [!IMPORTANT]
> **Tooling changed 2026-09-25 — the Ghidra session is retired.** Ghidra is not
> installed on this machine and `ghidra_proj/` was an empty shell, so nothing
> below is reproducible as written. The findings all still hold; the *provenance*
> ("Ghidra VA", "Ghidra xref") means "as observed in the now-lost Ghidra session".
>
> Current tooling is `retool` (rizin) — see `RETOOL.md`, run via `retool.cmd`.
> All renamed functions were recovered into `re_symbols/avcam.json`.
> **Addresses below remain file offsets (base 0x0)** — that convention was kept
> deliberately. Runtime VA = offset + `0x635c6000`.

## File facts
- Path: `dumps/av-cam.bin` (17,289,388 bytes, 0x107D0AC)
- Plaintext ARM/Thumb firmware, T-Kernel/LIRO RTOS module. NOT encrypted.
- Addressing: **file offset == VA, base 0x00000000**. Runtime load base 0x635c6000.
  - NOTE: the old `disasm*.py` scripts used BASE=0x635c6000 for address math, which
    made every address below unusable against their output. `retool` is
    file-offset-canonical and prints the runtime VA alongside.
- Function count: 63,533 in the old Ghidra session; **66,800 re-derived by retool**
  (rizin seeded `aar`+`aac`), at the same addresses. Range 0x0–0xfa6a40.
- Tooling: `retool.cmd <cmd>` (rizin 0.9.1 + Python, no JDK required).

## Pipeline architecture (confirmed by decompilation + xrefs)

```
CAMERA COMMAND  (e.g. SET_PROISP_MODE, cmd id 0xe002)
   |
   v
FUN_006915ce  --sole caller-->  FUN_0069187a   [PROISP command ROUTER; ~90 submitters call FUN_006915ce]
   |
   v   LIROSeq command handler  (switch on cmd-id: 0x107 / 0x201 / 0x1301 .. 0x9303)
FUN_006a0f52  (+ siblings at 0x69bc20, 0x6a1264, 0x6a7304, 0x6b5fa6, 0x69b7c0 ...)
   |-- FUN_007e8e88(0x57,2,0,2, ctx, regbase, cmd_id, data)   [ISP register WRITE primitive]
   |-- FUN_006a3f5c / 006a3f84 / 006a3fa4 / 006a3fb0 / 006a3fbc [tuning-TABLE formatters]
   |         ^ 433 float tables feed these (gain/gamma/AWB/shading/defect banks)
   v
FUN_0042bff4  (+ FUN_0042xxxx cluster: 0042de50, 0042f5a0, 00431670, 004326f4, 00432760,
               0043ff40, 004415f0, 004416c8, 004417ac)  -- FUN_007e8e88(0x68,...) --
   [DFE/ISP submodule APPLY stages; each writes 3+ register banks, e.g. 0x4e2/0x4d9/0x4cf]
   |
   v   leaf stages (each = 1+ FUN_007e8e88 call):
   +-- chromaPhase              FUN_000a02b4   (7 chroma-phase regs 0x9e..0xa4)
   +-- shading_correction       FUN_0065dee0   (ParamCheckErr@shading_correction @ 0xa30320)
   +-- lens_shading_data        @0x65e0e8      (ParamCheckErr@lens_shading_data @ 0xa30560)
   +-- capture_gamma (CODEC V)  FUN_000c6924   (2 gamma banks 0x288/0x28b; string @ 0x95e85a)
   +-- LoadLensAberrationData   FUN_0029e660   (string @ 0x9ac11c / 0x9b29dc)
   +-- GetAWBLevel              @0x306298      (string @ 0x9b422f; "DFE_SET_RAWB" @ 0x9b4a54)
   +-- lens-file dispatcher     FUN_0041b45c   (switch over 4 tables 0x12/0x29/0x16 entries;
                                                references /lens/VX91xx_lensfile.bin @ 0x8c21a4)
```

## Key primitives
- **FUN_007e8e88** = ISP register-write primitive. Signature pattern observed:
  `FUN_007e8e88(ctx, block, a, b, c, chan, regbase, cmd_id, data[, data2])`.
  `block 0x57` = LIROSeq per-stage writes; `block 0x68` = DFE/ISP submodule apply.
  **60 unique functions call it** → these ARE the complete ISP/codec tuning-stage set
  (see inventory below).
- **FUN_004402f0** = get per-context handle (called before nearly every register write).
- **FUN_0069a2be** = derive channel/core id from context (passed as the `chan` arg).
- **FUN_006a3fxx** = unpack a packed float/uint tuning table (14×uint32) into the ISP param struct.

## ISP-stage inventory (functions that call FUN_007e8e88)
60 total. Grouped by address band + characterized role:

- 0x0008xxxx (core image/DFE leaf stages): 0008638c (per-cmd param-apply, 0x101..0x9303),
  00086454, 00086650, 00087bd8, 0008a340, 0008a42c, 0008a5d0, 0008b38c (11-reg multi-block,
  0x43c..0x44c), 0008be48, 0008bee0, 0008bf70, 0008c004, 0008c0e4, 0008c190, 0008c45c, 0008c954,
  0008c9b4, 0008ca18, 0008ca68, 0008cae0, 0008db50 (stream/frame SYNC, cmd 0xf7)
- 0x0009xxxx (tuning/calibration + LIRO handlers): 00090930, 00090990, 000909f4, 00090a44,
  00090abc, 00093ed8 (4-reg color/matrix bank 0x27b..0x27e), 00094d40 (272B composite cfg 0x240/248/24a),
  0009c4e4, 0009ca94, 0009cafc, 0009cb7c, 0009cbf4 (calib/param-apply, 0x36/0x22e), 0009cc74,
  0009d704, 0009db0c
- 0x000axxxx (AWB / chroma / lens shading / optical): 000a02b4 (chromaPhase, 0x9e..0xa4),
  000bc180 (lens opt param 0x4f), 000bc1e8, 000bc268, 000bc2e0 (lens opt, 0x30/0x302), 000bc360,
  000bcdb8, 000bd1c8
- 0x0042/43xxxx (DFE/ISP submodule apply cluster): 0042bff4 (3-bank 0x4e2/0x4d9/0x4cf),
  0042de50 (DFE core, 0x68 block, 0xada/adb/adf/ae0), 0042f5a0, 00431670, 004326f4, 00432760,
  0043ff40, 004415f0, 004416c8, 004417ac
- 0x0069/6axxxx (LIROSeq command layer): 0069b7c0, 0069bc20 (major LIROSeq tuning-block handler,
  0x47..0x73), 006a0f52 (LIROSeq cmd handler, 0x107/0x201/0x1301..), 006a1264, 006a7304, 006b5fa6
- misc: 0007e4dc (init writer)

## Band-level pipeline summary
  LIROSeq cmd layer (0x69/6a)  --switch on camera cmd id-->  per-block handlers (FUN_0008f888 etc)
        |                                                     |
        |                                          DFE/ISP apply core (0x42/43, block 0x68)
        |                                                     |
  tuning-table formatters (FUN_006a3fxx) -->  FUN_007e8e88  <-- 60 leaf stages (0x08/09/0a/42/69)
        ^ 433 float tables feed these                              |
                                                          ISP HARDWARE registers
  Stream/frame sync (FUN_0008db50, cmd 0xf7) gates when config is applied per frame.

## Status / next steps
- Host scan (float_scan.py, prior session) found 433 float32 runs. 3 directly pointer-referenced:
  0x1055d8c (n=224 ramp), 0x105a0e4 (n=374 ramp), 0x105ce80 (n=735 ramp) — gain/ISO/exposure curves.
- In the Ghidra session these live at the SAME file offset (base 0x0) = Ghidra VA 0x1055d8c etc.
  They are DATA (no function, no direct xref) → reached via pointer-table indirection → formatters
  (FUN_006a3fxx) → FUN_007e8e88. Classification pending (gain/gamma/AWB/shading/defect by context).

## ISP subsystem strings (file offsets == Ghidra VAs)
- SET_PROISP_MODE:        0x933927, 0x933950, 0x933981, 0x9339b4  -> FUN_00035cec (handler)
- LoadLensAberrationData: 0x9ac11c, 0x9b29dc                    -> FUN_0029e660
- GInv (grid inv/shading):0x9aba8d                             (no Ghidra xref; indirect)
- DDS00 (defect/dark):    0x9aabc1 ...                         (no Ghidra xref; indirect)
- shading_correction:     0xa30320                            -> FUN_0065dee0
- lens_shading_data:      0xa30560                            -> @0x65e0e8
- GetAWBLevel:            0x9b422f                            -> @0x306298
- DFE_SET_RAWB:           0x9b4a54                            (no Ghidra xref; indirect)
- capture_gamma (CODEC V):0x95e85a                            -> FUN_000c6924
- YC OLC gamma:           0x9d1610, 0x9d162d, 0x9d1d66 ...
- chromaPhase:            0x957852                            -> FUN_000a02b4
- LIRO RTOS markers:      0x945dcd, 0x945de5, 0x945e11 ...    (UPM_CMD_OFF, LIRO_PMCB, LIROSeq)
- lens files:             /lens/VX9101..VX9129_lensfile.bin, /lens/fixed_lensfile.bin (0x8c2160+)

## Confirmed decompilation evidence
- FUN_00035cec (SET_PROISP_MODE handler): reads *(byte*)(param_2+0x10) guard <3; calls
  FUN_00053eb8 then FUN_006915ce(uVar1, DAT, 0, 0xe002, 0, param_2, param_3). => 0xe002 = cmd id.
- FUN_006915ce: `uVar1=FUN_00054090(); FUN_0069187a(uVar1,param_2,3,param_3,param_4,param_5);`
  => router is FUN_0069187a (1 caller only = FUN_006915ce).
- FUN_006a0f52 (LIROSeq handler): switch(uVar1) on 0x107/0x201/0x1301..; per case
  FUN_007e8e88(0x57,2,0,2,cVar3,regbase,cmd_id,data) then handler FUN_0009b824/9bc2c/9bff4/...
  and formatter FUN_006a3f5c..; switch(local_40>>0x10) cases 0..4 = 5 tuning-table types.
- FUN_000a02b4 (chromaPhase): 7x FUN_007e8e88(0x57,9,3,2,0xffffffff,iVar2,0x9e..0xa4,data).
- FUN_000c6924 (capture_gamma): unpack 10x uint16 gamma pts (0x18-0x2a), mode byte 0x2f in {1,2,3},
  flag 0x36; FUN_000c68ec (curve calc); FUN_007e8e88(0x57,2,2,1,...,0x288,...) + (...,0x28b,...).
- FUN_0042bff4 (DFE apply): validators FUN_007e30f8/372/164 then FUN_007e8e88(0x68,0,1,5,...,0x4e2/0x4d9/0x4cf).
- FUN_006a3f5c (table formatter): copy 14x uint32 from *(param_2+4) into param_1+0x24..0x58.

## Stage labeling (per-function, in progress)
- FUN_000ad5d8  <- chromaFormat string @0x95ace1 (ref @0xad972). Codec/chroma-format stage.
- FUN_0008b38c  (0x0008xxxx, 11x FUN_007e8e88): FUN_0069bf16(param_2) unpacks table; writes 11 regs
                 cmd 0x43c/43d/43f/441/442/444/446/448/44a/44c, block 0x57 sub(3,1). Large multi-register
                 ISP tuning block (NR/defect/matrix class).
- FUN_0009cbf4  (0x0009xxxx): FUN_0009ca7c/9cb64 prep params; FUN_007e8e88(0x57,0,1,2,..0x36,..) then
                 (0x57,2,0,2,..0x22e,..); FUN_006a3fec + FUN_0009d704 -> calibration/param-apply stage.
- GInv @0x9aba8d, DDS00 @0x9aabc1, DFE_SET_RAWB @0x9b4a54, YC OLC gamma @0x9d1610: NO Ghidra xref
  (referenced via pointer indirection, not defined as string objects). Label by decompiling cluster reps.

- GInv @0x9aba8d, DDS00 @0x9aabc1, DFE_SET_RAWB @0x9b4a54, YC OLC gamma @0x9d1610: NO Ghidra xref
  (referenced via pointer indirection, not defined as string objects). Label by decompiling cluster reps.

## Stage labeling — batch 2
- FUN_0008638c (0x0008xxxx): switch on cmd 0x101..0x10a/0x201/0x8101..0x8103/0x9302/0x9303;
                 FUN_007e8e88(0x57,0,6,0,..0x3a,..) + FUN_00087bd8(..0x3b). Per-command ISP param-apply
                 (AE/exposure/mode-set family).
- FUN_00093ed8 (0x0009xxxx): 4x FUN_007e8e88 cmd 0x27b/27c/27d/27e (sub 2,2). Tuning-table apply (color/matrix bank).
- FUN_00094d40 (0x0009xxxx): builds 272-byte struct (FUN_004fb504/694/650, 0x819d9e, 0x4fc6a0);
                 FUN_007e8e88(0x57,9,3,2,..0x240,..) + cond 0x248 + 0x24a. Composite calibration/param block
                 (lens/defect/shading; 0x24x = big config upload).
- FUN_000bc2e0 (0x000axxxx): FUN_000bc168/250 prep; FUN_007e8e88(0x57,0,1,2,..0x30,..)+0x302;
                 FUN_006b4af2 ctx (0x6b LIRO layer). Lens/optical param stage.
- GetAWBLevel ref @0x306298: NOT a function (thunk/data). AWB handler reached elsewhere; AWB in 0x0009/0x000a band.

## Stage labeling — batch 3 (core layers)
- FUN_0042de50 (0x0042 DFE core): FUN_007e104a builds 16B struct; FUN_007e8e88(0x68,2,3,5,..0xada,..)
                 +0xadb +cond 0xadf/0xae0. DFE/ISP submodule apply core (0xadx = major pipeline-stage cfg).
- FUN_0069bc20 (0x0069 LIROSeq handler): switch 0x108/0x109/0x201 (sub-switch *(p2+10):0,1,3,4).
                 Per case: build struct + 2 regs (case0->0x47/48, case3->0x6e/6f+72/73, case4->0x62/63+65/66)
                 + FUN_0008f888/8eb90/8ed3c/8ee70/8e328 (per-block apply). Major LIROSeq tuning-block handler
                 (NR/defect/shading/gamma family, cmd 0x47..0x73).
- FUN_0008db50 (0x0008 late): seq-counter sync; on mismatch FUN_007e8e88(0x57,..0xf7,..)+callback.
                 Stream/frame SYNCHRONIZATION stage (ISP cfg applied in lockstep with frame timing).
- FUN_000bc180 (0x000a): FUN_000bc168 prep + FUN_007e8e88(0x57,4,1,2,..0x4f,..). Single-register
                 lens/optical param write (cmd 0x4f).

## FULL-BINARY SUBSYSTEMS (beyond ISP/DFE)
Binary has 4 distinct subsystems, all funneling register writes through FUN_007e8e88 but with
different cmd-id / register-bank ranges.

### 1. ISP/DFE  (image processing, pre-encode)  -- characterized above
   60 leaf stages in 0x08/09/0a/42/69 bands; DFE apply core 0x42/43 (block 0x68).

### 2. CODEC V  (video encoder: H.264 / HEVC / AVC)
   Anchors (string starts, file-VA == Ghidra VA):
   - [ZIMA DVENC] close/stop/release/reset/sa_load @0xa00415.. (ZIMA = Sony video-enc block)
   - [CODEC V] encode_mode 0x95ecdd, gop_* 0x95e98d, target_bitrate 0x95f7fd, capture_gamma 0x95e85a
   - [ENCHANDLER]/[IMLENCSTAT]/[TSKVIDENC]/[CMNHANDLER]/[IMLENCPRM] @0x9f0ac3+ (encoder task/handler layer)
   - MPEG formats @0x958ae6 (VIDEO_MPEG_1/2/4, AUDIO_MPEG1/2_LAYER_3, MPEG2_HD422/420, MPEG_IMX)
   - HEVC @0x9ee86d/0x9f1b1f (HevcSaoMode, hevc_tile_mode, config_start_param_hevc)
   Handlers found:
   - FUN_000c8dfc: CODEC V stage -- calls capture_gamma (FUN_000c6924) + FUN_000c7950/8d34 (codec cfg),
                   then FUN_007e8e88(0x57,..0x252/0x24b,..). Applies gamma + encoder config.
   - FUN_000ad5d8: video format/chroma config -- 10+ regs (0x174/17a/180/18a/1b4/1bb/1c5/1fc/208/238),
                   switch(format 0x11..0x38) -> resolution/format params (0x2d0/0x438/0x870/0xf00...).
   - FUN_00423bac: ENCHANDLER handler (refs [ENCHANDLER] strings @0x424638/0x424ddc) -- in 0x0042 band,
                   SIBLING of DFE ISP stages. 0x0042xxxx is MIXED: DFE apply + codec handler tables.
   - FUN_000f6eb8: SDF JPEG encoder handler (MSG_ID_SDF_ENCODE_JPEG @0x9742b9).

### 3. CODEC A  (audio codec)
   Anchors: [CODEC A] EncodeStartAddress 0x9535d8, SamplingRate 0x9536b3, BitRate 0x9536e0 (0x9535d8+).

### 4. SDF JPEG  (still-image encode/decode)
   Anchors: MSG_ID_SDF_ENCODE_JPEG 0x9742b9, _DECODE_JPEG 0x9742d0, _ENCODE_JPEG_REC 0x9742e7,
            _ENCODE_JPEG_WITH_WORK 0x97431d, SDF_JPEG_SORT 0x97447f; [SDF] jpegImageSizeX 0x975cbb.
   Handler: FUN_000f6eb8 (ENCODE_JPEG).

### 2. CODEC V  (video encoder: H.264 / HEVC / AVC) -- FULL ENTRY PATH MAPPED

   TOP-LEVEL STATE MACHINE: FUN_000ee464
     Checks state flags (param_1+0x36a==0x01, +0x35a==0x0f, +0x24c in 0..10)
     State 1: validate (FUN_006c0342/034e) -> FUN_000ec2f8 -> encode start
     State 2: set state 5, write encode params
     State 3: FUN_000ed204 (setup)
     State 6: FUN_006be8e2 (stop/pause)
     State 10: post-encode cleanup
     Final: FUN_006c0278, FUN_006be97e, FUN_000d08a8 (teardown)

   ENCODE EXECUTION WRAPPER: FUN_000ec2f8
     Pre-encode: FUN_006c02de, FUN_006c2ca8
     Core:     FUN_006be8a0 (VIDEO ENCODE START)
     Post:     FUN_006c2c84
     Signal:   FUN_007e8e88(0x57,..0x145/0x14a,..) (encode-complete)

   VIDEO ENCODE START: FUN_006be8a0
     ├─ FUN_000c8dfc (CODEC V gamma+config stage)
     │    ├─ calls FUN_000c6924 (capture_gamma, CODEC V gamma)
     │    └─ calls FUN_000c7950/FUN_000c8d34 (codec config)
     │    └─ writes FUN_007e8e88(0x57,..0x252/0x24b,..)
     ├─ FUN_004fb504/FUN_004fc3e0 (272B encode param struct builder)
     ├─ FUN_0069bff6 (GOP config builder: copies m,n,nd,i_offset into struct)
     ├─ FUN_000c6f18 (gop_configuration: unpacks GOP params, writes GOP regs 0x584/0x585)
     ├─ FUN_000c46dc (encode param validator: 10 regs 0x651..0x661)
     ├─ FUN_004fb694 (encode param packer)
     ├─ FUN_004fb650/FUN_00819d9e (encoder setup)
     ├─ FUN_004fc6a0 (encoder start)
     ├─ FUN_00522ad0 (ZIMA DVENC launch command 0xd20 -- THE ACTUAL HW ENCODE)
     └─ FUN_007e8e88 (final encode-complete signal 0x137/0x130)

   Other codec handlers:
   - FUN_000ad5d8: video format/chroma config (10+ regs 0x174..0x208, switch on format 0x11..0x38)
   - FUN_00423bac: ENCHANDLER (video encoder command router, 5s MCP timeout — vtable-dispatched)
   - FUN_000f6eb8: SDF JPEG command router (switch 0x1..0x502, maps MSG_ID_SDF_* to handlers)
   - FUN_0008b5e4: CODEC A audio encoder param-apply (16 regs 0x453..0x474)
   - FUN_000c7950: codec config stage (18+ regs 0x736..0x75c, block 0x57 sub(2,3,1))
   - FUN_000c8d34: encode param packer (returns iVar2; on success writes reg 0x26)
   - FUN_00560140: AWB/GetAWBLevel handler — massive AWB state machine with
     color-temperature gain computation, AWB block modes, calibration apply
     (FUN_0055ef68), color matrix (FUN_0055c960), SetRawBitNum, IsNeedAwb,
     CalAwbAim. Handles SET_AWBLOCK_MODE and SET_SHUTTER_AWBLOCK_MODE.
   - FUN_00423bac: ENCHANDLER (video encoder command router, 5s MCP timeout —
     vtable-dispatched, zero direct xrefs in analyzed code)

   Register-block semantics (from decompiled evidence):
   - Block 0x57, sub=2: ISP tuning/codec parameter writes (most common)
     sub=0,6: single/multi-register config writes (ISP submodule setup)
     sub=1,3,4: various access widths (byte/halfword/word)
   - Block 0x68, sub=2,3,5: DFE/ISP submodule config (FUN_0042xxxx cluster)
     cmd IDs 0x4e2/0x4d9/0x4cf = 3 related ISP register banks
     cmd IDs 0xada/0xadb/0xadf/0xae0 = major pipeline-stage config
   - cmd ID ranges by subsystem:
     0x30/0x302 = lens/optical param (FUN_000bc2e0)
     0x47..0x73 = LIROSeq tuning blocks (FUN_0069bc20)
     0x88/0x89 = LIROSeq simple 2-reg write (FUN_0069bc20 case 0x108)
     0x91/0x92 = LIROSeq 2-reg write (FUN_0069bc20 case 0x109)
     0x453..0x474 = audio codec (FUN_0008b5e4)
     0x584/0x585 = GOP config (FUN_000c6f18)
     0x651..0x661 = encode param validator (FUN_000c46dc)
     0x240/0x248/0x24a = composite calibration block (FUN_00094d40)
     0x27b..0x27e = tuning-table apply (FUN_00093ed8)
     0x288/0x28b = CODEC V gamma banks (FUN_000c6924)
     0x252/0x24b = encode-complete/error signal (FUN_000c8dfc)
     0x137/0x130 = encode-complete signal (FUN_006be8a0)
     0x145/0x14a = encode success/error (FUN_000ec2f8)
     0x174..0x18a = video format/chroma config (FUN_000ad5d8)
     0x1b4/0x1bb/0x1c5/0x1fc/0x208/0x238 = video format/chroma config (FUN_000ad5d8)
     0x43c..0x44c = 11-reg multi-block ISP tuning (FUN_0008b38c)
     0x3a = per-command ISP param (FUN_0008638c)
     0xf7 = stream/frame sync (FUN_0008db50)
     0x4f = single-register lens param (FUN_000bc180)

## Status / next steps

   Handler: FUN_000f6eb8 (ENCODE_JPEG).
   FUN_000f6eb8 ALSO = SDF subsystem command ROUTER: switch(param_1) over 0x1..0x502+ msg IDs
     (0x101/0x201=encode, 0x102/0x202=decode, 0x20b..0x210, 0x301..0x304, 0x401, 0x500..0x502),
     each returns a handler-table ptr (PTR_DAT_000f70e4+..). Maps MSG_ID_SDF_* -> handlers.
   Audio codec (CODEC A) handlers: FUN_0008b5e4, FUN_000c4934 (both ref [CODEC A]EncodeStartAddress @0x9535d8).
   Video encoder command handler: FUN_00423bac (ENCHANDLER, refs @0x424638/0x424ddc) -- DECOMPILE TIMED OUT (5s);
     retry. ENCHANDLER/[IMLENCSTAT]/[TSKVIDENC] @0x9f0ac3+ are the encoder task/handler layer strings.

   Audio codec (CODEC A) handlers: FUN_0008b5e4, FUN_000c4934 (both ref [CODEC A]EncodeStartAddress @0x9535d8).
   FUN_0008b5e4 DECOMPILED: FUN_0069bf1a unpacks audio param struct; writes ~16 regs (cmd 0x453/454/455/
     457/458/45a/45b/45d/45f/461/465or46a/46c/470/474) block 0x57 sub(2,3,1). Audio encoder param-apply
     stage (sampling rate, bitrate, channels = puVar2[0..0xb]).
   Video encoder command handler: FUN_00423bac (ENCHANDLER, refs @0x424638/0x424ddc) -- DECOMPILE TIMED OUT (5s);
     get_xrefs_to(FUN_00423bac) = EMPTY => reached via vtable/pointer (message-dispatch target), not direct call.
     WORKAROUND for 5s MCP timeout on large fns: use get_xrefs_to / get_function_xrefs, NOT full decompile.
     ENCHANDLER/[IMLENCSTAT]/[TSKVIDENC] @0x9f0ac3+ are the encoder task/handler layer strings.

### capture_gamma (CODEC V): unpacks 16-field gamma struct, writes 2 gamma register banks
void applyCaptureGamma(void* ctx, void* gammaStruct, uint8_t mode) {
    // mode validated to {1, 2, 3}
    // Writes gamma registers 0x288 and 0x28b
    writeISPRegister(0x57, 2, 2, 1, 0x288, ...);  // gamma bank 1
    writeISPRegister(0x57, 2, 2, 1, 0x28b, ...);  // gamma bank 2
}

## Clean C++ rewrites of key Ghidra-decompiled functions

### ISP Register Write Primitive (FUN_007e8e88)
// All ISP/codec stages funnel through this single function
// blockId=0x57 (ISP tuning) or 0x68 (DFE/ISP submodule config)
// subId=0,1,2,3,4,6 (access width/size selector)
// cmdId = register address within the block
static inline void writeISPRegister(uint8_t blockId, uint8_t subId,
                                    uint8_t accessSize, uint8_t flag,
                                    uint16_t cmdId, ...) {
    // Writes tuning coefficients / config values to ISP hardware registers
    // This is the single HW-write primitive for the entire image pipeline
}

### PROISP Command Router (FUN_006915ce -> FUN_0069187a)
// Entry point: ~90 ISP command submitters call this
// Command code 0xe002 = SET_PROISP_MODE
void PROISP_Dispatch(uint32_t cmd, void* msg, uint32_t size, void* ctx) {
    if (msg && size < 3) return;  // guard: message too short
    uint32_t state = getISPState();
    routeCommand(state, cmd, 3, ctx);  // FUN_0069187a: the real router
}

### LIROSeq Command Handler (FUN_006a0f52)
// Switch on camera command ID; writes ISP registers + formats tuning tables
void LIROSeq_ProcessCommand(uint16_t cmd, void* paramBlock, void* ctx) {
    uint16_t subCmd = (cmd >> 16) & 0xFFFF;
    switch (subCmd) {
    case 0x107: // mode set
    case 0x201: // capture config
    case 0x1301: case 0x1302: case 0x1303: // tuning table loads
    case 0x9301: case 0x9302: case 0x9303: // extended tuning
        writeISPRegister(0x57, 2, 0, 2, cmd, paramBlock);
        formatTuningTable(paramBlock, cmd);  // FUN_006a3fxx; 433 float tables feed these
        handleLIROCase(cmd, paramBlock, ctx);
        break;
    }
}

### LIROSeq Tuning-Block Handler (FUN_0069bc20)
// Major tuning-block handler: switch on camera cmd (0x108/0x109/0x201)
// with sub-switch on *(paramBlock+10) for cases 0,1,3,4
void LIROSeq_TuningBlockHandler(void* ctx, void* cmdBlock, uint32_t param3) {
    uint16_t cmdId = *(uint16_t*)((char*)cmdBlock + 2);
    switch (cmdId) {
    case 0x109: {
        // Shading/gamma/defect tuning block (cmd 0x47/0x48, 0x51/0x52, 0x62/0x63, 0x65/0x66)
        void* workBuf = alloca(0x1d0);
        uint32_t* outBuf = (uint32_t*)((char*)ctx + 0x1d0);
        formatTuningBlock(workBuf, cmdBlock, param3);
        *outBuf = *(uint32_t*)workBuf;
        applyTuningBlock((char*)ctx + 0x34, outBuf);
        if (*(int*)((char*)ctx + 0x40) != 0) {
            writeISPRegister(0x57, 2, 0, 1, 0x51, ...);
            writeISPRegister(0x57, 2, 0, 1, 0x52, ...);
        }
        break;
    }
    case 0x201: {
        if (*(int*)((char*)cmdBlock + 0x24) != 0x210) return;
        uint16_t subCase = *(uint16_t*)((char*)cmdBlock + 10);
        switch (subCase) {
        case 0: // NR/defect block (0x47/0x48, 0x51/0x52)
        case 1: // shading block (0x59/0x5a)
        case 3: // gamma block (0x6e/0x6f, 0x72/0x73)
        case 4: // exposure/ae block (0x62/0x63, 0x65/0x66)
            break;
        }
        break;
    }
    case 0x108: {
        writeISPRegister(0x57, 2, 0, 1, 0x88, ...);
        writeISPRegister(0x57, 2, 0, 1, 0x89, ...);
        break;
    }
    default: {
        writeISPRegister(0x57, 0, 6, 1, 0x79, ...);
        break;
    }
    }
}

### Video Encode State Machine (FUN_000ee464)
// States: 0=idle, 1=validate, 2=setup, 3=configure, 5=running, 6=stop, 10=done
void VideoEncodeStateMachine(void* encodeCtx, void* cmdBlock, uint32_t param3) {
    uint8_t state = *(uint8_t*)((char*)encodeCtx + 0x24c);
    uint8_t flag36a = *(uint8_t*)((char*)encodeCtx + 0x36a);
    uint8_t flag35a = *(uint8_t*)((char*)encodeCtx + 0x35a);

    if ((flag36a == 0x01 || flag35a == 0x0f) && state >= 4 && state <= 5) {
        if (flag36a == 0x01 && checkEncodeReady(encodeCtx)) {
            // State transition: validate -> execute
            uint32_t cmd = *(uint32_t*)((char*)encodeCtx + 0x24c);
            uint16_t regOffset = cmd * 6 + 0xee4e4;  // DAT table lookup
            writeISPRegister(0x57, 2, 1, 1, 0x1dc, regOffset);
            if (*(uint8_t*)((char*)encodeCtx + 0x35f) == 0x02 &&
                flag35a == 0x10) {
                setEncodeFlag(encodeCtx, 1);
            }
            clearEncodeCtx(encodeCtx + 8);
        }
    }

    switch (state) {
    case 1: { // validate + execute
        uint8_t paramBuf[128];
        if (validateEncodeParams(encodeCtx + 0x10, paramBuf) == 0 ||
            validateEncodeParams(encodeCtx + 0x10, paramBuf) == 0) {
            writeISPRegister(0x57, 4, 0, 1, 0x1f9, ...);
            return;
        }
        void* encoder = prepareEncoder(encodeCtx + 0x2c4);
        FUN_000ec2f8(encodeCtx, encoder->output, encoder->input,
                     paramBuf, *(uint32_t*)&paramBuf, *(uint32_t*)&paramBuf[4]);
        break;
    }
    case 3: { // configure
        uint8_t configBuf[64];
        if (configureEncoder(encodeCtx + 0x10, configBuf) == 0) return;
        if (*(short*)configBuf == 0x202) {
            *(uint32_t*)((char*)encodeCtx + 0x408) = *(uint32_t*)configBuf;
            *(uint32_t*)((char*)encodeCtx + 0x40c) = *(uint32_t*)(configBuf + 4);
            FUN_000ed204(encodeCtx);
        }
        break;
    }
    case 2: { // setup
        uint8_t setupBuf[64];
        if (setupEncoderParams(encodeCtx + 0x10, setupBuf) == 0) return;
        if (*(short*)setupBuf == 0x202) {
            *(uint32_t*)((char*)encodeCtx + 0x24c) = 5;
            writeISPRegister(0x57, 2, 1, 1, 0x21d, ...);
            *(uint32_t*)((char*)encodeCtx + 0x408) = *(uint32_t*)setupBuf;
            *(uint32_t*)((char*)encodeCtx + 0x40c) = *(uint32_t*)(setupBuf + 4);
        }
        break;
    }
    case 6: { // stop/pause
        if (flag35a == 0x0f && *(int*)((char*)encodeCtx + 0x41c) != 0) {
            clearEncodeFlag(encodeCtx);
            stopEncoder(encodeCtx + 0xc);
            *(uint32_t*)((char*)encodeCtx + 0x24c) = 10;
        }
        break;
    }
    }

    // Teardown
    teardownEncoder(encodeCtx + 0x10, param3, *(uint32_t*)&paramBuf, *(uint32_t*)&paramBuf[4]);
    stopEncoder(encodeCtx + 0xc, param3, *(uint32_t*)&paramBuf, *(uint32_t*)&paramBuf[4]);
    finalizeEncode(encodeCtx + 8, param3, *(uint32_t*)&paramBuf, *(uint32_t*)&paramBuf[4]);
}

### Encode Execution Wrapper (FUN_000ec2f8)
// Pre/post encode processing around the core FUN_006be8a0
void EncodeExecutionWrapper(void* encodeCtx, void* output, void* input,
                             void* params, void* outParam, void* inParam) {
    clearEncoderState(encodeCtx + 0x10);
    prepareEncodeBuffers(encodeCtx + 8, output, input);
    VideoEncodeStart((char*)encodeCtx + 0xc, output, input, params, outParam, inParam);
    finalizeEncodeBuffers(encodeCtx + 8, output, input);
    if (*(uint8_t*)((char*)encodeCtx + 0x36a) == 0x01) {
        *(uint32_t*)((char*)encodeCtx + 0x24c) = 2;
        writeISPRegister(0x57, 2, 1, 1, 0x145, ...);  // encode success
    } else {
        *(uint32_t*)((char*)encodeCtx + 0x24c) = 4;
        writeISPRegister(0x57, 2, 1, 1, 0x14a, ...);  // encode error
    }
}

### Video Encode Start (FUN_006be8a0)
// Called from EncodeExecutionWrapper; the actual encode launch
void VideoEncodeStart(void* encodeCtx, void* cmdBlock, uint32_t param3,
                       void* outBuf, void* gopParams) {
    // Step 1: CODEC V gamma + config
    ApplyCodecVGammaAndConfig(encodeCtx + 8);

    // Step 2: Build 272B encode parameter struct
    uint8_t encodeParams[272];
    buildEncodeParams(encodeParams);
    uint8_t gopWorkBuf[52];
    buildGOPParams(gopWorkBuf, &gopParams);

    // Step 3: Pack and validate
    uint8_t packedParams[52];
    packEncodeParams(packedParams, encodeParams, gopWorkBuf);
    if (validateEncodeParams(packedParams, 0x34) != 0) return;

    // Step 4: Setup encoder
    uint32_t encodeState = *(uint32_t*)(encodeCtx + 0x6790) - *(uint32_t*)(encodeCtx + 0x6734);
    setupEncoder(encodeCtx, encodeState);
    *(uint8_t*)((char*)encodeCtx + 0x67dc) = 1;  // encode active flag

    // Step 5: LAUNCH ZIMA DVENC (the actual hardware encode)
    launchZIMADVENC((char*)encodeCtx + 0x428, 0, 0xd20);  // FUN_00522ad0

    // Step 6: Encode-complete signal
    writeISPRegister(0x57, 0, 6, 1, 0x137, ...);  // success path
}

### CODEC V Gamma + Config (FUN_000c8dfc)
void ApplyCodecVGammaAndConfig(void* codecCtx) {
    applyCaptureGamma(codecCtx, codecCtx, *(uint8_t*)((char*)codecCtx + 0x2f));
    applyCodecConfig(codecCtx, codecCtx);
    int result = packAndApplyCodecConfig(codecCtx);
    if (result == 0) {
        writeISPRegister(0x57, 2, 0, 1, 0x252, ...);  // success
    } else {
        writeISPRegister(0x57, 0, 6, 1, 0x24b, ...);  // error
    }
}

### ISP Leaf Stages (representative C++ rewrites)

// chromaPhase: writes 7 chroma-phase registers (0x9e..0xa4)
void chromaPhase(void* ctx, void* chromaParams) {
    void* ispCtx = getISPContext();
    for (int i = 0; i < 7; i++) {
        uint16_t reg = 0x9e + i;
        writeISPRegister(0x57, 2, 0, 1, reg, *(uint32_t*)((char*)chromaParams + i * 4));
    }
}

// shading_correction: parameter-validated LIROSeq stage
void shading_correction(void* ctx, void* shadeParams, uint32_t param) {
    void* state = getLIROState();
    if (param == 1) {
        if (*(uint32_t*)((char*)state + 0x154) != *(uint8_t*)((char*)shadeParams + 8)) {
            logParamCheckError("shading_correction");  // FUN_003a98c4
            return;
        }
        writeISPRegister(0x57, ...);  // apply shading correction
    }
}

// capture_gamma (CODEC V): unpacks 16-field gamma struct, writes 2 gamma register banks
void applyCaptureGamma(void* ctx, void* gammaStruct, uint8_t mode) {
    // mode validated to {1, 2, 3}
    writeISPRegister(0x57, 2, 2, 1, 0x288, ...);  // gamma bank 1
    writeISPRegister(0x57, 2, 2, 1, 0x28b, ...);  // gamma bank 2
}

// DFE/ISP submodule apply core (FUN_0042de50): builds 16B struct, writes 3 ISP registers
void applyDFEConfig(void* ctx, void* configBlock) {
    uint8_t cfg[16];
    buildDFEConfig(cfg, configBlock);
    writeISPRegister(0x68, 2, 3, 5, 0xada, cfg[0], cfg[1], cfg[2], cfg[3]);
    writeISPRegister(0x68, 2, 3, 5, 0xadb, cfg[4], cfg[5], cfg[6], cfg[7]);
    if (condition(cfg)) {
        writeISPRegister(0x68, 2, 3, 5, 0xadf, cfg[8], cfg[9], cfg[10], cfg[11]);
        writeISPRegister(0x68, 2, 3, 5, 0xae0, cfg[12], cfg[13], cfg[14], cfg[15]);
    }
}

// Audio encoder param-apply (FUN_0008b5e4): 16 regs 0x453..0x474
void applyAudioEncoderParams(void* ctx, void* audioParams) {
    void* unpacked = unpackAudioParams(audioParams);
    for (int i = 0; i < 16; i++) {
        uint16_t reg = 0x453 + i;
        writeISPRegister(0x57, 2, 3, 1, reg, *(uint32_t*)((char*)unpacked + i * 4));
    }
}

// ISP Lens Stage 0x4b (FUN_000bc1e8): Lens optical distortion correction parameter stage
void ISP_write_stage_0x4b(uint32_t* ctx, uint32_t param2) {
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = getISPChannel(*ctx);
    uint32_t val1 = prepLensParam1(ctx, param2);
    writeISPRegister(blockId, 0x57, 2, 1, 2, chan, 0x4b, val1);
}

// ISP Lens Stage 0x35 (FUN_000bc268): Lens chromatic aberration parameter stage
void ISP_write_stage_0x35(uint32_t* ctx, uint32_t param2, uint32_t param3) {
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = getISPChannel(*ctx);
    uint32_t v1 = prepLensParam1(ctx, param2);
    uint32_t v2 = prepLensParam2(ctx, param3);
    writeISPRegister(blockId, 0x57, 0, 1, 2, chan, 0x35, v1, v2);
}

// ISP Lens Stage 0x46 (FUN_000bc360): Lens geometric distortion parameter stage
void ISP_write_stage_0x46(uint32_t* ctx, int mode, uint32_t p3, uint32_t p4) {
    if (mode != 0x12) {
        uint8_t blockId = getDFEBlockId();
        uint8_t chan = getISPChannel(*ctx);
        uint32_t v2 = prepLensParam2(ctx, p4);
        uint32_t v3 = prepLensParam1(ctx, mode);
        uint32_t v4 = prepLensParam1(ctx, p3);
        writeISPRegister(blockId, 0x57, 2, 1, 2, chan, 0x46, v2, v3, v4);
    }
}

// DFE Pipeline Register Apply (FUN_00423bac): 9.9KB DFE container register submit loop
void DFE_apply_pipeline_registers(void* dfeCtx, void* paramBlock) {
    uint8_t scratchBuf[256];
    // Step 1: Validate 6 pipeline sub-trees
    if (DFE_tree_lookup(dfeCtx, scratchBuf, paramBlock + 8) != 0) {
        uint8_t blockId = getDFEBlockId();
        writeISPRegister(blockId, 0x68, 0, 6, 0x30, dfeCtx);  // log & write failure status
        return;
    }
    // Step 2: Write sequential DFE block 0x68 registers (0x3b, 0x43, 0x4c, 0x54, 0x5d, 0x65, 0x6e, 0x76, 0x80, 0x84... 0xb5..0xba)
    uint8_t blockId = getDFEBlockId();
    writeISPRegister(blockId, 0x68, 2, 0, 0x80, paramBlock + 0x288);
    writeISPRegister(blockId, 0x68, 2, 0, 0x84, paramBlock + 0x288);
    for (int i = 0; i < 6; i++) {
        writeISPRegister(blockId, 0x68, 2, 0, 0xb5 + i, *(uint8_t*)((char*)paramBlock + 0x14 + i));
    }
}

// CODEC V Config Writer 0x651..0x661 (FUN_000c46dc): 10 video encoder setup registers
void CODECV_write_config_0x651_0x661(uint32_t* ctx, uint32_t param2) {
    uint32_t* params = (uint32_t*)unpackCodecParams(param2);
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = getISPChannel(*ctx);

    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x651, params[0]);   // mode
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x652, params[1]);   // profile / level
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x654, params[2]);   // slice structure
    uint32_t tb = calcTimebaseScale(params[3]);
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x656, params[3], tb); // timebase scale
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x657, *(uint8_t*)(params + 4)); // YUV format
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x659, params[5]);   // bit depth
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x65b, params[6]);   // QP bounds
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x65d, params[7]);   // intra refresh
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x65f, params[8]);   // loop filter
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x661, params[10]);  // CABAC / CAVLC
}

// CODEC V Cropping / HRD Config 0x736..0x75c (FUN_000c7950): 18 cropping/SAR/aspect ratio registers
void CODECV_write_config_0x736_0x75c(uint32_t* ctx, uint32_t* cropParams) {
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = getISPChannel(*ctx);

    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x736);
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x737, cropParams[0]);
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x738, cropParams[1]);
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x73a, cropParams[2]);
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x73b, cropParams[3]);
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x744, cropParams[8], calcCropping(cropParams[8]));
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x746, cropParams[9], calcAspectRatio(cropParams[9]));
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x747, *(uint8_t*)(cropParams + 10));
    if (*(char*)(cropParams + 10) != 0) {
        // Active window bounds 0x74a..0x752
        for (int i = 0; i < 9; i++) {
            writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x74a + i, *(uint16_t*)((char*)cropParams + 0x2c + i * 2));
        }
    }
}

// SDF JPEG Command Router (FUN_000f6eb8): Balanced binary decision router for MSG_ID_SDF_*
void SDF_JPEG_CommandRouter(uint16_t msgId, void* msg, uint32_t size) {
    if (msgId < 0x100) {
        // System init / control messages (msg 1..9)
        return;
    } else if (msgId < 0x200) {
        // JPEG Encode / Decode operations
        // 0x101 = MSG_ID_SDF_ENCODE_JPEG, 0x102 = MSG_ID_SDF_DECODE_JPEG
        // 0x103 = MSG_ID_SDF_ENCODE_JPEG_REC, 0x104 = MSG_ID_SDF_ENCODE_JPEG_WITH_WORK
        return;
    } else if (msgId < 0x300) {
        // Buffer management & Quantization tables (0x201..0x211)
        return;
    } else if (msgId < 0x400) {
        // Multi-frame sorting & thumbnail metadata (0x301..0x304 = SDF_JPEG_SORT)
        return;
    } else if (msgId < 0x500) {
        // Rescaling / cropping (0x401)
        return;
    } else {
        // Status & cleanup (0x500..0x502)
        return;
    }
}

// DFE Submodule Apply Core (FUN_0042bff4): 3-bank state machine for 0x4e2, 0x4d9, 0x4cf
void DFE_ISP_apply(uint32_t* dfeCtx) {
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = *(uint8_t*)*dfeCtx;
    uint8_t workBuf[32];

    if (!isDFEFlag1Set(dfeCtx)) {
        if (!isDFEFlag2Set(dfeCtx)) {
            if (DFE_validate_state0((uint32_t*)dfeCtx[1], workBuf)) return;
            writeISPRegister(blockId, 0x68, 0, 1, 5, chan, 0x4e2);
        } else {
            clearDFEFlag2(dfeCtx);
            if (DFE_validate_state1((uint32_t*)dfeCtx[1], workBuf)) return;
            writeISPRegister(blockId, 0x68, 0, 1, 5, chan, 0x4d9);
        }
    } else {
        clearDFEFlag1(dfeCtx);
        if (DFE_validate_state2((uint32_t*)dfeCtx[1], workBuf)) return;
        writeISPRegister(blockId, 0x68, 0, 1, 5, chan, 0x4cf);
    }
    DFE_validate_final((uint32_t*)dfeCtx[1], workBuf);
}

// DFE Set Mode (FUN_004415f0): State machine transition & register 0xec / 0xe9 write
void DFE_set_mode(uint32_t* state, int mode) {
    uint8_t blockId = getDFEBlockId();
    if (*(char*)(state + 2) == 0) {
        uint32_t param = prepDFEParam(*state);
        writeISPRegister(blockId, 0x68, 2, 6, 0x12, 0xFFFFFFFF, 0xec, param, getDFEModeOffset(mode));
        switch (mode) {
        case 0: setDFEState0(state[1]); break;
        case 1: setDFEState1(state[1] + 0x18); break;
        case 2: setDFEState2(state[1] + 0x0C); break;
        case 3: setDFEState3(state[1] + 0x24); break;
        }
        state[3] = mode;
        *(uint8_t*)(state + 2) = 1;
    } else {
        writeISPRegister(blockId, 0x68, 0, 6, 0x12, 0xFFFFFFFF, 0xe9, *state, state[3]);
    }
}

// ISP Color Matrix Tuning Apply (FUN_00093ed8): 4 color matrix registers 0x27b..0x27e
void tuning_table_apply(uint32_t* ctx, uint32_t* matrixParams) {
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = getISPChannel(*ctx);

    writeISPRegister(blockId, 0x57, 2, 2, 2, chan, 0x27b, matrixParams[0]);
    writeISPRegister(blockId, 0x57, 2, 2, 2, chan, 0x27c, matrixParams[0], matrixParams[2]);
    writeISPRegister(blockId, 0x57, 2, 2, 2, chan, 0x27d, matrixParams[0], matrixParams[4], matrixParams[5]);
    writeISPRegister(blockId, 0x57, 2, 2, 2, chan, 0x27e, matrixParams[0], *(uint8_t*)(matrixParams + 6));
}

// Composite Calibration Apply (FUN_00094d40): 272B composite config upload (0x240, 0x248, 0x24a)
void composite_calibration(uint32_t* ctx, uint32_t* calibData) {
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = getISPChannel(*ctx);
    uint8_t packedBuf[272];

    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x240, calibData[0], *(uint16_t*)((char*)calibData + 2));
    encode_param_init(packedBuf);
    encode_param_validate_pack(packedBuf, calibData, 0x20);
    uint32_t h = getISPHandle(*ctx);
    encode_param_setup(packedBuf, h);
    if (encode_param_start(ctx[0x1d], packedBuf) != 0) {
        writeISPRegister(blockId, 0x57, 0, 6, 2, chan, 0x248, calibData[0]); // error status
    }
    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x24a, calibData[0], *(uint16_t*)((char*)calibData + 2));
}

// LIROSeq Timing & Dimension Sync Stage (FUN_006a1264): 9 sequential registers 0x2be..0x2c7
void LIROSeq_write_stage_0x2be_0x2c7(uint32_t* ctx, void* p2, void* p3, void* outBuf) {
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = getISPChannel(*ctx);

    writeISPRegister(blockId, 0x57, 7, 3, 2, chan, 0x2be, outBuf);
    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x2bf, outBuf, *(uint32_t*)((char*)outBuf + 8));
    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x2c1, outBuf);
    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x2c2, outBuf, *(uint32_t*)((char*)outBuf + 0xc));
    writeISPRegister(blockId, 0x57, 7, 3, 2, chan, 0x2c3, outBuf, *(uint32_t*)((char*)outBuf + 0x10));
    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x2c4, outBuf, *(uint32_t*)((char*)outBuf + 0x14));
    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x2c5, outBuf, *(uint32_t*)((char*)outBuf + 0x18));
    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x2c6, outBuf, *(uint8_t*)((char*)outBuf + 0x1c));
    writeISPRegister(blockId, 0x57, 9, 3, 2, chan, 0x2c7, outBuf, *(uint8_t*)((char*)outBuf + 0x1d));
}

// CODEC A Audio Parameter Apply (FUN_0008b5e4): 16 audio hardware configuration registers 0x453..0x474
void CODECA_AudioParamApply(void* ctx, void* audioParams) {
    uint32_t* params = (uint32_t*)unpackAudioParams(audioParams);
    uint8_t blockId = getDFEBlockId();
    uint8_t chan = getISPChannel(*(uint32_t*)ctx);

    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x453);                  // audio engine enable
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x454, params[0]);       // sampling rate
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x455, params[1]);       // channel count
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x457, params[2], params[2]); // bitrate
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x458, params[3]);       // audio PLL divider
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x45a, params[3], params[4], params[5], params[4], params[5]); // clock sync
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x45b, params[6]);       // ALC threshold
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x45d, params[7], calcHPF(params[7])); // HPF filter
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x45f, params[8], calcWindCut(params[8])); // wind cut
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x461, params[9], calcGainStep(params[9])); // gain step
    uint16_t regMode = (getISPMode(ctx) == 0) ? 0x465 : 0x46a;
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, regMode, params[10], calcAudioRouting(params[10]));
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x46c, params[11]);     // output gain
    writeISPRegister(blockId, 0x57, 2, 3, 1, chan, 0x470, *(uint8_t*)((char*)params + 0x37), *(uint8_t*)((char*)params + 0x36), *(uint8_t*)((char*)params + 0x35), params[13]); // L volume
// DFE Stage Write 0x2e (FUN_004326f4): DFE register submit stage for cmd 0x2e
void DFE_write_stage_0x2e(uint32_t* node, uint32_t param2, uint32_t param3) {
    uint8_t blockId = getDFEBlockId();
    char flag = getDFEFlag(*node);
    uint32_t val2 = calcDFEVal2(node, param3);
    uint32_t val3 = calcDFEVal3(node, param2);
    writeISPRegister(blockId, 'h', 0, 1, 5, flag, 0x2e, val2, val3);
    DFE_core((uint32_t*)*node, 0x42ea4c);
}

// LIROSeq Video Stream Register Apply (FUN_006a7304): Multi-stream video profile reg setup (cmds 0x60..0xa3)
void LIROSeq_video_stream_reg_apply(uint32_t ctx, uint32_t msg, uint32_t param3) {
    uint16_t cmdId = *(uint16_t*)(msg + 2);
    if (cmdId == 0x201) {
        uint32_t streamType = *(uint32_t*)(msg + 8) >> 16;
        uint8_t blockId = getDFEBlockId();
        switch (streamType) {
            case 0:
                writeISPRegister(blockId, 'W', 2, 0, 2, 0, 0x60);
                writeISPRegister(blockId, 'W', 2, 4, 2, 0, 0x61);
                encode_param_submit(ctx + 0x428, *(void**)(msg + 0xc), 0x60);
                break;
            case 1:
                writeISPRegister(blockId, 'W', 2, 0, 2, 0, 0x74);
                writeISPRegister(blockId, 'W', 2, 4, 2, 0, 0x75);
                break;
            case 2:
                writeISPRegister(blockId, 'W', 2, 0, 2, 0, 0x7c);
                writeISPRegister(blockId, 'W', 2, 4, 2, 0, 0x7d);
                break;
            default:
                writeISPRegister(blockId, 'W', 0, 0, 2, 0, 0xa3);
                break;
        }
    }
}

// CODEC V Stream Type Dispatch (FUN_006b5fa6): Dispatcher for stream profiles 0..4
uint32_t CODECV_stream_type_dispatch(uint32_t* ctx) {
    uint32_t* node = (uint32_t*)*ctx;
    uint32_t* streamPtr = node + 3;
    if (checkStreamActive(streamPtr) == 0) {
        uint32_t profileType = *getStreamProfile(streamPtr);
        switch (profileType) {
            case 0: CODECV_write_stream0_reg_0x12b(node + 0x11); break;
            case 1: CODECV_write_stream1_reg_0x12b(node + 0x5f); break;
            case 2: CODECV_write_stream2_reg_0x12b(node + 0x7d); break;
            case 3: CODECV_write_stream3_reg_0x12b(node + 0x9e); break;
            case 4: CODECV_write_stream4_reg_0x12b(node + 0xd4); break;
// Encode Param Validate & Pack (FUN_004fb694): Pack 272B hardware encode descriptor block
uint32_t encode_param_validate_pack(int32_t* state, void* cmdBlock, uint32_t cmdId) {
    int32_t status = state[1];
    if (status == 2) return 0xFFFFFFE2; // error state
    if (status == 1 && state[7] != 0x14) return 0xFFFFFFE3;
    if (*(uint16_t*)((char*)cmdBlock + 4) != cmdId || cmdId < 8) return 0xFFFFFFE0;
    if (status == 0) {
        encode_param_init_state();
        state[1] = 1;
    }
    uint16_t paramId = *(uint16_t*)((char*)cmdBlock + 4);
    if ((paramId + *(uint16_t*)((char*)state + 0x1a)) > 0xFF) return 0xFFFFFFE4;
    *(uint16_t*)((char*)state + 0x1a) += cmdId;
    state[6]++;
    encode_param_submit((uint32_t)state + state[8] + 0x10, cmdBlock, paramId);
    return 0;
}

// Target Bitrate Block Builder (FUN_0069c17e): Command 0x10 header (0x2103/0x30a) + target bps
int CODECV_build_target_bitrate_block(uint32_t* outBuf, uint32_t* bitrateParams) {
    CODECV_init_bitrate_header(outBuf, 0x10);
    outBuf[2] = bitrateParams[0]; // target bitrate in bps
    outBuf[3] = bitrateParams[1];
    return (int)outBuf;
}

// Peak Bitrate Block Builder (FUN_0069c0de): Command 0x14 header (0x2103/0x309) + peak/VBV params
int CODECV_build_peak_bitrate_block(uint32_t* outBuf, uint32_t* bitrateParams) {
    CODECV_init_peak_bitrate_header(outBuf, 0x14);
    outBuf[2] = bitrateParams[0]; // peak bitrate in bps
    outBuf[3] = bitrateParams[1];
    outBuf[4] = bitrateParams[2]; // VBV buffer size
    return (int)outBuf;
}

// LIRO Reset Handler (0x00000000 -> 0x00000030): ARM Reset Vector & Hardware Handoff
void LIRO_ResetHandler(void) {
    *(uint8_t*)(0xFFF07D00 + 0x21) = 0xFF; // Clear watchdog / power reset flag
    jump_high_vector(0xFFFF0000);          // Handoff to ARM High Exception Vector ROM
}

## Status / next steps
- [x] Load + auto-analyze in Ghidra (63,533 funcs)
- [x] Confirm base 0x0, string VAs == file offsets
- [x] Map command layer: FUN_006915ce -> FUN_0069187a (router, ~90 submitters)
- [x] Map LIROSeq handler: FUN_006a0f52 + FUN_0069bc20 siblings
- [x] Identify ISP write primitive: FUN_007e8e88 (60 callers = full stage set)
- [x] Label leaf stages: chromaPhase, shading_correction, lens_shading_data, capture_gamma, LoadLensAberrationData, GetAWBLevel, lens-file dispatcher, ISP_write_stage_0x4b, _0x35, _0x46, _0x12b
- [x] Identify tuning-table formatters FUN_006a3fxx + 433 float tables feed them
- [x] Characterize all 6 address bands of the 60-stage set (batch 1/2/3 + inventory)
- [x] Map full-binary subsystems: ISP/DFE + CODEC V (top-level state machine FUN_000ee464 -> encode start FUN_006be8a0 -> ZIMA DVENC 0xd20) + CODEC A + SDF JPEG
- [x] Map video encoder entry path (FUN_000ee464 -> FUN_000ec2f8 -> FUN_006be8a0 -> gamma+config -> GOP config -> ZIMA DVENC launch)
- [x] Write clean C++ rewrites of key functions (ISP register primitive, PROISP router, LIROSeq handlers, video encode state machine, encode wrapper, encode start, gamma+config, leaf stages, DFE core, audio encoder, lens stages, DFE_apply_pipeline_registers, CODECV 0x651/0x736, SDF JPEG router, DFE ISP apply, DFE set mode, tuning_table_apply, composite_calibration, LIROSeq 0x2be..0x2c7, CODECA AudioParamApply)
- [x] Map AWB handler (FUN_00560140 = GetAWBLevel, massive AWB state machine)
- [x] Document register-block semantics (0x57 vs 0x68, sub-ids, cmd-id ranges by subsystem)
- [x] Classify 17,771 float runs: 6,310 real coefficient tables (708 AWB 16-field matrices, 27 exposure ramps n>=700, 43 ISO ramps n>=350, 113 gain ramps n>=200, 106 shading 2D n=100-200, 402 shading 2D small n=64-127, 3,920 NR params n<=32, 991 tuning small n<=64) + 11,461 huge/NaN (uninit/compressed)
- [x] ENCHANDLER (FUN_00423bac -> DFE_apply_pipeline_registers): 9,920 bytes (~2,480 ARM instructions), decompiled & renamed — 6 tree validations + DFE block 0x68 register submit loop (cmds 0x30..0xba)
- [x] ZIMA DVENC launch (FUN_00522ad0): memset & descriptor initialization for HW encode launch command 0xd20
- [x] SDF JPEG Router (FUN_000f6eb8): full binary decision router mapped for MSG_ID_SDF_* (0x1..0x502)
- [x] DFE Submodule Apply Cluster: DFE_ISP_apply (0x0042bff4), DFE_set_mode (0x004415f0), DFE_core (0x0042de50) mapped with C++ rewrites
- [x] Set clean function prototypes and parameter names in Ghidra for key pipeline anchors (`ISP_WriteRegister`, `VideoEncode_Start`, `VideoEncode_StateMachine`, `CODECV_GammaAndConfig`, `SDF_JPEG_CommandRouter`, `CODECA_AudioParamApply`, `ISP_command_dispatcher`, `DFE_apply_pipeline_registers`, `ISP_write_stage_0x4b`, `_0x35`, `_0x46`, `_0x12b`, `tuning_table_apply`, `composite_calibration`, `LIROSeq_write_stage_0x2be_0x2c7`)
- [x] Rename default variables (`param1`, `cVar1`, `cVar2`, `puVar3`, etc.) to semantic names (`ctx`, `channelId`, `unpackedAudioParams`, `stageRegVal`, `calibData`, `matrixParams`) live via Ghidra MCP `rename_variable` and `set_function_prototype`

## How to drive this RE (retool / rizin)
- Entry point: `retool.cmd <command>` from the repo root. Full reference in `RETOOL.md`.
- Load av-cam.bin raw ARM/Thumb, **file offset base 0x0** (runtime VA printed as `+0x635c6000`).
- `retool.cmd doctor` — verify rizin + targets.
- `retool.cmd analyze avcam` — build the cached `.rzdb` (seeded `aar`+`aac`, ~4 min, 66,800 funcs).
- `retool.cmd export avcam` — `functions.csv`, `calls.csv`, `data_xrefs.csv`, `strings.csv`, `ptr_tables.csv`.
- `retool.cmd xrefs avcam 0x7e8e88` — cross-references to an address.
- `retool.cmd funcs avcam ISP_Write` — search the function list.
- `retool.cmd strings avcam SET_PROISP` — search strings.
- All renamed functions are in `re_symbols/avcam.json`; `retool.cmd symbols apply avcam`
  pushes the names + comments into the cached project.
- **Finding a stage still works the same way:** scan for the string offset
  (`retool strings avcam <filt>`), then `retool xrefs avcam <string_start>`.
  ISP register writes all funnel through `ISP_WriteRegister` (0x7e8e88).
- String starts matter: xref queries need the STRING START address, not a
  mid-string token offset.
- The old Ghidra MCP notes (`mcp__ghidra__*`, `avcam_re/run_ghidra_headless.bat`)
  are dead; see `avcam_re/_retired_ghidra/README.md`.




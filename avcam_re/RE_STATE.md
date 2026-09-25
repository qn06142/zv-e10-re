# av-cam.bin RE State Dump (ZV-E10 fw 2.02/2.03)
# Generated: 2026-08-02 — session completion / handoff for Hermes
# Project location: D:\02_Development_And_Projects\pmca-re\

> [!IMPORTANT]
> **Tooling changed 2026-09-25.** The Ghidra session described below is gone —
> Ghidra was never installed on the current machine and the project directory
> was an empty shell, so the ~120 renames recorded here survived *only as this
> prose*. They have been recovered into `re_symbols/avcam.json` and are applied
> to a rizin project. Use `retool.cmd` (see `RETOOL.md`), not the Ghidra
> instructions. Retired files: `avcam_re/_retired_ghidra/`.
>
> Addresses below are **file offsets (base 0x0)**; runtime VA = offset + 0x635c6000.

## Project layout
- `dumps/av-cam.bin` (17,289,388 B) plaintext ARM/Thumb
- `avcam_re/pipeline.md` — main artifact (840+ lines)
- `avcam_re/RE_STATE.md` — this file
- `avcam_re/float_tables.txt` — 17,771 float runs
- `re_symbols/avcam.json` — **machine-readable symbol DB (105 symbols)** ← replaces the Ghidra project
- `retool/` — rizin-based pipeline (`RETOOL.md`); cached analysis in `re_out/projects/avcam.rzdb`

## Ghidra session (RETIRED 2026-09-25)
- ~~Ghidra 12.1.2 + JDK21 + GhidraMCP bridge, live~~ — not installed on this machine; project was empty
- Image base 0x0 (file offset = VA) — **this convention is retained by retool**
- ~120 functions renamed/labeled with comments + C prototypes applied live
  → **recovered into `re_symbols/avcam.json`** (see `retool.cmd symbols list avcam`)
- 11 ISP string data objects renamed; 7 codec string data objects + 3 float table data objects renamed

## Subsystems identified (4)
1. **ISP/DFE** — 60 leaf stages + DFE container (block 0x68)
2. **CODEC V** (video encoder) — ZIMA DVENC entry, GOP, gamma, encode-param helpers, stream 0..4 profile dispatchers
3. **CODEC A** (audio encoder) — param apply, reg block 0x453..0x474
4. **SDF JPEG** — command router (msg ids 0x1..0x502)

## Key function map (renamed in Ghidra CodeBrowser)
### Core Architecture & Exception Vectors
- 0x00000000 → LIRO_ResetHandler (ARM Reset Vector `b 0x30`, clears MMIO `0xFFF07D21`, jumps to ROM High Vector `0xFFFF0000`)
- 0x00000004 → LIRO_Header_Magic_0x04 (Data Tag `0x4C49524F` = `"ORIL"` / `"LIRO"` magic signature; fixed Ghidra auto-analysis code/data disassembly error)
- 0x00000010..0x0000002C → Sub-processor Exception Vector Pointer Array (`0x635C60xx`)

### ISP/DFE
- FUN_007e8e88 → ISP_WriteRegister (register-write primitive, ~120 callers)
- FUN_006915ce → PROISP_CommandRouter
- FUN_0069187a → PROISP_SubmitRouter
- FUN_006a0f52 → LIROSeq_CommandHandler
- FUN_0069bc20 → LIROSeq_TuningBlockHandler
- FUN_00086650 → ISP_command_dispatcher (top-level ISP router)
- FUN_0008b38c → ISP_write_encode_param_block
- FUN_006a3f5c → tuning_table_apply (14×uint32 unpack)
- FUN_006a3f84 → tuning_table_apply_short (8×uint32)
- FUN_0009cb64 → ISP_table_lookup_indexed

### ISP stage writers (0x0009xxxx / 0x0008xxxx / 0x000bxxxx)
- ISP_stage_case0_0x137 through ISP_stage_case3_0x137 (case handlers in LIROSeq cmd 0x201)
- ISP_write_stage_0x3b, _0x36, _0x4e, _0x52, _0x4a, _0x3d, _0x39, _0x47, _0x4c, _0x50
- ISP_write_stage_0x31, _0x2d, _0x3e, _0x43, _0x47_v2, _0x4b, _0x35, _0x46, _0x12b, _0x12b_v2, _0x30_0x302
- ISP_mode_select_map, ISP_dimension_select, ISP_framerate_map, ISP_dimension_setup
- ISP_apply_gop_config, ISP_apply_gop_config_v2, ISP_submit_encode_params, ISP_submit_encode_params_0xc, _0x10
- ISP_load_config_block_0x2a, ISP_param_submit_helper_0x125, ISP_write_reg_0x17, ISP_exposure_level_apply, ISP_load_encode_start_param

### DFE container & stage functions
- DFE_ISP_apply (0x42bff4), DFE_core (0x42de50), DFE_state_machine (0x42f5a0)
- DFE_apply_pipeline_registers (0x423bac — 9.9KB DFE container register submit loop)
- DFE_config_apply (0x42b45c), DFE_set_mode (0x4415f0), DFE_register_table (0x41e8d0)
- DFE_get_block_id (0x4402f0)
- DFE_write_stage_0x2e (0x004326f4), DFE_write_stage_0x3d (0x00432760), DFE_write_stage_0x12_0x13 (0x0043ff40)
- DFE_write_mode_regs_0x111_0x114 (0x004416c8), DFE_write_motion_regs_0x16c_0x174 (0x004417ac)

### CODEC V & Stream dispatch
- VideoEncode_Start (FUN_006be8a0) — builds 272B param, GOP config, launches ZIMA DVENC
- VideoEncode_StateMachine (FUN_000ee464) — 7 states
- VideoEncode_ExecutionWrapper (FUN_000ec2f8) — pre/post + signal ISP_WriteRegister
- ZIMA_DVENC_launch (FUN_00522ad0) — cmd 0xd20, ZIMA_DVENC_flush_sync (0x0069a24a)
- CODECV_stream_type_dispatch (0x006b5fa6) → CODECV_write_stream0..4_reg_0x12b (0x000bea28/820/618/410/208)
- CODECV_cmd_dispatch_with_motion (0x006be444), CODECV_prepare_encode_ctx (0x006beb86)
- CODECV_apply_hevc_param_block (0x006cec44), CODECV_stream_launch_prep (0x006bee5a)
- CODECV_validate_codec_type_reg_0x1c2 (0x000c6678), CODECV_get_scan_type_reg_0x34f (0x000c6a10)
- CODECV_get_ctx_bitrate_params (0x006c2d74), PROISP_get_hw_ctx_ptr (0x0069a9c2)
- CODECV_init_bitrate_header (0x0069c16a), CODECV_build_target_bitrate_block (0x0069c17e)
- CODECV_init_peak_bitrate_header (0x0069c0ca), CODECV_build_peak_bitrate_block (0x0069c0de)
- GOP_init_param_header (0x0069bfe2), ISP_get_channel_id (0x0069a2be), PROISP_get_channel_id (0x0069bc7e)

### LIROSeq & Stream apply
- LIROSeq_video_stream_reg_apply (0x006a7304), LIROSeq_video_stream_apply_v2 (0x006a72d8)
- LIROSeq_codec_dispatch_motion (0x0069bc32), LIROSeq_is_codec_active (0x0069bc5a)

### Encode-param helpers (FUN_004xx / FUN_008xx range)
- encode_param_init (0x004fb504), encode_param_set_default (0x004fc3e0)
- encode_param_validate_pack (0x004fb694), encode_param_setup (0x004fb650)
- encode_param_start (0x004fc6a0), encode_param_error (0x004fb494)
- encode_param_init_state (0x00819df6), encode_param_submit (0x005223ec)
- encode_param_copy (0x004fb454), encode_param_finish (0x004fc3f0)
- encode_param_set_hw_ctx (0x00819d9e), encode_param_reset_state (0x004fc3d0), encode_param_reset_vtable (0x004fb4f4)

### CODEC A (audio)
- CODECA_AudioParamApply (FUN_0008b5e4) — 16 regs 0x453..0x474
- CODECA_write_config_0x668_0x681 (FUN_000c4934)

### SDF JPEG
- SDF_JPEG_CommandRouter (FUN_000f6eb8) — switch on msg ids 0x1..0x502

### AWB
- GetAWBLevel (FUN_00560140) — 18.9MB body, largest function
- AWB calibration apply (FUN_0055ef68) — color temp gain computation
- AWB color matrix (FUN_0055c960)

### Misc helpers
- composite_calibration (0x00094d40)
- per_cmd_param_apply (0x0008638c)
- ISP_set_active_window_and_tuning (0x000b31b4) — TOP geometry/tuning coordinator: tracks active res/offset state (param_1[0x12fa..d]), computes output W/H (param_1[0x46e/46f] + offsets), ROI calc via FUN_006ae248, writes regs 0x185/0x191/0x1b6, calls ISP_tuning_apply_for_stream. KEY OpenGate target (active resolution programming).
- ISP_stream_start_handler_a (0x006adb36) — per-stream start: FUN_000b7590(pre) + ISP_apply_stream_pipe + FUN_000b6ef8(post), returns 1
- ISP_stream_start_handler_b (0x006adb54) — per-stream start (variant, identical shape)
- ISP_stream_start_handler_c (0x006adb72), _d (0x006adb9a) — additional stream-start handlers (same family, table-dispatched)
- ISP_apply_mode_config_a_wrapper (0x000afaa0) — mode apply entry wrapper: init + setup + config + ISP_apply_mode_config_a
- FUN_000b07c4 → ISP_commit_config_block (full ISP config commit: validate + FUN_000b6ef8 + FUN_000b1e30 + apply steps)
- FUN_000afea4 → ISP_apply_config_conditional (offset calc + conditional commit via FUN_000b6ef8)
> NOTE: stream-start handlers and mode-config wrappers are dispatched by INDEX from function-pointer tables (no static xrefs). The layer above (command router → these handlers) is table-driven — same resolution limit as ADF. The linear, labelable chain ends at ISP_set_active_window_and_tuning.


- ISP_apply_mode_config_b (0x000afad0) — mode apply entry (variant b), no return
- ISP_apply_stream_pipe (0x000afc70) — counter-driven multi-stage stream/pipe apply (iterates N sub-streams via PTR_LAB_000afdd0 counter vs stage count 0xafde8), conditionally calls set_active_window

## ISP tuning/geometry call chain (resolved 2026-08-03)
ISP_apply_mode_config_a/b  or  ISP_apply_stream_pipe
  → ISP_set_active_window_and_tuning        (geometry + ROI calc, regs 0x185/0x191/0x1b6)
      → ISP_tuning_apply_for_stream         (build config, alloc hw ctx)
          → ISP_tuning_stage_commit         (write reg 0x1e + apply wrapper + ZIMA_DVENC_launch)
              → ISP_tuning_stage_apply_wrapper → ISP_apply_tuning_0x40_0x54 (register blasters)
              → ISP_tuning_commit_and_launch (reg 0x1e + encode trigger)

- ISP_tuning_stage_reset (0x000a3814) — writes reg 0x4a (block 0x02), stage=0, then ISP_tuning_stage_commit
- ISP_tuning_stage_commit (0x000a35b8) — orchestrates one tuning stage: setup hw ctx (PROISP_get_hw_ctx_ptr), write reg 0x1e (block 0x06), ISP_tuning_stage_apply_wrapper, ZIMA_DVENC_launch on error
- ISP_tuning_commit_and_launch (0x0009f4e4) — writes reg 0x1e (block 0x06) + conditional ZIMA_DVENC_launch
- ISP_tuning_stage_apply_wrapper (0x006a6fb6) — calls ISP_apply_tuning_0x40_0x54 + buffer cmp/validate
- ISP_tuning_apply_for_stream (0x006a88c8) — TOP-LEVEL: builds tuning config from param struct (window/crop math via FUN_006b46xx), alloc hw ctx, calls ISP_tuning_stage_commit per stage
- ISP_apply_tuning_0x40_0x54 (0x0009f6e8) — blasts 21 regs 0x40..0x54 (block 0x09 sub 0x03) from byte buf
- ISP_apply_tuning_0x7c_0x99 (0x0009fe18) — blasts 30 regs 0x7c..0x99 from byte buf
- ISP_apply_tuning_0xf3_0xf4 (0x000a0aec) — 2 regs 0xf3,0xf4
- ISP_apply_tuning_0xf9_0xfb (0x000a0b48) — 3 regs 0xf9..0xfb
> Pattern: every `ISP_apply_tuning_0xNN_0xNN` is a contiguous-register blast helper (block 0x09 'W' 0x03). ~60+ such helpers back the `ISP_write_stage_0xNN` family. The register ranges map to ISP processing sub-blocks (NR/defect/shading/color/etc).

## ADF subsystem (NEW — discovered 2026-08-03)
- Audio/Digital-video Framework: message-passing component layer for AV routing.
- String block at 0x92e000..0x932000 with `[ADF][IN]`, `[ADF][OUT]`, `ProcMsg*`, `AdfSetSourceCtrl`, `AdfTransferAdjAudioCtrl`, `SET_INPUT`/`SET_OUTPUT`/`PRO_SET_*` tags.
- Biz<->Avio<->Aip message broker: HDMI input, shoe mic, HP monitor, rec-level, external codec, mixer.
- Dispatch is TABLE-DRIVEN (string ptrs stored in data tables, accessed via base+index) — Ghidra xref cannot resolve statically. To label ADF handlers, need either: (a) find the message dispatch vtable and trace, or (b) GhidraScript bulk-label by string-tag. NOT yet labeled (deferred).
- Note: av-cam.bin is the ISP/codec RTOS module; EXIF Make/Model/Software strings are NOT in this binary (no `ZV-E10` literal; only one `SONY` at 0xA14494 = DataflowInfraSender identifier, not EXIF Make). EXIF strings live in a different firmware blob.

## Firmware-modifiability proof (2026-08-03)
- av-cam.bin is PLAINTEXT (not encrypted) and UNSIGNED (patch survived reboot, no revert).
- String patch Ver.1.0.0->Ver.9.9.9 @0x9F9586 + ZIMA_AVC->MOD_ZIMA @0x9F95B3 verified on-disk (md5 1deaf700), persisted across reboot, then restored to orig (cdcae9d4).
- Conclusion: camera reads /system/av-cam.bin from disk at boot; no signature/integrity gate. Patch feasibility for OpenGate confirmed at the crypto level (only HW buffer limits remain).

## Progress Summary
- ISP/DFE: 60 stages + DFE subsystem labeled ✓
- ISP tuning-family: commit/apply/reset + ~4 register-blast helpers labeled ✓ (more helpers exist, pattern established)
- CODEC V: entry path + state machine + encode-param helpers + ZIMA_DVENC_launch + 5 stream profile dispatchers ✓
- CODEC A: audio handler (16 registers) ✓
- SDF JPEG: router ✓
- DFE container & stage functions labeled ✓
- ENCHANDLER resolved (`DFE_apply_pipeline_registers`) ✓
- ADF subsystem discovered (audio/AV routing) — deferred labeling (table-driven) ✓ identified
- Per-stage float table mapping & C++ rewrites updated ✓
- Function prototypes and variable renames applied live via Ghidra MCP ✓
- Firmware modifiability proven via live patch + reboot ✓
- 17,771 total runs >=16 float32
- 3 directly pointer-referenced: 0x1055d8c (n=224 gain), 0x105a0e4 (n=374 ISO), 0x105ce80 (n=735 exposure)
- 6,310 real coefficient tables (AWB 16-field matrices, exposure/ISO/gain ramps, shading)
- 11,461 huge/NaN, 0 zero-filled
- No direct uint32/uint64 pointers — indirection via LIROSeq formatters

## ENCHANDLER (resolved)
- FUN_00423bac → `DFE_apply_pipeline_registers` — 9,920 bytes, 6 tree validations + DFE block 0x68 register submit loop (cmds 0x30..0xba). Fully decompiled and renamed in Ghidra.

## Open Gate 3:2 Feasibility & 4 Software Patch Points

> [!WARNING]
> **Superseded 2026-09-26 — see `OPENGATE_PATCH_SURFACE.md`.** The four patch
> points below were re-checked with `retool consts` and **the constants are not
> present in code as described.** 2160 and 3376 are never encoded as Thumb
> instruction immediates anywhere in the image; they live in packed data
> descriptors of the form `(height << 16) | width`. The claims about 3376
> (patch point 1) and 135 (patch point 3) are not supported by the binary at
> all. The real 4K surface is a mode table at `0x89dae0` and a per-stream
> config table at `0x8c4440`. Treat the list below as a hypothesis that failed
> verification, not as a plan.

1. `ISP_dimension_select` (`0x0008a5d0`): Sensor readout Y-window (change `3376` -> `4000`).
2. `ISP_dimension_setup` (`0x0008c14e`): ISP scaler target output height (change `2160` -> `2560`).
3. `CODECV_write_config_0x651_0x661` (`0x000c46dc`): H.264 macroblock height (`mb_height` 135 -> 160).
4. `encode_param_validate_pack` (`0x004fb694`): Frame height assertion validator (relax `2160` limit).

> [!WARNING]
> Live flashing requires investigating DDR frame buffer RAM allocation sizes (`FUN_0069bc7e` / RTOS memory manager) to prevent RAM buffer overflow panics, ISP hardware FIFO line buffer limits, and container signature bypasses. The buffer-size fields in the per-stream config table (`0x000d9700` = 890,112 at `0x8c446c`) are the concrete place to look first.

## C++ rewrites in pipeline.md
Clean C++ rewrites of key functions:
- ISP_WriteRegister, PROISP_CommandRouter, LIROSeq_CommandHandler, LIROSeq_TuningBlockHandler
- VideoEncode_StateMachine, VideoEncode_ExecutionWrapper, VideoEncode_Start
- ApplyCodecVGammaAndConfig, capture_gamma, chromaPhase, shading_correction
- applyDFEConfig, applyAudioEncoderParams
- ISP_write_stage_0x4b, ISP_write_stage_0x35, ISP_write_stage_0x46, DFE_apply_pipeline_registers
- DFE_write_stage_0x2e, LIROSeq_video_stream_reg_apply, CODECV_stream_type_dispatch
- encode_param_validate_pack, encode_param_submit

## Progress Summary
- ISP/DFE: 60 stages + DFE subsystem labeled ✓
- CODEC V: entry path + state machine + encode-param helpers + ZIMA_DVENC_launch + 5 stream profile dispatchers ✓
- CODEC A: audio handler (16 registers) ✓
- SDF JPEG: router ✓
- DFE container & stage functions labeled ✓
- ENCHANDLER resolved (`DFE_apply_pipeline_registers`) ✓
- Per-stage float table mapping & C++ rewrites updated ✓
- Function prototypes and variable renames applied live via Ghidra MCP ✓
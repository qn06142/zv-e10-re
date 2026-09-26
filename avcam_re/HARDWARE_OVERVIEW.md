# Sony ZV-E10 hardware and firmware — consolidated overview

Single reference for the hardware as established from `dumps/av-cam.bin`
(17,289,388 B, SHA-free working copy). Supersedes the narrower documents:
`HARDWARE_TOPOLOGY.md`, `REGISTER_WRITE_PATH.md`, `SUBSYSTEM_MAP.md`,
`MODULE_CONTRACT.md`, `FEATURE_GATES.md`, `TABLE_PURPOSE_CORRECTION.md`.

All addresses are **file offsets**; runtime VA = offset + `0x635c6000`.

---

## 1. What the binary is

| | |
|---|---|
| Load base | `0x635c6000` (vectors are absolute pointers into that window) |
| Plaintext / signed | plaintext, **unsigned** — an earlier string patch survived reboot |
| Size | 17,289,388 B (`0x107D0AC`) |
| Header | `b 0x30` at `0x0`; `"ORIL"` magic at `0x4` |
| Vectors | eight self-contained pointers at `0x10..0x2c` → `0x58, 0xb4, 0x68, 0x78, 0x88, 0x98, 0x9c, 0xa0` |
| Code | 66,805 functions — 63,643 `arm16` (Thumb) + 3,162 `arm32`; median 28 B |
| Model identity | **none in the image.** No `ZV-`/`ILCE-`/`DSC-` string, and the firmware version `30110_05.2025031501` comes from `dumps/version.txt`, not this file |

It is **not a small driver** — at 66,805 functions with 1,585 `[ADF]` control-plane
strings it is effectively the main application running on the T-Kernel/LIRO
RTOS. That it carries no model identifier is consistent with the RTOS selecting
the per-body path at load time.

Sibling bodies `BOL310`, `BOL373`, `BOL473` appear in three pipeline stage
names, i.e. this is a shared multi-model build.

---

## 2. Topology

```
                    ┌──────────────── RTOS (T-Kernel / LIRO) ────────────────┐
                    │  Genlock · DFS frame-rate · SGC1 imager power · PLL  │
                    └───────────────────────────┬───────────────────────────┘
                                                │
  image sensor ──MIPI CSI-2 (D-PHY)──┐          │
              └─ComboPHY SLVS-EC─────┴─▶ DFE ──┴─▶ APL ──▶ ISP / ZIMA
                                    own DDR3        │        DVENC / DVDEC
                                   power rail      │
  system DDR ◀── DMM / OSAL ── unit alloc by mode id
  uc_SRAM   ◀── 3D LUT staging
  audio     ◀── SA AUD DRV / CODEC A / Audio Frontend
  lens      ◀── LIF (BL/HS power stages) + /lens/*.bin
  control   ◀── ADF · SDF · IDT · TRK · Biz · Avio · AIP · UIPC
```

**Sensor input — two paths coexist, selected per model.** MIPI CSI-2 receiver
(`CSI-2 Rx Link LaneEnable`, `MIPI D-PHY unknown id`, `MIPI Tx %d %d`) and
ComboPHY carrying SLVS-EC (`ComboPHY SLVS-EC PLL Lockup`, `ComboPHY MIPI
LaneStart`). Lane programming is visible as a register group:
`CLK%x XRST%x ILANE_EN%x … IBW%x … ILANESEL%x … ICONFIG4LANE%x`.

**DFE** (Digital Front End) has **its own DDR3** and a dedicated rail — `DFE DDR3
Init`, `waiting for DFE DDR power supply`. **APL** manages units and moves DDR
through `apl_mov_set_aic` with `R0(DDR)`, `R2(DDR)`, `W2(DDR)`.

**ZIMA** is the dedicated video codec engine: `ZIMA DVENC` (99 tagged strings),
`ZIMA DVDEC` (121), plus `ZIMA_AVC`, `ZIMA JPEG`, `ZIMA_LPCM_DEC`, with
per-instance numbering (`GetZimaNo`).

---

## 3. Memory

| region | evidence |
|---|---|
| system DDR | `path [0: NULL, 1: Audio Frontend, 2: DDR]`; `AsyncGetUnitMaxMemNumber` |
| DFE DDR3 | `DFE DDR3 Init osal_usleep` |
| uc_SRAM | `CC: Copy3DLUT uc_SRAM=[%d], SRAM addr=0x[%X]` — a microcontroller-side SRAM used to stage 3D LUTs |
| allocation | DMM/OSAL, `ERR_OSAL_UIPC`, `ERR_DMM_RET_CODE`, units sized **by mode id** |

---

## 4. Register programming — the part that matters for modification

```
ISP_WriteRegister       0x7e8e88  Thumb   1,983 bl call sites
ISP_WriteRegister_0x68  0x7e8eb8  Thumb   sibling, hardcodes block 0x68
 └─ core                0x44038c  Thumb   296 B — the implementation
      ├─ 0x44033c, 0x7e90dc          helpers
      ├─ 0x5223ec    ARM   5,004 xrefs   bit-field packer
      └─ 0x522ad0    ARM               ZIMA_DVENC_launch, cmd 0xd20
```

**Writes are not MMIO stores.** They accumulate in a per-context shadow and are
committed in batches:

| access | meaning |
|---|---|
| `ctx + 0x1900` | shadow area |
| `ctx + 0x1908` | **pending/dirty flag** (set by the helper at `0x7e8eb0`) |
| `ctx + ((block+0x300)<<3) + 4` | per-block state byte |
| `ctx + block*24` | **24-byte per-block descriptor** (stride `0x18`) |
| commit | `0x522ad0` (`ZIMA_DVENC_launch`, `0xd20`) |

Consequence: **there is no register address in the image to patch.** A value the
hardware needs must be changed in the shadow descriptor or in the code that
fills it, and the commit must still fire. The register-file base is obtained at
runtime; no literal names it, which is why a scan for out-of-image addresses
returns only artifacts.

**Block id space** (recovered from the instruction stream at each call site):

| block | calls | share | role |
|---|---|---|---|
| `0x57` | 1,168 | 59% | ISP stage writes |
| `0x68` | 747 | 38% | DFE container writes |
| `0x26` | 13 | <1% | |
| 35 others | 1–2 each | <1% | singletons |

96% of writes go to two blocks. The `+0x300` state indexing implies the block id
is a dense index into a per-context table.

`0x5223ec` is one of the most-referenced functions in the image; in ARM it
extracts bit ranges (`ands ip, r0, #3`) to pack several logical fields into
hardware words.

---

## 5. Video mode resolution

Table at **`0x89DADE`**, stride 16, 19 records, terminator `id = 0xFFFFFFFF` at
`0x89DC1C` (= base + 16·19 + 14). Record:

| offset | field |
|---|---|
| +0 | u16 padding (0 throughout) |
| +2 | u32 `(height << 16) \| width` |
| +6 | u32 flags — 1 for records 0..13, 0 for 14..18 |
| +10 | u32 family — 2 and 3 for the two 4K readouts, 1 otherwise |
| +14 | u32 mode id — `0, 19, 1, 20` for 4K, then 3..18 |

The four 2160-height records sit at `0x89DAE0`, `0x89DAF0`, `0x89DB00`,
`0x89DB10`; their height half-words at `+2` within each.

Its **only** consumer is the memory manager at `0x3ab074` (DMM/OSAL strings
around it), and that consumer tests the returned id against `{0, 19, 1, 20}` to
raise a distinct "4K" flag at `[r4+0xc0]`. So the table sizes memory and marks
4K modes; **it does not set the sensor readout**, which is why editing its
height changes nothing observable. Capture geometry is programmed by a register
write elsewhere.

---

## 6. Codecs

| | decoder | encoder |
|---|---|---|
| code region | `0x0a0000`–`0x0b0000` (155 decode fns, **0** encode) | `0x0d0000`–`0x0e0000` (62 encode, 5 decode) |
| state machine | `fcn.000bb63c` @ `0xbb63c`, 180 B, 17 states | `fcn.0008f888` @ `0x8f888`, 1,070 B, 11 states |
| log tags | **116** distinct `DEC_*` | **63** distinct `ENC_*` |
| framework | `VDF`, `DECHANDLER`, `IMLDECSTAT` | `VEF`, `ENCHANDLER`, `IMLENCSTAT` |
| engine path | `ZIMA DVDEC` | `ZIMA DVENC` |

Decode:encode = 219:173 = **1.27:1** on the 1,107 functions (1.7%) that
reference a string directly. Coverage is stated, not hidden: the other 98% call
helpers that do. Nearest-neighbour propagation was implemented and rejected —
median seed distance 9 KB, and it inverted the ratio.

Neither codec touches any data table; their configuration arrives as literals at
each call site through the two register blocks.

---

## 7. Pipeline stages — 86 named

The image pipeline's own vocabulary. Selected:

```
Stage_Apollo            Stage_Adjust            Stage_CaptureInit
Stage_ReadExecute       Stage_ReadSectionBranch Stage_ExposureInit
Stage_OpdBranch_BOL310  Stage_TDReadExecute_BOL373
Stage_OpdBranch         Stage_TDReadExecute    Stage_DfeRawTrans[SnrBranch]
Stage_Motionshot        Stage_MotionShot_Analysis   Stage_DualRec
Stage_Decomp[4SA_ForDualRec]  Stage_ExpandDeconvParam  Stage_LoadDeconvPsfTbl
Stage_ExpandSpicaParam  Stage_Deconv            Stage_Develop[Art]
Stage_BDRO              Stage_BFNR              Stage_ResizeHV
Stage_Rch_Rcv[_Trim|_Dist|_SameArea|_NormTrim|…]  Stage_Rcv_Dist*
Stage_Panorama[FaceMeta]      Stage_FaceDetect[PreReviewBranch]
Stage_AutoFraming[_Branch]   Stage_EncodeJpeg
Stage_Raw / Stage_RawPlay[Init]  Stage_Orientation  Stage_StillDate
Stage_SACC              Stage_SA_SPICA          Stage_STAR
Stage_THMCopy           Stage_SCNEnc[WithTHM]   Stage_CaComm
Stage_Notify*           Stage_CaptureInit       Stage_ExpandDeconvParam
```

Note: **zero occurrences of `IBIS`, `PixelShift` or `PIXEL` in the image.** The
ZV-E10 has no IBIS, so Pixel Shift Multi Shot is impossible regardless of what
`OPD` might stand for. The OPD / MotionShot / BDRO stages belong to other bodies
in the shared build.

---

## 8. Control plane and features

Log-tag prefixes give the internal split, with `[ADF]` (1,585) the control
plane and `[SDF]` (490), `[IDT]` (401), `[TRK]` (355) around it.

Top-level camera mode enum (from the module's own API strings):
`IDLE, PB, EE, HIGHLIGHT, HIGHLIGHT_REC, DFS, MIC_ADJUST, DOWNCON, CHK…`

Recording / delivery modes — 17 entries at `fcn.0008f5f8` (`0x8f5f8`), low bit
is a variant selector (audio / no-audio):
`SD_SAKUHINKA, HD_SAKUHINKA, HD_SAKUHINKA_NOAUDIO, STREAMING, ENC_PROXY,
GEARED_ENC, HILGT_PB_NOAUDIO, NAMESURO, BGMCHK, SLIDESHOW_NOAUDIO`

`FC/Feature/` is a real per-feature module directory — 21 files, 38 `Feature*`
classes, with the enable mechanism named in RTTI as
`tcub::feature::{FeatureConfigrator, StaticFeatureConfigrator,
DynamicFeatureConfigurator}`. `FeatureCaptureDummy` / `DataDummy` /
`fc_feature_capture_dummy.cpp` exist, i.e. a stub is compiled in — the shape of
a model-gated feature.

The module ships **155 self-documenting API parameter strings** (`- argN: name
[enum]`), including `state [0:HdmiInput Disable, 1:Enable]`, audio input
`[0:Off, 1:Int, 2:Shoe, 3:Zoom, 4:Wireless, 5:Ext, 6:Line, 7:XLR-BOX]`, audio
output as a `1/2/4/8` bitmask, and `streamId [3:ID0+ID2]`.

---

## 9. Tuning data — the hard limit

17,771 runs of ≥16 float32 and ~6,310 coefficient tables (AWB matrices,
exposure/ISO/gain ramps, shading, lens aberration). The ISP is algorithms
**plus** per-unit calibration that cannot be derived, only reused. This is the
main reason a from-scratch replacement is unrealistic while targeted
modification is not.

---

## 10. Known hardware limits

- `FW: Error : hsiz_arc > 3520 is not supported!` — a hard width ceiling
- `Ch %d is not supported. Change target ch to 0.` — channel limit
- 4K heights are 2160; no 2560 readout exists in the mode table
- BOL310 has `ImagerSleep` forcibly removed (`0x32dfc8`)
- ISP per-function enable check at `0x1e31fc` (FuncID/FuncType, error `0x230`)

---

## 11. Confidence summary

| claim | confidence |
|---|---|
| peripheral inventory (§2) | **high** — the module names its own hardware in log strings |
| encode/decode split (§6) | **high** — two independent methods agree |
| register-write model (§4) | **high** — read from the code path |
| mode table layout (§5) | **high** — terminator position and caller id check both confirm |
| any specific register address | **none** — no MMIO literals exist; earlier "hardware page" results were a resolver bug and are withdrawn |
| descriptor byte meanings, register-file base | **unknown** — the concrete next target |
| BOL310 → retail name | **unresolvable here** — needs Sony's model-code list, not this file |

---

## 12. Where to go next

1. **Descriptor layout** — the 24 bytes at `ctx + block*24`, and the register-file
   base (follow `ctx` back to its allocation).
2. **Feature enable bitmask** — reach `StaticFeatureConfigrator`'s vtable via its
   RTTI name and follow it to the data it reads. This converts the ranked
   candidate list in `FEATURE_GATES.md` into offsets.
3. **ISP FuncID gate** — `0x1e31fc`; what turns a FuncType on.

## Reproducing

```
retool.cmd subsystems avcam --blocks     # encode/decode regions
retool.cmd region    avcam 0x89dade      # is a data region referenced
retool.cmd xrefs     avcam 0x7e8e88      # the register primitive
retool.cmd disasm    avcam 0x44038c -n 40   # the write core
retool.cmd disasm    avcam 0x5223ec -n 12 --arm   # ARM-mode bit-field packer
retool.cmd strings   avcam Configrator   # the enable mechanism
```

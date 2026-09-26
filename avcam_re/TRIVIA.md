# Trivia: things this firmware did not obviously have in it

Findings that were **not** predictable in advance, and several that overturned an
earlier assumption of ours. Nothing here is a to-do; it is a record of what the
binary turned out to contain, so that a later reader does not "discover" it again
or assume it is a mistake.

Addresses are file offsets unless stated otherwise.

---

## 1. The build is shared across product lines, and it is not subtle about it

There is **no retail model identifier anywhere in 17 MB** — no `ZV-`, no `ILCE-`,
no `DSC-` product string. What it does contain spans several lines:

| code | line |
|---|---|
| `BOL310`, `BOL373`, `BOL473` | mirrorless bodies (`Stage_OpdBranch_BOL310`, `Stage_TDReadExecute_BOL373`) |
| `BOL1G`, `BOL2G` | two more (`api_EC_CaptureRawTDShutterJudge returns OFF on BOL1G`) |
| `DSC00001` | Cyber-shot compact |
| `PX280` | PX professional camcorder |

92 distinct `Stage_*` names. A compact, a camcorder and mirrorless bodies in one
image, with per-body conditionals baked in — e.g.
`FW: ImagerSleep not available on BOL310. force replace DISABLE`.

**Consequence:** the presence of a feature in this image says nothing about
whether this body offers it. See §2.

## 2. Golf Shot is in the firmware, and this body does not wire it up

84 `GOLFSHOT` strings and a complete pipeline:

```
[ADF][SAN] StartGolfShot / AnalyzeGolfShot / StopGolfShot    sound analysis
[GOLFSHOT]SA_BGEST      background-noise estimate
[GOLFSHOT]SA_LPF        low-pass filter stage
[GOLFSHOT]SA_SSP        signal processing
FW: Stage_EncodeJpeg_GolfShot_THM       a real pipeline stage
FW: GolfShotJpegStream                  it produces a clip
[ADF]CheckShotDetectInDetectRange / shotDetectVfcSub exist|not exist
```

RTTI names exist for three `AdfSoundAnalyzer{Start,Analyze,Stop}GolfShot`
classes, so they were compiled in with virtual methods — real code, not leftover
strings. Golf Shot is an **AX-series camcorder feature**; this body does not wire
it up, which is why it is unfamiliar.

This cost us an error. An earlier commit asserted Golf Shot was a ZV-E10 feature
the user could enable. That was recall presented as fact and is withdrawn. The
general lesson is recorded as its own entry, §11.

## 3. Dummy implementations are compiled in *alongside* the real ones

This is the mechanism behind "compiled in but not wired up", and it is explicit
rather than implied:

```
13SaDriverDummy                        21AdfSoundAnalyzerDummy
N6Camera2FC19FeatureCaptureDummyE      N6Camera2FC9DataDummy8FaceDataE
N4tcub5debug24DummyAvBizCmdExecutionerE
N4tcub5debug24DummyAvBizPinExecutionerE
N4tcub5debug28DummyAvBizCmdCompExecutionerE
N3VEF30PathProcessExtVideoCommonDummyE
30AvcDecAudioModuleStateDecDummy        N8TanzTool7DummyIpE
[CdDummyAvCtrlMemoryManager]            Stage_DummyPreReview
SB_Async/SB_ZpdFittingTbl_Dummy.cpp     AllocSetDummyStdYc
[ADF]Dummy Class                        [ADF]ExecDummySubsystem mId uT op uH %x %x %x %x
```

Note `AdfSoundAnalyzerDummy` sitting directly beside the real
`AdfSoundAnalyzer*GolfShot` — a dummy and a real implementation of the same
interface, chosen at runtime. Also `Camera::FC::DataDummy::FaceData`, i.e. a
dummy face-data implementation, and a whole `tcub::debug` namespace of dummy AV
business executioners.

**The dummy path is explicit in code.** A dummy ADF class does this:

```
0x481cc  push {r0, r1, r2, lr}
0x481ce  ldr  r0, [0x481ec]     ; "[ADF]Dummy Class\n"
0x481d2  bl   fcn.00699e48      ; log it
0x481d6  bl   fcn.00053eb8
0x481dc  ldr  r1, [0x481e8]     ; = 0x20506000
0x481e2  bl   PROISP_CommandRouter
```

It logs, then routes a no-op command. `0x20506000` occurs **exactly once** in the
whole image — it is that path's private "do nothing".

## 4. `PROISP_CommandRouter` is a structured command space, not MMIO

Because every call site names a peripheral, sweeping the first argument maps the
ISP command surface. 756 command IDs recovered from the call sites:

| group (`0x20GG`) | calls | | group | calls |
|---|---:|---|---|---:|
| `0x2000` | 174 | | `0x2030` | 43 |
| `0x2010` | 118 | | `0x2040` | 80 |
| `0x2011` | 78 | | `0x2041` | 47 |
| `0x2012` | 59 | | `0x2042` | 1 |
| `0x2013` | 72 | | `0x2050` | 32 |
| `0x2014` | 7 | | `0x2001` | 3 |
| `0x2020`–`0x2028` | 1–23 each | | | |

20 groups, 313 distinct low-16-bit indices inside them. All 756 fall inside
`0x2000xxxx`–`0x2050xxxx`. These are **command IDs, not addresses** — which is
why nothing here appears in any MMIO scan.

## 5. The "hardware commit" was `memset`

`0x522ad0` was named `ZIMA_DVENC_launch` (command `0xd20`) and cited as the point
where the register-write path commits to hardware. It is the C library's ARM
`memset` — fills `0xFF`, replicates the byte with `orr lsl 8/16`, unrolled
`stmge ip!, {r2,r3}`. 5,459 xrefs. `0x5223ec` was named `encode_param_submit` and
is `memcpy`. Both names were auto-scraped and never checked; one had rizin's own
*speculative* nearby-string comment recorded as if it were a real symbol.

rizin's signature matching, once the names were corrected, independently printed
`void *memset(void *s, int c, size_t n)` and
`void *memcpy(void *s1, const void *s2, size_t n)`.

## 6. The register file is addressed by logical offset plus a bank bias

Not one MMIO address appears at any file offset. Call sites pass a small logical
offset (`0x2098`, `0x2028`, …) and a 12-byte accessor adds a bank constant:

```
0x7f534a  sub  r0, r0, #0x0cc00000     -> 0xf3400000
0x7f5362  add  r0, #0xf3000000 / #0x400000  -> same value, two instructions
0x7f5394  add  r0, #0xf2000000 / #0xa30000  -> 0xf2a30000
```

Banks: **`0xF3400000`, `0xF2A30000`, `0xF2A00000`**, all outside the firmware's
own load window. The two spellings of `0xF3400000` exist only because it is not
encodable as a single Thumb modified immediate while `-0x0CC00000` is.

## 7. Every hardware write is mirrored

`0x45db14` stores to the device, reads the value back, then writes that read-back
through a global pointer at file offset **`0x0107CB26`**. So there is a single
4-byte global through which every register write is observable.

## 8. The firmware contains its own typos and its own Japanese

- `CACHE_REC_RECODING` — "recording", misspelled, and it is the state the camera
  actually sits in while recording.
- `- arg1:Path [0:Idle, 1:PB, 2:EE, 3:DownConv 4:HighLight 5:Sakuhin]` —
  録画 *sakuhin* = recording, preserved in the path enum, where **5** is the
  recording path.

## 9. Enable/disable is expressed as a valid flag beside the value

Two independent instances, which is what makes it a convention rather than a
coincidence:

- ZIT SA feature gate: `enabled ⟺ (ctx+4 == 1) || FuncType == 0`
- encoder parameters: `.is_valid_qp_clip_min_i_pic` beside `.qp_clip_min_i_pic`,
  and the same for max and for I/P/B pictures

Also `skip_frame_for_bit_rate_and_qp` — the encoder **drops frames** when the bit
rate overshoots.

## 10. Things that are present but cannot work on this body

- **No IBIS.** Zero occurrences of `IBIS`, `PixelShift` or `PIXEL` in the image.
  Pixel Shift Multi Shot is impossible regardless of what `OPD` might mean; the
  OPD / MotionShot / BDRO stages belong to other bodies in the shared build.
- **High frame rates are fully implemented — a claim we got wrong.** See §13.
- **A hard width ceiling** the module states itself: `hsiz_arc > 3520 is not
  supported!`
- **The mode table's only consumer is the memory manager** (`0x3ab074`), which
  sizes buffers and marks 4K. It does not set sensor readout, which is why
  editing its height changes nothing observable.

## 13. High frame rates are fully implemented

**We asserted the opposite and were wrong.** The claim "no 4K60 / high frame
rates are not present" was inferred from the mode table at `0x89DADE` topping out
at 2160 lines — but that table is the **memory-sizing** table, consumed only by
the memory manager. It has never carried frame rates. Reading recording
capabilities off it was the same category of mistake as editing its height and
wondering why nothing happened.

Frame rate lives somewhere else entirely, and it is thorough:

```
enc/sfmc_enc_timing_i_a1_diadem_normal_120p100p.cpp
[TIMING120p]start_timing = %x
[TIMING120p]vfc:0x%X,gop:%d,start_timing:0x%X,enc_pic_count:%d
[TIMING120p][num_of_frames:%u][in_param.num_of_encode_picture:%llu][in_param.sysv_rate:%u]
[TIMING120p][THM] unexpected marking_type(%d)
[TIMING120p][CUT] unexpected marking_type(%d)

enc/sfmc_enc_timing_i_a1_diadem_normal_240p200p.cpp
[TIMING240p] ... the same set
```

A **dedicated timing state machine per high-frame-rate mode**, with `THM` and
`CUT` frame-marking types — the marking that assembles a clip. Alongside the
normal-rate ones (`[TIMING 24p]`, `[TIMING 30p]`, `[TIMING 60I]`).

There is also an explicit high-speed lifecycle:

```
STATE_HS_STOPPING
STATE_YC_PIN_WAITING_ON_HS_RECEIVED_START_COMP
[TIMING]Waiting for YC Pin for HS.
DEBUG:[INT SYS HS] ... register / unregister / change_mode / Cycle / PreVfc
```

and frame-rate conversion lives in the record state machine itself:

```
sfmc_enc::sfmc_enc_state_cacherec::convert_frame_rate_value(__uint8_t)
sfmc_enc::sfmc_enc_state_normal::convert_frame_rate_value(__uint8_t)
```

The frame-rate name table carries `119_88`, `200` and `239_76` next to
`23_976 / 29_97 / 59_94`. `HS` also appears as `MODE_HIGH_SPEED`, `tsk_syshs`,
`int_syshs`, `SYSV][HS]`, and `Time24Hz/25Hz/30HzHighSpeedModifier`.

So 120p is not merely permitted — it has its own timing module, its own state
machine, and frame-marking for clip assembly.

## 14. How we got things wrong

Kept because the failure modes recur.

- **Recall presented as fact.** Golf Shot was attributed to the ZV-E10 on the
  strength of low-confidence product knowledge, in a document that was otherwise
  evidence-based. The binary had never claimed it.
- **Auto-scraped symbol names inherited a guess as a comment.** `ZIMA_DVENC_launch`
  carried rizin's speculative "nearby string" annotation; downstream prose then
  cited it as the hardware commit (§5).
- **Adjacent functions read as one.** The "ISP gate at 0x1e31fc" was actually the
  tail of the previous function; the gate is at `0x1e31ee`–`0x1e31f2`.
- **A span-based xref search matched neighbouring strings** and produced
  convincing, wrong reference lists. Exact matching only.
- **A hand-rolled Thumb modified-immediate expansion** gave `0x04C00000` where
  rz-asm gives `0x0CC00000` for the identical bytes.
- **A BL decoder reading J1/J2 from the wrong halfword** found zero call sites and
  reported success.
- **A template match comparing against a wildcard byte** instead of skipping it,
  which matched nothing — including its own template site.
- **Reading recording capability off the memory-sizing table.** The mode table
  has no frame-rate field and never did; concluding "no high frame rates" from
  it was reading the wrong table entirely (§13).
- **A "hardware page" histogram was published and then withdrawn** as a resolver
  artifact. The banks finally found in §6 are unrelated to those values and came
  from a different derivation.

## 12. Small oddities worth keeping

- `[ADF]Dummy Class` is the only string in the image ending in a literal `\n`
  inside a log call.
- `fc_alg_transfer_to_animal.cpp` and `fc_api_smile_shutter.cpp` — 120 `FC/`
  modules in total, a full face/object-detection framework.
- A test buffer overflow check exists and is exercised:
  `[TSKVIDENC][GET_HW_LOG][ENC]: channel_id(%d) is not within the range`.

## Reproducing

```
retool.cmd strings avcam GOLFSHOT      # §2
retool.cmd strings avcam Dummy         # §3
retool.cmd disasm  avcam 0x481cc -n 10 # §3, the dummy path
retool.cmd disasm  avcam 0x7f534a -n 24 # §6, the accessor table
retool.cmd disasm  avcam 0x45db14 -n 6 # §7, the write + trace mirror
retool.cmd disasm  avcam 0x522ad0 -n 20 --arm  # §5, memset
retool.cmd strings avcam CACHE_REC     # §8
retool.cmd strings avcam qp_clip       # §9
retool.cmd strings avcam SuperSlowMotion # §10
```

Addresses and offsets from §3–§4 were recovered by a one-off sweep of
`PROISP_CommandRouter` call sites; that sweep is not yet part of `retool`.

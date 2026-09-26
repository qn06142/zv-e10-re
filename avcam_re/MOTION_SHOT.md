# Motion Shot: what it is and how it is gated

Addresses are file offsets. `ctx` is the per-capture context; `cap_mode` is
`ctx[0x90]`.

**What Motion Shot is, on the evidence:** detect a moving subject and
automatically record a clip of it. The detector is *vision*, in the face/detection
layer, and it produces *video*:

```
Camera::FC::Alg::HumanMovingArea / HumanMovingAreaImpl
MovingObjectOperator            "No moving object is detected by FC...."
Stage_Motionshot.cpp            Stage_MotionShot_Analysis        MotionShot_Base
Stage_Rcv_DistResize_MotionShotMiniYc
NS_SCALAR_INFRA MotionShotVideoManager / MotionShotVideoSequence
    ...StageExecSAE / StageExecSRCE / StageExecRCE / StageExecPost / StageWaitSAComp
FW: SET_MOTION_SHOT_MODE[%d:]    MS_DUMP_RAW_PRELIGHT_{LUMINUS,NONLUMINUS}
```

Whether Sony markets it on a ZV-E10 is **not established** — nothing in the image
says so, and it should not be assumed either way.

## The chain, end to end

```
setting        motion_shot_mode                  one of 221 sequencer-validated
validator      CheckSetMotionShotMode           one of 210
setter         SET_MOTION_SHOT_MODE[%d:]         ref 0x6590fe  -> stores to ctx+0xd4
per-mode       fcn.00316ef8                      cap_mode (ctx[0x90], 0..33) -> value
   case 5:     ldr.w r3, [r4, 0xd4] ; cmp r3, 1     <-- motion shot lives in cap_mode 5
gate           ctx+0x10c  zeroed unless cap_mode == 5
entry          sa_func_MOTIONSHOT_{init,acquire,start,release,exit}
pipeline       Stage_MotionShot_Analysis -> MotionShotVideo* -> clip
```

## The capture-mode gate

`ctx+0xd4` holds the mode value; `cap_mode` selects the context in which it is
consumed. A separate function then clears the *request flag* when the capture mode
is not the allowed one:

```
0x317128  ldr.w r3, [r5, 0x10c]      ; request flag
0x31712c  cmp   r3, 1
0x31712e  bne   0x317144
0x317130  cmp   r4, 5                 ; allowed only in cap_mode 5
0x317132  beq   0x317144              ; allowed -> skip
0x317134  ldr   r0, [0x3172e4]        ; "FW: Mshot mode forced off! cap_mode:%x"
0x317136  mov   r1, r4
0x31713a  bl    fcn.003a98c4
0x31713e  movs  r3, 0
0x317140  str.w r3, [r5, 0x10c]       ; <-- request zeroed
```

Two siblings in the same block, same shape:

| feature | flag | flag value | allowed `cap_mode` | message |
|---|---|---|---|---|
| **Mshot** | `ctx+0x10c` | 1 | **5** | `FW: Mshot mode forced off! cap_mode:%x` |
| trinity | `ctx+0x110` | 1 | 23 | `FW: trinity mode forced off! cap_mode:%x` |
| SpotMulti | `ctx+0xbc` | 9 | 1 | `FW: SpotMulti mode forced off! cap_mode:%x` |

Only these three exist in the ~2.5 KB region — this is not a large table. Note the
flag comparison value varies (`+0xbc` is tested against 9, not 1), so a parser that
assumes `cmp #1` will miss gates.

`fcn.00316ef8` itself is only 184 bytes — a 34-way `tbb` returning one value per
capture mode. It does **not** set the request flags; the gate lives in a different
function that rizin has not separately named.

## Two candidate levers

**A — set the mode value.** `ctx+0xd4 = 1`, which is what `case 5` tests for.
Blunt: it changes the value the firmware believes the user selected.

**B — neutralise the gate.** At `0x317130`/`0x317132`, make the `cap_mode == 5`
test always pass, so the flag is never cleared. Surgical: it changes only the
enforcement, leaving the request itself intact.

**B is the better shape** — it does not forge a user selection, it stops the
firmware from vetoing a request it already received. It is also the same shape as
the ZIT SA patch: one conditional becomes unconditional.

## The one thing that decides whether either works

**Nothing found so far writes `ctx+0x10c`.** The gate only ever *clears* it. If
no code path on this body ever sets it, then neutralising the gate achieves
nothing, and the real work is finding the writer.

So the next question is narrow and answerable: **who writes `ctx+0x10c`?** That
is a single store instruction to find. Everything else is already mapped.

Two secondary unknowns:

- Which `SaDriver*` type the audio path needs — unresolved, and it matters if the
  pipeline turns out to touch audio (`StageWaitSAComp` suggests it may).
- Whether `MS_DUMP_RAW_PRELIGHT_*` implies a sensor readout mode this body cannot
  enter. Untested.

## Comparison with Golf Shot

| | Motion Shot | Golf Shot |
|---|---|---|
| implementation | complete | complete |
| setting | `motion_shot_mode` | none |
| validator | `CheckSetMotionShotMode` | none |
| per-mode resolution | case 5 of 34 | none |
| capture-mode gate | `ctx+0x10c`, allows 5 | none |
| entry points | `sa_func_MOTIONSHOT_*` | `sa_func_GOLFSHOT_*` |
| sensing | vision (`HumanMovingArea`) | sound (mic) |

Golf Shot has the bottom half only. Motion Shot has the whole chain, which is why
it is the better target — and the honest caveat is that "whole chain" means
"fully built", not "offered on this model".

## Confidence

| claim | confidence |
|---|---|
| Motion Shot is detect-moving-subject-then-record, via vision | **medium-high** — from the algorithm, stage and pipeline names; no prose description exists in the image |
| mode value stored at `ctx+0xd4`, consumed in cap_mode 5 | **high** — read from the setter and `case 5` |
| the three capture-mode gates and their allowed modes | **high** — read from the instruction stream |
| `sa_func_MOTIONSHOT_*` entry family | **high** — names and demangled signatures present |
| offered on a ZV-E10 | **not established** |
| a writer for `ctx+0x10c` exists on this body | **unknown — and it is the crux** |

## Reproducing

```
retool.cmd disasm avcam 0x316ef8 -n 40   # the 34-way cap_mode resolver
retool.cmd disasm avcam 0x316f08 -n 40   # its case table; case 5 reads ctx+0xd4
retool.cmd disasm avcam 0x317128 -n 24   # the Mshot / trinity / SpotMulti gates
retool.cmd strings avcam motion_shot_mode
retool.cmd strings avcam MOTIONSHOT
retool.cmd strings avcam Mshot
retool.cmd strings avcam HumanMovingArea
```

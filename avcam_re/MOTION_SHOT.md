# Motion Shot: what it is, how it is gated, and why it never runs

Addresses are file offsets (runtime VA = offset + `0x635c6000`). `ctx` is the
per-capture context.

> ## Retraction: the two-byte patch recommended below would not work
>
> An earlier revision recommended patching the CapMgr flag `ctx+0x10c` — preset it
> in the constructor and stop the validator clearing it. **That recommendation was
> wrong, and this revision withdraws it.** The chain that flag feeds ends in a
> **write-only byte**: the flag's only effect is to set a global at file `0xf59a58`,
> and nothing in the image reads that global. Patching the flag arms a dead end.
>
> What replaces it is a more useful result, though it points somewhere deeper: the
> Motion Shot **pipeline** is live code. Its stages are registered, the
> `sa_func_*` name dispatcher is called from 16 sites including the Motion Shot
> stage code itself, and that stage code is reached. So `ctx+0x10c` is *not* the
> activation path — the real one is the sequencer, and finding it is a bigger job
> than a byte patch.

> **Correction to this file's own premise.** An earlier revision opened with
> "`cap_mode` is `ctx[0x90]`". That is wrong. `ctx[0x90]` is a 0..33 selector
> feeding the *separate* 34-way per-mode **limit resolver**; the capture mode that
> the gates actually test is **`ctx[0x00]`**. The two were conflated. See
> "Where the mode comes from" below.

**Status: the crux is resolved.** The previous revision of this file ended on an
open question — *nothing found writes `ctx+0x10c`*. That is now answered, and the
answer is more specific than expected: **the code that sets the flag belongs to a
class that this firmware never instantiates.**

## What Motion Shot is, on the evidence

Detect a moving subject and automatically record a clip of it. The detector is
*vision*, in the face/detection layer, and it produces *video*:

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
per-mode       fcn.00316ef8                      34-way tbb on cap_mode -> a limit
   case 5:     ldr.w r3, [r4, 0xd4] ; cmp r3, 1  <-- motion shot lives in cap_mode 5
flag init      fcn.0007f4dc  (CapMgr ctor)       ctx+0x10c := 0
arming         RcFill::vfn[6] @ 0x7fc696         ctx+0x108 := 1 ; ctx+0x10c := 1
                                                     <-- NEVER CALLED, see below
gate           fcn.00316fd0                      ctx+0x10c := 0 unless cap_mode == 5
consumer       fcn.0039eb6c                      if ctx+0x10c == 1 -> fcn.003a25fc(1)
sink           fcn.003a25fc                      global byte @ file 0xf59a58 := 1
entry          sa_func_MOTIONSHOT_{init,acquire,start,release,exit}
pipeline       Stage_MotionShot_Analysis -> MotionShotVideo* -> clip
```

## The capture-mode gate

`ctx+0xd4` holds the mode value; `cap_mode` selects the context in which it is
consumed. A separate function clears the *request flag* when the capture mode is
not the allowed one:

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

Only these three exist in the region. Note the flag comparison value varies
(`+0xbc` is tested against 9, not 1), so a parser that assumes `cmp #1` will miss
gates. There is **no fourth gate** — `ctx+0x114` is not gated.

The three "forced off" strings sit together at `0x9b61dd`/`0x9b6204`/`0x9b622d`,
immediately after `FW: SR_CAPMODE is changed! %x %x` (`0x9b61bc`, ref
`0x0317018`). All three are rejections; there is no "mode on" log for any of them,
so the arming side is silent by construction.

## Where the mode comes from

`fcn.00316fd0` owns all three gates, and it is the function that establishes what
the mode is. Its entry:

```
0x316fd0  push.w {r3, r4, r5, r6, r7, r8, sb, sl, fp, lr}
0x316fd4  mov   r5, r0              ; r5 = ctx
0x316fda  mov   fp, r1              ; second argument
0x316fdc  ldr   r3, [r0, 8]
0x316fe0  cmp   r3, 0
0x316fe2  bne.w 0x3172b4
0x316fe6  ldr.w r4, [r0, 0xc8]      ; r4 = ctx+0xc8
0x316ffa  cmp   r4, 0x12
0x316ffe  bne   0x317064
...
0x317000  ldr   r4, [r5]            ; r4 = ctx[0]
...
0x317022  ldr   r3, [r5]            ; the capture mode
0x317024  cmp   r3, 9
0x317026  bhi   <default>
0x317028  tbh   [pc, r3, lsl 1]      ; 10 cases
```

**`TBH` computes `base + 2*entry`, not `base + entry`.** With the ×2 every one of
rizin's case labels matches; with ×1 five entries land inside the table, which is
impossible. (I got this wrong twice before checking — the brute-force "which base
looks plausible" scorer was the wrong tool.) Resolved mapping, base `0x31702c`:

| `ctx[0]` | 0 | 1, 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| case at | `0x317068` | `0x317056` | `0x3172c0` | `0x3172c6` | `0x317040` | `0x317044` | `0x31704a` | `0x317050` | `0x317068` |
| `r4` becomes | 0 or 9 | 0 | 24 | 1 | **9** | 8 | 9 | 27 | 0 or 9 |

The two cases that compute rather than assign both call the same 5-instruction
helper, which returns **only 0 or 9**:

```
0x864566  ldr  r3, [r0, 0x1c]
0x864568  ldr  r0, [r3, 0x1c]
0x86456a  cmp  r0, 9
0x86456c  ite  eq
0x86456e  moveq r0, 9
0x864570  movne r0, 0
0x864572  bx   lr
```

and its result is both stored to `ctx[0]` (`str r0, [r5]` at `0x31706e`) and copied
into `r4` (`mov r4, r0` at `0x31707a`).

### Is `r4 == 5` reachable?

This is the question the whole patch hinges on, and the answer is **yes, but only
through one narrow route**.

Every *literal* assignment to `r4` in the function is one of
`{0, 1, 6, 8, 9, 0x18, 0x1a, 0x1b, 0x1c}` — 19 sites, **none of them 5**. The
register-derived assignments are `mov r4, r0` with `r0 ∈ {0, 9}` (above) and
`asrs r4, r1, 31` giving `{0, -1}`. So no case of the `tbh` yields 5.

But `r4` also carries **`ctx+0xc8` verbatim** into the gate. The route is the
`bne 0x317064` at `0x316ffe`, and the branches that reach `0x3170f8` *without*
executing the `movs r4, 0x1b` at `0x3170f6` are at `0x3170a6`, `0x3170b0`,
`0x3170ce` and `0x3170da`; from there `0x317108  bne 0x317128` lands on the gate.
The only filters that route puts on `ctx+0xc8` are `!= 0x12`, `!= 0x1e` and
`!= 8` — and **5 passes all three**.

So the "motion shot is allowed" branch is live, but only when `ctx+0xc8 == 5`.
That reframes patch A: rather than "5 never happens", the accurate statement is
that **whether the flag survives depends on an unbounded 32-bit field**, which is
exactly the kind of dependency you do not want to rely on. Making the clear
unconditional removes the dependency.

Corroboration that 5 is a real internal mode: the second dispatch at `0x317184`
has a dedicated branch for it —

```
0x31718e  cmp  r4, 3
0x317190  ble  0x3171a6        ; modes 1..3 clamp
0x317192  cmp  r4, 5
0x317194  bne  0x3171c2
0x317196  b    0x3171a6        ; mode 5 clamps the same way
0x317198  cmp  r4, 0x17
0x31719a  beq  0x3171d2        ; mode 23 exits early
```

so the firmware does have handling for mode 5, it is simply not produced by the
`ctx[0]` dispatch on this build.

### `ctx+0xc8` is a latch of the previous mode

The function's epilogue writes back exactly the four registers it loaded at entry:

```
entry   0x316fe6  ldr.w r4, [r0, 0xc8]      0x316fea  ldr.w sl, [r0, 0xc0]
        0x316fee  ldr.w r7, [r0, 0xcc]      0x316ff2  ldr.w r6, [r0, 0xb8]

exit    0x31727e  str.w sl, [r5, 0xc0]
        0x317286  str.w r7, [r5, 0xcc]
        0x31728e  str.w r4, [r5, 0xc8]      <-- the resolved mode, latched
        0x317292  str.w r6, [r5, 0xb8]
```

So `ctx+0xc8` holds **the mode resolved by the previous invocation**, and it is the
value the `cmp r4, 0x12` at `0x316ffa` branches on. Since the exit value comes from
the same `r4` whose literal set is `{0, 1, 6, 8, 9, 0x18, 0x1a, 0x1b, 0x1c}`, the
latch should never hold 5 either.

**This is not fully closed.** `+0xc8` has 164 writers image-wide, and five
functions write it while also touching the CapMgr flag triple
(`fcn.000722d8`, `fcn.001b8580`, `fcn.001f8888`, `fcn.002e0dd0`, `fcn.00316fd0`).
The identity test is weak — `0xbc` is a very common offset, and two of those five
have function sizes rizin got badly wrong (128 KB), so "also touches" is not
trustworthy. One of the others could write this object's `+0xc8` with a 5 from
somewhere else entirely.

### Why the ambiguity does not change the recommendation

Patch A is the right call **under either hypothesis**, which is why the open
question above is not blocking:

| if… | then A is… |
|---|---|
| `r4 == 5` is reachable | harmless — the flag would have survived anyway when the mode is 5, and A only removes the clear in the other modes |
| `r4 == 5` is never produced | **required** — the flag is otherwise guaranteed to be zeroed the first time any mode change runs |

So A does not depend on resolving the question, and neither does the A+B
recommendation. Patch B is required regardless, because the only arming site is
the never-constructed `RcFill`.

The residual risk that *is* real and unquantifiable: with A, the Motion Shot flag
survives into capture modes that were never meant to service it, and the consumer
`fcn.0039eb6c` will set the global at `0xf59a58` in those modes. What reads that
global is unknown, so the failure mode if the patch is wrong cannot be predicted
from the binary — it has to be observed on hardware.

## The flag lifecycle — the crux, resolved

### 1. Initialised off

`fcn.0007f4dc`, the CapMgr constructor (one caller, `bl` at `0x069969e`):

```
0x7f4ee  movs  r0, 2
0x7f4f0  movs  r1, 1
0x7f4f2  strh.w r0, [r3, 0x106]
0x7f4f6  strh.w r1, [r3, 0x10a]
0x7f4fa  movs  r1, 0
0x7f4fc  str.w  r0, [r3, 0x110]     ; trinity := 2
0x7f500  adds  r0, r3, 4
0x7f502  str.w  r1, [r3, 0x10c]     ; MotionShot := 0
0x7f506  str.w  r1, [r3, 0x114]     ; := 0
```

`ctx+0x110` is initialised to **2**, not 1 — so the trinity gate's `cmp #1` never
fires on a fresh object. 0 = off, 1 = requested, other = n/a.

### 2. Only ever cleared by the gate

The gate above is the only place in the validator that writes the flag, and it
writes 0.

### 3. Exactly one arming site exists — and it is dead

A constant-propagating sweep of every `str.w [Rn, #0x10c]` (123 sites, filtered by
nearest-preceding-definition) finds exactly **two** sites that write the literal 1:

| site | instruction | reachable? |
|---|---|---|
| `0x0475978` | `str.w r0, [r2, #0x10c]` | unrelated struct (a 0x475978–0x4762ca cluster) |
| `0x07fc6b0` | `str.w r2, [r4, 0x10c]` | **this is the one** |

```
0x7fc696  push {r4, r5, r6, lr}      ; r4 = ctx (from r2)
0x7fc6a6  ldrh.w r3, [r4, 0x98]
0x7fc6aa  movs  r2, 1
0x7fc6ac  str.w  r2, [r4, 0x108]
0x7fc6b0  str.w  r2, [r4, 0x10c]     ; MotionShot := 1
0x7fc6b6  ldrh.w r2, [r4, 0x94]
```

**This function has no `BL` caller anywhere in the image.** It is, however, a
virtual function: it appears at file offset `0x0fc7730` in a vtable array, as
`vfn[6]` of a class named **`RcFill`**.

### 4. `RcFill` is never constructed

This is the finding. An object constructor must load the vtable's address point
(`vtable offset + BASE`) into the object. Searching the whole image for that
32-bit constant — as a stored literal in both Thumb-bit states, and as a
`MOVW`+`MOVT` pair — finds **nothing** for `RcFill`. Eight siblings in the same
family *do* have theirs referenced and are genuinely instantiated:

```
9RcCalcDst  6RcCopy  19RcExecutionCtrlDstH  19RcExecutionCtrlDstV  16RcExecutionCtrlH
13RcHwAccessDst  8RcResize  11RcResizeDst  12RcResizeDstH  9RcResizeH
12RcResizeDstV
```

`RcFill` is absent from that list. So the Motion Shot arming code is **compiled in
but never reachable**: this is a build exclusion, not missing code. Consistent
with the rest of this image being a shared multi-model build (`BOL1G/BOL2G/BOL310/
BOL373/BOL473/DSC00001/PX280`, no retail model string).

`RcFill`'s typeinfo is at file `0x101fa1c`; `[0] = 0x6458f438` is the shared
`__si_class_type_info` vtable (hence the whole family shares it), `[1]` is the
name `6RcFill`, `[2]` names the base class **`RcResize`**. RTTI in this image is
length-prefixed plain strings, *not* `_Z`-mangled — a `_Z` regex finds nothing.

### 5. The consumer

One function reads the flag and acts on it — `fcn.0039eb6c`, a 6-state machine
(`tbh` at `0x39ee36`), at three sites, all identical:

```
0x39ee48  ldr.w r0, [r3, 0x10c]
0x39ee4c  cmp   r0, 1
0x39ee4e  bne   0x39ee54
0x39ee50  bl    fcn.003a25fc
```

(the others are at `0x39ef9e` and `0x39f306`). `fcn.003a25fc` is a one-byte global
setter:

```
0x3a25fc  ldr  r3, [0x3a2604]      ; delta 0xbb7456
0x3a25fe  add  r3, pc
0x3a2600  strb r0, [r3]            ; global @ file 0xf59a58 := 1
0x3a2602  bx   lr
```

That global has **exactly one** reference by the `ldr [pc]/add pc` idiom — the
write. Its reader must address the flag table by another route, so what consumes
`0xf59a58` is still unresolved.

## Why the GUI route is closed

Not an assumption — the flash dump was searched. `nflasha3_system.bin` (48 MB) is a
`0x14000` header + `av-cam.bin` verbatim at `+0x14000` + ~31 MB of boot loaders
and userland (`Etools-NAND-BOSS-lld_171H` DMAC/LDEC, `boot.c`, glibc/`ld.so`);
`nflasha6.bin` is the panel/LCD/EVF driver (`CDiScript::GetUIString`,
`CMD_R_GET_UI_STRING`, `PANELEVF_*`); the only real filesystem is `nflasha13.bin`
(`HASH/`, `HISTORY/`). `/setting` is a genuine mount (`/setting/sen/smode`,
`/setting/mode/dmode`, `/setting/env.txt`).

**There is no Motion Shot display string anywhere** — ASCII or UTF-16, in any
readable image. Everything is a log, a validator name, or a mangled symbol. In
`av-cam` the menu layer is an uninstantiated shell: `tcub::MenuManager` RTTI with
**zero** references, `MenuManagerProxy`/`MenuManagerImpl`/`MenuMsgPostponer` also
unreferenced, and a whole menu-id namespace of seven entries (`b1_menu_onoff`,
`b1_menu_stillmode`, `b4_menu_panorama`, `b7_menu_selftimer`, `b4_menu_movie`,
`b4_menu_active`, `b8_menu_convlens`) — none for motion shot or golf shot.

So: **model present, code present, setting present, no front end, and the arming
object excluded.** `/setting`'s load manifest does list `sa_motionshot.bin`,
`sa_motionvideo_u0.bin`, `sa_motionvideo_u1.bin` — the detection neural nets ship on
this camera.

Caveat: `fdat_decrypted.bin` (353 MB) and `fw_dec_best.bin` returned *zero* hits for
any of these terms, which almost certainly means those artefacts are still
compressed rather than being evidence of absence. They are not treated as evidence
either way.

## Patch candidates — all three verified, none recommended

All three are **one byte**, and all three were validated empirically: flip the
byte in a copy, disassemble before and after, and confirm the only change in the
window is the intended one.

| | file offset | change | effect | verdict |
|---|---|---|---|---|
| **A** | `0x0317133` | `d0` → `e0` | `beq 0x317144` → `b 0x317144`: the flag is never cleared | correct, **pointless** — nothing reads the result |
| **B** | `0x007f4fa` | `00` → `01` | `movs r1,#0` → `movs r1,#1`: preset the flag at construction | correct, **pointless** — and has a side effect |
| **C** | `0x039ee4f` | `d0` → `e0` | the consumer's `bne` becomes unconditional: always call `fcn.003a25fc` | correct, **pointless** — sets an unread byte |

Validation output:

```
A: 0x0317133: 0xd0 -> 0xe0
   before: 0x00317132  beq  0x317144
   after : 0x00317132  b    0x317144
   6/7 instructions unchanged in the window

B: 0x007f4fa: 0x00 -> 0x01
   before: 0x0007f4fa  movs r1, 0
   after : 0x0007f4fa  movs r1, 1
   6/7 instructions unchanged in the window
```

They are recorded because they are verified and because the *reason* they do not
work is the finding. **Do not flash them expecting Motion Shot.** A, B and C
together would leave the camera setting a `.bss` byte that nothing reads — a
plausible-looking patch that does nothing at all, which is worse than no patch
because it looks like progress.

The `+0x114` side effect of B is moot for the same reason, though for the record:
`+0x114` has 277 accesses image-wide and 28 sites compare it against a constant,
but **none of those is in a function that also touches the CapMgr flag triple**.

### The registrar does not exist

The obvious next move was to find what *does* wire the live part of the framework,
on the assumption that if a registration mechanism exists, Motion Shot's absence
from it is the patch site. A scan of the pointer regions for
`{function pointer, class name}` pairs found **1607 pairs in 29 runs** — and
appeared to include the Motion Shot classes:

```
0x1024cbc  fn 0x0fc9438  NS_SCALAR_INFRA33ScalarInfraMotionShotVideoManagerE
0x1024cd4  fn 0x0fc9438  ...MotionShotVideoSequenceStageExecSAE
0x1024cf8  fn 0x0fc9438  ...MotionShotVideoSequenceStageWaitSACompE
```

**That is an artifact, and the registrar does not exist.** `0x0fc9438` is the
shared **`__si_class_type_info` vtable** — a data address, not a function. So each
pair is an Itanium **typeinfo object**: `[0]` = own vtable, `[1]` = name. Adjacent
typeinfo objects are indistinguishable from a `{ctor, name}` registration table
once you scan for the pattern, and the Motion Shot classes appear simply because
all 137 of the family's typeinfo objects sit in one array.

Two tooling errors behind it, both worth recording:

- **`is_code` as `offset < 0x1000000` is wrong for this image.** `0x0f00000`+ is
  largely zero-filled (`0x0f4de48` is sixteen zero bytes) and `0x0fc0000`+ holds
  vtables, so the test classifies data as code. The *construction* test is
  unaffected — it searches for the exact 32-bit value, not a class — so the
  construction verdicts above stand. The flag-table and handler-table
  classifications that used `is_code` do not.
- A `{code, name}` pair is not evidence of registration without first checking what
  the "code" pointer actually is. Here it was a vtable.

So the question "what instantiates the concrete layer on models that use this
framework" is **unanswered**, and it is the right place to dig next: if the
mechanism is in a different component rather than this image, that is consistent
with everything above, and it would mean the answer is not in `av-cam.bin` at all.

### The wiring is not in another component either

If a different component owns the registrar, that component must contain the
framework vocabulary. Every readable flash partition was searched:

| component | size | `NS_SCALAR_INFRA` | `ScalarInfra` | `MsgHandler` | `ComponentFactory` | `MotionShot` |
|---|---:|---:|---:|---:|---:|---:|
| **`av-cam.bin`** | 16.5 MB | **344** | **85** | **68** | **6** | **17** |
| `nflasha3_system` | 48 MB | 344 | 85 | 68 | 6 | 17 |
| `nflasha1` / `nflasha2_setting` / `nflasha5_wbi1` / `nflasha6` / `nflasha10_tmp` / `nflasha13` / `nflasha4_cmmex` / `nflashaB0*` | 4–60 MB | 0 | 0 | 0 | 0 | 0 |

The counts are **identical term for term**, and every `nflasha3_system` hit is
byte-identical to av-cam at `+0x14000` — verified on six sample offsets, all
`True`. So the entire sequencing framework lives in `av-cam.bin` and nowhere else,
and there it is not instantiated.

### And the analysed image is the one in the flash

`nflasha3_system` embeds av-cam at `0x14000`. The embedded copy is byte-identical
to `dumps/av-cam.bin` except for **18 bytes**, all after offset `0xaa15a` — a
build-stamp region, four of them word-aligned, none of them plausible pointers.
Every offset this document cites is in the identical region:

```
identical    0x0317133  patch A
identical    0x007f4fa  patch B
identical    0x007f502  CapMgr ctor, ctx+0x10c := 0
identical    0x0317140  the clear
identical    0x033c794  the Motion Shot stage
identical    0x03a25fc  the sink setter
identical    0x07b9b5e  ldrb.w r0,[r0,0x23] -- the stage selector
identical    0x07bdf92  the stage dispatcher's tbb
identical    0x0fc7714  RcFill's vtable
identical    0x1074ad0  the 37-entry handler table
```

So the analysis is of the build that is actually on the camera.

**Not searched:** `nflasha16` (140 MB), `nflasha4_cmmex` (12 MB), `nflasha12_cert`
(40 MB) and `nflasha13` (4 MB) are 0% printable — encrypted or compressed. If the
registrar exists anywhere it is in those, and they cannot be read without
decryption. Given that 140 MB is a plausible size for a data partition rather than
firmware, that is the least likely place for it, but it is formally unexamined.

### The flash inventory is complete; there is no hidden component

Earlier I recorded `nflasha16`, `nflasha4_cmmex`, `nflasha12_cert` and
`nflasha13` as "0% printable — encrypted or compressed… if the registrar exists
anywhere it is in those." **That was wrong**, and measuring each partition in full
rather than sampling one megabyte corrected it: 0% printable is what *erased*
flash looks like, not only what encrypted data looks like.

| partition | size | uniform | identified as |
|---|---:|---:|---|
| `nflasha16` | 140 MB | **100%** | erased — 1 distinct byte value in the whole partition, no content at all |
| `nflasha12_cert` | 40 MB | 97.5% | `kdosfs` volume containing only a FAT boot sector |
| `nflasha13` | 4 MB | 75% | `kdosfs` volume: `HASH/`, `HISTORY/`, `UPDATE LOG/` — the **update log** |
| `nflasha4_cmmex` | 12 MB | 66.7% | `CMMeX` data container, 5 repeats of one record, `G46DSDS` markers; no code, no menu vocabulary |
| `nflashaB0` / `B0_exbl` | 1 / 2 MB | 0% / 50% | `EXBL` — external **bootloader**; 400 "strings" are ARM instruction bytes, not text |
| `nflasha6` | 16 MB | 75% | panel / LCD / EVF driver (already searched: zero hits) |
| `nflasha1` | 7.9 MB | 11.8% | `mkfs.fat` volume (already searched: zero hits) |
| `nflasha10_tmp` | 12 MB | 8.3% | real content (already searched: zero hits) |
| `nflasha2_setting` | 20 MB | 50% | model binaries incl. `sa_motionshot.bin` (already searched) |
| `nflasha5_wbi1` | 60 MB | 41.7% | real content (already searched: zero hits) |
| `nflasha3_system` | 48 MB | 56.2% | av-cam verbatim at `+0x14000` + boot loaders + userland |

So every byte of the flash is accounted for, and none of it contains the wiring.
The only unread thing left anywhere is the `UDTRFIRM` payload in the update package.

### The `UDTRFIRM` payload is now read — and it holds a component the dump never had

**The crypter was identified: `AesCbcCrypter` (CXD90045).** The giveaway was cheap.
Run every candidate generation over the *first* block and keep the one that
yields `UDTRFIRM`; only CXD90045 does, the other eight raise `Wrong checksum`. The
cipher is 1024-byte blocked, not the 1000-byte SHA-1 stream that
`research/firmware/sha1_decrypt.py` implements, which is why the earlier keystream
diverged after block 0. Now implemented standalone in
`research/firmware/fdat_decrypt.py`, with 14 tests.

**`dumps/fdat_decrypted.bin` was a false positive and everything derived from it
was worthless.** It decoded to a flawless-looking `UDTRFIRM` header, but the CramFS
magic was absent at `0x200` and *every* 1 MB block measured 37.1% printable —
random. Block 0 always looks right under the wrong scheme; that is precisely why a
valid header proved nothing. A first reimplementation of mine repeated the error in
a subtler form by putting the IV in the last 16 bytes of the trailer instead of at
`[-0x110:-0x100]`, and the per-block checksum is what caught it.

Decoded: model `0x01030010`, version 2.03, `firmwareOffset=0x24200`,
`firmwareSize=370,850,816`, CramFS body at `0x200` with the correct magic
`45 3d cd 28`, and the payload is a **tar with 174 members**.

**Six partitions in the flash dump were read failures, not empty partitions.**
`nflasha7`, `nflasha11`, `nflasha15`, `nflasha17`, `nflasha18_lens` and `nflasha23`
are all 0 bytes locally, and the package supplies real content for two of them:

| partition | role (`partinf.conf`) | in our dump | in the package |
|---|---|---:|---:|
| `nflasha7` | **Rootfs**, 8 MB | 0 (failed) | 5,132,288 |
| `nflasha15` | **usr**, 300 MB | 0 (failed) | 249,105,408 |
| `nflasha3` | System (Main), 48 MB | 50,331,648 | 30,157,824 |
| `nflasha1` | System (Updater), 8 MB | 8,323,072 | 8,323,072 |

`nflasha7` turned out to be a generic busybox/glibc userland (libxtables,
libxt_tcp) with **zero** framework or menu vocabulary — a dead end. `nflasha15` did
not.

### The front end is in `nflasha15`, not in av-cam — which is why the GUI route looked closed

`nflasha15` holds a **separate camera application**: 334 ELF files, and a 21.3 MB
ARM shared object at file `0x0c91ac00` carrying `CamUser`, `ObjRenderer`,
`Sequence`, `MSGID` and `VALUEID` vocabulary. This is the menu and camera-mode
layer, and it is the component whose absence from av-cam made "no Motion Shot
display string anywhere" look like a dead end rather than a structural fact.

Its headers cannot be trusted — the section table is garbage (`sh_name=142870960`),
`.dynamic` is zeroed, and `e_entry` lands on a repeating data pattern — but the
program headers are sane and the strings are real, so it was read at string level.

**The Golf Shot / Motion Shot comparison is the clean result.** Golf Shot works on
this camera, so its symbol set is the control:

| | Golf Shot (works) | Motion Shot |
|---|---|---|
| message / param / value plumbing | present | **present and complete** |
| `CamMode*` class | `N7CamUser15CamModeGolfShotE` | **absent** |
| capture / play sequences | 14 classes | **1** (`SetMotionShotMode` only) |
| layout cmds + `ACSRID_..._LAYOUT` | present | **absent** |
| `OPEN_MODE_EE_GOLFSHOT`, `DefStruct::CAMERA_MODE_GOLFSHOT` | present | **absent** |

Motion Shot has `MSGID_SET_MOTION_SHOT_MODE_CMD`, `MSGID_NOTIFY_MOTION_SHOT_MODE_EVT`,
`MSGID_NOTIFY_MOTION_SHOT_RESULT_EVT`, `PARAMID_MOTION_SHOT_MODE`,
`VALUEID_MOTION_SHOT_MODE_ON/OFF`, `VALUEID_MOTION_SHOT_SUCCESS/FAIL` and
`NID_MOTION_SHOT_RESULT_NOTIFY` — the whole bottom half. It has none of the top
half. This is the same shape as the av-cam verdict, arrived at independently from a
different binary in a different layer.

The layer also states the rejection explicitly:
`CamMsgConv) ##### ERROR!!! SetMotionShotModeForLiro NON SUPPORTED MsgID[0x%04x]`
— "Liro" being the internal model code. That is a *dispatch* rejection, so clearing
it would silence an error message, not create a missing mode class and missing
capture sequences. Same conclusion as the Golf Shot debug-command fallback.

The 83,587-entry `cmnViewSetting*` menu schema (a data blob, outside any ELF)
contains **zero** Motion Shot and **zero** Golf Shot entries, so neither feature is
menu-driven.

### …but Motion Shot's *user-facing strings* are present, and Golf Shot's are not

Outside the code, in the string-resource table, Motion Shot has a full UI
vocabulary and Golf Shot has almost none:

```
STRID_FUNC_MOTION_SHOT_VIDEO
STRID_FUNC_MOTION_SHOT_VIDEO2
STRID_FUNC_MOTION_SHOT_VIDEO_INTERVAL_ADJUSTMENT
STRID_FUNC_MOTION_SHOT_VIDEO_INTERVAL_ADJUSTMENT_GUIDE
STRID_INFO_MOTION_SHOT_VIDEO_CTRLPANEL_CONTROLPANEL / _PAUSE / _PLAY
STRID_INFO_MINUTE_SEC_V, STRID_INFO_MF_DISTANCE_NUM1_DOT_NUM1_VAL_V
… and Vietnamese text: "chọn khoảng Motion", "t.gian d.trog MotionShotVideo"
```

Golf Shot has **zero** `STRID_FUNC_*` entries and only two help-text headings
(`JPEG GolfShot`, `JPEG GolfShot(APSC)`). So the control panel, play/pause and
interval-adjustment strings for Motion Shot exist and are localised.

**Caveat, and it is a real one:** these are `STRID_*` identifiers in what is
probably a string table shared across a model family, so their presence proves
Motion Shot was *built*, not that this model exposes it. It is evidence about
Sony's intent, not a patch site.

### The package is an older build, so the above is a proxy, not the camera's own code

`nflasha1` from the package differs from the camera's own `nflasha1` in **79.5% of
its bytes** (both start `NO NAME    F`; they are different FAT images of different
firmware). `partinf.conf` is dated 2020/11/13. So the CamUser binary and the
`STRID_*` table analysed above are the **2020 / v2.03** versions, while the camera
runs a 2025 build. The camera's own `nflasha15` was never captured, so its current
contents remain unknown.

**What this changes:** the V2.03 av-cam has an *identical* Motion Shot vocabulary to
the current build (344 `NS_SCALAR_INFRA`, 12 `MotionShot`, 6
`ScalarInfraMotionShotVideoSequence`, 1 `6RcFill`) and the *same* construction
verdicts — every Motion Shot class unreferenced in both. So the exclusion is
longstanding rather than a regression introduced by newer firmware, which is a
stronger result than "the 2025 build disabled it".

**What it does not change:** there is still no patch. The search space grew by
249 MB and one genuinely new component, and the answer is the same, now confirmed
from two independent layers.

### Bonus: the installed version, from the camera's own update log

`nflasha13`'s `UPDATE LOG/` records the last update performed:

```
[20110101 00:00:02]Updater: START. MODE=1 Serial
                  Base Version: 100.102.017
                  Body Version: 100.102.017
                  EDISX START. / EDISX END.
                  Darwin update START. / PFORMAT START. / PFORMAT END.
                  DDR Training data update done. / Darwin update END.
                  Updater: END. FIRMUP OK!
```

So the flash was written by updater `100.102.017`, which is a third version
string alongside `dumps/version.txt`'s `30110_05.2025031501` and the update
package's `0x0203`. Worth keeping in mind when comparing builds: they are not the
same numbering, and the update package is the oldest of the three.

## Verdict: there is no patch, because there is no live state to patch

The last link is closed, with a positive control at every step.

The stage dispatchers whose case 2 selects the Motion Shot stage are virtual
methods — each has exactly one vtable slot. Those classes are never instantiated:

| address point | literals | MOVW/MOVT | verdict |
|---|---:|---:|---|
| `0x1074ad0` — the 37-entry handler table holding the 7-way dispatcher | **0** | 0 | never constructed |
| `0x1074ad4`, `0x1074adc` | 0 | 0 | never constructed |
| dispatcher slots `0x1072814`, `0x107a994`, `0x107ae5c` | 0 in `[slot-16, slot+8)` | 0 | dead |
| dispatchers at `0x7ba712`, `0x7ba8b0` | no vtable slot at all | — | not virtual; not reached |
| **`ScalarInfraSequenceIf` vtable `0x1024adc` — the control** | **15** | 0 | **CONSTRUCTED** ✔ |
| same, four further address points | 1, 19, 1, 1 | 0 | **CONSTRUCTED** ✔ |

The control sits in the *same* `0x10xxxx` region as the dead table, so the zeros
are a property of the target, not of the search.

### The full exclusion stack

| layer | finding | how established |
|---|---|---|
| front end | no Motion Shot display string anywhere, ASCII or UTF-16 | exhaustive search of every readable image |
| CapMgr flag | `ctx+0x10c` init 0, cleared unless mode 5 | read from the instruction stream |
| mode 5 | no literal assignment to `r4` yields 5; the `ctx+0xc8` latch is written from that same `r4` | 19 literal sites enumerated |
| flag consumer | sets a global at `0xf59a58` that **nothing reads** | 3 negatives vs a consumed neighbour |
| flag arming | `RcFill::vfn[6]` never constructed | construction test, 4/4 control |
| sequencer | `MotionShotVideoManager` / `MotionShotVideoSequence` never constructed | same test; 115 of 137 concrete `NS_SCALAR_INFRA` classes unreferenced |
| **stage dispatch** | the dispatchers that select case 2 = Motion Shot belong to classes that are never constructed | same test, 5/5 control in-region |

Every layer is independently sufficient to prevent the feature, and the last one
closes the question: the code that would *run* the Motion Shot stage is only
reachable from objects that are never built. There is no `+0x23` byte in existence
to set to 2, because no such object exists.

**So this is not "the patch has not been found yet".** The consistent reading is
that Motion Shot is excluded from this build at every layer, deliberately, as part
of a shared multi-model image.

Residual caveat, stated for completeness: the test would miss a vtable address
computed arithmetically rather than loaded as a literal or `MOVW`/`MOVT`. Writing a
constructor that way would be perverse, and the control fires on 5 address points
in the same region, so it is not a plausible explanation for these zeros.

### What enabling it would actually take

All the compiled code is present — the stage functions, the `sa_func_MOTIONSHOT_*`
entry points, the pipeline classes, and the `sa_motionshot.bin` /
`sa_motionvideo_u0/u1.bin` neural nets in `/setting`. What is missing is the
wiring. A port would have to:

1. construct `MotionShotVideoManager` and the sequence;
2. register the sequence in the 37-entry handler table at `0x1074ad0`;
3. supply the missing factories (every concrete `*Factory` in the family is also
   unreferenced);
4. provide a trigger, since there is no UI.

That is code injection, not a byte patch, and its correctness could only be
confirmed on hardware — the failure mode cannot be predicted offline because the
one byte the flag reaches has no reader to reason about.

## Status: no working patch

The success criterion was a patch that makes Motion Shot record. **There isn't
one, and the evidence says there isn't one to find in this image.** What is banked
is the exclusion stack above, the two retracted byte-patches with byte-level
validation, the one-byte stage selector, and the tooling to re-check every step
(`retool/offsets.py`, 38 tests, each anchored to a real instruction).

## Open unknowns

- **How the concrete `NS_SCALAR_INFRA` layer is meant to be wired.** 115 of 137
  classes are never instantiated, including every factory. Something must construct
  them on models that use this framework — a registration list, a linker section, a
  model-dependent table. Finding that is the prerequisite for any port.
- Where the `Stage_*` names *are* consumed, given they are not in a central
  registry. If the 92 clusters are all self-logging, the stage chain must be
  hard-coded by vtable rather than by name.
- Which state the `ScalarInfraSequenceIf` implementers are in on this model, given
  none of the concrete ones is built.
- What writes the CapMgr's `ctx+0xc8` besides the latch epilogue. Not blocking
  anything now, but it is what to settle to understand the mode resolution.
- Which `SaDriver*` type the audio path needs — still a guess
  (`SaDriverLinearPhase` is unverified). Matters because `StageWaitSAComp` suggests
  the pipeline may touch audio.
- Whether `MS_DUMP_RAW_PRELIGHT_*` implies a sensor readout mode this body cannot
  enter. Untested.
- Whether the 126 published flags in the `0xf59a50` table include the one a
  working implementation would actually use.
- **What the camera's own `nflasha15` contains.** It is 0 bytes in the local dump
  (a read failure, not an empty partition), and the 2020 package copy is the only
  version ever examined. The current build's front end is therefore unverified; it
  could in principle have gained a `CamModeMotionShot` since. Re-dumping
  `nflasha7`/`nflasha15`/`nflasha11` is the cheapest way to close this, and the
  package proves they are not empty.
- Whether the `STRID_*` Motion Shot strings are reachable in the *current* build's
  string table, or are vestigial entries in a family-wide table. That needs the
  current `nflasha15`, for the same reason.

## Withdrawn / corrected claims

Recording these because each was stated as fact and was wrong.

- ~~"Nothing found writes `ctx+0x10c`."~~ **Wrong.** 123 `str.w [Rn,#0x10c]` sites
  exist. My first sweep tested `(hw2 & 0x0F00) == 0` to recognise the plain
  imm12 form, but the 12-bit immediate occupies all of `hw2[11:0]` — **its bit 8
  is part of the offset, not a flag** — so every access to a field at 0x100 or
  above was silently dropped. The correct discriminator is `hw2 & 0x0800 == 0`.
  `0x317128` is `ldr.w r3,[r5,#0x10c]` = `f8d5 310c`, the ordinary imm12 form with
  imm12 = 0x10C. (I first "corrected" this by claiming the field used the imm8×4
  scaled encoding; that was also wrong, and is why `retool/offsets.py` now refuses
  the uncalibrated T3/T4 forms outright rather than guessing a scale.)
- ~~"`ctx+0x10c` is written 0 at those sites."~~ My "writes 1" filter only matched
  immediates of 1, so it skipped the `movs r1, 0` that overrides an earlier
  `movs r1, 1` and made the CapMgr constructor look like the armer. The correct
  rule is **nearest preceding definition of any value**.
- ~~"the menu might be surfaced by a per-model filter."~~ There is no label to
  surface. Verified by exhaustive search, not inferred.
- ~~"the flash dump holds a per-model capability list."~~ `nflasha2_setting.bin` is
  a container of algorithm binaries, not a settings table. Its four motion-shot hits
  are all the `sa_motionshot.bin` filename in a load manifest.
- ~~"`fcn.00316ef8` is where the request is armed."~~ It is a per-mode **limit
  resolver** — a 34-way `tbb` returning one value per capture mode, clamped against
  a per-mode maximum with "not supported" logging. Case 5 only *reads* `ctx+0xd4`.
- ~~"`cap_mode` is `ctx[0x90]`."~~ Wrong. `ctx+0x90` is a 0..33 selector for the
  separate per-mode limit resolver; the mode the gates test is `ctx[0x00]`. The
  two were conflated, and "no code writes literal 5 to cap_mode" was an
  observation about the wrong field.
- ~~"Mode 5 is probably never produced, so the gate is dead."~~ Not established.
  No literal assignment to `r4` is 5 and no `tbh` case yields it, but `r4` also
  carries `ctx+0xc8` into the gate and 5 passes that route's only filters. The
  branch is live-but-narrow, not dead.
- ~~`TBH` entries are byte offsets from the table base.~~ They are **doubled**:
  `target = base + 2*entry`. I read this wrong twice before checking it against
  rizin's case labels, which were right all along.
- ~~"`movs r4, r1` at 0x317038 is how mode 5 arrives."~~ That address is a `tbh`
  table entry (0x000c) disassembled as code. Scanning for register definitions
  inside a function containing a jump table will keep producing these; the table
  has to be subtracted first.
- ~~`nflasha5_wbi1` / `nflasha6` contain golf-shot and menu code.~~ Both false
  positives from binary noise (`GOLFS`, `pp 7GolfS`) and a panel driver
  respectively. `nflasha6` has 13 "menu" hits, all `PANEL*`/`PANELEVF*` test names.
- ~~Most flash partitions are FAT.~~ A weak `0xAA55` check produced false positives
  on six partitions. Only `nflasha13.bin` is a genuine FAT12 volume.

### Tooling traps hit while doing this

- LDR/STR (immediate): T2 is selected by **`hw2 & 0x0800 == 0`**, not
  `hw2 & 0x0F00 == 0`. The immediate is a full 12 bits, so its bit 8 is offset,
  not a flag — the wider mask hides every field at 0x100+. This is what made
  `ctx+0x10c` look untouched.
- Thumb-1 `B<cond>` keeps the condition in **bits [11:8]**, not [15:12]
  (`b eq`=0xD0xx, `b ne`=0xD1xx, `b`=0xE0xx). I hand-decoded this wrong twice and
  briefly believed rizin was emitting a wrong mnemonic.
- `add rX, pc` is `0x4478 | Rd` with **`Rd` in bits [2:0]** — the base already has
  bit 3 set, so `0x447B & 0xF == 0xB`, not 3. Masking with `0x44F0` matches nothing.
- A PC-relative global's *delta* is relative to the using instruction, so searching
  for one delta value finds only that one site. Resolve every `ldr rX,[pc]/add
  rX,pc` pair instead — 102,754 pairs, 64,993 distinct globals in this image.
- `[typeinfo][vfn...][0]` groups are individual `_ZTV` vtables, **not** one
  registry array. Consecutive classes separated by a null are separate vtables, so
  a class appearing there proves nothing about instantiation.
- libstdc++ `__si_class_type_info` layout is `[0]`=own vtable, `[1]`=name,
  `[2]`=base typeinfo. A shared `[0]` across a family is the typeinfo *vtable*.
- rizin reported a 3.6 MB "function" at `0x7fc684` and zero callers for every
  setter there; decode `BL` by hand (J1/J2 are in the **second** halfword) instead.
- Constant propagation must use the **nearest preceding definition of any value**,
  not "the nearest assignment of the value I want".
- A FDAT block carries at most **1020** payload bytes, not 1024 — 4 go on checksum
  and size|endflag. Chunking a synthetic image by 1024 makes
  `b"\xff" * (1024 - 4 - len(payload))` multiply by a *negative* count, which
  yields an empty pad and a silently malformed block rather than an error.
- The `AesCbcCrypter` IV is the **first** 0x10 bytes of the 0x110-byte trailer, not
  the last 16: the reference implementation seeks to `-0x110` and then reads `0x10`,
  so the IV lands at `[-0x110:-0x100]`. My standalone reimplementation put it at the
  end and produced a block whose payload decrypted perfectly while its checksum
  disagreed — the per-block checksum is the only reason that surfaced.
- **A valid magic on the first block is not evidence of a successful decryption.**
  `dumps/fdat_decrypted.bin` decoded to a correct `UDTRFIRM` header while every
  subsequent block was random, because the block *size* was wrong (1000 vs 1024) and
  keystreams that agree on block 0 diverge immediately after. Check a structure
  further in — the CramFS magic at `0x200` — or measure printable density across
  many blocks, not just the header.
- `retool.xrefs.iter_references` only resolves the `ldr rX,[pc]` + `add rX,pc`
  *delta* pattern. It cannot see `movw`/`movt` pairs, which is how string literals
  are usually materialised, so "no references to this string" from that function
  alone means nothing. It returned zero for every probe in the `nflasha15` CamUser
  binary — **including the Golf Shot controls that are known to work** — which is
  what identified the pattern gap rather than a dead string.

## The flag chain dead-ends in a write-only byte

`ctx+0x10c` has exactly one consumer, and the chain from there is short:

```
ctx+0x10c == 1
  -> fcn.0039eb6c, three identical sites (0x39ee48, 0x39ef9e, 0x39f306)
  -> bl fcn.003a25fc          which is only: strb r0, [r3]   (set a global)
  -> global byte @ file 0xf59a58 := 1
  -> nothing.
```

`0xf59a58` is **never read**. Three independent negatives, and a contrast that
shows the method works:

| check | `0xf59a58` (Motion Shot) | `0xf59a5e` (a neighbour) |
|---|---|---|
| `ldr rX,[pc]` + `add rX,pc` references | **1** — its own setter, `0x3a25fc` | 1 — its getter, `0x3a2608` |
| 32-bit runtime-VA literal anywhere in the image | **0** | 1 — at `0x100c29c` |
| getter in the accessor cluster `0x3a25fc`–`0x3a2718` | **absent** | present, 3 BL callers |
| BL callers of its accessor | 7 (all *setters* in `fcn.0039eb6c`) | 3 readers |

The accessor cluster at `0x3a25fc`–`0x3a2718` is a flag table spanning
`0xf59a58`–`0xf59b80`. It provides a **setter** for `+0` and **getters** for
`+2 … +9`. 126 of that array's 304 bytes are additionally published as runtime-VA
pointers in `.data.rel.ro`; `0xf59a58` is not among them. The whole array is
zero-initialised (`.bss`).

So the flag is set from seven places and read from none. That is a third
independent exclusion, alongside the unconstructed `RcFill` and the mode gate — and
it is the one that makes the byte patch pointless.

## The pipeline exists but is not instantiated — the sequencer is dead

The Motion Shot *implementation* is all present and internally consistent: the
stage functions exist, they load their own names for logging, and they call the
`sa_func_*` dispatcher, which is itself live.

```
0x00334f48  bl    fcn.0056d50c          ; the sa_func name dispatcher
0x00334f4c  mov   r2, r0
0x00334f4e  cbz   r0, 0x334f5a
0x00334f50  ldr   r0, [0x335170]        ; "FW: %s: sa_func_MOTIONSHOT_start error (%d)"
```

The `sa_func` dispatch region `0x56d000`–`0x56e000` is the target of 16 BL call
sites, and `sa_func_MOTIONSHOT_init` / `_exit` are referenced from inside it. Three
of those 16 callers are in the Motion Shot stage code itself.

> **Correction: "its stages are registered" was an overreach, and is withdrawn.**
> 53 of 86 `Stage_*` names carry code references, which looked like a registry. It
> is not: clustering all 109 references gives **92 clusters of 3–4**, every one a
> `ldr rX,[pc]` inside an individual function. That is each stage loading *its own
> name* for a log line. It proves the functions exist, not that a sequencer can
> select them.

### The construction test

A constructor must reference its class's vtable address point (`vtable offset +
0x635c6000`) as a literal or a `MOVW`+`MOVT` pair. Absence of that reference means
nothing in the image points at the vtable — not even a derived class's secondary
base slot.

The test was **validated against four cases already settled independently** before
its verdict was believed:

| class | established as | test says |
|---|---|---|
| `8RcResize` | constructed | CONSTRUCTED ✔ |
| `11RcResizeDst` | constructed | CONSTRUCTED ✔ |
| `12RcResizeDstH` | constructed | CONSTRUCTED ✔ |
| `6RcFill` | dead | never constructed ✔ |

4/4, so the method reproduces both known answers.

| class | vtable | literals | MOVW/MOVT | verdict |
|---|---|---|---|---|
| `ScalarInfraMotionShotVideoSequence` | `0x0fc88c4` | 0 | 0 | **never instantiated** |
| `ScalarInfraMotionShotVideoManager` | `0x0fc88a4` | 0 | 0 | **never instantiated** |
| `...MotionShotVideoSequenceStageExecPost` | `0x0fc88f4` | 0 | 0 | **never instantiated** |
| `...MotionShotVideoSequenceStageWaitSAComp` | `0x0fc88dc` | 0 | 0 | **never instantiated** |

### The whole concrete layer is dead, not just Motion Shot

Running the same test across every `NS_SCALAR_INFRA` typeinfo name — **137 of
them** — splits perfectly along interface-vs-implementation:

| | count | what they are |
|---|---:|---|
| vtable referenced | **22** | `MsgHandler`, `ComponentFactoryIf`, `ComponentFactoryBase`, `ScalarInfraSequenceIf`, `ScalarInfraSequenceStageIf`, `ScalarInfraSyncSequenceIf`, `CmdIf`, `SystemCmdIf`, `CLogFactory`, `SubsystemAccessorIf`… — **all abstract bases and interfaces** |
| vtable not referenced | **115** | `MotionShotVideoSequence`, `MotionShotVideoManager`, `ScalarInfraSequenceJpeg`, `SequenceLiveView`, `SequenceSa`, `SequenceIdle`, every `*Factory`, every concrete `*Stage*`… — **all concrete implementations** |

Not one concrete sequence or factory in the family is instantiated. That is a much
broader fact than "Motion Shot is excluded", and it is the real shape of this build:
**the `NS_SCALAR_INFRA` framework is present as interfaces; its concrete layer is
compiled in but never wired up.** (Caveat on the positive side: for the 22, a
vtable reference can come from a derived class's base slot rather than a real
constructor, so "referenced" is the weaker claim. The 115 are unambiguous — their
vtables are pointed at by nothing at all.)

### What this means

`ctx+0x10c` was never the activation path, and the sequencer that would run the
feature is not instantiated either. So the exclusion stack is:

1. no menu or front end of any kind (verified by exhaustive search);
2. the CapMgr flag is initialised 0, cleared unless mode 5, and mode 5 is very
   likely never produced;
3. that flag's only consumer sets a byte nothing reads;
4. the object that arms the flag, `RcFill`, is never instantiated;
5. and now: **`MotionShotVideoManager` and `MotionShotVideoSequence` are never
   instantiated either**, along with every other concrete `NS_SCALAR_INFRA` class.

**Conclusion: enabling Motion Shot on this body is a port, not a patch.** The good
news is that all the compiled code is present — the stage functions, the `sa_func`
entry points, the pipeline classes — so a port is a wiring job (construct the
manager, register the sequence, supply the factories) rather than a
reimplementation. The bad news is that nothing in the existing firmware does that
wiring, and there is no UI to drive it, so it would have to be triggered
out-of-band.

## The live lead: a one-byte stage selector

This is the most concrete thing found, and it is a real gate rather than a
bookkeeping flag.

Every stage dispatcher in the `0x7b9000`–`0x7be400` family reads the same single
byte to decide which stage to run:

```
0x007b9b5e  ldrb.w r0, [r0, 0x23]
0x007b9b62  bx    lr
```

Each dispatcher is then a switch on that byte whose cases all pop the frame and
tail-branch:

```
0x007bdf86  push {r4, lr}
0x007bdf88  mov  r4, r0
0x007bdf8a  bl   fcn.007b9b5e        <- the selector byte
0x007bdf8e  cmp  r0, 6
0x007bdf90  bhi  0x7bdfe4
0x007bdf92  tbb  [pc, r0]
   ...
0x007bdfbe  mov r0, r4 ; pop.w {r4, lr} ; b.w 0x33c794
```

Reading the case bodies in address order (robust — the `tbb` table's alignment is
ambiguous because `Align(PC,4)` lands *before* the table) gives **59 case bodies
forming repeated 5-way groups**, and in **seven** of those groups the Motion Shot
stage `0x33c794` is the target:

| group | case 0 | case 1 | **case 2** | case 3 | case 4 |
|---|---|---|---|---|---|
| a | `0x33a294` | `0x3366d0` | **`0x33c794`** | `0x339214` | `0x329154` |
| b | `0x33a294` | `0x3366d0` | `0x330744` | **`0x33c794`** | `0x339214`, `0x329154` |
| c | `0x33a294` | `0x3366d0` | `0x3390d8` | **`0x33c794`** | `0x329154` |
| e | `0x33a294` | `0x3366d0` | `0x339158` | **`0x33c794`** | `0x329154` |
| g | `0x33a294` | `0x3366d0` | **`0x33c794`** | `0x329154` | — |

`0x329154` is the last case in every group (the idle stage), and `0x33a294` /
`0x3366d0` are the first two in every group. So the byte at `+0x23` is a small enum
and **2 selects the Motion Shot stage** in at least two of the groups.

The dispatchers are virtual methods — each has exactly one vtable slot
(`0x1074ae0`, `0x1072814`, `0x107a994`, `0x107ae5c`).

> **Correction: the stage functions *are* reachable.** A BL-only scan reported
> "0 BL callers — NOT CALLED BY ANYTHING" for the Motion Shot stage functions.
> That was wrong: the compiler emits these switches as **tail calls**, so
> `0x33c794` is reached from **17 `b.w` sites** across `0x7ba72e`–`0x7be276`, and
> the other stage functions from 4 and 1. A call-graph scan that only understands
> `BL` will call a whole region of tail-called code dead.

### What is still missing

The selector byte has **no immediate-offset writer at all** — 0 sites for
`strb rX,[rY,#0x23]`, 0 for `strh`, 0 for `str.w`. So the object is not populated
by field assignment; it is filled by a **struct copy** from a descriptor, and that
descriptor is where a patch would go (a single byte in a data table). It has not
been located.

Nor is it established that any instance of the objects owning these dispatchers
exists. The vtable→class identification failed: scanning backwards from a vfn slot
for a typeinfo pointer lands in a **neighbouring vtable** in that densely packed
region — the one attempt returned `imola33imola_common_enc_dec_base_handlerE` for
the stage dispatcher, which is plainly the wrong class, so no verdict is claimed
from it. The construction test itself still reproduces its 2/2 control.

## Comparison with Golf Shot

Golf Shot is the *reverse* case, which is why it is not simply the better target:

| | Motion Shot | Golf Shot |
|---|---|---|
| stages | 3 names, **all referenced** | **0** `Stage_*` names |
| `sa_func` dispatch | live, 16 callers, called from its own stage code | names present, no `Stage_` membership |
| pipeline log strings | referenced | mostly **0 references** — `[SAN]StartGolfShot` 0, `[SAN]StopGolfShot` 0, `[SAN]AnalyzeGolfShot` 0, `[ADF][DBGCMD]SoundAnalyzer StartGolfShot` 0, `[GOLFSHOT]SA_* Exec Err` 0, every `ALOCK_ERR` 0 |
| setting / validator / gate | all three present | none |
| debug-command trigger | none | `[ADF][DBGCMD]SoundAnalyzer StartGolfShot` exists but its log string has **0 references** |

So the earlier fallback plan — trigger Golf Shot through the `[ADF][DBGCMD]` debug
command for a zero-patch win — **is not supported either**: that command's own
string is unreferenced, which is the same unreachable-string pattern already in the
recurring-failure list. A handful of Golf Shot strings do have references
(`Stage_EncodeJpeg_GolfShot_THM` ×1, `GolfShotJpegStream` ×1, `[GOLFSHOT]FREE_ERR`
×2, `[SAN]StopGolfShot` ×1), so parts of it are reachable, but there is no
demonstrated entry path.

Neither feature is a patch on this build. Motion Shot has a live pipeline with no
reachable trigger; Golf Shot has partial code with no demonstrated entry.

## Confidence

| claim | confidence |
|---|---|
| Motion Shot is detect-moving-subject-then-record, via vision | **medium-high** — from the algorithm, stage and pipeline names; no prose description exists in the image |
| mode value stored at `ctx+0xd4`, consumed in cap_mode 5 | **high** — read from the setter and `case 5` |
| the three capture-mode gates and their allowed modes | **high** — read from the instruction stream |
| `ctx+0x10c` initialised to 0, cleared only by the gate | **high** — both sites read directly |
| `0x7fc696` is the only arming site | **high** — exhaustive sweep of all 123 stores with constant propagation |
| it is `RcFill::vfn[6]` | **high** — vtable slot, typeinfo name read from RTTI |
| **`RcFill` is never instantiated** | **high** — no literal and no `MOVW`/`MOVT` for its vtable address anywhere, while 8 siblings have theirs; residual gap: an address synthesised arithmetically rather than loaded would be missed |
| `fcn.0039eb6c` is the only consumer | **medium-high** — one function passes a `cmp`+branch test on a `+0x10c` load; a consumer branching on the value some other way would be missed |
| **the global at `0xf59a58` is never read** | **high** — three independent negatives (1 reference vs 2 for a neighbour, 0 published literals vs 1, no getter vs 3 callers), and the array it belongs to is otherwise routinely published |
| the stage functions exist and call the live dispatcher | **high** — `bl fcn.0056d50c` at `0x334f48`, immediately followed by the `sa_func_MOTIONSHOT_start error` check |
| ~~the stages are registered in a sequencer~~ | **withdrawn** — the 109 `Stage_*` references form 92 clusters of 3–4, each a function loading its own name for a log; that is not a registry |
| the vtable-construction test is sound | **high** — reproduces 4/4 cases settled independently (3 constructed, `RcFill` dead) |
| **`MotionShotVideoManager` / `MotionShotVideoSequence` are never instantiated** | **high** — 0 literal and 0 `MOVW`/`MOVT` references to either vtable's address point |
| 115 of 137 `NS_SCALAR_INFRA` classes are never instantiated, and the split is exactly interface-vs-implementation | **medium-high** — the split is clean, but for the 22 "referenced" the reference may be a derived class's base slot rather than a constructor; the 115 are unambiguous |
| `ctx+0xc8` is a latch of the previous resolved mode | **high** — the epilogue writes back exactly the four registers loaded at entry |
| the latch never holds 5 | **medium** — the exit value is the same `r4` whose literal set excludes 5, but five other functions also write a `+0xc8` and the identity test separating them is weak |
| the three patch bytes and their effects | **high** — each validated by before/after disassembly |
| **the flag patches would enable the feature** | **withdrawn — they would not**; the chain they arm terminates in an unread byte |
| **enabling Motion Shot is a port, not a patch** | **high** — five independent exclusions, the last two of them validated by a method with a 4/4 control |
| Golf Shot's `[ADF][DBGCMD]` route is a zero-patch win | **not supported** — that command's own log string has 0 references |
| offered on a ZV-E10 | **not established** |

## Reproducing

```
retool.cmd disasm avcam 0x316ef8 -n 40   # the 34-way cap_mode resolver
retool.cmd disasm avcam 0x317128 -n 24   # the Mshot / trinity / SpotMulti gates
retool.cmd disasm avcam 0x7f4dc  -n 16   # the CapMgr constructor: flag := 0
retool.cmd disasm avcam 0x7fc6a6 -n 10   # the arming site, +0x10c := 1
retool.cmd disasm avcam 0x39ee46 -n 12   # the consumer's cmp + branch + call
retool.cmd disasm avcam 0x3a25fc -n 6    # the global setter
retool.cmd strings  avcam Mshot
retool.cmd strings  avcam MOTIONSHOT
retool.cmd strings  avcam motion_shot_mode
retool.cmd strings  avcam HumanMovingArea
python -m retool globals 0xf59a58         # PC-relative global resolver
python -m retool offsweep 0x10c str       # constant-propagating offset sweep
```

The last two are `retool/offsets.py`, added so these offsets are reproducible from
committed tooling rather than from one-off scripts.

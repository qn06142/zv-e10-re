# Motion Shot: what it is, how it is gated, and why it never runs

Addresses are file offsets (runtime VA = offset + `0x635c6000`). `ctx` is the
per-capture context.

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

## Patch candidates

All three are **one byte**, and all three were validated empirically: flip the
byte in a copy, disassemble before and after, and confirm the only change in the
window is the intended one.

| | file offset | change | effect | risk |
|---|---|---|---|---|
| **A** | `0x0317133` | `d0` → `e0` | `beq 0x317144` → `b 0x317144`: the flag is **never cleared** | flag stays set in modes that cannot service motion shot |
| **B** | `0x007f4fa` | `00` → `01` | `movs r1,#0` → `movs r1,#1`: **preset** the flag at construction | `r1` is shared with the `+0x114` store, so that field also becomes 1 |
| **C** | `0x039ee4f` | `d0` → `e0` | the consumer's `bne` becomes unconditional: always call `fcn.003a25fc` | bypasses the mode check entirely; which of the three sites is the right one is unknown |

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

Patch A is the same shape as the already-validated ZIT SA patch at `0x1e31f0`
(`08 d0` → `08 e0`).

**Recommended shape: A + B, two bytes.** Together they mean the flag is set once at
construction and never vetoed, so the camera proceeds down its own Motion Shot path
exactly as it would on a model where the feature is offered. The firmware's config,
validation and init all still run; we change a *default*, not a forged state.

**Why not C alone:** it is the smallest diff, but it discards the mode check rather
than satisfying it, and the three candidate sites are in different states of a
6-way switch with no way yet to tell which is the live one.

### The `+0x114` side effect of patch B

`r1` feeds both `str.w r1,[r3,0x10c]` and `str.w r1,[r3,0x114]`, and no register
holds 1 at that point, so a single-byte edit cannot set one without the other.

Mitigating evidence: `+0x114` has 277 accesses image-wide and 28 sites compare it
against a constant, but **none of those is in a function that also touches the
CapMgr flag triple** (`+0x10c`/`+0x110`/`+0xbc`). Within the 19 functions that do
share that triple, `+0x114` is written and read but never compared to an immediate
after a load. It behaves like a sibling field of the same request block, not like a
tested predicate. That is mitigation, **not proof** — treat as unquantified.

## Open unknowns

- **What sets `ctx+0xc8`.** This is now the load-bearing unknown: the Motion Shot
  flag survives the gate only when `ctx+0xc8 == 5`, and nothing found writes a
  literal 5 to it. Until that field's origin is traced, patch A is what removes
  the dependency.
- What reads the global at file `0xf59a58`, and therefore what the flag ultimately
  drives. It has exactly one reference by the `ldr [pc]/add pc` idiom — the write.
- Whether `ctx+0xc8` is something a user can influence at all, given there is no
  UI.
- Which `SaDriver*` type the audio path needs — still a guess
  (`SaDriverLinearPhase` is unverified). Matters because `StageWaitSAComp` suggests
  the pipeline may touch audio.
- Whether `MS_DUMP_RAW_PRELIGHT_*` implies a sensor readout mode this body cannot
  enter. Untested.
- The reader of `ctx+0x114` that would settle the patch-B side effect.

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

## Comparison with Golf Shot

| | Motion Shot | Golf Shot |
|---|---|---|
| implementation | complete | complete |
| setting | `motion_shot_mode` | none |
| validator | `CheckSetMotionShotMode` | none |
| per-mode resolution | case 5 of 34 | none |
| capture-mode gate | `ctx+0x10c`, allows 5 | none |
| arming object | `RcFill` — **never instantiated** | n/a |
| entry points | `sa_func_MOTIONSHOT_*` | `sa_func_GOLFSHOT_*` |
| sensing | vision (`HumanMovingArea`) | sound (mic) |

Golf Shot has the bottom half only. Motion Shot has the whole chain, which is why
it is the better target — and the honest caveat is that "whole chain" means
"fully built", not "offered on this model". Motion Shot's exclusion is now
*located* rather than inferred, which is the new fact.

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
| the three patch bytes and their effects | **high** — each validated by before/after disassembly |
| `cap_mode` 5 is reachable in practice | **unknown — the remaining blocker** |
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

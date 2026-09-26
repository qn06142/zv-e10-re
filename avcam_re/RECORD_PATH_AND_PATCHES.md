# Record button → hardware: the path, and where to patch

Addresses are **file offsets**. Bank addresses are absolute runtime addresses.

This traces what the firmware does when record is pressed in video mode, as far
as it is currently established, and identifies concrete patch points. Where a
link in the chain is not yet proven it is marked, rather than filled in.

## Summary of patch candidates

| # | target | offset | change | effect | risk |
|---|---|---|---|---|---|
| **1** | ZIT SA feature gate | **`0x1e31f0`** | `08 d0` → `08 e0` | forces every FuncType through the enable check | med — see below |
| **2** | transfer-size limit, 60 Hz | `0x3f6dc` / `0x3f6e2` | raise `0x321` and `0x40` | raises the per-frame transfer ceiling | low |
| **3** | transfer-size limit, 48 Hz | `0x3f728` / `0x3f72e` | as above | as above, 48 Hz path | low |
| 4 | record clip duration | not located | — | — | — |

Candidate 1 is the one that answers "enable a feature the camera has switched
off". Candidates 2–3 are ceilings rather than gates.

---

## 1. The feature gate — `ZIT SA`, the strongest result

### What it is

`fcn.001e31e4` is the entry point of a subsystem the firmware calls **ZIT SA**,
and it does two things: it checks whether the requested function is enabled, and
if so runs the `ZIT_Sa*` open/start/close lifecycle. The log strings give the
names away — one function emits all of these:

```
0x1e31bc  'IMG:%s: `CloseFreeZitMMUParam' error'
0x1e31f4  'IMG:ERROR:FuncType:%x is not enable at FuncID:%x'
0x1e320e  'IMG:ERROR: ZIT_SaOpen %x'
0x1e3222  'IMG:ERROR: ZIT_SaStart %x'
0x1e323e  'IMG:ERROR: ZIT_SaStart %x'
0x1e3280  'IMG:ERROR: ZIT_SaClose %x'
0x1e329a  'IMG:convDdcByCpu: Bad Input format.'
0x1e33c4  'IMG:ZitSA_ConvDdc: saParamBuf is shortage. %d %d'
0x1e3432  'IMG:ZitSA_ConvDdc: outBuffer overflow.'
0x1e3464  'IMG:ZitSA_ConvDdc: outBuffer overflow.'
```

Nearby strings name the neighbours: `ZIT_Sa_ConvDdc`, `CloseFreeZitMMUParam`,
`ddl_saMmuMakeParamAll`. `Sa` with `ZitMMU` and `ConvDdc` reads as a scene /
analysis service working over an MMU, which is consistent with the image
pipeline's own vocabulary rather than with recording as such. **What "SA"
expands to is not established.**

### The gate, exactly

```
fcn.001e31e4(r0 = ctx, r1 = arg, r2 = FuncType):

  0x1e31e4  push  {r3, r4, r5, r6, r7, lr}
  0x1e31e6  mov   r7, r2              ; FuncType
  0x1e31e8  ldr   r2, [r0, 4]         ; ctx->field_0x04
  0x1e31ee  cmp   r2, #1
  0x1e31f0  beq   0x1e3204            ; enabled if field_0x04 == 1
  0x1e31f2  cbz   r7, 0x1e3204        ; enabled if FuncType == 0
  0x1e31f4  ldr   r0, [0x1e324c]      ; -> the FuncType/FuncID message
  0x1e31f8  mov.w r6, #0x230
  0x1e31fe  bl    fcn.003a98c4        ; log it
  0x1e3202  b     0x1e3248            ; return 0x230

enabled path:
  0x1e3204  mov   r0, r4
  0x1e3206  bl    fcn.001e3158        ; ddl_saMmuMakeParamAll
  0x1e320c  cbz   r0, 0x1e3214
  0x1e3214  bl    fcn.0076447e        ; ZIT_SaStart
  0x1e3234  bl    fcn.001e30e0        ; close/free
  0x1e3248  mov   r0, r6
  0x1e324a  pop   {r3, r4, r5, r6, r7, pc}
```

So the enable condition is:

```
enabled  ⟺  (ctx->field_0x04 == 1)  ||  (FuncType == 0)
```

The enable state is a single word at **`ctx+4`**, and `FuncType 0` is always
allowed. Nine callers, all in `0x1e34bc`–`0x1e4af8`.

### The patch

Current bytes at `0x1e31f0` are `08 d0`, which rz-asm's disassembler renders as
`beq 0x14`. The same displacement as an unconditional branch is `08 e0`:

```
0x1e31f0   08 d0   beq 0x14     ; branch to 0x1e3204 if equal
0x1e31f0   08 e0   b   0x14     ; always branch to 0x1e3204
```

Both verified by `rz-asm -a arm -b 16 -d`:

```
$ rz-asm -a arm -b 16 -d "08d0"   ->  beq 0x14
$ rz-asm -a arm -b 16 -d "08e0"   ->  b   0x14
```

A two-byte change that removes the gate. The `cbz r7` at `0x1e31f2` becomes dead
but is harmless.

**The risk, stated plainly:** the gate exists because a disabled FuncType has no
allocated MMU parameters. Forcing entry means `fcn.001e3158` and `fcn.0076447e`
run against parameters that may not exist. Expect either a clean no-op, a garbage
result, or a fault in the SA subsystem — not a working feature. The correct way
to use this is as a **probe**: if forcing a FuncType produces visibly different
behaviour rather than a crash, that FuncType is real and gated, and the enable
word at `ctx+4` is what gates it. Flipping `ctx+4` to `1` at runtime is the
lower-risk version of the same experiment and needs no code patch at all.

The FuncType values in use around this code are `0x21`, `0x22`, `0x23` and
`0x41` (from the switch in `fcn.001e2f84`, which extracts bytes from a record
fetched via `fcn.000196a0`). The first lookup key tried at `0x1e3180` is
`mvn #0x21002100` → `0xDEFFDEFF`.

---

## 2. The transfer-size ceiling

`fcn.0068b61a` picks a per-frame transfer budget by frame rate:

```
0x68b628  bl   fcn.0003f79c          ; query the mode
0x68b62c  ldr  r3, [var_ch]
0x68b62e  cmp  r3, #3
0x68b630  beq  0x68b642              ; == 3  -> 48 Hz
0x68b632  blt  0x68b63a              ; <  3  -> default
0x68b634  subs r3, #6
0x68b636  cmp  r3, #4
0x68b638  bls  0x68b64a              ; 6..10 -> third variant
0x68b63a  bl   fcn.0003f6b8          ; 60 Hz
0x68b642  bl   fcn.0003f704          ; 48 Hz
0x68b64a  bl   fcn.0003f750          ; 6..10
```

and the 60 Hz variant is a short, fully readable function:

```
fcn.0003f6b8(r0 = ctx):
  0x3f6c4  bl   fcn.0003f590
  0x3f6ca  bl   fcn.0068b55a
  0x3f6ce  ldr  r1, [sp+0x14]         ; mode code
  0x3f6d0  cmp  r1, #1
  0x3f6d2  beq  0x3f6da
  0x3f6d4  cmp  r1, #3
  0x3f6d6  bne  0x3f6f2              ; -> error, returns 0
  0x3f6e6  ldr  r3, [r4+0x10]         ; count
  0x3f6e8  movw r0, #0x321
  0x3f6ec  muls r0, r3, r0
  0x3f6ee  adds r0, #0xc0
  0x3f6f0  b    0x3f6fc              ; return
  0x3f6da  ldr  r3, [r4+0x10]
  0x3f6dc  movw r0, #0x321
  0x3f6e0  muls r0, r3, r0
  0x3f6e2  adds r0, #0x40
  0x3f6f2  ldr  r0, [0x3f700]         ; 'LimitTransSize60Hz'
  0x3f6f6  bl   fcn.00699e48
  0x3f6fa  movs r0, #0
```

```
limit = 0x321 * ctx->count + 0x40   (mode 1)
limit = 0x321 * ctx->count + 0xC0   (mode 3)
limit = 0                           (any other mode)
```

`0x321` is 801. Raising it, or raising the `0x40`/`0xC0` bases, raises a
per-frame transfer ceiling. **Not established:** what `ctx->count` counts, and
whether the caller compares a measured value against this or uses it as an
allocation size. The two patch sites are `movw r0, #0x321` and the following
`adds`.

---

## 3. The record lifecycle, as far as traced

### State machine

A nine-state machine, names contiguous at `0x9636ef`:

```
CACHE_REC_INACTIVE     0x9636ef
CACHE_REC_OPENING      0x963702
CACHE_REC_INITIALIZING 0x963714
CACHE_REC_STARTING     0x96372b
CACHE_REC_CACHING      0x96373e
CACHE_REC_RECODING     0x963750   <- the firmware's own spelling
CACHE_REC_STOPPING     0x963763
CACHE_REC_FINALIZING   0x963776
CACHE_REC_CLOSING      0x96378b
```

These have **no direct PC-relative reference** — they are a name table reached by
computed address, which is why the log format is `= 0x%x(%u)`: a value printed
alongside its name from that table. The enum values behind them are not yet
recovered; recovering the table's base and stride would give both the values and
the transition function.

### Encoder state machine

`enc/sfmc_enc_state_normal.cpp`, code around `0xe2180`–`0xe2600`. It dispatches
on a message id (`cmp r1, #0xd` / `#0xe` / `#0xf`) and logs
`[STATE]%s unknown callback id`, `[STATE]queue_set_qos_param`,
`enc_internal_stop_comp`, `[STATE]illegal timing`.

### Stop timing

`[TIMING]calc_stop_timing: m_state: %s-> STATE_SAKUHINKA_CANCEL_STOPPING`
referenced from `0xed92c`, with
`[TIMING]calc_stop_timing: [m_start_param.interval_by_frame:%u]` and
`[TIMING][CHK_STOP_TIMING_NOT_AHEAD_OF_DEADLINE][m_state:%s]` from `0xee530`.
This is where a recording **duration** limit would be computed.
`interval_by_frame` is the obvious input and the obvious thing to instrument.

### Recording mode

`SD_SAKUHINKA`, `HD_SAKUHINKA`, `SD_SAKUHINKA_NOAUDIO`,
`HD_SAKUHINKA_NOAUDIO` (SAKUHINKA = 録画, recording) at `0x9543b7`–`0x954433`,
selected through a 17-entry enum at `fcn.0008f5f8` (`0x8f5f8`).

`IMG:MovieStart mode:%x` sits at `0xa34ffd` but has no direct reference; the code
near `0x17796` references a neighbouring string and is FP-arithmetic
(`vcvt.f32.s32`, `vdiv.f64`), so **that is not the MovieStart path** and I have
not located the real one.

### Where this reaches the hardware

The record path does not touch registers directly. Hardware programming goes
through the register-bank accessors — `0x7f5346` (read) and `0x45db14` (write) —
against banks `0xF3400000`, `0xF2A30000`, `0xF2A00000`. See
`REGISTER_MMIO_MAP.md`. The two are joined by a path that is **not yet traced**:
nothing found so far connects the record state machine to the bank accessors.

---

## 4. Corrections to earlier work

- **`0x522ad0` is `memset`, not `ZIMA_DVENC_launch`.** It fills `0xFF` with
  unrolled `stmge ip!, {r2,r3}`; 5,459 xrefs. **`0x5223ec` is `memcpy`**, not
  `encode_param_submit`; unrolled `ldm`/`stm` by 16 with an `ands ip, r0, #3`
  alignment fixup; 5,004 xrefs. Both were auto-scraped names. Consequently the
  "commit via `ZIMA_DVENC_launch` command `0xd20`" account of the register-write
  path is wrong: `0x4403e2` is `memset(buf, 0xFF, 0x200)`. Symbol DB and
  `REGISTER_WRITE_PATH.md` updated.
- **The "ISP per-function enable check at `0x1e31fc`" is at the wrong
  address.** `0x1e31fc` is the `add r0, pc` in the *previous* function
  (`fcn.001e3158`, the `ddl_saMmuMakeParamAll` path, which logs
  `IMG:ddl_saMmuMakeParamAll error %x` and returns `0x230`). The FuncType/FuncID
  gate is at `0x1e31ee`–`0x1e31f2` in `fcn.001e31e4`, and the message
  `IMG:ERROR:FuncType:%x is not enable at FuncID:%x` does exist, at `0x9a32d1`.
  The old claim's wording was right; the address and the characterisation
  ("ISP") were not — this is the ZIT SA subsystem.

## 5. What is not established

- The record **button press → message** link. No key/button driver located yet.
  `RecStartInfoMsgHandler` and `RecStopMsgHandler` exist as RTTI at `0x983402`
  and `0x983426`; reaching their vtables via those type names is the next step.
- The `CACHE_REC_*` enum values and the transition function.
- The real `MovieStart` path.
- The clip **duration** limit — the most obvious thing to want, and not found.
  `clipDurationPtm64_low/high` (`0x95ab62`, `0x95ab93`) and `clipFrameCounter`
  (`0x95af54`, referenced from `0xae086`) are the places to look.
- What `ZIT SA` stands for, and what its FuncTypes do.
- Any link from the record state machine to the register banks.

## 6. Confidence

| claim | confidence |
|---|---|
| gate condition `(ctx+4 == 1) \|\| FuncType == 0` | **high** — read from the instruction stream |
| `0x1e31f0` patch bytes `08 d0` → `08 e0` | **high** — both decoded by rz-asm |
| gate is a ZIT SA / scene-analysis lifecycle, not ISP | **high** — from the log strings it emits |
| `CACHE_REC_*` nine-state record lifecycle | **high** for the names; values not recovered |
| transfer ceiling `0x321*n + 0x40/0xC0` | **high** for the formula; **unknown** what it bounds |
| encoder state machine in `sfmc_enc_state_normal.cpp` | **medium** — from string references, chain not walked |
| `ZIT SA` meaning, button-press entry, duration limit | **not established** |

## Reproducing

```
retool.cmd disasm avcam 0x1e31e4 -n 40   # the ZIT SA gate + lifecycle
retool.cmd disasm avcam 0x1e3158 -n 24   # ddl_saMmuMakeParamAll (the 0x230 path)
retool.cmd disasm avcam 0x1e2f84 -n 24   # the FuncType switch (0x21/0x22/0x23/0x41)
retool.cmd disasm avcam 0x3f6b8 -n 20    # transfer ceiling, 60 Hz
retool.cmd disasm avcam 0x3f704 -n 20    # transfer ceiling, 48 Hz
retool.cmd disasm avcam 0x68b61a -n 16   # the frame-rate dispatch
retool.cmd disasm avcam 0x522ad0 -n 20 --arm   # memset, not ZIMA
retool.cmd strings avcam SAKUHINKA       # recording modes
retool.cmd strings avcam CACHE_REC       # the record state machine
retool.cmd strings avcam FuncType        # the gate message
```

rizin prints `void *memset(void *s, int c, size_t n)` at `0x522ad0` and
`void *memcpy(void *s1, const void *s2, size_t n)` at `0x5223ec` — its own
signature matching, arrived at independently of the disassembly.

**Known issue:** `retool symbols apply` exits with rizin `3221226356`
(`STATUS_HEAP_CORRUPTION`) partway through its save. The renames do land and the
project stays usable for queries, but the sync is not clean. Rebuild with
`retool analyze avcam --force` if the project starts misbehaving.

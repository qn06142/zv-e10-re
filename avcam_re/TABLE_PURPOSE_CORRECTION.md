# Correction + code-derived findings (2026-09-26)

Follow-up to `OPENGATE_PATCH_SURFACE.md`. That file asserted the *purpose* of
two data structures from their contents. Both assertions were guesses. This
file records what the consuming code actually says, and retracts what could
not be substantiated.

## The trap: PC-relative deltas look exactly like pointers

A Thumb compiler materialises a data address as two instructions:

```
ldr  rX, [pc, #imm]      ; literal pool slot
add  rX, pc              ; effective address = pool_value + PC
```

The pool holds a **delta**, not an address. A delta is a plausible 32-bit value
and often has bit 0 set, so it reads like a Thumb function pointer. Reading
pool values as addresses produced two confident, wrong conclusions during this
investigation:

| Wrong claim | What the delta actually pointed at |
|---|---|
| "16 pointer-table entries at `0x8f6c8` are a handler vtable" | Strings: `SD_SAKUHINKA`, `STREAMING`, `GEARED_ENC`, … |
| "literal `0x89dae0` at `0x0c0768` references the mode table" | The string `DEC_REPORT_RESUME_DECODE` |

`retool/xrefs.py` now resolves deltas correctly. Note that rizin's `axt`
returns **nothing** for this image — verified even against strings that are
demonstrably referenced — so `retool xrefs` does not use it.

Two bugs were found and fixed while building this, both of which had produced
plausible-looking but wrong output:

- A halfword **index** was used where a **byte address** was required, so pool
  slots came out as `0x47b98` instead of `0x8f6c8`. Every target was wrong.
- The `add rX, pc` recogniser had a bit-mask condition that was never true, so
  it matched nothing at all.

## Verified: the mode table at `0x89DADE` (19 records)

Established by reading the consumer, not by inspecting the bytes.

The accessor is `fcn.001aabdc`:

```
0x1aabe6  bl   0x7403ca              ; resolve a sub-index
0x1aabea  ldr  r3, [0x1aac78]        ; delta
0x1aabec  add  r3, pc                ; r3 = 0xB772C8  (32-bit indirection table)
0x1aabee  ldr.w ip, [r3, r0, lsl 2]  ; ip = indirection[sub-index]
0x1aabf8  ldr  r7, [0x1aac7c]        ; delta 0x6f2ede
0x1aabfa  lsl.w r8, r2, 4            ; stride = 16
0x1aabfe  add  r7, pc                ; r7 = 0x89DADE
0x1aac00  add.w r0, r7, r8          ; r0 = 0x89DADE + 16*index
0x1aac04  ldrh.w r7, [r7, r8]        ; load record key0
0x1aac08  cmp   r7, r3               ; vs caller's u16
0x1aac0c  ldrh.w r8, [r5, 2]        ; caller's second u16
0x1aac10  ldrh  r7, [r0, 2]         ; record width
0x1aac12  cmp   r8, r7
```

So the table is a **linear search** over a 16-byte-stride grid at `0x89DADE`,
terminated by a record whose mode id is `0xFFFFFFFF` (at `0x89DC1C`, which is
exactly `0x89DADE + 16*19 + 14`). 19 records.

The struct fields are 2-byte-offset within each 16-byte record, so the code
reaches them as `base+2` with `[r0+0], [r0+4], [r0+8], [r0+0xc]`:

| record offset | type | field |
|---|---|---|
| +0 | u16 | padding (0 in every record) |
| +2 | u32 | `(height << 16) | width` |
| +6 | u32 | flags — 1 for records 0..13, 0 for 14..18 |
| +10 | u32 | family — 2 and 3 for the two 4K readouts, 1 otherwise |
| +14 | u32 | mode id — 0, 19, 1, 20 for the 4K records, then 3..18 |

```
  n   record   (h<<16)|w     flags family    id
   0  0x89dade   2160x3840       1      2     0
   1  0x89daee   2160x3840       1      3    19
   2  0x89dafe   2160x4096       1      2     1
   3  0x89db0e   2160x4096       1      3    20
   4  0x89db1e   1080x1920       1      1     3
   5  0x89db2e   1080x2048       1      1     4
   6  0x89db3e   1080x960        1      1     5
   7  0x89db4e    480x640        1      1     6
   8  0x89db5e    480x768        1      1     7
   9  0x89db6e   1280x720        1      1     8
  10  0x89db7e    812x1440       1      1     9
  11  0x89db8e    920x1440       1      1    10
  12  0x89db9e   1080x1440       1      1    11
  13  0x89dbae    540x960        1      1    12
  14  0x89dbbe    540x1440       0      1    14
  15  0x89dbce    540x1920       0      1    15
  16  0x89dbde    540x960        0      1    16
  17  0x89dbee    240x720        0      1    17
  18  0x89dbfe    288x720        0      1    18
  19  0x89dc0e   -- terminator: id = 0xFFFFFFFF at 0x89dc1c
```

**The mode ids are independently corroborated.** The sole caller tests the
returned id against `{0, 0x13 (19), 1, 0x14 (20)}` — exactly the four 4K
records — and sets a separate "4K" flag at `[r4+0xc0]` when it matches:

```
0x3ab0b2  ldr  r3, [r4, 0x48]   ; id from the resolver
0x3ab0b4  cbz  r3, ->is4k
0x3ab0b6  cmp  r3, 0x13         ; 19
0x3ab0ba  cmp  r3, 1
0x3ab0be  cmp  r3, 0x14         ; 20
0x3ab0c2  movs r2, 1            ; -> [r4+0xc0] = 1
```

So "4K mode" is keyed on the **mode id**, not on the dimensions. That is a
separate concept from the height field, and is the more likely real lever.

### Note on two intermediate corrections in this file

An earlier revision withdrew the `family`/`mode id` fields as a 4-aligned
misread, and an earlier one still had the base as `0x89dae0` with a packed
first word. **The original field reading was right**; only the base needed
refining, to `0x89DADE` with the fields 2-byte-offset. The withdrawal was
itself the error and is reversed here. Both were caught by the terminator at
`0x89DC1C` and by the caller's id comparison, neither of which is a
coincidence.

### How the resolver is called

`fcn.001aabdc` is a **memoising** wrapper. It reads a cache table at
`0xC972C8` (which is all zeros in the image — `.bss`, populated at runtime) and
writes results to the sibling table at `0xC972C6`. On a cache miss it falls
into a scan that walks records from the cached index upward.

Its **only** call site is `0x3ab074`, which fills a struct: `family ->
[r4+0x44]`, `mode id -> [r4+0x48]`, from `key = r4+4` and `selector = [r4]`.
The surrounding code references DMM/OSAL memory-manager strings
(`AsyncGetUnitMaxMemNumber`, `PowerOnUnit`, `osal_try_valloc_msg`,
`ERR_OSAL_UIPC`, `ERR_DMM_RET_CODE`), so this consumer sizes/configures a
memory unit. It is shared infrastructure, not specific to one direction.

### Correction to the earlier file

`OPENGATE_PATCH_SURFACE.md` placed the table at `0x89dae0` and read the record
as `(res, 1, family, id)` with `res = (h<<16)|w`. The base is `0x89DADE` and
the packing is **two u16 fields (width, height)**, not one packed word — the
apparent `(h<<16)|w` word is just how two adjacent u16 fields look in a hex
dump. The field semantics above are correct; the framing was not.

The failed flash is **not** explained by an offset mistake. `+2` is a packed
`(height << 16) | width`, so writing `0x0A000F00` over the word at `0x89DAE0`
leaves the width (low half, `0x0F00` = 3840) untouched and only raises the
height. That edit was structurally correct.

What the code does explain is that this table is a **lookup consumed by the
memory manager** (DMM/OSAL, at `0x3ab074`). Editing its height changes how
memory is sized, not what the sensor is told to read out. The capture
geometry is programmed elsewhere, by a register write. So the firmware ran
normally and produced no visible change: the edit took effect, but on a field
that does not drive the output.

The more promising lever is the one the caller keys off — **the mode id**.
Records 0..3 are ids `0, 19, 1, 20`, and the caller raises a distinct "4K" flag
from exactly that set. Whatever programs the sensor for a 4K readout is
downstream of that flag.

Addresses, for reference: packed words at `0x89DAE0`, `0x89DAF0`, `0x89DB00`,
`0x89DB10`; height half-words at `0x89DAE2`, `0x89DAF2`, `0x89DB02`, `0x89DB12`;
mode ids at `0x89DAEC`, `0x89DAFC`, `0x89DB0C`, `0x89DB1C`.

## Retracted: the "per-stream encoder config table" at `0x8c4440`

No consumer was found. With the corrected resolver:

- **0** PC-relative references land in `0x8c4000..0x8c6000`.
- The 16-byte "records" there contain a `0xffffffff` marker and values that
  look like buffer sizes, but that was pattern-matching.

The "14 records carry a 2160-height word" claim came from the same
`(h<<16)|w` misreading, so it is withdrawn. `0x8c4440` may still be meaningful
data reached by a computed address, but **its purpose is unknown** and nothing
here supports calling it encoder configuration.

The nearby pointers at `0x8c4d28`, `0x8c4d35`, … that looked like a vtable
are deltas, resolved above to recording-mode name strings.

## Verified: recording-mode name table at `fcn.0008f5f8`

A pure lookup: compares `r1` against IDs and returns a name string. IDs and
names (deltas resolved, strings read back to their start):

| id | name | id | name |
|---|---|---|---|
| 0x00 | *(Genlock NULL message)* | 0x10 | `ENC_PROXY` |
| 0x08 | `SLIDESHOW_NOAUDIO` | 0x1c | `HD_SAKUHINKA` |
| 0x0a | `NAMESURO` | 0x1f | `STREAMING` |
| 0x0b | `NAMESURO` | 0x20 | `STREAMING` |
| 0x0c | `BGMCHK` | 0x21 | `GEARED_ENC` |
| 0x0d | `BGMCHK` | 0x22 | `GEARED_ENC` |
| 0x0e | `SD_SAKUHINKA` | 0xf0 | `HILGT_PB_NOAUDIO` |
| 0x0f | `SD_SAKUHINKA` | 0xf1 | `HILGT_PB_NOAUDIO` |
| | | 0xf2 | `HD_SAKUHINKA_NOAUDIO` |

Consecutive ID pairs share a name (0x0a/0x0b, 0x0e/0x0f, 0x1f/0x20, 0x21/0x22,
0xf0/0xf1), so the ID is not a plain enum — the low bit selects a variant
within a mode, consistent with the `_NOAUDIO` suffixes. `SAKUHINKA` (動画) is
Japanese for video, so these are movie-record modes.

It belongs to a **family of enum→string getters** at `0x8f1a4`–`0x8f7e8`:
eleven functions of the same shape (`add rX, pc` / `bx lr` tables) with table
sizes growing 2 → 13 entries. Naming one without naming the family would be
misleading, so all eleven are left unnamed pending a caller survey.

## Encoder or decoder? (tested 2026-09-26)

The hypothesis that this table belongs to the **decode** side was tested
directly, and is **not supported** by what the code shows.

The decoder functions were located via their strings and their data
references enumerated:

| function | decoder string | data bases used |
|---|---|---|
| `fcn.000a4178` | `DEC_REPORT_RESUME_DECODE` | 41 — **all 41 are strings, 0 are tables** |
| `fcn.000c0520` / `fcn.000c0598` | `dec/sfmc_dec_timing_sm.cpp` | 2 each, both strings |
| `fcn.000c069c` | `dec/sfmc_dec_timing_sm.cpp` | strings only |
| `fcn.000a4cd8` | `play_back_mode` | 2, both strings |
| `fcn.00095ba8`, `fcn.0009941c`, `fcn.0009ccfc`, `fcn.000a8280` | `STAE CHART TRANSITION` | strings only |

So the decoder path touches **no data tables at all** through PC-relative
addressing, and in particular not `0x89DADE`. Conversely the mode table's only
caller (`0x3ab074`) sits in DMM/OSAL memory-manager code, which is
direction-agnostic.

**Caveat, stated plainly:** this rules out the decoder as a consumer of *this*
table. It does not rule out a separate decode-side dimension table elsewhere
that has not been found, and it does not explain the failed flash. The
strongest code-based explanation for that is the width/height offset error
above, not a wrong subsystem.

## What is still unknown

- `0x8c4440` and the rest of `0x8c4000..0x8c6000`: no consumer found.
- The 39 image-wide words with height 2160: only these 4 records are now
  explained. The rest may be derived copies.
- Whether records 0..3 (family 2 and 3) are two distinct 4K sensor readouts or
  one readout under two pipeline configurations — the notes treat them as
  separate and nothing here settles it.
- Whether the `key` field (0 in all 19 records) selects a variant that this
  firmware build never uses, or is simply always passed as 0.

## Reproducing

```
retool.cmd xrefs  avcam 0x89dade      # references to the mode table
retool.cmd region avcam 0x8c4440      # verdict: unreferenced
retool.cmd disasm avcam 0x1aabd0 -n 26
retool.cmd disasm avcam 0x1aa9a4 -n 20
retool.cmd disasm avcam 0x8f5f8 -n 70
```

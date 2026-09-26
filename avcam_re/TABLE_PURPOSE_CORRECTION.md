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

So the table is a **linear search keyed on two 16-bit caller-supplied values**,
with a 16-byte stride. Record layout (little-endian, base `0x89DADE`):

| offset | type | meaning |
|---|---|---|
| +0 | u16 | key (caller-supplied selector; 0 for every entry in this build) |
| +2 | u16 | width |
| +4 | u16 | height |
| +6 | u32 | flags (1 for records 0..13, 0 for 14..18) |
| +10 | u32 | family (2 and 3 for the two 4K readouts, 1 otherwise) |
| +14 | u32 | mode id |

All 19 records, terminated by a zero record at `n=19`:

```
  n    off     key  width height flags family  id
   0 0x89dade     0   3840   2160     1      2   0
   1 0x89daee     0   3840   2160     1      3  19
   2 0x89dafe     0   4096   2160     1      2   1
   3 0x89db0e     0   4096   2160     1      3  20
   4 0x89db1e     0   1920   1080     1      1   3
   5 0x89db2e     0   2048   1080     1      1   4
   6 0x89db3e     0    960   1080     1      1   5
   7 0x89db4e     0    640    480     1      1   6
   8 0x89db5e     0    768    480     1      1   7
   9 0x89db6e     0   1280    720     1      1   8
  10 0x89db7e     0   1440    812     1      1   9
  11 0x89db8e     0   1440    920     1      1  10
  12 0x89db9e     0   1440   1080     1      1  11
  13 0x89dbae     0    960    540     1      1  12
  14 0x89dbbe     0   1440    540     0      1  14
  15 0x89dbce     0   1920    540     0      1  15
  16 0x89dbde     0    960    540     0      1  16
  17 0x89dbee     0    720    240     0      1  17
  18 0x89dbfe     0    720    288     0      1  18
  19 0x89dc0e   -- end of table
```

**Purpose, from the code:** given an output width (and a selector), return the
height, family and mode id. It is a sensor/output **mode resolver**, not a
generic descriptor table. The mode ids it returns are what the rest of the
firmware uses to program the pipeline.

### Correction to the earlier file

`OPENGATE_PATCH_SURFACE.md` placed the table at `0x89dae0` and read the record
as `(res, 1, family, id)` with `res = (h<<16)|w`. The base is `0x89DADE` and
the packing is **two u16 fields (width, height)**, not one packed word — the
apparent `(h<<16)|w` word is just how two adjacent u16 fields look in a hex
dump. The field semantics above are correct; the framing was not.

The 2160 → 2560 patch idea survives: records 0..3 carry height 2160, and
`height` is a u16 at record offset +4, i.e. at `0x89DAE2`, `0x89DAF2`,
`0x89DB02`, `0x89DB12`. Setting those to `0x0A00` (2560) is a 4-byte edit per
record. **Untested on hardware**, and the buffer-size concern below still
applies.

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

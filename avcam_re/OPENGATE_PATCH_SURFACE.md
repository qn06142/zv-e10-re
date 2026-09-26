# OpenGate 3:2 — verified patch surface (2026-09-26)

> [!IMPORTANT]
> **Partly superseded — read `TABLE_PURPOSE_CORRECTION.md` first.**
> The four patch-point verdicts below are sound and still stand. But the *table
> interpretation* in the second half was inferred from data contents and two
> parts of it are wrong: the mode table's base is `0x89DADE` (not `0x89dae0`),
> its resolution is two `u16` fields rather than one packed `(h<<16)|w` word,
> and the "per-stream encoder config table" at `0x8c4440` has **no consumer**
> and is retracted. The correction file also explains the PC-relative delta
> trap that produced both errors.

Re-examines the four patch points listed in `RE_STATE.md` using `retool`.
**One of them is confirmed as a real descriptor table; the other three
constants do not exist in the binary as claimed.** Addresses are file offsets;
runtime VA = offset + `0x635c6000`.

## Summary

| RE_STATE.md claim | Verdict |
|---|---|
| 1. `ISP_dimension_select` @ `0x8a5d0`: 3376 → 4000 | **Not present.** 3376 is never an instruction immediate. |
| 2. `ISP_dimension_setup` @ `0x8c14e`: 2160 → 2560 | **Wrong location.** 2160 is a data field, not code. Real site found below. |
| 3. `CODECV_write_config_0x651_0x661` @ `0x000c46dc`: 135 → 160 | **Not present** as an immediate. |
| 4. `encode_param_validate_pack` @ `0x004fb694`: relax 2160 | **Wrong location.** Same descriptor fields as #2. |

The constants are real, but they live in **packed data descriptors**, not in
code. The original notes appear to have read the *values* correctly (2160 and
3840 are genuine 4K dimensions) while attributing them to the wrong addresses.

## Method

`retool consts` scans for every encoding of a value: Thumb-2 `MOVW`/`MOVT`
immediates, aligned `u16`, and aligned `u32`.

The `MOVW` decoder was validated before use against a known instruction
(`movw r3, #0x303` at `0x8a60c`, halfwords `0xf240` / `0x3303` → 771). An
earlier version of the decoder read only the first halfword and produced
garbage; a negative result from it would have been meaningless.

## 2160 is never an instruction immediate

```
2160 (0x870):  264 raw matches -> 0 thumb-movw, 19 u16-le, 245 data
3376 (0xd30):   49 raw matches -> 0 thumb-movw,  7 u16-le,  42 data
 135 (0x087): 3035 raw matches -> 0 thumb-movw, 211 u16-le, 2824 data
```

All code-region matches are coincidental bit patterns, not constants. For
example the seven "in-function" 3376 hits are VFP/NEON encodings:

```
0x2c30bc:  1b03f003 003c0d30     <- vector load + immediate field
0x835fa4:  f841a926 a8110d30     <- vld1.16 / VFP immediate
0xae2e78:  7fd10d2c 7ff82254 ... <- vmov/vldr doubleword
0x1033e5c: 64460d2e 64460d30     <- NEON vmov
```

`3376` in particular is a red herring: it is not a dimension in this image at
all. The "sensor readout Y-window" claim is unsupported.

## Where 2160 actually lives: the video mode table

A table of 16-byte mode records begins at **`0x89dae0`**, format
`(height << 16) | width`, then a constant `1`, a family, and a mode id:

```
0x89dae0: 08700f00  00000001 00000002 00000000   2160 x 3840   family 2  id 0
0x89daf0: 08700f00  00000001 00000003 00000013   2160 x 3840   family 3  id 0x13
0x89db00: 08701000  00000001 00000002 00000001   2160 x 4096   family 2  id 1
0x89db10: 08701000  00000001 00000003 00000014   2160 x 4096   family 3  id 0x14
0x89db20: 04380780  00000001 00000001 00000003   1080 x 1920   id 3
0x89db30: 04380800  00000001 00000001 00000004   1080 x 2048   id 4
0x89db40: 043803c0  00000001 00000001 00000005   1080 x 960    id 5
0x89db50: 01e00280  00000001 00000001 00000006    480 x 640    id 6
0x89db60: 01e00300  00000001 00000001 00000007    480 x 768    id 7
0x89db70: 02d00500  00000001 00000001 00000008    720 x 1280   id 8
0x89db80: 032c05a0  00000001 00000001 00000009    812 x 1440   id 9
0x89db90: 039805a0  00000001 00000001 0000000a    920 x 1440   id 0xa
0x89dba0: 043805a0  00000001 00000001 0000000b   1080 x 1440   id 0xb
0x89dbb0: 021c03c0  00000001 00000001 0000000c    540 x 960    id 0xc
```

The ids are sequential and the family field separates the two 4K readouts
(2 and 3) from everything else (1). This is a sensor/stream mode selector
table, and it is the object the old notes were describing.

**The four 2160-height entries are the real patch surface for a 3:2 change:**
`0x89dae0`, `0x89daf0`, `0x89db00`, `0x89db10`. Setting the high half
`0x0870` → `0x0A00` yields 2560-height modes (`0x0A000F00` = 2560x3840,
`0x0A001000` = 2560x4096).

## Second table: per-stream encoder config

A denser table of 0x60-byte (96-byte) records sits at **`0x8c4440`**, mixing a
resolution word with a `0xffffffff` marker, register values and buffer sizes:

```
0x8c4440: 0000000e 08700f00 ffffffff 00000002    <- 2160x3840, stream 2
          00000000 0000000c 00000001 000f0003
          0108001e 0001009c 00000705 00000001
          00015f90 00000000 000d9700 00000006
          00003937 00000004 00039386 1f480100
          0003a980 00013c01 00030401 050f1705
0x8c44a0: 0000000e 08700f00 ffffffff 00000003    <- same, stream 3
          ... 000c0003 ... 01080018 ... 25800100
```

Word 3 is a stream index; the records otherwise differ only in a few register
words. **14 records in `0x8c4440..0x8c5680` carry a 2160-height word**, at
`0x8c4440`, `0x8c44a0`, `0x8c4620`, `0x8c4680`, `0x8c46e0`, `0x8c4750`,
`0x8c47b0`, `0x8c4810`, `0x8c5490`, `0x8c54f0`, `0x8c5560`, `0x8c55c0`,
`0x8c5620`, `0x8c5680` (word offset within each record varies: +0, +4, +8 or +12).

`0x000d9700` (890,112) and `0x00015f90` (89,488) are consistent with per-stream
buffer sizes, which is the RAM-pressure concern the old notes flagged.

## Confidence and open questions

- **High confidence:** the packing `(h << 16) | w`, the table locations, and the
  absence of 2160/3376/135 as instruction immediates. All mechanically verified.
- **Medium:** that these tables are the *only* place a 3:2 change must be made.
  `retool consts` finds 39 descriptors with height 2160 image-wide; only the 4
  in table A and 14 in table B are characterised here. The rest are in
  unrelated regions (`0x0c3408`, `0x18aab4`, `0xeb294`…) and may be derived
  copies rather than independent sources.
- **Untested:** the actual firmware-modifiability conclusion in `RE_STATE.md`
  (string patch survived reboot) was not re-verified here — it needs hardware.
- **Not attempted:** no patch was written. The buffer-size fields above are
  exactly the kind of thing that turns a resolution change into a RAM overflow,
  so a real attempt needs a device and a recovery path.

## Reproducing

```
retool.cmd consts avcam 0x8a5d0 3376
retool.cmd consts avcam 0x8c14e 2160
retool.cmd consts avcam 0x8c4440 2160 --whole
retool.cmd disasm avcam 0x8a5d0 -n 48
```

Note `retool consts` resolves an address to its containing function first;
`0x8c14e` is mid-function inside `fcn.0008c0e4`, not a function entry.

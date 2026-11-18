# Hardware register map and the logical-register convention

**Status: the register file is located.** The earlier note that no MMIO address
is obtainable from this image was wrong in its conclusion, though its reasoning
about the *file-relative* scan was right. Addresses exist, but they are built at
runtime from a small bias vocabulary, so no file offset contains one.

Addresses below are **file offsets** unless stated otherwise. Bank addresses are
**absolute runtime addresses** (outside the firmware image, as shown below).

## The convention in one line

```
address = caller_base + BANK + element_offset        element_offset: +0, +4 or +8
READ :  value = *(address)                            -> 0x7f5346
WRITE:  *(address) = value, and mirror the read-back -> 0x45db14
```

The firmware never names a register. Call sites pass a small **logical register
offset** (16-bit, e.g. `0x2098`) and a thin accessor adds the bank base.

## The two primitives

Both are two instructions. Read from the bytes at `0x7f5346` and `0x45db14`:

```
0x7f5346   ldr r0, [r0]      ; register READ  -- 47 xrefs
           bx lr

0x45db14   str r1, [r0]      ; register WRITE -- 96 xrefs
           ldr r3, [0x45db24] ; = 0x00c14602
           add r3, pc         ; PC = 0x45db1c  -> 0x0107211e
           ldr r2, [r0]       ; read back
           ldr r1, [0x45db28] ; = 0x0000aa08
           ldr r3, [r3, r1]   ; -> global pointer at file offset 0x0107cb26
           str r2, [r3]       ; trace the value that was actually stored
           bx lr
```

Every hardware write is therefore also recorded through a global pointer at file
offset **`0x0107CB26`**, which holds the address of a trace slot. That is a ready
made observation point for register traffic, and it is a single 4-byte global to
redirect if you want to watch or alter writes.

## The accessor table

Nine wrappers at `0x7F534A`–`0x7F53AA`, each 12 bytes: one or two bias
instructions, an optional element bump, then a tail branch to the read or write
primitive. Read straight from the instruction stream:

| entry | operations | net bank | +off | access |
|---|---|---|---|---|
| `0x7f534a` | `sub #0x0cc00000` | `0xf3400000` | 0 | READ |
| `0x7f5352` | `sub #0x0cc00000` | `0xf3400000` | 0 | WRITE |
| `0x7f535a` | `sub #0x0cc00000` | `0xf3400000` | 0 | WRITE |
| `0x7f5362` | `add #0xf3000000` `add #0x400000` `add #4` | `0xf3400000` | 4 | WRITE |
| `0x7f5370` | `sub #0x0cc00000` | `0xf3400000` | 0 | WRITE |
| `0x7f5378` | `add #0xf3000000` `add #0x400000` `add #4` | `0xf3400000` | 4 | WRITE |
| `0x7f5386` | `add #0xf3000000` `add #0x400000` `add #8` | `0xf3400000` | 8 | WRITE |
| `0x7f5394` | `add #0xf2000000` `add #0xa30000` `add #4` | `0xf2a30000` | 4 | WRITE |
| `0x7f53a2` | `add #0xf2000000` `add #0xa30000` `add #8` | `0xf2a30000` | 8 | WRITE |

Two shapes appear for the same bank because `0xF3400000` is not encodable as one
Thumb modified immediate while `-0x0CC00000` is; both compute the identical
offset, which is checked numerically rather than assumed:

```
sub #0x0CC00000                ->  -0x0CC00000 = 0xF3400000
add #0xF3000000 + #0x00400000  ->  +0xF3400000 = 0xF3400000     identical
```

A third bank comes from a different wrapper pair, `0x45db2c` / `0x45db3c`, which
add a caller index as well:

```
0x45db2c  ldr  r3, [0x45db38]   ; = 0xf2a00004
          adds r3, r0, r3       ; + caller base
          adds r0, r3, r1       ; + caller index
          mov  r1, r2
          b.w  fcn.0045db14

0x45db3c  ... = 0xf2a00008 ...                        (element +8)
```

### Bank vocabulary

| bank | how it appears | notes |
|---|---|---|
| **`0xF3400000`** | `sub #0x0CC00000`, or `add #0xF3000000` + `add #0x400000` | 7 of 9 wrappers |
| **`0xF2A30000`** | `add #0xF2000000` + `add #0xA30000` | 2 wrappers |
| **`0xF2A00000`** | literal `0xF2A00004` / `0xF2A00008` in the indexed wrappers | element +4 / +8 |

Element offsets are `+0`, `+4`, `+8` — a 32-bit word, then its successor, i.e.
consecutive register slots.

### These are device addresses, not firmware data

```
firmware load window : 0x635C6000 .. 0x646430AC   (base 0x635c6000 + image size)
0xF2A00000  inside firmware window: False
0xF2A30000  inside firmware window: False
0xF3400000  inside firmware window: False
```

A store to any of them cannot touch firmware code or data, so this is genuinely
the hardware register file rather than an internal buffer.

### Worked example

`fcn.007f5d8c` reads the live register file and packs the result into a 16-byte
scratch. It calls the READ accessor with logical offsets `0x2098`, `0x2094`,
`0x2028` and `0x2010`, which land at:

| logical | bank `0xF3400000` | bank `0xF2A00000` |
|---|---|---|
| `0x2010` | `0xF3402010` | `0xF2A02010` |
| `0x2014` | `0xF3402014` | `0xF2A02014` |
| `0x2028` | `0xF3402028` | `0xF2A02028` |
| `0x2094` | `0xF3402094` | `0xF2A02094` |
| `0x2098` | `0xF3402098` | `0xF2A02098` |

The scratch layout it builds (from the instruction stream at `0x7f5d8c`):

| scratch | contents |
|---|---|
| `+0x00` | u32 from the `0x2098` accessor |
| `+0x04` | u16: `0x2098` if the `0x2098` and `0x2094` reads agree, else `0x2094` |
| `+0x06` | bit 0 of the `0x2028` read |
| `+0x07` | bit 1 of the `0x2028` read |
| `+0x08` | bit 2 of the `0x2028` read |
| `+0x09` | 1 if the `0x2010` read returned 0, else 0 |
| `+0x0c` | `0x2010` read `& 3` |

## How this closes the register-write loop

The 24-byte descriptor filled by `fcn.007e8e4a` is at `ctx + block*24`, stride
`0x18`, block id in the core's `r1` (`mla r2, 0x18, r6, r4`). Its layout, read
from the store instructions at `0x7e8e4a`:

| offset | size | contents |
|---|---|---|
| `+0x00` | u32 | `0x10000000`, constant passed by the caller |
| `+0x04` | u32 | 24-bit value, `scratch[0] & 0x00FFFFFF` — the top byte is masked off |
| `+0x08` | u32 | u16 from `scratch[4]`, zero-extended |
| `+0x0c` | u8 | caller's `src[0]` |
| `+0x0d` | u8 | caller's `src[4]` |
| `+0x0e` | u8 | caller's `src[8]` |
| `+0x0f` | u8 | caller's `src[0xc]` — note the last two are swapped relative to source order |
| `+0x10` | u16 | `1`, a valid/armed flag |
| `+0x14` | u32 | credit counter, maintained by the core at `0x44038c` |

So a register write is: read the live hardware register through the accessor
family, pack the observed state into the descriptor at `ctx + block*24`, set
`+0x10`, and commit. The descriptor carries **state read back from the hardware**,
not a value being pushed into it. That is consistent with `0x45db14` reading the
register back immediately after storing.

Block ids remain dominated by `0x57` (ISP) and `0x68` (DFE); a full BL scan gives
**4,220** call sites to `ISP_WriteRegister` (`0x7e8e88`) and **3** to the `0x68`
wrapper (`0x7e8eb8`) — see the correction below.

## Corrections to earlier notes

- **"1,983 bl call sites."** A complete Thumb BL scan gives **4,220** to
  `0x7e8e88`, 3 to `0x7e8eb8` and 2 to the core. The earlier figure came from a
  partial scan and is superseded.
- **"No MMIO address exists; register-file base unknown."** Superseded. The banks
  are `0xF3400000`, `0xF2A30000` and `0xF2A00000`. What remains true is that no
  *file offset* contains a bank address — they are assembled from biases at
  runtime, which is why a file-relative scan found nothing.
- The previously **withdrawn** "hardware page" histogram naming `0xda2e9000`,
  `0xf1f000` and `0xf4f000` stays withdrawn. That was a resolver artifact. The
  three banks here are unrelated to those values and rest on a different
  derivation: literal-pool constants read from the instruction stream, with the
  arithmetic checked numerically.

## Confidence

| claim | confidence |
|---|---|
| getter/setter primitives and their byte-level behaviour | **high** — 2 and 6 instructions, read directly from bytes |
| accessor table, bank vocabulary, element offsets | **high** — read from the instruction stream; both encodings of `0xF3400000` checked to be identical |
| the three banks are device MMIO | **high** — all outside the firmware's load window |
| trace mirror via the global at file offset `0x0107CB26` | **high** — pool and `add rX, pc` arithmetic resolved and in range |
| 24-byte descriptor layout | **high** — every field from a distinct store instruction |
| which physical block each bank is (ISP vs DFE vs ZIMA) | **not established** — plausible from the call path, unproven |
| logical offset -> register name | **not established** — no name table found yet |

## Reproducing

```
retool.cmd disasm avcam 0x7f5346 -n 4      # the register READ primitive
retool.cmd disasm avcam 0x45db14 -n 6      # the WRITE primitive + trace mirror
retool.cmd disasm avcam 0x7f534a -n 24     # the accessor table
retool.cmd disasm avcam 0x45db2c -n 4      # the indexed wrapper (bank 0xF2A00000)
retool.cmd disasm avcam 0x7f5d8c -n 22     # reads the live register file
retool.cmd disasm avcam 0x7e8e4a -n 20     # fills the 24-byte descriptor
retool.cmd disasm avcam 0x4403a4 -n 12     # the core: descriptor indexing
```

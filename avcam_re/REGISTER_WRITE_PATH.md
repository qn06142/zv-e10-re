# Register-write architecture and the ISP/DFE programming model (2026-09-26)

Extends the topology map with the part that matters most for firmware
modification: **how a register write actually reaches the hardware.** Anyone
patching this firmware has to go through this path.

Addresses are file offsets; runtime VA = offset + `0x635c6000`.

## The call chain

```
ISP_WriteRegister      0x7e8e88   (Thumb)  4,220 bl call sites
ISP_WriteRegister_0x68 0x7e8eb8   (Thumb)  sibling wrapper, block 0x68
  └─ core              0x44038c   (Thumb)  296 bytes -- the real implementation
       ├─ 0x44033c     (Thumb)  74 bytes  helper
       ├─ 0x7e90dc     (Thumb)  20 bytes  tiny struct init
       ├─ 0x440080     (Thumb)            record build + pool push
       ├─ memset       0x522ad0  (ARM)    5,459 xrefs  <- was misnamed
       └─ memcpy       0x5223ec  (ARM)    5,004 xrefs  <- was misnamed
```

## Correction: the "commit" is a memset, not a ZIMA launch

This document previously recorded `0x522ad0` as `ZIMA_DVENC_launch` (command
`0xd20`) and described it as the hardware commit. **That was wrong.** `0x522ad0`
is the C library's ARM `memset`:

```
adds r0, #0xff        ; fill byte = 0xFF
orr  r3, r3, r3, lsl 8
orr  r3, r3, r3, lsl 16
stmge ip!, {r2, r3}   ; unrolled 8-byte stores
```

5,459 xrefs is a library primitive, not a codec entry point. `0x5223ec`, named
`encode_param_submit`, is equally `memcpy` — `ands ip, r0, #3` alignment fixup
then unrolled `ldm`/`stm` by 16 bytes, 5,004 xrefs. Both names were auto-scraped
with no verification; one of them had a comment that was rizin's own speculative
"nearby string" annotation, which was mistaken for a real symbol.

So at `0x4403e2` the core calls `memset(buf, 0xFF, 0x200)` — clearing a 512-byte
buffer — and at `0x4400c4` it calls `memcpy(dst, src, n)` to copy a record. The
hardware is **not** programmed by a commit at this point.

Where the hardware *is* written is `0x45db14`, found via the register banks; see
`REGISTER_MMIO_MAP.md`. That is a plain `str r1, [r0]` to a device address,
followed by a read-back and a trace mirror.

`0x7e8e88` is a thin wrapper: it copies six incoming stack arguments into a
struct and tail-calls `0x44038c`. `0x7e8eb8` is the same shape but hardcodes
block `0x68`.

## Mixed ARM/Thumb — a decoding trap

`0x5223ec` and `0x522ad0` are **ARM (32-bit) functions**, reached from Thumb
via `blx`. Read as raw Thumb halfwords they look like nonsense (`ands r1, r0;
invalid; rev r0, r0`) because the first ARM word `0xE92D4001` splits into the
halfwords `0x4001` and `0xE92D`. In ARM they are clean:

```
0x5223ec  push {r0, lr}
          subs  r2, r2, #4
          blt   ...
          ands  ip, r0, #3        <- bit-field extraction
          bne   ...
```

I briefly took these for mislabeled functions; they were correct and my decode
was wrong. The image has **3,162 `arm32` functions against 63,643 `arm16`**, so
this comes up constantly.

The cached rizin project records instruction width per address, so
`retool disasm` gets it right by default. `--arm` is for forcing 32-bit at an
address the project has not analysed.

## The programming model: shadow state, per-block records, batched commit

From `0x44038c`:

| access | meaning |
|---|---|
| `sb = ctx + 0x1900` | per-context state area |
| `ldrb r1, [sb, 8]` → `ctx+0x1908` | **pending/dirty flag** |
| `strb r1, [r0, 8]` in the `0x7e8eb0` helper | sets that flag |
| `ldrb r3, [ctx + ((block+0x300)<<3) + 4]` | per-block state byte, read twice (`+0x300` and `+0x30d` slots) |
| `mla r2, 0x18, block, ctx` | **per-block descriptor, 24 bytes each** at `ctx + block*24` |
| `ldr r3, [r2, 0x14]` vs `r7+0x33` | a per-block counter/threshold comparison |

So writes are **not** individual MMIO stores. They accumulate into a
per-context shadow area, each block owning a 24-byte descriptor, and a dirty
flag plus a per-block state byte gate when the accumulated state is released —
by clearing a 0x200-byte buffer, building a 16-byte-header record and pushing it
to a pool at `0x440080`. The descriptor layout is in `REGISTER_MMIO_MAP.md`.

The actual hardware store is a separate path entirely, reached through the
register-bank accessors rather than through this descriptor.

## Block id space

Recovered from the instruction stream at the 1,983 call sites:

| block | calls | share | notes |
|---|---|---|---|
| **0x57** | 1,168 | 59% | ISP stage writes — the dominant family |
| **0x68** | 747 | 38% | DFE container writes; has its own wrapper at `0x7e8eb8` |
| 0x26 | 13 | <1% | |
| 35 others | 1–2 each | <1% | singletons |

96% of writes go to two blocks. The `+0x300` state-byte indexing in the core
implies the block id is a dense index into a per-context table, consistent with
only a small number being real.

## The bit-field packer

**Correction:** `0x5223ec` was described here as a bit-field packer reached from
5,004 places. It is `memcpy` — see the correction section above. The earlier
reading came from the same auto-scraped name and was never checked against the
instruction stream.

## What this does and does not give you

**Gives you:**
- the exact call path a register write takes
- the shadow/commit protocol and the per-block descriptor geometry
  (`ctx + block*24`, 24 bytes)
- the block id space, and that two ids dominate
- confirmation the hardware is never written directly, so there is no MMIO
  address to patch

**Does not give you:**
- the meaning of the 24 descriptor bytes, or of the sub-fields inside a block
- which bits of a packed command are which hardware field
- the base address of the ISP/DFE register file — it is obtained at runtime, and
  no literal in the image names it

So the remaining work is the 24-byte descriptor layout and the register-file
base. That is the concrete next target, and it is small.

## Reproducing

```
retool.cmd disasm avcam 0x7e8e88 -n 46   # the wrapper
retool.cmd disasm avcam 0x44038c -n 40   # the core
retool.cmd disasm avcam 0x7e8eb8 -n 20   # the 0x68 wrapper
# 0x5223ec and 0x522ad0 are ARM library routines -- decode with -b 32 to see why:
retool.cmd disasm avcam 0x5223ec -n 12 --arm   # memcpy
retool.cmd disasm avcam 0x522ad0 -n 12 --arm   # memset
```

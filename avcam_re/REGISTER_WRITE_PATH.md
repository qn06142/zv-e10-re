# Register-write architecture and the ISP/DFE programming model (2026-09-26)

Extends the topology map with the part that matters most for firmware
modification: **how a register write actually reaches the hardware.** Anyone
patching this firmware has to go through this path.

Addresses are file offsets; runtime VA = offset + `0x635c6000`.

## The call chain

```
ISP_WriteRegister      0x7e8e88   (Thumb)  1,983 bl call sites
ISP_WriteRegister_0x68 0x7e8eb8   (Thumb)  sibling wrapper, block 0x68
  └─ core              0x44038c   (Thumb)  296 bytes -- the real implementation
       ├─ 0x44033c     (Thumb)  74 bytes  helper
       ├─ 0x7e90dc     (Thumb)  20 bytes  tiny struct init
       ├─ 0x5223ec     (ARM)    5,004 xrefs  bit-field packer
       └─ 0x522ad0     (ARM)              ZIMA_DVENC_launch, cmd 0xd20
```

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
flag plus a per-block state byte gate when the accumulated state is committed —
via `0x522ad0` (`ZIMA_DVENC_launch`, command `0xd20`). For block `0` the commit
path additionally goes through `0x5223ec` with the log format
`[file:%s][L:%d]`.

This is the single most useful architectural fact for modification work: the
hardware is programmed in **batches through a shadow/commit protocol**, not by
poking registers. A patch that changes a value the hardware needs must change
it in the shadow descriptor (or the code that fills it), and the commit must
still happen.

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

`0x5223ec` is called from **5,004 places** — one of the most-referenced
functions in the image. Decoded in ARM it extracts bit ranges
(`ands ip, r0, #3`, `ands ip, r1, #3`) and dispatches on them, with a logging
path carrying `[file:%s][L:%d]`.

This is how the firmware builds packed hardware commands: several logical
fields get bit-sliced into one or two words here. The old notes named it
`encode_param_submit`; the behaviour is consistent with that name (packing an
encode/command parameter block) though the logging path is also part of it.

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
# ARM-mode targets -- decode with -b 32, not -b 16:
retool.cmd disasm avcam 0x5223ec -n 12 --arm
retool.cmd disasm avcam 0x522ad0 -n 12 --arm
```

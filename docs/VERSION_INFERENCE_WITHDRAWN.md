The Version-screen inference is withdrawn: a null model refuted it

Date: 2026-09-28. Negative result, recorded because the claim it removes was made
in the previous message and acted on neither by me nor, as far as I know, by
anyone else yet. Better to catch it here.

## What was claimed, and on what evidence

The previous message said the camera's Version screen formats two integers as
`major.minor` with `%2d.%02d`, on the strength of `viewUnified6.so` containing:

```
LG_viewversionnumber::LayoutVERSION
LG_viewversionnumber::LayoutINITIAL_VERSION
%2d.%02d
ViewVersionNumber
```

**The only evidence was that the string was present in the binary.** No code
reference was ever shown, because there isn't one that this method can find.

## Why that evidence is worthless here

`%2d.%02d` is not referenced by any 32-bit constant in `.text` — searched as a
pool constant, as `movw`/`movt` immediates, and as a 16-bit relative offset. All
zero. Nor is it in `.data.rel.ro`, nor reachable from a pool anchor within 0x600
bytes.

On its own that could mean the string is reached by base-plus-offset, or is dead.
So the null model: what fraction of `.rodata` strings in this library *are*
referenced by an aligned `.text` constant?

| | |
|---|---:|
| `.rodata` NUL-terminated strings (len >= 4) | 330 |
| collected distinct 32-bit constants in `.text` | 32,837 |
| **of those 330 strings, referenced** | **1 (0.3%)** |
| **unreferenced** | **329 (99.7%)** |

**Unreferenced is the norm.** `.rodata` is plain `ALLOC`, not a merged string
section, so this is not explained by section flags — it means strings in this
library are addressed by a scheme a 4-byte-aligned constant scan does not capture
at all. Under that null model, `%2d.%02d` being unreferenced carries **no
information whatsoever**. It is exactly as unreferenced as 99.7% of its
neighbours.

Therefore: the presence of `%2d.%02d` next to the class names is a coincidence of
`.rodata` layout, not evidence that the version is two integers formatted that
way. The claim is withdrawn.

This is the same failure the project has hit repeatedly — a signal that could not
vary — caught before anything was flashed on the strength of it.

## What *is* established

The RTTI walk works, and is worth keeping:

- `.data.rel.ro` in this library is fully relocated: 7,505 `R_ARM_RELATIVE`
  entries whose addends live in the slot, so it is readable statically.
- Every one of the five `LG_viewversionnumber` typeinfo names has **exactly one**
  reference there, which identifies the typeinfo struct unambiguously:
  `LayoutVERSION` at 0x8c794, `LayoutINITIAL_VERSION` at 0x8c6e4,
  `LayoutLAYOUT_VERSION_INFO` at 0x8c58c, `LayoutConverterBase` at 0x8c598,
  `MyLayoutGroupConverter` at 0x8c4dc.

What is **not** established: anything at all about the version value. Not its
format, not its magnitude, not whether it is stored as text or computed.

## Why the disassembly could not be carried further

Two things blocked it, and both are recorded rather than worked around:

1. **Function boundaries in the version module are unreliable.** A loose decode of
   0x3ed00..0x3f700 yielded almost nothing but a handful of `bl`s, which is the
   misalignment signature. Decoding only inside recovered function bodies fixed
   that in earlier work, but the region here interleaves code and data and the
   recovery does not cleanly separate it.

2. **A wrong inference about a "constant".** The vtable appeared to give a
   three-instruction function at 0x3edf4 returning a single word from its pool.
   The word at 0x3edfc is `0x6afa4eea` — two ARM instructions, not data. So
   0x3edf4 is not a function start, the vtable slot was misread, and the
   "initial version constant" was never a constant. Caught only because the value
   was obviously code rather than a version number.

Note also that `viewUnified2.so`'s loader table lists `viewVersionNumber.so` and
`ViewVersionNumberToInstance`, so `viewUnified6.so` is very likely that plugin —
but `viewUnified6.so` does not contain the string `viewVersionNumber.so`, so that
identification is inference, not established.

## Where this leaves the displayed version

Still unknown, and now honestly so. To find it, the workable route is not string
hunting at all:

- resolve the vtable from the typeinfo at 0x8c794 properly, and identify each
  virtual by **what it calls**, not by position;
- or find who *calls* the version code — the caller must pass or fetch the value,
  and the caller is likely in `viewUnified2.so` or the framework, where strings
  and constants may be resolvable in the normal way.

Both are real work. Neither is a find-and-replace, and I am not going to pick a
pair of integers that look version-shaped and flash them — that is precisely the
search this project has already falsified six times.

## The camera was not touched

No file was written in this investigation. The camera still carries the three
verified changes: magenta guides, `PLAYBACK` -> `OPENCODE`, and the
`DeviceInfo.xml` version `9.9.99.99999`. `/usr` is `ro`.

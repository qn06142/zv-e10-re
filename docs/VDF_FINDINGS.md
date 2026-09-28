# VDF — Video Display Framework findings

Status: **static analysis complete; no visible display effect obtained.**
Last updated: 2026-09-28.

## What VDF is

`VDF` = "Video Display Framework", a message-driven display subsystem inside
`/system/av-cam.bin`. 361 `N3VDF*` mangled RTTI names, plus a set of long
`virtual VDF::VDF_ERR VDF::Class::Method(...)` strings that are **log
strings**, not RTTI names. Those log strings are the useful ones: they are
referenced pc-relative from real code, so they resolve to genuine function
addresses by name.

## Load base

`0x635C6000`, solved from RTTI name pointers (375/400 validated) and
independently corroborated by the ORIL init table. Runtime address = file
offset + `0x635C6000`.

## Reference encoding (the reusable result)

`av-cam.bin` is a **raw binary, not an ELF** (`0a 00 00 ea 4f 52 49 4c` — ARM
code then `ORIL`), and carries no relocations. A pointer to a string or table
is built in two instructions:

```
ldr  rX, [pc, #imm]      ; pool word is a FILE offset, not an address
add  rX, pc              ; rX = pool + pc  ->  the file offset
```

Two conventions matter, and getting either wrong silently yields zero matches:

1. **Do not apply the load base.** The pool word and `addr` are both file
   offsets; their sum is already the target. Subtracting `BASE` shifts every
   key by 6.4 MB.
2. **`pc` is the raw `addr + 4`, not `Align(PC,4)`.** ARM's architecture says
   `ADD (register)` reads `Align(PC,4)`, but this toolchain's encoded literal
   is `target - (addr+4)`. Using the aligned value lands 2 bytes low.

Both are implemented and regression-tested in `thumb.pcrel_strrefs`, against
three independently-anchored ground truths (the three-string log macro at
`0x001621A8`, and a LUT base that must be 4-byte aligned to be usable as
`ldr.w rX, [rX, rY, lsl #2]`).

## Resolved methods

`research/firmware/vdf_methods.py` resolves 35 of 36 signature strings (the
36th is a duplicate `SystemCmdNotfound::Execute` key, not a real miss):

| method | file offset | insn |
|---|---|---|
| `VdfDisplayCmdSetOsdAlpha::Execute` | `0x00150A9C` | 74 |
| `VdfDisplayCmdSetOsdAlpha::Activate` | `0x0015091E` | 1 (thin) |
| `VdfDisplayCmdSetPanelOsdLuminance::Execute` | `0x00151360` | 75 |
| `VdfDisplayCmdSetPanelOutPin::Execute` | `0x00151450` | 386 |
| `VdfDisplayCmdSetPanelReverse::Activate` | `0x00151CBA` | 52 |
| `VdfSrvcDrawOsdManager::Execute` | `0x00178892` | 86 |
| `VdfInputCmdUpdateYuv::Execute` | `0x001681A0` | 32 |
| `SystemCmdPinSend::Execute` | `0x00184938` | 468 |
| `SystemCmdSysv::Execute` | `0x00185534` | 331 |
| `SystemCmdDebug::Execute` | `0x001803AE` | 1447 |

`SetPanelBrightness` has no `Execute` signature string, but `0x00150BA8` (313
insn, 30 calls) is adjacent to the `SetOsdAlpha` pair and behaves identically
in shape; it is the brightness command. Treat that identification as strong
but not string-proven.

## Why a panel command cannot simply be called

`SetOsdAlpha::Execute` at `0x00150A9C` and `SetPanelBrightness::Execute` at
`0x00150BA8` share a shape:

```
push {r4,r5,r6,r7,lr}
ldr  r3, [r3, #8]            ; arg3 (SubsystemAccessorIf*) -> vtable slot 2
blx  r3
ldrb r2, [r5, #1]            ; the value, a byte in the command object
...
ldr.w r3, [r3, #0x44c]       ; more subsystem vtable slots
ldr.w r3, [r3, #0x454]
ldr.w r3, [r3, #0x45c]
ldr.w r3, [r3, #0x6cc]
ldr.w r3, [r3, #0x858]
```

So a display command needs **two live interface objects** — a
`MsgAccessorIf*` and a `SubsystemAccessorIf*` — and reaches the panel handle
through a chain of virtual calls on the subsystem accessor, at vtable
offsets `0x44c / 0x454 / 0x45c / 0x4bc / 0x4d4 / 0x670 / 0x6cc / 0x858`. The
vtable is therefore >0x858 bytes and its methods must return valid subsystem
pointers. Fabricating those from an injected stub is not a safe experiment: a
wrong pointer there is a hard hang, not a visible effect.

The message-post helper is `0x0072F47C`:

```
push {r0,r1,r4,r5,r6,lr}
str  r3, [sp]
movs r0, #3
mov  r1, r6 / r2, r5 / r3, r4
bl   0x17B388                ; the msgpump
```

Callers pass `r0 = 0xEEEEEEEE` as a "no sender" sentinel, `r1 = value`,
`r2 = context pointer`, `r3 = command id` (e.g. `0x5D8`, `0x51`). This is the
legitimate path, but the command id and payload layout are per-subsystem and
would have to be reconstructed exactly.

## The brightness path is a table lookup, not a register write

In `SetPanelBrightness::Execute` (`0x00150BA8`):

```
0x00150BEA  ldr   r3, [pc, #0x378]     ; -> 0x0087D7E4
0x00150BEC  ldrb  r2, [r5, #1]         ; brightness value, an INDEX
0x00150BEE  add   r3, pc
0x00150BF0  ldr.w r3, [r3, r2, lsl #2] ; curve = table[brightness]
0x00150BF4  str   r3, [sp, #0x18]
0x00150BF6  strb  r3, [sp, #0x21]
```

The table at file `0x0087D7E4` is 16.16 fixed point, incrementing by `0x10000`
per entry in 16-entry rows — a colour/scale LUT, **not** a monotone brightness
curve, so editing it would not do the obvious thing.

**Writability is unproven.** Because the image is not an ELF there are no
section headers to read, so which byte ranges are writable cannot be
determined offline. It would have to be established at runtime before any data
patch — and a data patch to a misidentified table is exactly the kind of
unquantified side effect that bricks a device.

## Correction: vtable slots do NOT identify methods

The vtables at `0x00FBB0F8` etc. are real: they decode cleanly at
`(stored & ~1) - BASE` (every entry carries the Thumb bit, bit0 set), slot
`[-1]` matches the typeinfo address exactly, and they are spaced on 32-byte
boundaries with a `0x00000000` terminator.

But the per-class slots do **not** line up with the string-resolved method
addresses. `SetPanelReverse` slot `[5]` is `0x0071E632` while its `Activate` is
`0x00151CBA`. An earlier claim that "slot [5] == Execute" was based on a
single coincidence with `SetOsdAlpha` and is **wrong**. Slot index is
unidentified. See the note in `vdf_methods.py`.

## Bottom line

The framebuffer the search was aimed at does not exist in CPU-visible memory.
The picture path is descriptor-driven (APL/AIC + XDMAC + HME), `0x6AA00000` is
a hardware aperture that wedges the CPU on a single-byte read (reproduced 3x),
and `MemTotal` is 128 MB against a claimed 1 GB window. The decode-path hook we
own calls `0xA9F90`, which is a **ring-buffer index refill**
(`ldr r5,[r4,#4]` / `cmp` against a limit / `str r0,[r4,#4]`), not a pixel
path — no decoded pixels pass through it.

Reaching a visible display effect requires a full VDF message transaction with
valid subsystem interface pointers, or a runtime-proven writable data symbol.
Neither is available offline, and guessing is a hang risk.

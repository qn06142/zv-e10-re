
> **SESSION RECORD - not a reference.** This is a dated log of how a finding was
> reached. Anything still true of it has been extracted into the topic docs; do
> not cite this file as fact. Kept for provenance only, so that a retracted
> claim is not silently re-derived.
>
> Current documentation: [docs/README.md](../README.md)
# ZV-E10 — display surfaces and the framebuffer hunt

Status: **the framebuffer hunt is closed. It does not exist in CPU-visible
memory.** Last updated 2026-09-28.

This records the on-camera investigation so the negative results aren't
repeated, and documents the reusable tooling it produced.

## The finding

There is no CPU-visible framebuffer. The display is descriptor-driven
(APL/AIC + XDMAC + HME) and the panel is fed by a private `ldec` driver. Four
independent lines of evidence, each checked against a positive control:

1. **`/dev/mem` only reads at page granularity.** `dd bs=4096 count=1` returns
   4096 bytes; `dd bs=4 count=4` returns a **0-byte file with no error**. So
   sub-page reads silently yield nothing, which makes fine-grained pointer
   chasing through `/dev/mem` impossible. This is the single most useful
   operational fact found.

2. **The candidate surfaces are not scanout buffers.** Four `/dev/stream`
   surfaces were dumped by mmapping the offsets the UI engine maps:

   | surface | offset | profile |
   |---|---|---|
   | s2 | `0x20312000` | 98.7% zeros, sparse metadata |
   | s3 | `0x3F7ED000` | 2.8% zeros, all 256 values — the `wbi_cmpr` compressor |
   | s4 | `0x228B2000` | 89.3% zeros, packed sub-byte nibbles |
   | s1 | `0x22312000` | 98.7% zeros |

   Writing `0xFF` to s4 and re-dumping gave **99.8% identical bytes** (4089/4096;
   the 7 differing are live heap pointers). The UI redraws it, so it is a
   back/scratch buffer, not what the panel scans out.

3. **s4 is a descriptor table, not pixels.** Its head holds kernel VAs
   (`0x828B2000`, `0x828B2030`, …), an `0xFFFFFFFF` terminator, and a
   `0x00200000` size field matching the 2 MB surface. Following those pointers
   led to kernel code and klog format strings (`" startEvent -\n"`,
   `"  Count = %d"`), not a buffer.

4. **s3 and s4 are compressed.** s4's byte pairs have equal high and low
   nibbles (`df dd`, `af aa`, `5f 55`, `2f 22`) — packed sub-byte data,
   consistent with the `wbi_cmpr` writeback compressor in `/proc/cmdline`.

## Corrections to earlier claims

Two things stated during this investigation were wrong and are recorded so they
don't get repeated:

- **"The linear map is confirmed"** was overclaimed. `PA = VA - 0x80000000` is
  the standard layout for this config and remains the working assumption, but
  the "proof" was misread: `0xE9DB6B77` was taken as a valid ARM prologue from
  a read that was actually klog strings. A clean read of `PA 0x028B2000` shows
  format strings, not code.
- **"s4 is the framebuffer"** was based on flat 1513-byte runs, which also
  appear in descriptor tables. The poke test disproved it.

## Why VDF is not a route to a visible effect

35 of 36 VDF `Execute`/`Activate` methods resolve by name (see
`docs/03-binaries.md`), but every display command takes two live interface
objects and reaches the panel through subsystem vtable slots `0x44c`–`0x858`.
Calling one from injected code is a hang risk, not a visible effect.

## Tooling produced (reusable)

No cross-compiler is available, but `keystone` and `capstone` are, so static ARM
Linux helpers are assembled and wrapped in a hand-built ELF32:

- `arm_helper.py` — builds the helpers. The layout rules matter:
  `p_offset` and `p_vaddr` **must be congruent mod page size**, or the kernel
  maps the wrong page and the process is SIGKILLed. Unaligned `p_offset` keeps
  the file ~1 KB, which matters because the camera shell truncates commands at
  ~1022 characters and a longer one wedges the session.
- `arm_verify.py` — ELF + disassembly checks, mode-aware.
- `arm_static_check.py` — catches the register and branch bugs that hand-written
  ARM assembly invites (banned scratch registers, unresolved branch targets).
- `arm_stack_sim.py` — simulates every stack access against the frame size.
  This is the check that *should* have run before the first transfer; both
  segfaults were stack overruns that looked fine in disassembly.

### Traps that cost real time

- ARM `MOV` (immediate) is an 8-bit value rotated by an even amount: an 18-bit
  constant such as a page offset of `0x22312` is **not encodable** and keystone
  raises `KS_ERR_ASM_INVALID_OPERAND`. Use `movw`/`movt`.
- The camera shell truncates a command at ~1022 characters and **wedges** the
  session on a much longer one; the retry path needs elevation to work.
- `busybox` must be invoked as `busybox` to dispatch applets, not by its own
  name.
- The camera has `/bin/busybox` with a working `base64 -d`, which is the only
  practical way to move a binary across (there is no push command).

## What a visible effect would actually require

Either a full VDF message transaction with valid subsystem interface pointers,
or a writable data symbol proven at runtime. Neither is reachable offline, and
guessing is a hang or brick risk on a device that can only be recovered by
reflashing. The built-but-unflushed logger payload (`dumps/av-cam.injected.bin`,
md5 `f1f96e3f…`) remains the only verified, reversible change available.

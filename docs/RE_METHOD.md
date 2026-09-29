# Reading these binaries: the parts that are easy to get wrong

Every finding in this project that concerns code was read out of an ELF rather
than guessed at. That is only possible because the objects are ordinary ARM
ELF32 files with full symbol tables — no packing, no stripping, no encryption.
This note records the decoding traps that cost real time, each one verified
against the actual files rather than recalled.

The subjects: `libtestcmd.so`, `libIMDB.so`, `im.elf` (all in `/usr/bin` and
`/usr/lib` on the camera, and mirrored in `dumps/camera_2025/`), plus the
`av-cam.bin` RTOS image. Tools: `research/firmware/annotate.py`,
`thumb.py`, `arm_helper.py`, `elf_catalog.py`, `opx_payload.py`.

## 1. These are Thumb, and the symbol table says so

`.dynsym` sets bit 0 of `st_value` on every Thumb function. In
`libtestcmd.so` **all 25** `STT_FUNC` symbols have an odd `st_value` and none
have an even one:

    cmdline_get_size   st_value = 0x1cb1   size = 232

So the code address is `0x1cb0`. Decoding at the odd address in ARM mode gives
something that looks like code and is not:

    ARM at 0x1cb1:  e9f04397  strbls pc, [r3, -sb, ror #1]
                      b0044600  strheq r0, [r6], #-0x40
                      af4e68ee  cdp p14, #6, c4, c8, c15, #5

    THUMB at 0x1cb0: 2de9f043  push.w {r4, r5, r6, r7, r8, sb, lr}
                      97b0      sub   sp, #0x5c
                      0446      mov   r4, r0
                      00af      add   r7, sp, #0
                      4e68      ldr   r6, [r1, #4]

The second is a textbook prologue. The first is the giveaway that the ISA is
wrong: `cdp` and a conditional store through `pc` are not things a compiler
emits.

**The trap is that the wrong decode does not fail.** It yields a full, evenly
sized, entirely fictional instruction stream, with plausible-looking branches.
Nothing raises. This is why "disassemble it and read it" is not a safe
operation on a binary whose ISA has not been established first.

Establish it by checking `st_value & 1` across `STT_FUNC` symbols, not by
eyeballing the first decode.

## 2. Reading past a function's end

Walking instructions until an epilogue needs care in two ways.

**The epilogue may be spelled several ways.** `thumb.py:is_return()` matches on
`ins.mnemonic.split('.')[0]`, so it catches `pop`, `pop.w`, `ldmia`, `ldmia.w`
and `ldmdb` alike. Matching the bare string `pop` is not safe, and the reason
is version-dependent — worth stating precisely, because the exact failure has
moved:

    capstone 5.0.7   00bd -> "pop {pc}"      f0bd -> "pop {r4, r5, r6, r7, pc}"
    older builds                  "pop"                     "pop.w"

On 5.0.7 a `== 'pop'` test happens to work, because capstone normalises the
wide form to the same spelling; on a build that emits `pop.w` it silently
misses every wide epilogue and the walk runs off the end of the function.
Matching the stem works on both. `thumb.py` is written that way, so it is
correct either way — but the comment in that file claimed capstone *always*
emits the `.w` form, which is not true of the pinned version here.

**`pc` in the operand string is not a return.** Every PC-relative literal load
prints as `ldr r3, [pc, #0x10c]`. A test that looks for `pc` anywhere in
`op_str` treats those as function ends, stops early, and reports a function a
fraction of its real length. The check has to be on the *destination*
register:

    if stem == 'ldr':
        return ins.op_str.split(',')[0].strip() == 'pc'

This one produced a fake "calls memcpy twice" signal and a fake 136-instruction
function before it was caught — attributed instructions and call targets from
the *following* function to the one being analysed.

## 3. PLT stubs are ARM, even in a Thumb library

The linker emits the PLT in ARM regardless of the library's ISA. The giveaway is
PLT[0], which is the standard `get_pc_thunk`:

    0d7c  str  lr, [sp, #-4]!
    0d80  ldr  lr, [pc, #4]
    0d84  add  lr, pc, lr
    0d88  ldr  pc, [lr, #8]!

Decoding `.plt` as Thumb is wrong. (`capstone` will happily do it and produce
branch instructions that look fine.)

There are three stub encodings in this file and the resolver has to handle all
of them, because assuming the common one silently annotates nothing:

    12-byte:  add ip, pc, #A ; add ip, ip, #B, 20 ; ldr pc, [ip, #C]!
     8-byte:  add ip, sp|pc, #A ; ldr pc, [ip, #B]!
     inline:  the same 8-byte pair, emitted into .text rather than .plt

The reliable way to resolve a stub to a symbol is **not** to assume
stub-order == relocation-order. It is to decode the stub's
`ldr pc, [ip, #imm]!`, compute the GOT address it lands on, and look *that* up
in `.rel.plt` / `.rel.dyn`. `annotate.py:plt_map()` does this. The
order-assuming version annotated calls with the wrong symbol names, which is
worse than no annotation at all.

## 4. vaddr is not file offset

To get from a symbol to bytes, go through `PT_LOAD`:

    file_offset = p_offset + (vaddr - p_vaddr)

This is not a formality. The first segment of each of these objects:

    libtestcmd.so   .text  vaddr 0x0000  p_offset 0x0000   identity
    libIMDB.so      .rodata vaddr 0x0000 p_offset 0x0000   identity
    im.elf          .text  vaddr 0x8000  p_offset 0x0000   NOT identity

So the shortcut `file_offset = vaddr` is correct for the two shared objects —
where all the icon-font and protocol work happened — and **wrong for `im.elf`**,
where it is off by 0x8000. A method that worked on every earlier subject and
then silently misreads the next one is exactly why the general form is worth
writing down. Always resolve through the program headers.

## 5. Literal pools are the value, not the code

Constant data in these binaries lives in pools interleaved with the code and
reached by `ldr rX, [pc, #imm]`. The immediate is a byte offset from the
instruction, so the target is `(addr + 4 + imm) & ~3`. Decoding those bytes as
instructions produces junk — `annotate.py` stops and prints the tail of a
function as `u32` words precisely because the disassembler cannot know the
difference.

This is also how the OSAL protocol was read. `testcmd_run_scenario` builds a
16-byte message header, and the four values come from the pool:

    [0x00] 0x00940021   [0x04] 0x000000dc
    [0x08] 0x00000003   [0x0c] 0x00dc0292   <- destination

and the payload is built by `memcpy` with immediate lengths — `char name[0x20]`,
then `u32 name_len` at `+0x20`, `u32 data_len` at `+0x24`, payload at `+0x28`.
None of that is in any header; it is only visible as the literals the code
loads. `annotate.py` decodes each `ldr`-from-pool and, where the loaded word
points at printable data, prints the string — which is how
`docs/SERVICE_AUDIT.md` got the scenario message layout.

## 6. Imports say what a binary does, and it is the cheapest evidence there is

`im.elf` is 23 KB with a full `.dynstr`. Its import list alone establishes that
it is the imaging manager:

    dlopen dlsym dlclose        IMDB_find_entry IMDB_get_entries
    mount umount mmap munmap    Backup_read Backup_write
    fork waitpid putenv         osal_* (snd/rcv/reg/valloc/free)

and its `.rodata` is unobfuscated plain text naming every mount point, every
boot-mode keyword, and the format string of the IMDB record it walks. A
23 KB binary with readable strings settles what a 21 MB binary cannot.

The same trick retired a claim. `av-cam.bin` had been recorded as "encrypted
body, secure-core decrypts at boot". Measuring entropy over 4 KB blocks shows
2,459 of 4,221 blocks below 6.5 bits/byte across the whole 16.5 MB file, and
`CMD_ID_SDF_EXEC` sits in the clear at `0x97471a`. The high-entropy blocks are
compressed sections, not a cipher. That turned the `osal_id` namespace from
hidden into searchable — 519 distinct values in the `0x00dc????` family, and
adjacency to string literals is meaningful because ARM compilers put literals
near the code that references them.

## 7. `imdb_raw` is an offset table, and 132 bytes of it are the whole key list

`libIMDB.so` exports one data symbol, `imdb_raw`, 132 bytes — 66 `u16`, of
which nine are offsets into `.rodata`, and they resolve to nine mode names:

    0x3512 -> "sim"      0x3516 -> "usbj"     0x351b -> "resub"
    0x3521 -> "adjust"  0x3528 -> "test"     0x3532 -> "default"
    0x353f -> "qemu"     0x3549 -> "nfs"      0x3552 -> "set"

(The tenth non-zero word, `0x0002`, is a count, not an offset — reading
strings at it yields `LF`.) Decoding the table and following each offset took a
minute and settled the mode-selection question with no camera involved. The
174-library manifest is the surrounding `.rodata`, walked in order.

## 8. Assembling without a compiler

No ARM cross-compiler is available; keystone-engine is. `arm_helper.py` builds
static ARM binaries from assembled code wrapped in a hand-made ELF32, and
`opx_payload.py` assembles a 66-byte function into an *existing* object with no
new relocations at all — raw `svc #0` syscalls, so the loader has nothing extra
to bind.

Two details worth keeping:

**Leave `p_offset` unaligned.** The layout is

    0x000  ELF header (52) + one program header (32) = 0x54
    0x054  strings
    0x200  code          <- entry point

with `p_offset = 0x54` and `p_align = 1`, so the kernel maps at
`p_vaddr - p_offset` and every string address is known *before* assembly —
`movw`/`movt` immediates need no patch pass. Page-aligning would force a 4 KB
file, ~6.2 KB of base64 as shell text, and a command that long wedges the
camera shell. That was reproduced: a 6,480-character command timed out the
session and needed a manual replug.

**When replacing a function, check the slot is self-contained.**
`cmdline_show_revision` is 68 bytes of which the last 28 are its own literal
pool, so the whole function can be replaced wholesale. A function whose pool
is shared or external cannot.

## What this bought

`docs/SERVICE_AUDIT.md` and `docs/BINARY_MAP.md` hold the findings. The point
of this note is that none of them required guessing: every protocol, ID,
mount table and message layout above came out of a symbol table, a literal
pool or an import list, and each is reproducible by re-running the scripts
named at the top.

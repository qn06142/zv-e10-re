# The testcmd / uipc message interface

Found by digging the camera's filesystem rather than by more display
hunting.  This is Sony's **own supported command interface**, so it is the
legitimate control path — the thing to reach for instead of fabricating VDF
interface objects or poking a driver's ioctl space blind.

Last updated 2026-09-28.

## What is on the camera

Pulled from `/usr/bin` and `/usr/lib`:

| file | size | role |
|---|---|---|
| `sndcmd.elf` | 5380 | send a message |
| `rcvcmd.elf` | 5024 | receive a reply |
| `testcmd.elf` | 5172 | combined |
| `libtestcmd.so` | 10128 | the implementation |
| `libosal_uipc.so` | — | the uipc transport |

They are ordinary ARM EABI **Thumb** shared objects / executables (GCC 4.5.1,
glibc 2.4), so unlike `av-cam.bin` they carry full section headers and
disassemble offline with no camera involvement at all.

`libtestcmd.so` is version **1.7, built Mar 15 2025**.

## The command line

Verbatim from `sndcmd.elf`'s own strings:

```
<options> [osal_id] [size]:[data] ...

  --ver      show version number of testcmd module
  --ifile    payload text filename to input
  --ibfile   payload binary filename to input
  --obfile   payload binary filename to output
  --ulogio   invoke osal_printf instead of fprintf
  --sync     invoke sync msg instead of async msg
  --sid      source OSAL_ID (default: 0x00dc0000)

  size   b | w | d | digit
  data   decimal or hex(0x) or string
```

`rcvcmd.elf` takes `--ifile`, `--tmo <ms>`, `--sync`.

## The grammar, from the disassembly

`cmdline_read_data_from_file` (Thumb, `0x1908`):

```
0x1910  ldr  r1, [pc, #0x60]     ; "rb"
0x191A  bl   0x1534              ; fopen
0x1928  bl   0x18D0              ; next token from the line
0x1932  rsb  r2, r4, r8          ; bytes still wanted
0x1936  bl   0x16D8              ; convert one field to bytes
0x1946  adds r6, r6, r0          ; advance output
0x194A  cmp  r4, r8              ; until `size` bytes are read
0x1950  movs r1, #0x40           ; 64-character lines
0x1954  blx  0xDC0               ; fgets
```

The field converter at `0x16D8` is where the separator is decided:

```
0x1700  ldrb r2, [r5, r3]
0x1702  cmp  r2, #0x3a           ; ':'
0x1704  bne  0x1760
...
0x1722  cmp  r3, #0x0a           ; LF
0x1726  cmp  r3, #0x0d           ; CR
0x172E  bic  r2, r4, r1          ; clear the ':' bit
0x1738  and  r4, r1, r4
```

`0x3a` is `':'`, and the same separator appears in `.rodata` as `"%s:%s"`.
So a payload file is **`key:value` fields, hex-encoded**, read until the
requested byte count is satisfied.

## The message layout

`cmdline_get_size` (Thumb, `0x1CB0`) assembles a 32-bit little-endian header
from the first four bytes of the structure and adds a length field at
offset `0x2c`:

```
0x1CD2  ldrb r2, [r4, #1]
0x1CD4  ldrb r3, [r4]
0x1CD6  orr  r3, r3, r2, lsl #8
0x1CDA  ldrb r2, [r4, #2]
0x1CDC  orr  r3, r3, r2, lsl #16
0x1CE0  ldrb r2, [r4, #3]
0x1CE2  orr  r3, r3, r2, lsl #24
0x1CE6  ldr  r2, [r7, #0x2c]
0x1CE8  adds r3, r3, r2
```

So: **a 32-bit LE header followed by a payload**, with the total length
carried at offset `0x2c`.

## Why this matters

The blocker on the `ldec` route was that the ioctl argument struct could not
be recovered: `PA 0x5F00A000` returns 0 bytes through `/dev/mem`, the kernel
text mapping is unreachable, `swapper_pg_dir` is not exported, and
`/proc/self/pagemap` returns all zeros even for our own heap.  Every route to
the driver's code was closed.

This interface sidesteps that entirely: it is a **documented userspace path**
into the camera's message bus, with a grammar recoverable offline from a
library that disassembles cleanly.  No kernel memory reads, no driver poking,
no invented struct layouts.

## Tooling

- `testcmd_elf.py` — correct ELF32 parse of `libtestcmd.so` (25 sections, 24
  named functions with exact addresses)
- `testcmd_thumb.py` — Thumb disassembly with PLT symbol resolution and
  `.rodata` annotation

Both lessons are load-bearing: the `.dynsym` addresses carry the Thumb bit
(`0x1909` means `0x1908`), so ARM-mode decoding produces plausible-looking
nonsense rather than an error.  And the earlier ELF parse read header fields at
wrong offsets, yielding `e_type=0x280013` and 44 unnamed PLT stubs — fiction
that looked like a packed binary.  The file was a normal `.so` all along.

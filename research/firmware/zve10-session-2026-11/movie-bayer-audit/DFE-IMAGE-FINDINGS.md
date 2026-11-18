# DFE image findings — 6 November 2026

**Type correction:** Mwrap +0x44/+0x54 are transfer counters (`tcnt`), not
recovered address reports. Native diagnostic execution now verifies the label
and argument order. Previous address-report interpretations are withdrawn.

The normally selected DFE executable is already available. It is the 65,536-byte
`dfe_dat.bin`, embedded in `av-cam.bin` at `0x64560700`. The newly found
`/usr/dfe/dfe.bin` path is a fallback, not evidence of a missing larger runtime.

## Image selection

`0x639daeb4` calls `0x63da0666`, which tail-calls `0x639dfb38`. The latter
unconditionally returns 1 and supplies the embedded pointer and length 0x10000.
The loader takes the embedded branch and skips external I/O. The external path
at `0x639daf10` is reached only when that getter returns zero.

`verify_dfe_loader_selection.py` runs three native-loader cases: the actual
getter; a forced getter failure with external I/O unavailable; and a forced
failure with fixture file data. Actual code selects the embedded image. Transfer
preparation/submission and external I/O are intercepted, so this does not prove
that loading succeeds on hardware. In particular, the loader's returned 1 must
not be presented as physical transfer verification.

Read-only ext2 directory walks of both archived `nflasha15.img` copies find no
`dfe` directory in the filesystem root corresponding to `/usr`. All six archived
tree tarballs were checked for DFE member names. `system.tgz` contains:

| Member | Bytes | SHA-256 |
| --- | ---: | --- |
| system/dfe_dat.bin | 65536 | 6350ef6f6627445eadd7d6427c0a4f0b735e0ef5971a8df731813dfe7e15e502 |
| system/dfe_app.bin | 1956 | 8f9a8d3f8e270d959088c2cb4029b8a115be8d72c70cb18932f4772c27c3cd5f |

This search establishes what these snapshots contain, not every possible camera
filesystem configuration. `dfe_app.bin` is not embedded byte-for-byte in av-cam.

## Small bootstrap

The 1,956-byte `dfe_app.bin` contains mixed ARM/Thumb code, initialization,
transfer-descriptor construction and XDMAC error diagnostics. Its absolute
addresses support loading at `0xfe1ed000`. It is not a recovered pixel algorithm.

Original startup `0xfe1ed010` copies eight bytes from `0xfe1ed79c` to
`0xfe1f0000`, including pointer `0xfc036ff8`, and zeros `0xfe1f0800..0xfe1f0fff`.
Original initializer `0xfe1ed0a0` constructs an object at `0xfe1f0020` and zeros
12 words at `0xfc017fd0..0xfc017ffc`.

`verify_dfe_bootstrap.py` executes these original instructions, including native
memory-copy code. Only the DMA entry `0xfe1ed5a0` is intercepted, returning a
fixture status of zero. Its two captured three-word requests are:

| Operand 0 | Operand 1 | Byte count |
| --- | --- | ---: |
| 0x01017fd0 | 0x01010000 | 0x7fd0 |
| 0x01017fd0 | 0x01030000 | 0x10000 |

Native helper `0xfe1ed282` adds `0x05000000` to both address operands using
32-bit arithmetic. Thus `0xfc017fd0` becomes `0x01017fd0`, and `0xfc030000`
becomes `0x01030000`. This establishes a software address-conversion operation,
stronger than matching low address bits. It does not establish hardware alias
coherence. Request operand direction and DMA fill/copy semantics are deliberately
left unassigned until the DMA control format is resolved. These requests must
not be called an observed upload or pixel transfer.

## The 64 KiB ARM executable

The image build string is `20180731_00_1994_LEO`, at file offset 0xffe0.
Its reset vector points to `0x0100c000`. Startup configures banked stacks and
branches into the C runtime at `0x01000034`; runtime entry `0x010046b8` calls
`0x0100074c`, which ultimately enters `0x01000500`.

The main loop uses a CP15 wait-for-interrupt instruction at `0x010005f0`.
It also has software fallback checks: after more than 700 consecutive
observations of selected pending bits it runs servicing code. One fallback calls
the already tested register-script handler `0x0100030c` at `0x01000658`.
Separate counters are written at local addresses `0x01036fec`, `0x01036ff0`,
and `0x01036ff4`. No time duration can be assigned to 700 loop iterations.
An exception-return version of the script service also exists at `0x01000778`;
the exact vector-publication contract remains to be traced.

The native command decoder at `0x010001d4` operates on 12-byte records at
context `0x01036d00` plus 0x10. Commands 0/1/2 are no-op/write/read; commands
3/4 contain polling/timer behavior still needing separate verification. Events
8 and 16 service two configured script ranges. Thirty decoder tests and fourteen
callable-handler tests were already recorded. Normal segment termination and
invalid bounds both leave status byte 1 equal to 2; that byte alone is not a
success/failure discriminator.

## Implications and next leads

### Verified parameter ABI and an unchecked subtraction

`verify_dfe_parameter_bridge.py` now links native Thumb publisher `0x63da0ab6`
to native ARM consumer `0x01001870`. The publisher writes twelve input words at
target+0x20..0x4c and a control word at +0xfc. Its normal caller
`0x63d9d378` obtains the twelve words through getter `0x639dfcac`, from ROM
`0x63e8801c`. The test transfers the actual published bytes to an ARM RAM fixture
at `0x01030000`, then executes the original consumer. No function callbacks are
used in these two routines; the host harness retains its standard memory helpers.
Physical bus operation and pixel contents are not modeled.

The twelve ROM words are:

```
000005f0 00000011 000005f0 00000022
00000000 00000000 01f60000 01f6c9e0
01f92780 01f9f160 00000000 0000000c
```

The publisher's normal caller obtains control value 0x7200 from `0x63da0f46`;
the ABI test separately varies bit 4 to exercise both consumer selections.
The first two pairs are numerically (1520,17) and (1520,34). Their exact semantic
names remain provisional; they must not be called full-frame image dimensions
or a recovered 1080p Bayer source. Two later pairs contain values shaped like
addresses. Their pixel/table role and allocation ownership remain unresolved.

The ARM routine copies and derives working records at +0x50..+0xb8. Bit 4 of
the control argument selects input pair +0x40/+0x44 instead of +0x38/+0x3c.
It rounds input words +0x48 and +0x4c down to multiples of four, subtracts them
from input word +0x20, and later subtracts both low two-bit remainders. These are
unsigned 32-bit operations with no range rejection in this routine. Twelve
native cases cover both selections and six boundary input combinations.
With first input word 1520 and subtraction inputs 1521 and 0, the final derived
word at +0x90 is 0xffffffff. This demonstrates an unchecked arithmetic boundary,
not an observed camera memory corruption or proof that upstream validation is
absent. Any new caller must validate these dimensions before reaching this code.

The host `0xfc080104` writer also requires a correction in interpretation:
`0x63d25dfc` reads that same status register and writes it back, while
`0x63d25e24` clears selected status bits and updates the interrupt mask at
`0xfc080108` under OS lock 0x27. This is interrupt-status/mask handling, not an
established publication of the shared script. Matching the ARM event register
does not prove a submit path.

Next inspect ARM `0x01002544` and `0x01003598`, called conditionally from
`0x01001228`, and their use of the derived records and DMA helper `0x01001458`.
This can distinguish control-table transfers from image transfers. The standalone
register-script publisher is still unresolved; an offset match in unrelated
large software objects supplies no evidence for it.

### Register consumers and default-mode exclusion

That inspection now reaches original ARM register configurator `0x01001e3c`.
The parameter bridge verifier executes 24 additional cases through it, with
explicit zero subconfiguration +4, plane selector 0/1 and RAM-backed registers.
It programs banks `0x01098300` and `0x01098380`. The original host AIF constructor
`0x637a3be0(kind=1, port=2/3)` independently selects host base `0xfc098000`;
the generic write-bank formula is base+0x200+port*0x80. These are corresponding
write-side register banks under the recovered address conversion.

For the recovered ROM defaults (subtraction inputs 0/12), both banks receive:

| Field | Value |
| --- | ---: |
| Active bytes per line | 3016 |
| Gap bytes per line | 24 |
| Lines minus one | 16 |

The supplied first address pair is transformed by OR with `0xfe000000` before
register writes. For example `0x01f60000` becomes `0xfff60000`. The verifier
checks exact arithmetic, not the physical address-space meaning of that prefix.
Do not interpret the resulting high address as ordinary host DDR without a bus
mapping. The complete 17-line stride span is 51,680 bytes; its data content,
packing and bit precision remain unknown.

Native getter `0x63d22c70` checks the corresponding enables (bits 17/18).
All 23 nonzero results from the native 149-drive-mode default lookup have both
enables clear. Resource 0x39 used by the 23.976 candidates has flags 0x01902111.
Thus this recovered default setup does not establish an active movie frame
source. It must not be confused with resource 0x39's separate logical AIFs 7/8,
whose constructed physical base is `0xfc0ac000`, ports 0/1.

The native dispatch table at `0x645bab60` additionally identifies bit 20's object
as `Camera::DFECore::ZpdPre`, not a generic full Bayer writer. This type evidence
does not determine what its output contains. The active movie processing objects
also include `Ofmt_Mwrap` (bit 13, object `0x6426acc0`), a stronger next target
for the default movie output route than disabled ports 2/3.

### DMA length and status counterexamples

`verify_dfe_dma_contract.py` compares original ARM start `0x01001458` / wait
`0x01001498` against original bootstrap Thumb routine `0xfe1ed5ac`.
It passes 40 length/channel cases and 11 status cases. Function bodies are not
mocked. Register reads return explicitly fixed fixture values; no DMA or pixels
are simulated. Runs are capped at 2,000 instructions to observe software loops;
this cap is not a camera timeout.

The ARM starter writes `((byte_count >> 2) - 1) | 0xa0800000` to the selected
channel control register without checking zero or alignment. Counts 0..3 yield
0xffffffff. Larger unaligned counts are truncated. The bootstrap instead rejects
zero/nonmultiples of four with return 0x10 before writing DMA registers.

The ARM waiter returns as soon as status & 0x70000 is nonzero, returning that
raw status. It does not distinguish the terminal values. The bootstrap maps
0x50000 to success (0), while 0x10000/0x20000/0x30000/0x40000/0x60000/0x70000
return nonzero codes (1/2/3/4/255/7). With fixed error bits 0x80000, 0x100000,
or 0x180000, the bootstrap returns 8; the ARM waiter continues polling.
Static callsites `0x01003664` and `0x0100372c` do not inspect the ARM waiter's
returned raw status. This demonstrates weaker local error handling, not that a
specific physical error occurs or explains the older USB patch's corruption.

A new capture caller must preflight byte counts and buffer bounds and establish
error/timeout handling and ownership before using these helpers. Globally
patching the shared routines is not justified by these isolated tests.

### Active movie Mwrap scripts recovered

`verify_movie_mwrap_scripts.py` now has ten original-instruction script cases using real
mode headers, original Mwrap constructor `0x637a2608`, original header application
`0x63d24fc8`, and original script executor `0x637a6c24`. Only logging is mocked;
MMIO is RAM and the transfer-counter registers are deliberately marked sentinels.
Each actual mode script makes exactly 25 writes:

| Sensor / drive | Header owner | Script at owner+0x38 | Register +0x18 |
| --- | --- | --- | --- |
| 0x1f / 4 | 0x645bb194 | 0x63e71d44 | 0x0027f060 |
| 0xb5 / 0x94 | 0x645bb838 | 0x63e6e5e0 | 0x0020cba0 |

Both target Mwrap base `0xfc0a7000`, with +0x14=3, +0x1c=0x2f8,
+0x64=0x31, +0x68=0x17c0 and +0x6c=1. The units of +0x18/+0x1c/+0x68
are not established here; do not label +0x18 as a byte count or compute frame
dimensions by assuming units. Presence of value0x31 alone does not prove a
specific Bayer packing or decoder.

None of these scripts writes +0x44/+0x54. Native getters `0x63d25034` and `0x63d2504c`
read those respective registers and mask off bits25..31, preserving low25 bits.
The tests prove script sentinel preservation and this exact masking. Executing
native diagnostic `0x637a2448` now verifies its exact format:

```
IMG:Mwrap%d-%d trnsmode%d state%d %d tcnt%x %x status%d %d
```

The two `tcnt` arguments come from +0x44/+0x54, while states come from
+0x40/+0x50 and status bits from +0x4c/+0x5c. The earlier address-report
interpretation was a type error based on the bit mask. These registers are not
a frame-pointer lead. No actual frame address is recovered.

Related allocator `0x637a229c` manipulates a shared twelve-entry map using
registers `0xfc0a7804`, `0xfc0a7808`, `0xfc0a780c`, and per-output counts under
OS lock0x21. Helper `0x637a21b4` selects native index arrays for requested counts
1/2,4,6,8/10/12 and returns0 for3/5/7/9/11. This is a concrete next ownership
lead. The twelve entries must not yet be called twelve full-frame buffers or
DDR banks. Trace its callers and the map's units before attempting a memory tap.

### Shared-map ownership model and caller scope

`verify_mwrap_map.py` executes 150 original allocation cases and ten original
release cases, compared with independent mask/nibble calculations. Fixtures set
prior counts, enable masks and RAM-backed register values. OS locks and logging
are intercepted; no physical ownership fence or memory transfer is simulated.

The context has two byte counts at +4/+5 and an enabled-entry mask at +8.
Output0 takes entries [0,count); output1 takes [12-count,12). Allocation rejects
an unsupported requested count or a count whose sum with the other output
exceeds12. Register `0xfc0a7804` supplies owner bits; `0xfc0a7808/0c` hold twelve
four-bit indices. Mapping values outside selected entries are preserved.
Release disables the selected entries and clears the selected count, but leaves
hardware owner bits and index map unchanged. Stale map contents therefore do
not demonstrate an allocated buffer or a fresh frame.

Recovered caller `0x637a2a60` belongs to `Camera::DFECore::Ofmt_Swrap`, vtable
`0x64588a90`, with allocator tail-call at `0x637a2aa8`. Its underlying object is
`Ofmt_OutSgc`, not the movie `Ofmt_Mwrap` object. Native helper `0x63d2701a`
reads its register +0x50 low3 bits, then `0x637a4490` maps encoded values0..6
to entry counts12/10/8/6/4/2/1. This proves the software count conversion; it
does not prove the size or storage location represented by each entry.

### Fast twelve-bit mode configuration

The script verifier now additionally covers sensor modes5/7/f, drive17/18/1c
(all hexadecimal). Earlier native sensor timing tests identify these as
uncompressed compressType0, twelve-bit packet configurations with nominal
59.94/47.952/59.94 fps respectively. The actual Mwrap scripts preserve that
distinction from the23.976 candidates:

| Sensor / drive | Script | +0x18 | +0x1c | +0x64 | +0x68 | +0x6c / +0x70 |
| --- | --- | --- | --- | --- | --- | --- |
| 5 / 17 | 0x63e72740 | 0x909c8 | 0x1fc | 0x2c | 0x7f0 | 0 / 1 |
| 7 / 18 | 0x63e72740 | 0x909c8 | 0x1fc | 0x2c | 0x7f0 | 0 / 1 |
| f / 1c | 0x63e71264 | 0x11ac50 | 0x5f8 | 0x2c | 0x17e0 | 0 / 1 |

This connects the fast native imager candidates to a matching twelve-bit packet
setting further downstream. It does not establish a complete accessible RAM
frame, actual packing/precision, ownership, or measured cadence. Inferring
storage pitches by multiplying register values by8 remains a hypothesis until
the transfer-counter and stride units are independently established.

There is no present evidence that the 64 KiB file is merely a boot stub waiting
for a missing, larger `/usr/dfe/dfe.bin`. It contains the normally selected
executable, its runtime entry, service loop, interrupt code and register-script
execution. This does not prove that it implements every DFE operation.

The useful next targets are the main CPU's publication of the script at
`0xfc036d00` under the demonstrated conversion, the meaning of nearby shared
state, and DMA control/descriptor construction. Matching the host's actual
register scripts to sensor compression and RAW writer setup can connect this
processor to the capture pipeline. No frame buffer, frame freshness fence,
24 fps Bayer output, higher-bit-depth pixel contents, or working SuperSpeed
patch is established by this work.

# RAW geometry and destination bounds — 6 November 2026

No validated continuous Bayer DDR source or physical crop operation is established
by these tests. They identify native configuration fields and reject unsafe ways
to construct the missing RAW geometry.

## Original geometry diagnostics

`inspect_native_dfe_geometry.py` executes native constructors, resource lookup,
mode headers, driver-parameter builder `0x6379cb68`, final setup `0x6379a57c`,
and native diagnostics for sensor modes5/7/1f/b5. Driver-query bytes come from the
prior native query verifier. Encoder inputs2/8 and the72 clock input are explicit
fixtures. Native setup selects resource0x39 for each of these drive modes.
OS locks, atexit, logger and operation lookup are intercepted; MMIO is RAM.

Values below are exactly what the original diagnostics report, in hexadecimal.
H/V units, packed-field widths and inclusive/exclusive conventions must not be
inferred from the diagnostic letters alone:

| Sensor | Rcv H / V | Lnk HV | Img HV | Of HV |
| --- | --- | --- | --- | --- |
| 5 | 32a / 4bb | 064b04ad | 025a0497 | 01fc0492 |
| 7 | 32a / 4bb | 064b04ad | 025a0497 | 01fc0492 |
| 1f | 32a / d8a | 064f0d7b | 064e0d7b | 05f00d76 |
| b5 | 32a / b22 | 064f0b13 | 064e0b13 | 05f00b0e |

The values are unchanged after both tested full parameter-builder calls, rather
than merely copied from unexecuted scripts. Source, register/stack arguments,
RTTI, native diagnostic PCs and common parameter records are saved in
`native-dfe-geometry-diagnostics.json`. These diagnostics do not supply a frame
pointer or prove that their H/V values are the RAW writer's source dimensions.

## RAW left/top fields are destination offsets

`verify_raw_geometry_offsets.py` executes sixteen original RAW setup cases at
`0x6379e2b8`. Geometry, buffer address/capacity and encoding are fixtures. It
varies left0/16, top0/2, gap rows0/1 for encodings0 and3, with pitch1984,
active width1920 and height1080.

Native setup produces:

```
destination = supplied_base + bytes(left) + top * bytes(pitch)
line_bytes = bytes(active_width)
line_gap = bytes(pitch) - line_bytes + gap_rows * bytes(pitch)
lines_minus_one = height - 1
```

For these aligned test inputs, encoding0 uses2 bytes/sample and encoding3 uses
3/2 bytes/sample. Exact physical packing/precision is not modeled.

Changing left/top/gap changes these DDR layout values. All formatter and shared
register writes remain identical within each encoding. Observed writes are in
RAW formatter/DMA windows `0xfc0a8000..0xfc0a9fff` and shared registers
`0xfc0a0500/0504/0560/0564`; no writes target the known Ifmt geometry region.
Thus these fields must not be used as demonstrated sensor/input crop controls.
The actual source size and any required input crop remain to be established.

## Accepted descriptor exceeding the supplied buffer

Two additional native counterexamples use pitch1920, left16, active width1920,
height1080, top0, gap0, repeat1. The active width plus left padding exceeds
the declared pitch. Native required-size function `0x63d2356a` reports only
the full-pitch frame size. RAW setup accepts that capacity without diagnostics:

| Encoding | Accepted capacity | Programmed destination | Described end | Buffer end | Excess |
| --- | ---: | --- | --- | --- | ---: |
| 0 | 4147200 | 20000020 | 203f4820 | 203f4800 | 32 bytes |
| 3 | 3110400 | 20000018 | 202f7618 | 202f7600 | 24 bytes |

The end is calculated from actual programmed base/line/gap/line-count registers.
No DMA was executed, so this is an accepted out-of-bounds descriptor, not an
observed physical memory overwrite. It does not establish that an existing USB
patch triggers this particular condition.

Before any new caller uses this path, it must validate left+active_width<=pitch,
nonzero and supported dimensions, format alignment, complete destination extent
including top/gaps/repeats, arithmetic overflow, and buffer ownership. Native
capacity acceptance alone is insufficient. An arbitrary1920x1080 geometry with
left/top populated cannot be presented as a working1080p sensor crop.

The next source-specific link is the RdcW0 input route and its actual frame/line
boundaries in fast12-bit mode. The existing Mwrap route is a MIPI transmitter,
not a recovered DDR buffer. A correct geometry record still needs an independent
RAW completion/ownership fence, as the native stop timeout can return while busy.

## Native start preconditions and lifecycle distinction

`verify_raw_start_contract.py` executes64 original CamAif start cases at
`0x63d23398`, dispatching original Aif start `0x637a3ad0`. Constructed RAW
objects are used; destination/line registers deliberately remain zero in RAM
MMIO. Fixtures vary module enable, request bit, skip byte, prior enable, busy,
and low-five error bits. Only logging and harness memory helpers are intercepted.

When module byte+0x14 is enabled, request bit+0x204 bit0 is clear and Aif skip
byte+9 is clear, the native path sets Aif control+0x200 bit0. It does so even
with destination0 and line length0, and does not reject the busy fixture. A
specific prior-disabled/idle/error case emits a diagnostic and writes the
status-clear bit, then still enables. These are local preconditions expected
of its caller, not proof that the stock firmware normally starts unconfigured
DMA or that such a hardware write actually transfers data.

The CamAif vtable at `0x64588788` distinguishes lifecycle slots: +0 dispatches
`0x63d2345a`, which enables common/logical gates and invokes Aif/formatter
initialization; +8 dispatches `0x63d23398`, the conditional start path. RAW Aif
initialization is `0x63d2615c`, which writes reset-style commands to its base;
formatter initialization is `0x63d258bc`, writing `0x100` to `0xfc0a8700`.
Physical command-register semantics are not independently modeled here.

A resource flag inserted after normal resource initialization cannot be assumed
to have initialized that newly enabled RAW module. Existing SetParams tests
establish register calculation, not a complete initialized/running device.
Likewise, successful start dispatch supplies no DMA completion or frame proof.

The formatter setup's writes to `0xfc0a0500/0504` and `0560/0564` must not be
called shared-state clobbers based solely on RAM-backed MMIO. The paired
addresses/access patterns may implement command semantics on hardware; those
semantics are unresolved. Neither assumed ordinary RAM behavior nor universal
MMIO success is sufficient to validate concurrent insertion into a live route.

## Geometry catalog and movie AIF descriptor provenance

The native drive scan uses IDs `0..0xb9`. The catalog verifier calls the original
header lookup `0x637a6e88` for all 186 IDs and the native geometry selector
`0x63d234e0` for all eight slots of each of the 13 distinct returned owners.
All 104 selections return null from the firmware image. A separate fixture with
distinct words in each slot confirms that logical IDs 5 through 12 select
`+0x5c..+0x78`, and the other 248 byte values return zero. This covers the
shipped catalog, including fallback owners. Runtime overrides remain an open
question.

The four native mode traces for sensors 5, 7, 1f and b5 record zero writes to
`0xfc0ac000..0xfc0acfff` during header application and both full parameter
calls. The eight parameter calls all reach the original CamAif parameter method
`0x6379e1f4` for logical IDs 7 and 8 with enable byte 1. That method copies the
enable byte into the object. The generic setup calls that take AIF geometry in
`0x6379a57c` target logical 5/6 and 9/10. This leaves descriptor provenance for
ports 0/1 of `0xfc0ac000` unresolved beyond the tested stages.

The other direct caller found for AIF descriptor writer `0x63d264ac` is
`0x63d271e6`, inside ZpdPre's native header method. It takes six halfwords
from owner `+0x58` and builds a descriptor with `0x63d27158`. All four tested
modes reach this call with bank `0xfc098000`, port 1, and the same descriptor
beginning `fffa0000 20 c9c0 1`. The `0x20` line field and the bank/port identify
a separate transfer from the two movie AIF channels under investigation. The
trace executes the original descriptor writer against RAM MMIO. Pixel content
and hardware completion remain outside the model.

## Movie AIF7/8 are labelled R0/R1 by native diagnostics

The direct GOT references to the two CamAif objects lead to their constructors.
References to their backing AIF objects also lead to the diagnostic at
`0x6379b694`. Its `IMG:CurAddr` format labels eight arguments `R0` through `R5`
and `W0` through `W1`. The original getter reads `bank + 0x210 + port * 0x80`.
The role verifier sets distinct sentinels in those registers and executes the
original diagnostic, intercepting the logger to inspect register and stack
arguments. The exact mapping is logical 7/8 to `R0/R1`, and logical 5/6 to
`W0/W1`. The sentinels verify argument provenance. They are not captured frame
addresses.

Treat AIF7/8 as the read-side branch when tracing resource 0x39. Their enabled
flags and current address reports provide no basis for treating them as Bayer
producers. The fast-mode MIPI output and the RdcW0 input path remain candidates
for locating a producer and writable destination.

## Packed W0 geometry needs a whole number of formatter blocks

Nine additional native setup cases exercise encoding 3 around 16-pixel
boundaries, including the 1996-pixel active width reported for fast modes
5/7 by GetArcFrame. These are hypothetical W0 geometry records using pitch
2016 and height 1122. GetArcFrame describes a different stage and supplies
no evidence that its width is the W0 input width.

The formatter encodes `floor(width / 16) - 1` at `0xfc0a8910` while the
DMA uses `24 * ceil(width / 16)` bytes per line at `0xfc0a9224`. For width
1996 those values describe 124 formatter blocks and 125 DMA blocks, with
no native diagnostic. Widths 2004 and 2008 describe 125 versus 126 blocks.
The aligned controls 1920, 2000 and 2016 agree. Width 15 produces the
underflowed formatter word `0xffff0461` for height 1122.

This rules out copying the unaligned reported widths verbatim as a
self-consistent encoding-3 descriptor. Padding or selecting a different
encoding requires independent evidence of source geometry and formatter
behavior. The emulator verifies register programming only.

## Full fast-mode setup with hypothetical W0 geometry

Six paired traces run the original header and parameter setup for sensors
5/7 with and without bit 21 and a fixture in header slot `+0x5c`. With the
fixture installed, all six reach the real W0 setup and program destination
`0x20000000`. At width 1996, encoding 0 programs 3992 line bytes and a
40-byte gap. Encoding 3 programs 3000 line bytes and a 24-byte gap at both
1996 and 2000, with different formatter block counts as tested above.

The stock MMIO write sequence outside the W0 formatter/DMA windows and four
shared registers is unchanged. Encoding 0 adds writes of `0x1c0` to
`0xfc0a0504/0564`. Encoding 3 adds `0xc0` there and `0x100` at
`0xfc0a0500/0560`. These four addresses are the unresolved part of the
configuration delta. The trace does not simulate their hardware semantics,
resource acquisition, stream start, sensor input selection, or DMA completion.

The paired trace also caught an older harness input error. With the debug
address override disabled, builder `0x6379cb68` takes the buffer address from
the public request at `+0x08`, capacity from `+0x18` and repeat count from
`+0x14`. The older test put the address in the repeat field. The corrected
movie null-geometry test now checks that W0 sees the intended buffer address
and still confirms zero W0 writes when geometry is absent.

## Shared register writes follow per-channel format masks

The four addresses are used by the native format methods of `RdcR2`, `RdcR3`,
`RdcW0`, and `RdcW1`. The verifier obtains each object from the original DFE
constructor and executes its `+0x2c` method for encodings 0 through 9, with two
different prior register images. All 80 executions produce the same command
sequence for a given channel and encoding, with no reads from the four
registers. The paired writes to `0504/0564` and `0560/0500` form disjoint masks
that together cover only the corresponding channel's bits. The channel masks
are R2 `0x003`, R3 `0x018`, W0 `0x1c0`, and W1 `0xe00`.

This supports a per-channel format set/clear command interpretation. The
original code passes a format enumeration to these methods and supplies no
source selector. Physical register semantics and the route into W0 still
require independent evidence. The current trace does not justify assuming
that an added W0 mask replaces other channels' configuration.

## Full fast-mode start and callback ordering

All six paired W0 setup cases now run native start `0x6379ab48` with a
callback fixture. The W0-enabled cases dispatch `0x63d23398` on logical 5
and set bit 0 in `0xfc0a9200`. Stock and modified cases register the same
IRQ selector, `0x11`. In all six enabled cases, supplying stock IRQ status
bits `0x80000` and `0x1000` while keeping W0 busy at `0xfc0a9204` makes the
original interrupt handler `0x6379ef08` invoke the callback while W0 is
still busy. This is an injected ordering test. It demonstrates that the
callback code lacks a W0 completion check. Physical event ordering, source
routing and transfer completion remain outside the emulator model.

The paired verifier now runs native resource acquisition `0x6379aee4` before
header setup. With W0 added only to active flags, a competing resource
`0x2f` is refused before release and remains refused afterward in all six
cases. Release `0x6379ad4c` returns success and invalidates the token, but
reloads default flags before subtracting them from the global reservation
mask. W0's dynamic bit `0x200000` stays reserved.

A separate test adds W0 to both default and active flags. Release now clears
the reservation, and the competing resource can acquire while the injected
W0 busy bit is still asserted. The two cases separate software reservation
accounting from a DMA fence. A candidate tap needs to preserve both until
completion is independently established. Hardware busy is a controlled
register fixture in these tests.

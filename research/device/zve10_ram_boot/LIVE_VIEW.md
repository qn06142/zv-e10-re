# Custom RTOS live-view bring-up

21 November 2026. `rtos_live_view.c` is a separate C payload for the existing
`rtos.bin` loader. It shows sensor/preview register observations on the rear LCD.
It does not yet start the sensor or display sensor pixels.

The ten observed banks are ISP channels 3/9, FOPD R0/W0/W1, DFE core W0,
and the four YUV0/YUV1 plane banks. Addresses follow the saved
[Senser readout](../zve10_hardware_map/evidence/20261120-senser-isp-readout.json)
and the [FOPD contracts](../../../docs/hardware/SENSOR_DMA.md).
Each row shows control at `+0`, status at `+4`, the address candidate at `+0x10`,
changed observations and address changes, all in hexadecimal. Neither counter
counts frames. Register reads are sequential, not an atomic hardware snapshot.

The first sample is saved before `zvrt_display_init()` drains inherited video
AIF channels. It is still **after** the loader's Linux shutdown and `crt0`'s
platform quiesce. The payload cannot establish the stock shooting state or
preserve the stock live-view producer. A quiet bank after takeover does not prove
that it was quiet before takeover. `live_view_initial[10][3]`,
`live_view_samples[10][5]` and `live_view_polls` remain available as ELF symbols.
These records are cacheable runtime memory, not a persistent post-reset log.

Press OK to freeze/resume sampling. The two uncached LCD buffers continue flipping
while frozen. A flip timeout retries the same pending buffer before any repaint
or swap. Counters saturate at `FFFFFFFF`. The payload only reads the selected
sensor registers and never dereferences their address values. Startup and the
existing display/input runtime still write their established peripheral registers.
Battery removal returns to stock using the existing manual recovery workflow.

## Build and offline verification

From the repository root in PowerShell:

```powershell
.venv/Scripts/python.exe research/device/zve10_ram_boot/build_rtos.py --source research/device/zve10_ram_boot/rtos_live_view.c --display --out .local/out/rtos-live-view
.venv/Scripts/python.exe research/device/zve10_ram_boot/verify_live_view.py .local/out/rtos-live-view
```

The ARM verifier checks the package CRC, all ten read locations, unchanged,
status-only and address-changing observations, saturation, initial records,
OK freeze/resume, five alternating framebuffer flips, and timeout retry without
repainting. It executes compiled sampling, drawing and main-loop instructions;
input and display services are modeled. It checks that these routines issue no
sensor MMIO writes and write only image state, stack, handoff and the two LCD
buffers. This test does not execute `crt0`, establish physical MMIO behavior,
or verify sensor completion, buffer ownership or physical LCD output.

The candidate is built locally; it has not been installed or hardware-tested.
Use the established guarded loader workflow and preserve the installed image
before an on-camera trial. No autoload or persistent boot-selection change is
part of this payload.

## Next imaging milestone

Resolve and implement sensor/DFE initialization after takeover, then identify a
completed YC frame with measured geometry/packing and a producer reuse fence.
Only then add a source reader/converter or native YUV scanout. Existing VPH
address traces do not establish those missing completion and lifetime contracts.

## Sensor initialization continuation

The native imager initializer at `0x637abba4` now executes offline with saved
Backup reads in place of Linux callbacks. Its own read lists bind 19 parameter
units to firmware RAM: twelve `0xbc` units and seven `0x132` units. The extractor
checks every native-selected destination and verifies the resulting bytes against
the saved properties. This recovers the profile loading omitted by a firmware-file
only test: the imager configuration at `0x640ba460` starts zeroed in that file.
Saved Backup data is still not a fresh current-body capture.

`imager_sequencer.c` ports the native index-1 register accessors at
`0xfc088300/0xfc088e00/0xfc088f00`. An additional native-instruction check maps
IRQ 132, DFE event 0, to the index-1 sequencer callback. The C completion handler
matches the original local acknowledgement, engine park and DFE acknowledgement
order. Parking writes mode 2 without the three-write software-start pulse.
The caller must invoke it for a real IRQ; reading event number zero outside an
interrupt is not a completion check. Other DFE event numbers are rejected.

```powershell
.venv/Scripts/python.exe research/device/zve10_ram_boot/build_rtos.py --source research/device/zve10_ram_boot/rtos_live_view.c research/device/zve10_ram_boot/imager_sequencer.c --display --out .local/out/rtos-live-view-sequencer
.venv/Scripts/python.exe research/device/zve10_hardware_map/audit_imager_sequencer.py .local/dumps/av-cam.bin .local/out/rtos-live-view-sequencer/rtos.elf
.venv/Scripts/python.exe research/device/zve10_hardware_map/extract_imager_profile.py .local/dumps/av-cam.bin .local/dumps/staged/audit/Backup.bin --mode 5 --out .local/out/rtos-live-view-sequencer/native-mode5.json
```

The sequencer port passes 180 comparisons/guard cases, including the complete
native IRQ dispatcher with modeled OS notification. The saved-profile mode-5
readout produces three uploads of 251, 45 and 124 bytes. Internal mode 5 is a
fixture selector, not a verified live-view preset. The extractor models event
waits and omits the per-frame SetImgRd descriptor. Its raw write log must not be
replayed as an initialization recipe. Raw command bytes stay in local outputs.

The diagnostic payload does not yet call these new sequencer functions. Full
sensor initialization, link acquisition and completed-frame delivery are still
under development. On 21 November the USB probe found no camera; the owner
reported that it needed charging and requested continued offline work followed
by a wait. No camera writes or flash operation were performed during this work.

### Connected-camera checkpoint, 21 November

The subsequent USB Senser capture matched all 19 selected code pages against
the reference and retrieved 19 stable sensor profiles plus 16 scalar settings.
Units `0xbc000e` and `0xbc0010` differ from the archived Backup. The native
initializer/readout replay now supports the freshly captured properties and
the identified current-body firmware. It completes offline with three command
uploads; host event waits remain modeled.

Reading the live imager singleton confirmed its IMX284 vtable and internal mode
`0x11` in both requested/prior fields. Its `+0x22c..+0x257` timing block was zero
in Senser. These measurements explain why the USB service state cannot supply
the active shooting configuration for the custom runtime.

A bounded recorder was uploaded as `/log/zvlv21.sh`, read back byte-for-byte and
started with the available `setsid` applet. The live process and
`WAITING_FOR_SHOOTING` status were observed. It waits at most 180 seconds for a
non-idle imager mode, then records three RAM/register/IRQ samples under
`/log/zvlv21`. It issues no sensor-start or MMIO-write commands. The owner
reported disconnecting USB, leaving normal live view on and reconnecting.

The initial service session could not accept terminal input under the host
approval policy. After the camera returned in Mass Storage mode, the host
retired its stale session and retrieved all 13 recorder files in one read-only
Senser session. The recorder reported `DONE` and the session closed normally.
[Metadata checkpoint](../../../docs/hardware/data/imager-bringup-20261121.json)

All three shooting samples show imager mode `0x01` in requested, current and
previous fields. The `+0x22c..+0x257` block stayed zero in shooting as well as
Senser. The captured body firmware and profiles replay mode `0x01` offline and
produce uploads of 251, 45 and 124 bytes. Event waits are still modeled.

FOPD W0 showed changing current and programmed addresses in the `0xfe4xxxxx`
range with `+0x24 = 0x29400`. YUV1 plane 0 scanned from `0x16a00000` with a
1024-byte fetch, 128-byte line gap and 570 rows. Separate reads of the status,
current address and base can straddle an update. The samples establish activity
and geometry but provide no completed-buffer identity or reuse interval.

Across 3.77 seconds, IRQ 83 advanced by 565, IRQ 84 by 2709, LCD IRQ 102 by
188 and XDMAC5 IRQ 194 by 226. IRQ 132 stayed at two. The captured body's ARM
instructions verify that IRQ 83 writes back status at `0xf3950610` and reports
whether bits 24–27 were set. IRQ 84 acknowledges its pending word from
`0xf3c30004` at `0xf3c30008` before dispatching up to eight callbacks. The
offline audit tests these contracts with fixture callbacks. The native slot
registration path at `0x6377fe50` indexes the same 32-byte records before
calling `0x63d1dbb8`. The slot therefore needs to be bound to the registered
consumer on a running camera. The event that retires a particular W0 frame
remains open.

```powershell
.venv/Scripts/python.exe research/device/zve10_hardware_map/audit_shooting_irqs.py .local/out/rtos-live-view-hardware-20261121-03/av-cam-body.bin
```

A second shooting capture read the IRQ 84 subscriber table from its physical
RAM alias (`0x04263d24`). All three snapshots matched. Slots 4–7 were active
with sources `0x17`, `0x1e`, `0x1d` and `0x1c`. They share wrapper `0x63d63829`
and use distinct callback targets `0x6394ed6d`, `0x63950d79`, `0x6395151d`
and `0x638d0e81`, respectively. The audit fed each captured table to the
original dispatcher and wrapper. It verified the exact callback and argument
for each pending bit and for all four together. The test stops at the callback
entry. Slot 7 posts flag `0x100000` to event group `0x1a` and stores the
incoming value. Mapping that event to a specific retired W0 DMA range still
requires evidence from the consumer or writer.

### RTOS preview trial staged on the camera

`rtos_preview_trial.c` tests the YUV1 busy-to-idle edge as a sampling trigger
after platform quiesce and before LCD takeover. It admits only the recorded
YUV1 base and geometry, bounds the wait, and samples the even bytes as a
packed 4:2:2 luma hypothesis. It checks the registers again after copying into
private memory. The LCD shows the last admitted sample and reports whether a
second sample differed. This test samples up to two frames and then holds its
result. The edge belongs to the display reader and provides no ownership fence
with the sensor producer.

```powershell
.venv/Scripts/python.exe research/device/zve10_ram_boot/build_rtos.py --source research/device/zve10_ram_boot/rtos_preview_trial.c --display --out .local/out/rtos-preview-trial
```

The compiled ARM trial passed modeled cases for differing and identical
samples, no edge, a geometry mismatch, and DMA going busy again during sampling.
The 7,576-byte trial (`fb305f8603338777a2fd0938b46b058b78f1f7cfb2b728dbd4a157225c97baf8`)
was installed at `/log/zve10-ram-boot/rtos.bin`. `boot.ko` reached `READY`, unloaded,
and the host read back the installed file byte for byte. The prior shell image
is at `/log/zve10-ram-boot/rtos.pre-preview-trial.bin`. After GO the camera LCD
reported `No YUV1 busy-to-idle edge`. The initial geometry check passed, the
sampling deadline elapsed, and the display path presented the result. No pixel
copy occurred because the required edge never arrived.

The second trial uses a backwards jump in the OSD0 scanout address as its
sampling clock, with a bounded timer fallback. It records whether YUV1 and
FOPD W0 current addresses change during the polling window. It still compares
two grayscale samples from the same verified YUV1 geometry. OSD timing provides
no DMA ownership guarantee. The 7,600-byte candidate passed modeled wrap,
timeout fallback, address movement, geometry rejection and pixel comparison
checks. SHA-256 `224ce228c2253eef3fa3c70a69c4683eb5229728265dac2f198982ae89c898e7`.
USB staging reached `READY`, unloaded and matched the installed binary byte for
byte. The first trial is backed up at `/log/zve10-ram-boot/rtos.pre-preview-v2.bin`.
The second physical trial reached the LCD and displayed `Two identical YUV1
samples`, with `OSD wraps: 0`, `YUV moved: 0`, and `FOPD moved: 0` as read from
the owner photo. The timer fallback sampled the admitted DDR range twice.
The even-byte interpretation rendered a block pattern with no recognizable
image. This shows the CPU can sample the retained buffer and display a result.
During the two bounded windows the trial observed no evidence of a running
producer. The block pattern does not identify the buffer's encoding.
Photo SHA-256 `aa3dd2acf21f7ee063b535bd5567fbb803f31ad4675d0ecf230e0b732594d9c4`.

A useful next test needs to make the sensor/receiver advance after takeover.
Until it does, changing the sampling clock cannot produce new pixels from
this retained buffer. Native VPH scanout or a verified YC layout is needed to
interpret those pixels.

### Bayer RAW target

The capture target is now Bayer from DFECore RdcW0 at `0xfc0a9200`. Its known
destination geometry uses active line bytes, line gap and rows minus one.
FOPD W0 at `0xf3020280` is sampled alongside it as a separate pipeline stage.
The prospective capture path should keep the native bytes and record the
verified geometry, packing, CFA and completion condition alongside them.

`rtos_bayer_probe.c` builds a standalone RTOS diagnostic that displays both
writers' programmed ranges and observed activity after GO. It computes a
DDR0 span only for RdcW0, checks the full span against the aperture and leaves
candidate addresses undereferenced. In the ARM model, the payload counted
address changes and both busy edges, accepted a valid span and rejected zero
and out-of-bounds spans. It issued no sensor or writer MMIO writes. The package
is at `.local/out/rtos-bayer-probe/rtos.bin`. The 8,356-byte binary
(`bb670114499cec12eb19f347cdf2a03650823ec2031c1e81e337d8a38e155962`)
was installed and read back byte for byte. The existing loader reached `READY`
and unloaded. The previous preview trial is backed up under
`/log/zve10-ram-boot/rtos.pre-bayer-probe.bin`. The owner ran GO and photographed
the result. DFECore RdcW0 reported zero control, status, current, base, geometry
and computed DDR span. FOPD W0 retained control `2`, status `0`, current
`0xfe43d200`, base `0xfe413e80` and `+0x24 = 0x29400`. Both writers reported zero
address changes, zero busy rises and falls, and zero geometry changes across
`0x257` (599) post-GO polls. FOPD's retained values match a stock shooting
sample. Photo SHA-256 `b2fb9518839292192ebe91cbd5d40f3fd3ead7e32b59fff66cab7caf1eefd641`.

RdcW0 remains an acquisition candidate. The native fast-mode callback can fire
while RdcW0 is busy, so a callback alone cannot release its buffer. The existing
offline formatter audit also derives two bytes per sample for encoding 0 without
establishing the actual wire bit depth or layout. The first Bayer success check
is one completed frame in RTOS-owned memory with verified packing, followed by
a host readback of the original bytes.

Six checked slices of the installed body firmware match the local reference,
covering the RdcW0 formatter reset (`0x63d258bc`), AIF reset and arm helpers
(`0x63d2615c`), RAW geometry builder (`0x6379e2b8`), RAW arm (`0x637a3ad0`),
CamAif init and start (`0x63d23398` through `0x63d23469`), and the RAW IRQ
aggregator (`0x6379ef08`). The next write trial needs sensor and receiver
activation plus a writer destination and geometry for an owned buffer. The
observed post-GO registers supply no existing RdcW0 destination to reuse.

### Bayer baseline in Senser

The 21 November USB service capture read control, status, current address and
destination geometry for DFECore RdcW0 and FOPD W0. Every field in both writers
was zero at uptimes 94.03 and 94.98 seconds. The IMX284 object reported mode
`0x11`. IRQs 83/84 advanced by 114/685 while the sequencer IRQ 132 and XDMAC5
IRQ 194 stayed unchanged. This gives a baseline for testing explicit sensor
activation with Senser connected and shows why IRQ 83/84 counts alone cannot
certify a Bayer transfer. The capture issued no sensor-start or MMIO writes.
The complete local record is `.local/out/rtos-bayer-senser-20261121-01/capture.json`.

### Native preview start/stop in Senser

The ZV-E10 ran Sony's native `/usr/bin/scenario.elf` with USB Senser
connected throughout each test. `CAMERA_SCN_EE_START_STOP b:0 b:0` started
movie preview and switched the IMX284 from mode `0x11` to `0x05`.
`CAMERA_SCN_EE_START_STOP b:1 b:0` started still preview in mode `0x01`.
Both starts returned payload byte `0x01`. The active FOPD W0 destination
pointer changed between samples in both modes.

| Preview | IMX284 mode | FOPD W0 current address samples | FOPD W0 +0x24 |
| --- | --- | --- | --- |
| Movie | `0x05` | `0xfe425880`, `0xfe43ae00` | `0x27000` |
| Still | `0x01` | `0xfe468600`, `0xfe459380` | `0x25800` |

All sampled DFECore RdcW0 fields stayed zero in both runs.
`CAMERA_SCN_EE_START_STOP b:16 b:0` returned payload byte `0x01` in each
run, restored idle mode `0x11`, and cleared the sampled FOPD W0 fields.
The test did not copy image data or flash firmware. The local captures are
`.local/out/rtos-bayer-senser-ee-20261121-04/capture.json` (movie) and
`.local/out/rtos-bayer-senser-ee-20261121-05/capture.json` (still).

The separate `CAMERA_SCN_EXTERNAL_RAW_RECORD` plugin dispatches external RAW
output on/off and device acquire/release. That dispatch does not establish an
internal RdcW0 destination or a Bayer frame completion signal.

### One-shot RAW capture in Senser

On 21 November, the ZV-E10 accepted Sony's `adjstctl.elf 0x404 0x4e`
(`C_RAWDATA_CAP`) with USB Senser connected and still preview active.
The owner heard the shutter. The IMX284 switched from still-preview mode
`0x01` to capture mode `0x37`, then returned to `0x01`.
`adjstctl.elf 0x404 0x1` (`G_CHK_CMP`) returned payload `0x01` while
busy and `0x00` after the capture. The RTOS handler at `0x6391c104` copies
the busy flag to that payload. The idle flag alone does not certify a frame.

The Linux command table routes block `0x404` to OSAL queue `0x000301d7`.
On the capture branch, the RTOS dispatch at `0x6391c660` goes through
`0x63af4890` and selects adjustment mode `0xa00a` for code `0x4e`.
RdcW0 remained zero at every sampled point, including a sample in mode
`0x37`. The sparse samples leave the actual still-capture DMA channel
and its completion event unresolved.

#### Published buffer metadata

The first completed run changed the published descriptor from zero to DMM
unit type `0x347` and length `0x03000000` (48 MiB). The next completed run
published the same type and length with a fresh handle, `0x2b68` after
`0x10f6`. Stock `DmmConfig.bin` maps type `0x347` to extent `0x489`,
which also has a configured size of 48 MiB.

| RTOS virtual address | Observed value | Provenance |
| --- | --- | --- |
| `0x643bbb14` | `0x03000000` | Length published by `0x6391d2b0` |
| `0x643bbb24` | `0x17a0` (6048) | Row-width term used by the native partial-read calculation |
| `0x643bbb28` | `0x347` | Published DMM unit type |
| `0x644a472e` | `0x2b68` | Published handle for the second completed run |
| `0x643bbc84` | `0x0001` | Readiness field checked by the native partial-read handler |
| `0x643bbc8c` | `0x0b000000` | Base address used by the native partial-read handler |
| `0x643bbc90` | `0x03000000` | Length field used by the native partial-read handler |

The partial-read handler at `0x6391c190` computes a row step of
`2 * 6048 = 12096` bytes. That establishes the factory handler's address
arithmetic. The active rectangle, sample precision, packing, CFA order,
DMA completion and buffer lifetime still need verification. The local Linux
DMM proc listing had no matching row for the observed type, extent or handle.
The native base address was read from metadata. No image bytes were read.

The first attempt to query `C_GET_RAW_YC_DATA` through `adjstctl.elf`
timed out and lost the Senser session. Subsequent runs collected only the
descriptor fields with read-only memory accesses. In both completed RAW
trials the preview-stop scenario acknowledged the command, but the sampled
imager remained in mode `0x01`. A later read-only Senser session still
reported `0x01`. No firmware was flashed.

Local evidence is under `.local/out/rtos-bayer-senser-native-20261121-03/`
and `.local/out/rtos-bayer-senser-native-20261121-04/`. The latter contains
`capture.json` and the later read-only `post-session.json`.

#### Native buffer ownership and layout

The still capture publisher at `0x63926fe0` takes a DMM handle from a
halfword in the capture context. The slot-zero caller at `0x63d8fd52`
uses context offset `0x67b0`. The publisher frees any previous retained
handle through `0x63926fb8`, moves the new handle to `0x643d7320`,
invalidates its context slot and opens it through `0x63970228`. The wrapper
then calls ordinary capture cleanup at `0x638d933c`, which walks the context
slots and skips the invalidated entry. On the
branch that publishes unit `0x347`, the row-width and second dimension come
from context offsets `0x214` and `0x218`. The publisher sums the DMM extent
lengths for the advertised size and copies the DMM open reply into the public
partial-read descriptor.

The offline verifier executes the original publish, capture cleanup and release routines with
fixtures for DMM and logging. It checks an empty source, first publication,
replacement, and release. With the two handles seen on the camera, the
original code frees `0x10f6` before opening `0x2b68`. Releasing `0x2b68`
clears the retained handle and its stored base. The public descriptor still
reports handle `0x2b68`, readiness `1`, and base `0x0b000000` after release.
The retained handle and a valid ownership window are therefore required
before copying from the published address. The replay does not model cache
coherency or verify how long the physical camera keeps the allocation.

The existing IMX284 provider audit reports 14-bit **sensor packets** for mode
`0x37`. The receiver profile for the same mode reports a 6028×4024 canvas
and a 6000×4000 active rectangle. Those numbers describe the receiver stage.
The adjustment buffer separately reported a 6048-sample row term and its
reader advances two bytes per sample. The relationship between those two
layouts and the actual bit alignment still require a captured pixel sample.

Replay from the checkout with
`python research/firmware/zve10-session-2026-11/movie-bayer-audit/verify_still_raw_handoff.py .`.

### Software Bayer display demo

`rtos_bayer_display.c` fills two 640×480 RGBA4444 buffers and flips them through
the existing LCD scanout path. The CPU maps each LCD pixel to a 2×2 RGGB cell,
averages its two green samples and writes the resulting color. The LCD path
scans out the completed buffer at native size. It does not scale the image.

The build repeats staged RGGB frames when available. Without a compatible clip
it generates a fresh 960×720 test frame on each iteration and labels the LCD
`TEST PATTERN`. The staged path is labeled `STAGED BAYER`. GO shuts down the
stock capture services, and the independent RTOS sensor producer is still
missing. This demo verifies the resize and display loop before that producer is
connected.

Build from the checkout with:

```powershell
.venv/Scripts/python.exe research/device/zve10_ram_boot/build_rtos.py --display --source research/device/zve10_ram_boot/rtos_bayer_display.c --out .local/out/rtos-bayer-display
```

To stage a sequence, the existing loader reads
`/log/zve10-ram-boot/clip.bin`. The Bayer clip format starts with a 16-byte
little-endian header (`<4sHHII`) containing `ZVBR`, even width, even height,
frame count and a zero reserved word. The header is followed by exactly
`count * width * height` little-endian 16-bit samples, tightly packed in
RGGB order with full-scale white at 65535. The loader caps the whole file at
16 MiB. Sensor dumps need verified packing and normalization before they can
be supplied in this format.

ARM emulation passed packaged image CRC, color reconstruction with known
Bayer values, staged frame wraparound, changing test frames, malformed clip
fallback, and display flip retry and timeout. It uses modeled LCD calls.

#### Verified sensor frame readback

A following Senser run triggered `C_RAWDATA_CAP` and acquired handle
`0x0b75`. The completed descriptor reported a 6048×4024 raster, 12,096
bytes per row and a 48 MiB allocation at `0x0b000000`. The retained handle
and public descriptor matched before and after the final transfer and the
camera-side checksum. Restarting the USB session preserved the same handle
and starting bytes. The full 50,331,648-byte host file matched the
camera-side SHA-256
`19b49b46e0ba0915788e9f4623118e33ca792e11504ca5bb24e7a9bc862d35f4`.

Interpreting the first 48,674,304 bytes as little-endian 16-bit samples gives
a recognizable image when each 2×2 cell is averaged to grayscale. The four
mosaic positions averaged 1436, 2412, 2414 and 1515 in row order. This
supports a Bayer mosaic with green on the off-diagonal. Red/blue order
remains unverified. Samples in the recorded raster ranged from 522 to
10,577, consistent with 14-bit sensor samples stored in 16-bit words.
The saved RAW includes the allocation tail and has no image header.

Transfer records and the original bytes are in
`.local/out/rtos-bayer-senser-readback-03/`. This capture used the stock
sensor services while Senser was running.

#### Embedded Senser frame test

The `rtos-senser-frame.bin` build embeds the verified Senser capture as a
single Bayer fixture and selects it before any staged clip. The encoder
averages groups of eight by eight samples at each Bayer position separately,
applies a display tone curve and pads the reduced mosaic to 756×568 with black
bars. The RTOS still reconstructs and resizes the image on the CPU, then
loops the same frame on the 640×480 LCD. The test uses provisional RGGB
ordering. Red and blue order and white balance are uncalibrated.

The ARM replay displayed three identical frames using alternating
framebuffers and the `SENSER RAW` label. On the camera, the 866,796-byte
payload matched a full Senser readback and the loader reported READY.
The module then unloaded. The previous payload is saved at
`/log/zve10-ram-boot/rtos.pre-senser-frame.bin`. The lab record is
`.local/out/rtos-senser-frame-stage-01/stage.json`. GO and the rear-LCD
check remain pending.

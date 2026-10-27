# Sony ZV-E10 reverse engineering

Reverse engineering of the **Sony ZV-E10**, firmware 2.02/2.03, kernel
`3.0.27_nl-rt106+`. Reached through the camera's service-mode USB shell, which
yields a root BusyBox prompt without breaking a finger off.

This repository is a fork of **[ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE)**
(MIT, © 2015 ma1co), which provides the USB plumbing. Everything under `docs/`,
`avcam_re/`, `retool/` and `research/` is ZV-E10-specific work added on top.

## Hardware-verified: custom VGA video over USB

![Synthetic colour bars and frame counter captured from the Sony ZV-E10 over USB](docs/assets/zve10-vga-colour-bars.gif)

*Ten actual camera-to-PC frames: 640×480 YUY2 synthetic colour bars, with counters 1–10 along the bottom. The loop plays at 10 fps for presentation; capture timing was not measured.*

The camera runs our own video producer and sends its frames through the USB video pipeline. The permanent **2.4p** patch survived reboot, delivered ten exact frames in FFmpeg, delivered another ten when FFmpeg reopened the same streaming session, and displayed the bars and counters in **OBS**.

- **640×480 YUY2 over USB 2**, advertised at 10 fps. The captures validate delivery and counters; sustained frame rate was not measured.
- **Custom producer and transport:** synthetic frames reach a standard PC video client through the camera's USB gadget.
- **Persistent activation and recovery:** the tested patch activates during USB Streaming setup, with verified recovery files preserved.

See the [hardware test report](docs/uvc_yuy2_patch_v24p.md), [reproducible producer source](research/firmware/yuy2_transport_v24p/README.md), and [capture provenance](docs/assets/zve10-vga-colour-bars.json).

Live sensor acquisition is the next research layer. **Revision 3.0's VGA resize candidate is installed and reboot-verified, but has not been stream-tested; camera testing is paused.** The next major push uses the proven VGA transport and new Sony allocator/metadata findings to trace a genuine **4K / 12-bit** source. See the [next-push plan](docs/90-session/4K_12BIT_NEXT_PUSH.md).

The earlier [magenta framing-lines patch](docs/magenta_framing_lines.md) remains documented as the first verified LCD palette modification.

## What this found

**A working code-execution path into the camera's housekeeping stack.** The
service shell can write `/usr/lib`; the filesystem is ext2 on `nflasha15`, is
remountable `rw`, and is *not* wiped at boot. Replacing a shared object the
camera loads by name means the dynamic loader runs your code as root.

Proved rather than theorised: a 66-byte Thumb-2 payload of raw `svc #0` syscalls
was injected into `libtestcmd.so`, a marker file appeared, and the library was
restored to stock and md5-verified. `libIMDB.so` — loaded by `im.elf`, the
process owning 417 message queues — is the interesting target and has
deliberately *not* been touched, because a malformed replacement costs the
service shell with **no recovery mechanism** (no boot up = no USB = dead).

**A live view of the RTOS.** `/proc/tmonitor` returns a ~50 ms window of the
real-time scheduler: 60+ tasks, wait channels with **kernel addresses**, a
`MODULE::task` map from the firmware's modules to their work, and an IRQ
hot-spot profile. It names `osal_rcv_msg_tmo` and `osal_wai_sem_tmo` — the RTOS
message-bus primitives — at addresses. `mask=0` in the kernel command line means
nothing is masked out; the facility had been recorded as idle and unused, which
was wrong.

**What the graphics path actually is.** Not OpenGL. `libObj.so` carries a
196-entry table of GL ES 2.0 / EGL entry-point *names* — including 8 `*DMP`
vendor extensions — and exports **none** of them; no `libGLESv2.so` or `libEGL.so`
exists, and nothing in 650 catalogued ELFs exports the GL API. The renderer is
DMP SUGILITE silicon behind `/dev/dmpgles2`. That driver's ioctl is a 17-command,
4-byte-scalar control surface in which exactly one command reaches the hardware,
and it is a fixed kick rather than a register write — the register programming is
kernel-internal. The drawing API is `libObj.so`'s 517 exported `GRM_*` symbols,
already resident in the imaging manager.

**The camera's command vocabulary.** The scenario plugins' message ids are
immediates in code, not data; sweeping `movw`/`movt` across all 35 recovered 96
distinct values, which `libSysDef.so`'s self-describing tables then name. The
object table joins exactly against `libObj.so`'s exports — 25 implemented, 20
declared-only, **zero orphans in either direction**.

**The UI resource formats.** The `.uxc` container round-trips and is navigable:
302/302 files, 12,082/12,082 index entries landing inside the file. The colour
palette was proved authoritative on hardware by a colour that appears nowhere in
Sony's palette. The view files provably contain **no** colour field — 2.5×
chance over 211,844 windows — so that line of attack is closed, cheaply.

**Why the application seems missing — and what is actually running.**
`BOOTMODE=NORM`, no forcing file, no kernel flag, yet no application is loaded.
The application core (`appFw.so`, `gui.so`, `libNVM.so`, `libInfraWebApi.so`) is
named by the load manifest and simply is not on the filesystem.

But the *entry point* is what is missing, not the machinery. The load manifest
names 174 libraries `im.elf` may load; `/proc/<im.elf>/maps` shows **97** actually
resident, including `libObj.so`, `libMWF.so`, `libSysDef.so` and two of the seven
`viewUnified*` engines. And `im.elf` itself holds `/dev/dmpgles2` open with
`grm_gles` at refcount 2 — which is the mechanism behind the LCD still playing SD
media in service mode. The DMP 2D engine and the VDF OSD port therefore sit in a
live process that is not the application.

**Active Research: Full-sensor 3:2 Open Gate video recording pipeline.** The Sony ZV-E10 APS-C
sensor has a physical active imaging area of $6000 \times 4000$ (3:2). In stock
4K recording, the camera discards 624 vertical sensor lines (15.6%) to force a
16:9 aspect crop. Reverse engineering the BIONZ X RTOS (`av-cam.bin`), `libObj.so`,
and `libmpr.so` uncovered the video recording pipeline and sensor crop parameters.
*Status:* While the underlying mechanism and 138 patch sites are mapped out in
[`batch_patch_opengate.py`](batch_patch_opengate.py), **the patch is experimental and not working properly yet for reliable recording**. See [`docs/90-session/OPENGATE_PATCH_GUIDE.md`](docs/90-session/OPENGATE_PATCH_GUIDE.md)
and [`docs/90-session/OPENGATE_138_PATCH_SUITE.md`](docs/90-session/OPENGATE_138_PATCH_SUITE.md) for the technical analysis.

**USB webcam research:** custom synthetic VGA delivery is hardware-verified with the 2.4p transport. The [live sensor-source investigation](docs/uvc_vga_v30_candidate_20261027.md) now uses Sony's resize APIs and explicit buffer ownership. Its 3.0 candidate has passed installation/reboot checks; live output and pixel packing are still unverified.

## Start here

| | |
|---|---|
| **[`docs/agents/STATE.md`](docs/agents/STATE.md)** | **one page, self-contained** — state of play, blockers, the traps that bite. Read this first. |
| **[`docs/uvc_yuy2_patch_v24p.md`](docs/uvc_yuy2_patch_v24p.md)** | **Verified VGA USB colour-bars result** — FFmpeg captures, same-session reopen and OBS |
| [`docs/90-session/4K_12BIT_NEXT_PUSH.md`](docs/90-session/4K_12BIT_NEXT_PUSH.md) | Next major investigation: genuine 4K / 12-bit source and precision-preserving pipeline |
| [`batch_patch_magenta.py`](batch_patch_magenta.py) | Earlier hardware-verified LCD framing-lines patcher |
| [`docs/agents/REFERENCE.md`](docs/agents/REFERENCE.md) | **one page, self-contained** — the measured facts: hashes, offsets, id tables, format layouts |
| [`docs/90-session/OPENGATE_PATCH_GUIDE.md`](docs/90-session/OPENGATE_PATCH_GUIDE.md) | **Open Gate 3:2 pipeline research (WIP)** — 138-patch matrix analysis |
| [`docs/90-session/OPENGATE_138_PATCH_SUITE.md`](docs/90-session/OPENGATE_138_PATCH_SUITE.md) | **Open Gate 3:2 RE synthesis** — BIONZ X SDF pin disconnect and technical notes |
| [`docs/90-session/UVC_WEBCAM_HIJACK_GUIDE.md`](docs/90-session/UVC_WEBCAM_HIJACK_GUIDE.md) | **UVC USB webcam research (WIP)** — gadget architecture, descriptor tables |
| [`docs/README.md`](docs/README.md) | the granular per-subject reference, `01`–`09` |
| [`avcam_re/HARDWARE_OVERVIEW.md`](avcam_re/HARDWARE_OVERVIEW.md) | `av-cam.bin` internals: topology, register model, ISP/codec pipeline |
| [`research/README.md`](research/README.md) | 322 analysis scripts, indexed |

Every load-bearing claim is reproducible by a tracked script:

```powershell
& ".venv\Scripts\python.exe" -B -m pytest -q
& ".venv\Scripts\python.exe" -B research\firmware\check_docs.py
```

`docs/` holds the granular reference, `docs/agents/` the consolidated views, and
`docs/90-session/` a quarantine of dated session logs that nothing should cite as
fact.

## Open Gate 3:2 Video Recording (Experimental Research)

> [!WARNING]
> **Work In Progress — Not Working Properly:** While the sensor cropping structures, ISP parameters, and memory patch addresses have been reverse engineered, **this patch does not yet produce working video recordings**. Scripts are provided for ongoing community research and debugging.

The ZV-E10's APS-C CMOS sensor captures $6000 \times 4000$ pixels (3:2). In stock 4K recording, the camera discards 624 vertical sensor lines (15.6%) for a 16:9 crop. The research prototype tests volatile memory patching:

```powershell
# Research / debugging execution (RAM-only, zero flash writes):
& ".venv\Scripts\python.exe" batch_patch_opengate.py --width 3240
```

- **Detailed Technical Reference:** See [`docs/90-session/OPENGATE_PATCH_GUIDE.md`](docs/90-session/OPENGATE_PATCH_GUIDE.md).

## High-Speed UVC USB Webcam (Experimental Research)

> [!WARNING]
> **Live sensor capture remains experimental.** Synthetic VGA colour bars are verified in FFmpeg and OBS using the 2.4p transport. The 3.0 native VGA resize candidate is installed but awaits a live test. The older descriptor/MJPEG experiments below are separate research tools.

The research patcher inspects and tests custom UVC resolutions and descriptor modifications:

```powershell
# Dry-run inspection (no camera required):
python batch_patch_uvc.py --mode opengate --dry-run

# Revert camera to factory stock:
python batch_patch_uvc.py --mode stock --overwrite
```

- **Detailed Technical Reference:** See [`docs/90-session/UVC_WEBCAM_HIJACK_GUIDE.md`](docs/90-session/UVC_WEBCAM_HIJACK_GUIDE.md).

## Talking to the camera

Service mode needs the camera in mass-storage mode (PID `0x0d95`), then gives a
root shell over the USB serial console (PID `0x0336`). On Windows the camera
must be bound with Zadig to `libusb-win32`. Full instructions are in upstream's
own README — see [Upstream tool](#upstream-tool) — because duplicating them here
would only guarantee drift.

```powershell
# one command per argument; a run is accepted only when a prompt returns
& ".venv\Scripts\python.exe" research\device\zve10_retry.py "ls -l /usr/lib"
```

**Read `zve10_shell.log`, never the console.** The wrapper truncates the console
at 25 lines; four claims in this project's history were wrong purely from
trusting it.

Camera-side essentials that cost real time: it is BusyBox 1.34.1 ash built
without `base64`, `stty`, `md5sum`, `tr`, `head` or `which` — use
`busybox <applet>`. `dd` has **no `conv=notrunc`**, so any `dd of=<live file>`
truncates the target; use `cp`. Commands are bounded at ~1,022 characters and a
longer one is accepted and **silently discarded**.

## Firmware analysis — `retool`

Static analysis of the dumped images is a self-contained
[rizin](https://rizin.re)-based pipeline with no JDK/Ghidra dependency:

```powershell
retool.cmd doctor            # verify engine + targets
retool.cmd analyze avcam     # build cached analysis project
retool.cmd export avcam      # functions / calls / xrefs / strings / tables
```

Addresses are **file offsets (base 0x0)**; the runtime load address
(`+0x635c6000` for `av-cam.bin`) is printed alongside. Renamed functions live in
`re_symbols/*.json` with provenance back to the notes that justify them. See
[RETOOL.md](RETOOL.md). This replaced the retired Ghidra setup
(`avcam_re/_retired_ghidra/`).

## No Sony binaries are committed here

Firmware images, partition dumps, UI resources and camera libraries are all
git-ignored and were never committed. What is committed is names, offsets,
table geometry and analysis — the actual output of the work.

Patched objects are reproducible from a tracked script plus a file you pull off
your own camera; the recipes and hashes are in
[`research/firmware/PATCHED_OBJECTS.md`](research/firmware/PATCHED_OBJECTS.md).
The boundary, including the one upstream exception, is in
[`docs/09-provenance.md`](docs/09-provenance.md).

## Credits and AI disclosure

Two different things are credited in **[`CREDITS.md`](CREDITS.md)**, and they are
deliberately kept apart:

- **Code in this repository** — `pmca/`, `updatershell/`, the entry points and the
  CI configs are upstream's, from **[ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE)**
  (MIT, © 2015 ma1co) and its four other contributors. They authored 260 of the
  368 commits here.
- **Prior art consulted, not vendored** — nothing of
  **[Erik Smit's nex-hack](https://github.com/erik-smit/nex-hack)** or
  `steelcnn/nex-hack` is in this tree. They are credited because their public
  work was read and cited while working out the Sony firmware unpacking and
  `av-cam` structure, not because they contributed anything to this repository.

**The reverse engineering was carried out with AI coding agents** — Hermes Agent,
OpenCode, Antigravity and Codex. That file also sets out what the results do and
do not rest on: which are machine-checked, which are hardware-verified, which are
only inferred — and the four confident-wrong-answer bugs this project's own
history produced, each with the control or null model that caught it. **Please
read it before relying on anything here.**

## Risk

Several routes documented here are one-way doors. Replacing `libIMDB.so`, or
corrupting `udtrbody.bin`, means the system never boots: **there is NO way back**
(no boot up = no USB = dead / hard brick). Modern BIONZ X cameras have no autonomous
SD card unbrick bootloader. Remounting `/usr` rw on an ext2 filesystem with no journal
can leave it permanently unbootable. The [modification notes](docs/07-modification.md)
mark which is which.

Do this only to a camera you are willing to permanently brick.

## Upstream tool

`pmca/`, `updatershell/`, `pmca-console.py` and `pmca-gui.py` originate upstream.
Local USB work includes the libusb0 locality fix, Windows WinUSB support and
device-opening fixes. See [CREDITS.md](CREDITS.md) for attribution.

For installation and usage of that tool, use
[upstream's README](https://github.com/ma1co/Sony-PMCA-RE#readme) rather than a
copy here.

## Licence

MIT, inherited from upstream, with the upstream notice retained in
`LICENSE.txt`. See [`CREDITS.md`](CREDITS.md).

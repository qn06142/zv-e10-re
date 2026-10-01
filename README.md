# Sony ZV-E10 reverse engineering

Reverse engineering of the **Sony ZV-E10**, firmware 2.02/2.03, kernel
`3.0.27_nl-rt106+`. Reached through the camera's service-mode USB shell, which
yields a root BusyBox prompt without breaking a finger off.

This repository is a fork of **[ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE)**
(MIT, © 2015 ma1co), which provides the USB plumbing. Everything under `docs/`,
`avcam_re/`, `retool/` and `research/` is ZV-E10-specific work added on top.

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
service shell and the only way back is an SD card.

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

## Start here

| | |
|---|---|
| **[`docs/agents/STATE.md`](docs/agents/STATE.md)** | **one page, self-contained** — state of play, blockers, the traps that bite. Read this first. |
| [`docs/agents/REFERENCE.md`](docs/agents/REFERENCE.md) | **one page, self-contained** — the measured facts: hashes, offsets, id tables, format layouts |
| [`docs/README.md`](docs/README.md) | the granular per-subject reference, `01`–`09` |
| [`avcam_re/HARDWARE_OVERVIEW.md`](avcam_re/HARDWARE_OVERVIEW.md) | `av-cam.bin` internals: topology, register model, ISP/codec pipeline |
| [`research/README.md`](research/README.md) | 322 analysis scripts, indexed |

Every load-bearing claim is reproducible by a tracked script:

```powershell
& ".venv\Scripts\python.exe" -B -m pytest -q      # 139 pass, 8 skip (need artefacts only the card/camera can supply)
& ".venv\Scripts\python.exe" -B research\firmware\check_docs.py
```

`docs/` holds the granular reference, `docs/agents/` the consolidated views, and
`docs/90-session/` a quarantine of dated session logs that nothing should cite as
fact.

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
corrupting `udtrbody.bin`, means the service side never boots and the camera is
recovered by SD card rather than by USB. Remounting `/usr` rw on an ext2
filesystem with no journal can leave it unbootable. The
[modification notes](docs/07-modification.md) mark which is which.

Do this to a camera you are willing to brick.

## Upstream tool

`pmca/`, `updatershell/`, `pmca-console.py` and `pmca-gui.py` are upstream's, and
**exactly one upstream file has been modified** — `pmca/usb/driver/generic/libusb.py`,
a locality fix so a Zadig-bound camera is claimed through libusb0 rather than
enumerated-then-failing on libusb-1.0. See [CREDITS.md](CREDITS.md).

For installation and usage of that tool, use
[upstream's README](https://github.com/ma1co/Sony-PMCA-RE#readme) rather than a
copy here.

## Licence

MIT, inherited from upstream, with the upstream notice retained in
`LICENSE.txt`. See [`CREDITS.md`](CREDITS.md).

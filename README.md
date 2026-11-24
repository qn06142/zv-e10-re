# Sony ZV-E10 research

> **Project status (24 November 2026): On hiatus.**  
> Active hardware experiments and development are paused for now. The codebase, emulator, and research notes are left at a clean checkpoint below — see [current status](docs/CURRENT_STATUS.md) and the [Bayer handoff](research/device/zve10_ram_boot/BAYER_HANDOFF.md) for where work stopped.

Reverse engineering, bare-metal OS runtime (`ZVOS`), standalone QEMU emulation, and tooling for the Sony ZV-E10 (firmware 2.02/2.03). The project goal is native Bayer RAW acquisition and USB delivery.

Start with the [camera overview](docs/CAMERA_OVERVIEW.md), [current status](docs/CURRENT_STATUS.md), [hardware handoff](docs/hardware/HANDOFF.md), and [access and tools](docs/ACCESS_AND_TOOLS.md).

## Repository layout

| Directory | Contents |
| --- | --- |
| [docs](docs/README.md) | System overview, topic documentation and dated research history |
| [research](research/README.md) | Camera diagnostics, firmware analysis, experimental recipes and evidence |
| [retool](docs/tools/RETOOL.md) | Binary-analysis CLI, configured by reconf.toml |
| scripts | Patch/build orchestration, host tools and staging kits |
| tests | Offline verification suites |
| pmca and updatershell | Upstream PMCA transport, shell and application components |

Camera analysis, symbol records, capture metadata and verification utilities are grouped under research. Firmware dumps, frame payloads, generated output, scratch and vendor checkouts live under the ignored .local directory. See the [layout guide](docs/tools/REPOSITORY_LAYOUT.md) for the full map.

The root batch_patch scripts and retool launchers are existing command entry points. Source and local inputs follow the [provenance rules](docs/reference/09-provenance.md).

## Verified checkpoint

- **Bare-metal ZVOS runtime (`research/device/zve10_ram_boot/`):** GUI-triggered takeover (`boot.ko` v3 + `crt0.S` + `zvrt_runtime.c`), self-owned 1 GiB DDR0 MMU takeover, platform quiesce, tear-free uncached 640×480 RGBA4444 double-buffered LCD scanout, animated fire, 5,258-frame 24 fps Bad Apple!! playback, and interactive button shell ([os_shell.c](research/device/zve10_ram_boot/os_shell.c), [ZVOS_SPEC.md](docs/hardware/ZVOS_SPEC.md)) verified on hardware/Unicorn.
- **Bayer RAW & UVC tracks:** Synthetic VGA colour bars (`2.4p`) were captured over the custom USB transport; bare-metal IMX284 + DFE RAW capture (`bayer_capture.h`, `senser_bayer_runner.c`) is in active bring-up ([BAYER_HANDOFF.md](research/device/zve10_ram_boot/BAYER_HANDOFF.md)).
- **QEMU 11.1.2 (`-M zve10`):** Standalone ARMv7 emulator boots stock `vmlinux.bin` + `initrd.img` to BusyBox `ash`, models OSD0/ADC/GPIO, and displays the adapted Sony menu (`emulator/`, [QEMU_EMULATOR.md](docs/hardware/QEMU_EMULATOR.md)).

See the [status page](docs/CURRENT_STATUS.md) and [hardware handoff](docs/hardware/HANDOFF.md) for evidence, hashes, and hardware vs. offline boundaries.

## Development

Run commands from the repository root.

```powershell
python -m pip install -r requirements.txt
python -m pytest
python -B research/firmware/check_docs.py
.\retool.cmd doctor
```

Some tests and analysis tools require locally dumped firmware or optional analysis dependencies. See [research setup](research/README.md) and [retool usage](docs/tools/RETOOL.md).

This repository builds on [ma1co/Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE). See [credits](CREDITS.md), [license](LICENSE.txt) and [provenance](docs/reference/09-provenance.md). Earlier research claims and the former long README are preserved in the [archive](docs/archive/README.md).

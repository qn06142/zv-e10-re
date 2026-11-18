# Sony ZV-E10 research

Reverse engineering and tooling for the Sony ZV-E10, firmware 2.02/2.03. The project goal is native Bayer RAW over USB. Camera experiments are paused while the system model and evidence are organized.

Start with the [camera overview](docs/CAMERA_OVERVIEW.md), then [current status](docs/CURRENT_STATUS.md) and [access and tools](docs/ACCESS_AND_TOOLS.md).

## Repository layout

| Directory | Contents |
| --- | --- |
| [docs](docs/README.md) | System overview, topic documentation and dated research history |
| [research](research/README.md) | Camera diagnostics, firmware analysis, experimental recipes and evidence |
| [retool](docs/tools/RETOOL.md) | Binary-analysis CLI, configured by reconf.toml |
| [avcam_re](avcam_re/HARDWARE_OVERVIEW.md) | Recovered camera-firmware structure |
| re_symbols | Symbol records and provenance |
| scripts | Patch/build orchestration and device-operation scripts |
| tests | Offline verification suites |
| verify | Capture and validation utilities |
| pmca and updatershell | Upstream PMCA transport, shell and application components |

The root batch_patch scripts and retool launchers are existing command entry points. Local dumps, generated outputs, tool downloads and environments are covered by the [provenance rules](docs/reference/09-provenance.md) and .gitignore.

## Verified checkpoint

Synthetic VGA colour bars were captured through the custom USB transport. The latest recorded permanent UVC installation is the 16 November colour-bars build. Native Bayer acquisition and sustained SuperSpeed delivery remain open. The [status page](docs/CURRENT_STATUS.md) links the evidence and distinguishes hardware observations from offline candidates.

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

# Research

Camera-facing tools, firmware analysis, experimental recipes and evidence live here. Start with the [camera overview](../docs/CAMERA_OVERVIEW.md) and [current status](../docs/CURRENT_STATUS.md).

| Directory | Purpose |
| --- | --- |
| [device](device/README.md) | SSH/USB inspection, capture and diagnostic utilities |
| [avcam](avcam/HARDWARE_OVERVIEW.md) | Recovered camera-firmware structure |
| symbols | Recovered symbol database |
| verify | Offline helper and capture verification |
| [captures](captures/README.md) | Curated capture metadata |
| [firmware](firmware/README.md) | Firmware analysis, UVC revision recipes, RAW-source work and dated evidence |
| common | Helpers shared by device and analysis scripts |
| disasm, scan, crypt, diag | Disassembly, byte/string analysis and format diagnostics |
| isp, lens | Imaging and lens investigations |
| updater, opengate | Update and recording-format investigations |
| emulator | Emulation helpers |
| log_decoder | Log analysis |

Run scripts from the repository root unless their README specifies otherwise. Many historical scripts depend on local firmware dumps or machine-specific paths. Check arguments and source before selecting an experiment.

Use [retool](../docs/tools/RETOOL.md) for the binary-analysis CLI and the [access guide](../docs/ACCESS_AND_TOOLS.md) for physical-camera diagnostics. Captured Sony binaries belong in the ignored dumps directory. Authored source, identities, measured facts and reproducible recipes follow the [provenance policy](../docs/reference/09-provenance.md).

The previous exhaustive filename list and portability counts are preserved in the [historical research index](../docs/archive/RESEARCH_INDEX_20261118.md).

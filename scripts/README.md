# Build and deployment scripts

This directory contains patch generation, build orchestration, deployment and inspection scripts. Run them from the repository root unless the script documents a different working directory.

| Script family | Role |
| --- | --- |
| build_* and gen_* | Build or generate experiment artifacts |
| patch_* | Generate, inspect or apply binary changes |
| deploy_* | Transfer a prepared candidate to the camera |
| audit_*, inspect_*, compare_* and diff_* | Inspect local inputs or camera state |
| restore_* and revert_* | Recover an earlier experiment state |

The root batch_patch_magenta.py, batch_patch_opengate.py and batch_patch_uvc.py remain command entry points used by existing callers. Consult their matching report and [current status](../docs/CURRENT_STATUS.md) before selecting a deployment.

Earlier text command sequences are in the [command archive](../docs/archive/commands/README.md). Captured evidence belongs with its dated research report. Firmware and generated binaries use the local paths described by the [provenance policy](../docs/reference/09-provenance.md).

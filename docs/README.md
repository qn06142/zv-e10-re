# ZV-E10 documentation

The repository-wide starting point is the [camera system overview](CAMERA_OVERVIEW.md). It maps boot, Linux, LiRo imaging, application/UI, lens control, recording, USB, Wi-Fi, storage and recovery, with evidence and open questions for each.

| Need | Start here |
| --- | --- |
| Map physical hardware, registers and peripheral protocols | [Hardware atlas](hardware/README.md) |
| Understand the whole camera | [Camera overview](CAMERA_OVERVIEW.md) |
| Find the latest evidenced state and project direction | [Current status](CURRENT_STATUS.md) |
| Connect and reproduce diagnostics | [Access and tools](ACCESS_AND_TOOLS.md) |
| Inspect the November live captures and installation records | [Evidence index](../research/firmware/evidence/zve10-20261117/README.md) |
| Check the supplied UVC/Bayer hook claims | [Claim review](../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md) |
| Build the small register debugger | [Diagnostic source](../research/device/zve10_diagnostics/README.md) |
| Browse subsystem docs | [References](reference/README.md), [USB](usb/README.md), [imaging](imaging/README.md), [UI](ui/README.md) and [host tools](tools/README.md) |
| Follow historical work | [Archive](archive/README.md) |

## Current research

The goal is native Bayer RAW over USB. Current work is a hardware atlas covering register semantics, mode-specific values, clocks/reset, sensor/DFE/DMA and accessory protocols before further display write trials. The resident runtime displayed full-screen color bars through the inherited LCD path. The latest buffer reuse experiment stopped at its descriptor guard. The latest recorded permanent UVC checkpoint is the November colour-bars installation. The later SuperSpeed rebuild is an offline candidate. Wi-Fi SSH enabled normal-shooting and recording diagnostics. The exact live Bayer output buffer and completion/lifetime contract remain unresolved. See [current status](CURRENT_STATUS.md) for dates, evidence and the next research boundaries.

## Detailed topic documents

| Document | Coverage |
| --- | --- |
| [01 hardware](reference/01-hardware.md) | Platform, firmware inventory, dumps and host/toolchain observations |
| [02 service shell](reference/02-service-shell.md) | Mounts, persistence, boot, application loading and graphics investigation |
| [03 binaries](reference/03-binaries.md) | ELF inventory, plugins, application objects, LiRo and display structure |
| [04 messaging](reference/04-messaging.md) | OSAL/UIPC, endpoints, command IDs, application manifest and scenarios |
| [05 formats](reference/05-formats.md) | UXC, view files, global.xdb, strings and palettes |
| [06 method](reference/06-method.md) | Decoding pitfalls and verification methods |
| [07 modification](reference/07-modification.md) | Writable partitions, persistent changes, update routes and file transport |
| [08 interfaces](reference/08-camera-interfaces.md) | USB/service modes, host tunnels, lens bus and command tools |
| [09 provenance](reference/09-provenance.md) | Authored research, upstream work and Sony data boundaries |

The [agent reference](archive/agents/REFERENCE.md) and [agent state archive](archive/agents/STATE.md) retain detailed earlier findings. The opening notice on each points to the consolidated pages. The dated entries under 90-session retain session history and superseded claims. Cite their underlying capture or audit when promoting a claim to current status.

## Image and USB research

| Subject | Evidence and scope |
| --- | --- |
| VGA synthetic colour bars | [2.4p hardware report](usb/uvc_yuy2_patch_v24p.md) and [source recipe](../research/firmware/yuy2_transport_v24p/README.md) |
| Live YC acquisition | [YC synthesis](usb/uvc_yc_subsystem_and_codex_findings.md), [backend recovery/corrections](usb/uvc_sony_backend_recovery.md) and [current claim review](../research/firmware/evidence/zve10-20261117/CLAIM_REVIEW.md) |
| USB ownership and completion | [Lifetime audit](../research/firmware/raw_frame_source/verified_yc/evidence/usb-lifetime-20261029/REPORT.md) |
| Historical 1080p candidate | [v43 recipe](../research/firmware/yuy2_transport_v43_usb3_hd/README.md). Use the later [candidate manifest](../research/firmware/evidence/zve10-20261117/transport/manifest.json) and current status for its hardware scope. |
| Native RAW receiver | [Receiver audit](../research/firmware/raw_frame_source/verified_bayer/evidence/native-dump-20261031/REPORT.md), [later gate correction](../research/firmware/raw_frame_source/verified_bayer/evidence/raw-pipeline-audit-20261031/REPORT.md) and [receiver component](../research/firmware/raw_frame_source/verified_bayer/raw_receiver_v01/README.md) |
| Historical deployment and diagnostic work | [USB diagnostic handoff](usb/uvc_yuy2_diagnostics_handoff.md), [encoder workspace fix](usb/uvc_encoder_workspace_fix.md) and [session archive](archive/sessions/HANDOFF.md) |
| Research implementation | [Research index](../research/README.md) and [patched-object recipes](../research/firmware/PATCHED_OBJECTS.md) |

## Adding evidence

Record the capture date, camera mode, boot/process identity where relevant, exact source/build identity, command, raw result and conclusion with its limits. Place shared captures under a dated evidence directory and link to them with repository-relative paths. Update the relevant topic and current status when the evidence changes.

Firmware images, patched Sony binaries, UI resources and private keys stay outside tracked documentation. Keep their identity, reproducible recipe and local provenance under the existing [provenance policy](reference/09-provenance.md).

Use the evidence labels defined in the camera overview. Hardware observation, offline instruction tests and candidate code establish different facts. Keep contradicted claims with a correction and a link to the replacement evidence.

## Checking the documentation

Run from the repo root.

```powershell
& ".venv/Scripts/python.exe" -B research/firmware/check_docs.py
```

The checker reports the set of MD5 identifiers, local links and heading anchors. When importing evidence, verify its manifest byte counts and SHA-256 values as well.

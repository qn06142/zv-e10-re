# UI research

- [Resident LCD bring-up](../../research/device/zve10_ram_boot/DISPLAY.md) progressed from a heartbeat with a black screen to hardware-confirmed full-screen RGBA4444 bars. The latest reuse experiment stopped at its descriptor guard. [Hardware handoff](../hardware/HANDOFF.md)

- [Returning GUI RAM loader](../../research/ui/version_gui_ram_loader/README.md) displayed HELLO on-camera; the current [privileged RAM handoff trial](../../research/device/zve10_ram_boot/README.md) produced an owner-reported restart. The current resident runtime v02 produced an owner-confirmed blinking heartbeat; post-trial Linux and file readbacks passed.

- [Direction-only Version sequence](../../research/ui/version_gui_sequence/v02/README.md) is installed and owner-confirmed to reach ARMED OK; it provides the GUI entry point for future loader work.
- [Version-screen button mapper](../../research/ui/version_gui_keys/README.md) records the on-camera directional button mapping.
- [Version GUI marker probe](../../research/ui/version_gui_probe/README.md) records the offline screen callback audit and visual probe for a future loader trigger.
- [Magenta framing lines](magenta_framing_lines.md) records the palette modification.
- [Sidecar GUI proposal](SIDECAR_GUI_PROPOSAL.md) describes an earlier host-side UI idea.
- [Resource formats](../reference/05-formats.md) covers UXC, views, global.xdb, strings and palettes.
- [Binary inventory](../reference/03-binaries.md) covers application objects and graphics interfaces.

The [camera overview](../CAMERA_OVERVIEW.md) places UI rendering alongside the imaging pipeline.

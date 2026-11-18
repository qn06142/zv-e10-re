# Radical GUI Rewrite: Sidecar UI Daemon Proposal

Based on our exploration, the stock Sony GUI (driven by `im.elf` -> `viewUnified*.so` -> `CautionConfig.so` -> Sugilite GPU) is deeply nested, heavily state-dependent, and prone to crashes if modified improperly via reverse engineering.

To achieve a modern, customizable camera UI (similar to Magic Lantern or professional cinema cameras), we propose **Architecture Pattern 1: Headless Sidecar Overlay**.

## The Architecture
1. **Unmodified Core Engine:** `im.elf` continues to manage autofocus algorithms, face tracking, sensor readout, and encoder pipelines. We do not attempt to replace the core logic.
2. **Sidecar Process (`zve10_gui.elf`):** A lightweight background daemon written in C/C++ running concurrently with `im.elf`.
3. **UI Framework:** Utilize a modern embedded framework like **LVGL** (Light and Versatile Graphics Library). LVGL is highly optimized, supports C, has a tiny memory footprint, and runs natively on Linux framebuffers.
4. **Input Interception:** The sidecar opens `/dev/input/event*` with `EVIOCGRAB` to temporarily "steal" input focus from `im.elf` when the custom UI is active.
5. **Framebuffer Rendering:** The sidecar maps `/dev/fb0` (or a hardware overlay plane if the Sugilite GPU exposes one) to render its UI.

## Activation Flow
- The sidecar listens for a long-press on a designated button (e.g., holding `Trash` or `C1` for 1.5 seconds).
- Upon detection, the sidecar grabs the input device (`EVIOCGRAB`), effectively freezing the stock UI's responsiveness to buttons.
- The sidecar clears or overwrites the framebuffer with its own UI layout.
- The user navigates the custom menu.
- When the user exits, the sidecar releases the input device (`EVIOCGRAB` un-grab) and triggers a UI redraw event in `im.elf` (e.g., by sending a benign key press like `Menu` or by clearing the screen), restoring stock behavior.

## Key Features Enabled by This Architecture
* **Real-time Anamorphic Desqueeze:** Since the sidecar has access to the raw framebuffer, it can read the Live View scanout buffer, apply a horizontal stretch (1.33x, 1.5x, 2.0x), and write it back to the screen.
* **Professional Video Tools:** Implement False Color, Waveform monitors, and Vectorscopes by analyzing the Live View buffer pixels in real-time.
* **Cinema Shutter Angle Display:** Calculate and display shutter angle (e.g., 180°) based on current framerate and shutter speed parameters fetched via `BackupManager`.
* **Zero Flash Writes:** The entire UI runs dynamically via `LD_PRELOAD` spawning the daemon or just launching it from SD card via auto-exec script.

## IPC (Inter-Process Communication)
The sidecar needs to communicate with `im.elf` to change camera settings.
- **Shared Memory / Sockets:** The `opengate_hook.so` (running inside `im.elf`) opens a Unix domain socket `/tmp/opengate.sock`.
- The sidecar sends JSON or binary commands (e.g., `{"cmd": "set_aspect", "val": 0}`) to the socket.
- `opengate_hook.so` receives the command and safely invokes internal functions like `_ZN13BackupManager11Backup_write...` or triggers `apply_dynamic_aspect()`.

This architecture completely bypasses the complexities of Sony's `.uxc` binary layouts and provides a vastly superior developer experience.

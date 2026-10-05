# Sony ZV-E10 Open Gate & Camera Firmware: Engineering Roadmap & Exploration Guide

This document outlines the current state, immediate action items, intermediate features, and radical architectural explorations (such as a full GUI rewrite) for the Sony ZV-E10 reverse-engineering initiative.

---

## 1. Executive Summary: Current Accomplishments

1. **4-Point In-Memory Open Gate Engine:**
   - **`libmpr.so` @ `0x5422e6`**: Whitelist bitmask expanded (`0x2b` $\to$ `0x2f`) to permit Aspect 2 (3:2) without error 5 rejection.
   - **`libObj.so` @ `0x978bea`**: 4K parameter compiler (`ConvertRecFormat`) outputs Aspect 2 (3:2) instead of hardcoded 1 (16:9).
   - **`libObj.so` @ `0x2d229c`**: UIPC encoder aspect configuration packet (`InfraMovieEncoderSeqSetAspect`) payload set to Aspect 2.
   - **`libObj.so` @ `0xeb0f26`**: Live View classification table entry 4 mapped to Case 1 (3240x2160 canvas).
2. **Volatile In-Memory Hooking (`LD_PRELOAD`):**
   - Implemented in `research/device/opengate_hook.c` and compiled to `bin/opengate/opengate.so`.
   - Modifies code segments via `mprotect` and cache flushing strictly in volatile RAM. Read-only flash partitions remain untouched.
3. **Hardware Emulation & Verification:**
   - RTOS Unicorn emulator (`research/emulator/avcam_emulator.py` and `simulate_opengate.py`) passes 100% of event dispatches (Event `0x8012`).
   - 151 passing automated tests in `tests/`.

---

## 2. Immediate TODO List for Jules

### [TODO-1] Implement Native Dynamic Menu Aspect Ratio Switching
- **Goal:** Allow the camera to switch between 3:2 Open Gate ($3240 \times 2160$) and stock 16:9 ($3840 \times 2160$) dynamically depending on the user's menu choice, instead of hardcoding 3:2.
- **Mechanism:**
  - Sony's menu system already includes a Still Aspect Ratio setting: `cmnViewSettingNodeRootStlImageAspectRatio` (3:2, 16:9, 4:3, 1:1), which can also be assigned to the `Fn` menu or Custom Buttons (`C1`).
  - The setting is saved in non-volatile backup memory via `BackupManager`:
    - Attribute ID: `0x1070012` (normal mode) / `0x10703b2` (MR mode).
    - Return values: `0` = 3:2, `1` = 16:9, `2` = 4:3, `3` = 1:1.
- **Implementation in `opengate_hook.c`:**
  - Hook `ConvertRecFormat` (`0x978bea`) with a small trampoline:
    ```c
    int aspect_choice = read_backup_attr(0x1070012);
    if (aspect_choice == 0) {
        *out_aspect = 2; // 3:2 Open Gate
        set_live_view_table(1); // 3240x2160 canvas
    } else {
        *out_aspect = 1; // Stock 16:9
        set_live_view_table(2); // 3840x2160 canvas
    }
    ```
  - Also dynamically update `0x2d229c` during encoder parameter preparation.

### [TODO-2] Runtime Hardware Hotkey / OSD Toggle
- **Goal:** Toggle Open Gate 3:2 $\leftrightarrow$ 16:9 on the fly with a physical button press (e.g. `C1` or `Trash` in video mode).
- **Mechanism:**
  - Hook key events either by intercepting `/dev/event*` input stream or by hooking `CKeyHandler` in `im.elf`.
  - When pressed in Movie mode, toggle `g_selected_aspect` and trigger a live OSD banner overlay (e.g. `[OPEN GATE 3:2]` vs `[4K 16:9]`).
  - Framebuffer OSD code is already prototyped in `research/device/osd_hook.c` and `osd_harness.py`.

### [TODO-3] Config File Enhancements (`/setting/opengate.conf`)
- **Goal:** Allow users to choose their preferred behavior without rebuilding binaries.
- **Config options to implement:**
  ```ini
  enable=1
  # Mode: 'auto' (follow camera menu aspect), '3:2' (force open gate), '16:9' (force stock)
  mode=auto
  # Hotkey toggle button: 'none', 'C1', 'trash'
  hotkey=C1
  # Show on-screen OSD notification on mode switch
  osd_banner=1
  ```

---

## 3. Mid-Term Exploration Ideas

### 1. Custom Framelines & Anamorphic Desqueeze Preview
- **The Problem:** 3:2 Open Gate is popular for anamorphic lenses (1.33x, 1.5x, 1.8x, 2.0x squeeze) and multi-aspect delivery (cropping to 2.39:1 cinemascope or 9:16 vertical video).
- **The Idea:**
  - Draw custom semi-transparent letterbox/pillarbox masks or guide lines directly onto the Live View framebuffer (`/dev/fb0`).
  - Implement a real-time horizontal desqueeze preview on the camera LCD/EVF so the anamorphic image appears geometrically normal while shooting.

### 2. Video Bitrate Unlocking (XAVC S 4K Overclock)
- **The Problem:** Sony limits XAVC S 4K to 100 Mbps (8-bit 4:2:0). Open Gate captures ~15% fewer horizontal pixels but higher vertical resolution; higher bitrates would improve motion fidelity.
- **Investigation:**
  - `libmpr.so` contains profile definition tables:
    `[pstRecMovieProfile] nBitrate = ...`
  - Test patching the profile table to request 150 Mbps or 200 Mbps from the hardware encoder.
  - Verify if SD card write buffers and thermal envelopes remain stable.

### 3. Native 4:3 Full-Sensor Video Mode
- **The Idea:**
  - Sensor dimensions are $6000 \times 4000$ (3:2).
  - A 4:3 crop ($5333 \times 4000$, recorded at $2880 \times 2160$ or $3240 \times 2430$) is the industry gold standard for 2.0x anamorphic lenses.
  - Explore whether `UtilStillSize::CnvMovieAspect(2)` (4:3) can be activated in the video encoder pipeline.

---

## 4. Radical Long-Term Exploration: Rewriting the GUI Subsystem Entirely

### A. How the Current Sony GUI Works
- **Application Structure:**
  - `im.elf` is the central user-space binary (~23 KB). It initializes `MWF` (Media Workflow Framework) and `AVBIZ`.
  - The UI logic lives in `viewUnified*.so` and `CautionConfig.so`.
  - The rendering engine is `ux::wgtsys::Widget` coupled to the Sugilite GPU / 2D blitter driver (`/dev/sugilite`, `grm_gles.ko`, `grm_ma.ko`), rendering into Linux framebuffer `/dev/fb0` (and `/dev/fb1`).
- **Pain Points of the Sony GUI:**
  - Complex, deeply nested menu trees.
  - Binary `.uxc` layout definitions that crash if modified incorrectly.
  - Unresponsive touch interactions and arbitrary feature locks across shooting modes.

### B. Architecture Pattern 1: The "Magic Lantern" Headless Sidecar Overlay (Recommended)
Instead of replacing `im.elf` (which handles autofocus algorithms, face/eye tracking, optical stabilization, auto-exposure, and lens communication), run a **sidecar UI daemon**:
- **Implementation:**
  - A lightweight C/C++ background process running alongside `im.elf` (e.g. `zve10_gui.elf`).
  - Uses a modern embedded UI library like **LVGL** (Light and Versatile Graphics Library) or **DirectFB / NanoVG**.
  - Directly opens `/dev/fb0` (or renders onto a hardware overlay plane).
  - Listens to input events via `/dev/input/event*`.
  - Communicates with `opengate.so` and `im.elf` via shared memory / Unix domain sockets.
- **User Experience:**
  - Long-pressing a designated button (e.g., holding `Trash` or `Fn` for 1.5 seconds) pauses the stock Sony OSD and displays the modern **Custom Hacker Menu**.
  - Features exposed:
    - Open Gate Aspect Selector (16:9, 3:2, 4:3, 1:1, 17:9).
    - Anamorphic Desqueeze (1.33x, 1.5x, 2.0x).
    - Custom Bitrate Slider (100–200 Mbps).
    - Video Assist Tools: False Color, Waveform, Vectorscope, Peaking, Zebra with custom IRE thresholds.
    - Shutter Angle display (180° rule) instead of reciprocal shutter speed fractions.

### C. Architecture Pattern 2: Deep Hooking & Hijacking `viewUnified` Widgets
- Hook `Widget::paint()` or `CmnViewSettingNode::invoke()` via `LD_PRELOAD`.
- Whenever a stock menu page is requested, intercept the draw callback and substitute a custom widget hierarchy.
- **Advantage:** Preserves stock hardware menu navigation.
- **Drawback:** Tight coupling to Sony's internal C++ ABI, which varies across firmware versions.

### D. Architecture Pattern 3: Full Custom Camera Operating System (Extreme Research)
- `im.elf` is merely a launcher. The real camera engine is exposed through:
  - `libObj.so` (high-level camera orchestration)
  - `libmpr.so` (movie pipeline & recording)
  - `libavcam` / `av-cam.bin` (BIONZ X RTOS coprocessor)
- In theory, an open-source camera application could be written in Rust or C++ that links directly against these shared libraries, completely bypassing Sony's legacy UI code and providing an interface as clean and responsive as modern cinema cameras.

---

## 5. Verification & Testing Reference

When developing on this branch, run the automated test suite to ensure no regressions:
```bash
# Run all tests
pytest -v

# Run Open Gate pipeline specific verification
pytest tests/test_opengate_pipeline.py -v

# Run BIONZ X Unicorn emulation simulation
pytest tests/test_simulate_opengate.py -v
```

All binaries can be rebuilt with:
```bash
python scripts/build_opengate.py
```

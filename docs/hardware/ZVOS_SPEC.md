# ZV-E10 Bare-Metal OS Specification (`ZVOS v0.1`)

This specification defines the architecture, memory map, boot ABI, and mode-switching contract for our bare-metal C OS on the Sony ZV-E10 (`CXD900x0`, ARMv7 Cortex-A5).

Items marked **[Verified]** are implemented and hardware-tested; items marked **[Planned]** are the next OS layers to build.

---

## 1. Design Principles

1. **Minimal custom core, borrowed generic libraries:** Keep the hardware-specific core small (~500 lines of C + startup assembly) and borrow single-purpose, zero-OS C libraries (**ChaN's `FatFs`** for SD FAT32/exFAT, optional **FreeRTOS** ARMv7-A port when 4K capture + SD write concurrency is needed, optional **TinyUSB** for USB streaming).
2. **Clean Linux exit:** `boot.ko` flushes and remounts RW filesystems read-only before stopping CPUs 1–3 and disabling IRQs/FIQs.
3. **Deterministic hardware ownership:** `crt0.S` quiesces non-display IRQs/timers/DMA and installs a self-owned 16 KiB ARMv7 L1 MMU table + `VBAR` vector table before entering C.
4. **Clean mode isolation:** Modes (Bad Apple, Fire, 4K Bayer RAW Recorder, Diagnostics) implement a single `os_mode` lifecycle (`enter` / `tick` / `exit`) with automatic scratch-memory reclamation on exit.

---

## 2. Boot & Loader ABI (`boot.ko` → `crt0.S`)

- **Trigger [Verified]:** `launcher.c` loads `/log/zve10-ram-boot/boot.ko` into `READY` and writes `GO` to its sysfs command parameter.
- **Shutdown sequence [Verified]:** `boot_worker()` runs `sys_sync()` → `do_emergency_remount(NULL)` → `sys_sync()` → `kernel_restart_prepare(NULL)` → `machine_shutdown()`, disables IRQ/FIQ on CPU0, refreshes the 500 ms watchdog, and enters `os_runtime.S` → `rtos.bin`.
- **Image format [Verified]:** 32-byte `ZVRT` header + CRC32-checked payload up to **1 MiB** (`ZVRT_MAX_IMAGE_BYTES = 1024 * 1024`).
- **Optional clip staging [Verified]:** `/log/zve10-ram-boot/clip.bin` up to **16 MiB** (`ZVRT_CLIP_MAX_BYTES`), staged via `vmalloc` and passed in the 48-byte `zvrt_handoff` struct.
- **Arena allocation:** Currently `ZVRT_ARENA_ORDER = 4` (64 KiB) **[Verified]**; **[Planned]** trim to `ZVRT_ARENA_ORDER = 2` (16 KiB L1 table only, copying `zvrt_handoff` into `.bss`/`.data`) to avoid `order:4` buddy allocation failures after extended Linux uptime.

---

## 3. Memory Map (`1 GiB DDR0` + `MMIO`)

`crt0.S` maps all `1 GiB` of `DDR0` (`PA 0x00000000..0x3fffffff`) both `1:1` (`0x000..0x3ff`) and at Sony's `+0x60000000` alias (`0x600..0x9ff`), plus Device MMIO (`0xf0000000..0xffffffff`, `0x00000406`). Linux `TTBR0` entries (`0x5f0..0x5ff` and `0xa00..0xeff`) are only borrowed during early relocation and wiped before `rtos_main()`.

| Virtual Range | Physical Range | Size | Cache Attr | Owner / Purpose | Status |
| --- | --- | --- | --- | --- | --- |
| `0x81000000..0x81ffffff` | `0x21000000..0x21ffffff` | 16 MiB | WBWA (`0x1140e`) | OS image (`.text/.rodata/.data/.bss`) + stacks (`sp` top `0x82000000`) | **[Verified]** |
| `0x84000000..0x84ffffff` | `0x24000000..0x24ffffff` | 16 MiB | WBWA (`0x1140e`) | Staged `clip.bin` (`ZVRT_CLIP_ADDR`) | **[Verified]** |
| `0x85000000..0x851fffff` | `0x25000000..0x251fffff` | 2 MiB | Non-Cacheable (`0x11402`) | `OSD0` uncached double-buffered framebuffers (`ZVRT_DISPLAY_PA`) | **[Verified]** |
| `0x85200000..0x85ffffff` | `0x25200000..0x25ffffff` | 14 MiB | Non-Cacheable (`0x11402`) | DMA descriptor & uncached I/O ringbuffer pool | **[Planned]** |
| `0x86000000..0x94ffffff` | `0x26000000..0x34ffffff` | 240 MiB | WBWA (`0x1140e`) | Cacheable mode scratch (`zvrt_mode_alloc`) | **[Implemented]** |
| `0x95000000..0x97ffffff` | `0x35000000..0x37ffffff` | 48 MiB | Normal NC (`0x11402`) | Dedicated still Bayer RAW DMA buffer | **[Implemented]** |
| `0xf0000000..0xffffffff` | `0xf0000000..0xffffffff` | 256 MiB | Shared Device (`0x406`) | SoC MMIO (`VPH`, `GIC`, `PL310`, `XDMAC`, `DMA330`, `GPIO`, `TIMER`) | **[Verified]** |

*(Note: `0x643eb19c` AIF mode table and `0x6441b27c` / `0x644194d8` OSD0 slots are read once during `zvrt_display_init()`.)*

---

## 4. Platform Quiesce & Fault Handling

- **`quiesce_platform` [Verified]:** Disables `GICC` (`0xf8000100`), `GICD` (`0xf8001000`, masks/clears 256 IRQs), local timer (`0xf8000608`), `XDMAC0/1` (`+0x18`), `DMA330` (`0xf0030020/2c` + `DMAKILL` on active threads/manager), and Output 1 (`0xf3440184`, `0xf3446000`).
- **Exception vectors (`VBAR`) [Verified]:** 8-entry ARMv7 vector table at `_vectors` reporting fault codes `1..10` via `zvrt_report_error(code)` on `LED_GPIO` (`0xf2910000`).
- **GIC IRQ dispatch [Planned]:** `zvrt_irq_register(uint32_t irq, zvrt_irq_fn fn, void *ctx)` + clean `GICC_IAR` / `GICC_EOIR` dispatch in `_vectors` IRQ stub.

---

## 5. Resident OS Services & Mode Interface

### 5.1 Display & UI Console
- **Scanout [Verified]:** `OSD0` at `640×480 RGBA4444` (`1,280`-byte pitch), 50 Hz VSYNC-locked double-buffering (`zvrt_display_init`, `zvrt_display_flip`, `zvrt_display_wait`).
- **Overlay font [Planned]:** Minimal 8×8 bitmap console (`zvrt_draw_text`) rendering mode menus, FPS/drop counters, and fault messages directly into the back buffer.

### 5.2 Input service

The shell calls `zvrt_poll_keys()` once per rendered frame. It returns the debounced `held`, `pressed` and `released` bitmasks. Two agreeing ADC conversions establish a ladder sample. Two successive matching polls commit a button transition. Invalid readings and conversion timeouts preserve the last held state and interrupt the debounce sequence.

Live `rtos_key_probe.c` hardware probing on the ZV-E10 established the actual direct SoC ADC/GPIO mappings (which differ from the older `Backup unit 0x01120000` / `B0` table):

| Control | ZVOS Key | Hardware Path & Observed Values |
| --- | --- | --- |
| OK (Center) | `ZVRT_KEY_OK` | `ADC1 B3` (`0xf2407020`, idle `0x3FF`), `0x000–0x05B` (`0x000`) |
| Left | `ZVRT_KEY_LEFT` | `ADC1 B3`, `0x05C–0x111` (`~0x0D4`) |
| Up | `ZVRT_KEY_UP` | `ADC1 B3`, `0x112–0x1B7` (`~0x15F`) |
| Down | `ZVRT_KEY_DOWN` | `ADC1 B3`, `0x1B8–0x257` (`~0x1FA`) |
| Right | `ZVRT_KEY_RIGHT` | `ADC1 B3`, `0x258–0x304` (`~0x2AD`) |
| C1 | `ZVRT_KEY_C1` | `ADC0 A4` (`0xf2406024`, idle `0x000`), `0x080–0x150` (`~0x0D9`) |
| Fn | `ZVRT_KEY_FN` | `ADC0 A4`, `0x180–0x238` (`~0x201`) |
| Menu | `ZVRT_KEY_MENU` | `ADC0 A4`, `0x239–0x2C0` (`~0x26D`) |
| Zoom Lever | — | `ADC0 A5` (`0xf2406028`, `0x3FF` vs `0x000`) |
| Mode (Top) | `ZVRT_KEY_MODE` | `GPIO G00` (`0xf2910010`), `0x00000400` |
| Rear Control Dial | `rear_delta` | `GPIO G00`, `0x00000004` + quadrature bits `0x1`/`0x2` (`g00 & 3U`) |
| Movie REC, Playback, Delete/Trash, Control Wheel ring | `ZVRT_KEY_REC`, `ZVRT_KEY_PLAY`, `ZVRT_KEY_DELETE`, `top_delta` | `FRONT(CA)` via UIPC `0x00280132` (not on `GPIO(0..23)` or `ADC0/1`) |

The runtime polls `ADC0 A4`, `ADC1 B3`, and `GPIO G00` (`0x400` for `ZVRT_KEY_MODE`, `g00 & 3U` for `rear_delta`) with a 50-tick (`>300` ADC cycles) conversion settle wait per `adc.c`. `os_shell.c` uses `MENU` (or `DELETE`) to exit Fire and Bad Apple!! modes. [Extracted name and source records](data/sony-key-names.json)

For `FRONT(CA)` (`Movie REC`, `Playback`, `Delete/Trash`, `Control Wheel rotary ring`), stock `input.ko` queries UIPC endpoint `0x00280132` (`kbd_timer_hndlr`). In `av-cam.bin`, the endpoint callback at `0x63a95dd4` (file `0x4cfdd4`) calls `0x63dd134e` (`0x80b34e`), `0x63dd08ae` (`0x80a8ae`), and `0x63dd1292` (`0x80b292`), which copy the state from the `g_front_state` snapshot (`0x4d7f30`). That snapshot is updated via UIPC `0x002804b6` (`0x4d8ba8` ← `0x1a31fc` ← `0x1a329c` 128-byte `0x30`-prefixed CRC16 packet over `0x00150300`). The direct bare-metal transport for `FRONT(CA)` after takeover remains to be wired up.

### 5.3 Mode Lifecycle (`struct os_mode`) **[Planned]**
```c
struct os_mode {
    const char *name;
    int  (*enter)(const struct zvrt_handoff *handoff); /* allocate mode memory, arm peripherals */
    int  (*tick)(uint32_t keys_pressed, uint16_t *fb); /* step 1 VSYNC frame; return 0=stay, 1=exit */
    void (*exit)(void);                                /* stop capture/DMA/IRQs, flush SD */
};
```
On every `switch_mode(next)` transition:
1. Call `current->exit()` (drain capture DMA, mask mode IRQs, flush/close open SD files).
2. Reset the 240 MiB mode scratch arena and 14 MiB uncached DMA pool with `zvrt_mode_reset()` and `zvrt_dma_reset()`.
3. Call `next->enter(handoff)` and resume the 50 Hz `tick()` loop.

---

## 6. External Library Integration Plan **[Planned]**

| Subsystem | Choice | Glue Required |
| --- | --- | --- |
| SD card filesystem | **ChaN's `FatFs`** (`ff.c` / `ff.h`) | ~100-line `disk_initialize` / `disk_read` / `disk_write` over ZV-E10 SDHCI |
| Preemptive tasks *(when needed for 4K RAW)* | **FreeRTOS** (ARMv7-A GIC port) | `vApplicationIRQHandler` wired to `GICC`, tick wired to `LOCAL_TMR` (`0xf8000600`) |
| Bare-metal USB streaming *(optional)* | **TinyUSB** | ZV-E10 USB controller DCD driver |

# ZV-E10 QEMU 11.1.2 Emulator (`pmca-re`)

21 November 2026. Standalone QEMU 11.1.2 (`-M zve10`) build, device models, storage synthesis, and boot status inside `pmca-re`.

> **Read-only reference boundary:** `D:\02_Development_And_Projects\zve10-qemu` (`HEAD == 42554a639e005455a1cc492744bd77341e7c41d2`) and `.local/dumps/` are strictly read-only inputs. `emulator.runner.verify_zve10_qemu_unmodified()` checks that `zve10-qemu` remains untouched.

---

## 1. Layout and Build Pipeline

| File | Purpose |
| --- | --- |
| [emulator/\_\_init\_\_.py](../../emulator/__init__.py) | Public exports (`QemuRunner`, `BootResult`, `verify_zve10_qemu_unmodified`, `rgba4444_to_png`). |
| [emulator/build\_qemu.py](../../emulator/build_qemu.py) | Extracts `qemu-11.1.2.tar.xz` (SHA-256 verified), overlays `emulator/qemu/` sources, applies `0001-register-zve10.patch`, builds with MSYS2 UCRT64 Ninja, and stages `.local/emulator/bin/qemu-system-arm.exe` + 35 UCRT64 DLLs. |
| [emulator/boot\_stub.py](../../emulator/boot_stub.py) | Patches `ej_head_init` (`mvn r2, #0` -> `mov r2, #0x100`) and wraps stock `vmlinux.bin` into a uImage (`LOADADDR=0x108000`), plus builds minimal test `initramfs` images. |
| [emulator/storage.py](../../emulator/storage.py) | Pure-Python FAT16 image synthesizer (`build_fat16_image`) with VFAT LFN support and Sony sector-0 `"8246" "1.00"` composite eMMC builder (`stage_storage`). |
| [emulator/stock_boot.py](../../emulator/stock_boot.py) | `prepare_stock_boot()` stages stock kernel, initrd, eMMC, and bootloader-owned `Backup.bin` RAM; `StagedStockBoot.runner_kwargs()` supplies reserved/uncached memory mappings and snapshot storage. |
| [emulator/runner.py](../../emulator/runner.py) | `QemuRunner` process/UART0/QMP harness, `pmemsave`, `capture_screendump`, `capture_osd0_png`, `rgba4444_to_png`, and `verify_zve10_qemu_unmodified`. |
| [emulator/qemu/hw/arm/zve10.c](../../emulator/qemu/hw/arm/zve10.c) | CXD90045 machine (`-M zve10`), DDR0/DDR1/eSRAM, Cortex-A9 (1–4 CPUs, VFPv3-D16, no NEON), A9MPCore GIC (256 IRQs, SPIs routed to CPU0), L2x0, PL011 UART0, `kemco` cmdline override at PA `0x00103000`. |
| [emulator/qemu/hw/timer/sony\_hwtimer.c](../../emulator/qemu/hw/timer/sony_hwtimer.c) | 9 Sony CXD4105/CXD90045 timer channels (`0xf2403000`, IRQs `153..161`). |
| [emulator/qemu/hw/arm/zve10-emmc.h](../../emulator/qemu/hw/arm/zve10-emmc.h) | Fujitsu `f_sdh30` SDHCI eMMC controller (`0xf0304000`, IRQ `227`). |
| [emulator/qemu/hw/arm/zve10-osd.h](../../emulator/qemu/hw/arm/zve10-osd.h) | VPH / `OSD0` display (`0xf3440000`, IRQ `102`), `ADC0`/`ADC1` (`0xf2406000`/`0xf2407000`), and `GPIO` (`0xf2910000`). |
| [emulator/qemu/hw/arm/zve10-gpe-init.h](../../emulator/qemu/hw/arm/zve10-gpe-init.h) | Startup GPE fence matcher (`0xf1000000`, IRQ `76`). |

Build QEMU standalone:

```powershell
.\.venv\Scripts\python.exe -m emulator.build_qemu
```

---

## 2. Emulated Hardware Summary

- **Memory & Boot:**
  - DDR0 `0x00000000` (1 GiB), DDR1 `0x80000000` (256 MiB when `memory='1280'`), eSRAM `0xfe000000` (32 KiB, SMP boot register at `0xfe005010`).
  - `zve10_reset()` writes `"kemco" + kernel_cmdline` at PA `0x00103000` (`VA 0x60103000`) when `-append` is supplied and `0x00103000` does not already start with `"kemco"`.
- **eMMC (`sony-f-sdh30`, `0xf0304000`, IRQ `227`):**
  - Bound to `blk_by_name("emmc0")` (or `drive_get(IF_SD, 0, 0)`).
  - Supports ADMA2, HS200 (`0x124 = 0x01000000`, `HOST_CONTROL1 +0x28 = 0x30`, `CAPABILITIES2 +0x44 = 0x00008000`, `+0x10c = 0x00080000`), `HOST_CONTROL2` (`+0x3e`) tuning handshake cleared on `CMD21`, `EXT_CSD` (`[179] = 0x08`, `[192] = 7`, `[196] = 0x17`), `CMD10` (`SEND_CID`), and R1b busy completion (`INT_CMD_COMPLETE | INT_XFER_COMPLETE`).
- **Display, ADC, GPIO (`zve10-osd.h`):**
  - `sony-vph-osd0` (`0xf3440000..0xf3446fff`, IRQ `102`): 50 Hz `QEMUTimer` VSYNC, `QemuConsole` 640×480 `PIXMAN_x8r8g8b8` scanout converting RGBA4444 from `0xf3441320` (`OSD0_STARTADRS`, default `0x04a00000`), and `0xf3441300` (`OSD0_CTRL`) `3 -> 2` latch transition.
  - `ADC0` (`0xf2406000`) / `ADC1` (`0xf2407000`): ready status (`+0x10 = 0`, `+0x18 = 0x04`) and neutral 10-bit channel values (`0x03f0`).
  - `GPIO` (`0xf2910000`): neutral button/G00 state (`+0x00 = 0x00000400`, `+0x10 = 0`) plus `+0x44`/`+0x48` set/clear.

---

## 3. Verification Status & Current Gaps

| Milestone | Status | Verified Behavior |
| --- | --- | --- |
| **M1: QEMU build & stock kernel UART0** | **Passed (automated)** | `.\.venv\Scripts\python.exe -m pytest tests/test_emulator_runner.py tests/test_housekeeping.py -v` -> `18 passed, 4 subtests passed` (`smp=1` and `smp=4`, QMP `info mtree`, `pmemsave`, R3 guard). `scripts/check_research.py` -> `Verified 27 evidence files and 31 experiment records. Tracked artifact check passed.` |
| **M2: Stock `initrd.img` + composite eMMC** | **Passed (automated)** | `stage_storage(kernel_only=True, include_usr=True)` + stock `vmlinux.bin` + `.local/dumps/firmware/initrd.img` (`smp=4`) boots in HS200 mode, mounts `/dev/nflasha7` (`/`), `nflasha15` (`/usr`), `nflasha10` (`/etc,/tmp`), `nflasha2` (`/setting`), `nflasha3` (`/system`), `nflasha11` (`/log`), `nflasha12` (`/cert`), and `nflasha18` (`/lens`), and reaches BusyBox `ash` (`uname -a`, `mount`, `ls`). |
| **M3: `OSD0` + `ADC0/1` + `GPIO`** | **Passed (automated)** | QMP `info mtree` and `xp` confirmed `sony-vph-osd0`, `zve10-adc0`, `zve10-adc1`, `zve10-gpio`, and `sony-f-sdh30`. Both `capture_screendump()` and `capture_osd0_png()` rendered the 640×480 RGBA4444 quadrant test pattern (`(255,0,0)`, `(0,255,0)`, `(0,0,255)`, `(255,255,255)`). |
| **M4: `av-cam.bin` (`LIRO`) & full boot** | **Partial (automated `liro.ko` verified)** | Loading `osal_utm.ko`, `osal_uipc.ko`, `utimer.ko`, `backup.ko Backup_load=0`, `osal_ulogio.ko`, `dmm.ko`, `dma330.ko`, and `liro.ko adr=0x035c6000 fn=/system/av-cam.bin load=1 debug=1` from `/bin/ash` loaded `/system/av-cam.bin` (`0 -> 635c6000 : 0 107d0ac loaded (OK)`) and ran `entry_pre` (`635c6044`) and `entry_main` (`635c6058`) to `end entry_main`. |

### Automated regression commands (21 November 2026)

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_emulator_runner.py tests/test_housekeeping.py tests/e2e_qemu/test_stock_milestones.py tests/e2e_qemu/test_menu_runtime.py -q
.\.venv\Scripts\python.exe scripts/check_research.py
```

The targeted suite, including the adapted menu regression, passed **21 tests and 4 subtests**. M2 asserts all nine mounts, required firmware/config files, and a write/read round trip on `/log`. M3 independently compares QMP scanout and physical RGBA4444 decoding against four expected colors, and checks the MMIO map and neutral ADC/GPIO values. It does not yet test input injection or VSYNC IRQ delivery.

M4 verifies the complete `Backup.bin` RAM copy before module loading, successful dependency insertion (including `udate.ko`), and the actual `av-cam.bin` load, `end entry_pre`, and `end entry_main` UART output. Shell completion markers are anchored to output lines so terminal echo cannot satisfy assertions. The E2E fixture checks every staging input's SHA-256 before and after execution, checks the external R3 reference, and uses the existing QEMU process-leak guard.

The former Tier 1 storage/LIRO scaffolding in `test_tier1_features.py` is consolidated in `test_stock_milestones.py`. The old assumptions about `wait_for_serial()` returning a result object and `/proc/liro/start` existing are removed from those tests. Other Tier 1/Tier 2 scenarios remain outside this verified command.

## 4. Reproducible stock userspace boot

```python
from emulator.runner import QemuRunner
from emulator.stock_boot import prepare_stock_boot

boot = prepare_stock_boot(work_dir=".local/emulator/stock-shell")
with QemuRunner(**boot.runner_kwargs(), timeout_s=45) as runner:
    runner.wait_for_serial(r"(?m)^/ # ", regex=True)
    print(runner.serial_output)
```

The helper stages `Backup.bin` from `trees/setting.tgz` at its header-specified PA (`0x02e80000` for this capture). Stock `backupfile_init()` converts the first header word with `arch_phys_to_cache()`; `Backup_load=0` skips the file-to-RAM copy and expects bootloader-preloaded contents. Merely providing the file on `/setting` is insufficient. The helper checks the BK4 header and that the entire destination fits the reserved Backup/LIRO arena.

`STOCK_INIT_CMDLINE` preserves the `kemco.txt` memory reservations, including `memrsv=680M@0x15800000:uc`. Without that uncached reservation, `udate_init_clock()` receives NULL from `arch_phys_to_noncache(0x200210e4)`. With staging and reservations, `backup.ko`, `udate.ko`, DMM, DMA330, and LIRO load in the automated ash-path test without the former exceptions. Stock kernel modules and dumps remain unchanged.

The helper defaults to `kernel_only=True` (`dmode=0`). Pass `kernel_only=False` to retain the normal setting partition. Use matching tree/card dumps from the same camera capture. QEMU runs the staged eMMC with `snapshot=on`, so guest filesystem writes do not persist into the reusable composite.

### Open items for the next session

1. **Unattended normal boot (`dmode=1`):** the production helper was probed for 20 seconds with a fresh normal composite. UART reached `Set MinDrv: emmc` with no backup file-load error or `udate` NULL dereference, but no LIRO entry milestone or application startup followed. The next initialization wait remains unresolved. Local UART log: `.local/emulator/normal-boot-probe/serial.log`.
2. **Post-LIRO runtime:** the automated milestone ends at `end entry_main`; continued UART shell responsiveness, firmware worker/IRQ behavior, and full camera application startup remain unverified. A subsequent shell command did not complete in the diagnostic run.
3. **Broader M3 coverage:** VSYNC IRQ delivery, page flips, and injected keys still need reconciliation with the older Tier 1/Tier 2 probe tests. The passing M3 baseline covers static scanout and neutral register state only.

## 5. Original Sony menu (adapted guest profile)

**Visible and regression-tested on the standalone pmca-re QEMU.** The original Sony Camera Settings 1 → Quality/Image Size menu, in English by default, renders at 640×480, including File Format/JPEG, JPEG Quality/Fine, JPEG Image Size, Aspect Ratio, and the panorama rows. This is the original Sony application/resource renderer running under an explicit adapter, separate from unattended stock boot.

Launch from any PowerShell directory:

```powershell
& 'D:\02_Development_And_Projects\pmca-re\scripts\start_emulator_menu.ps1'
```

The viewer shows QEMU screenshots; arrow keys send native direction events. Close the window to stop the guest transport and quit QEMU normally. Enter/Menu actions, physical panel mapping, live view, capture, and recording are not implemented by this profile.

Capture without opening a window:

```powershell
.\.venv\Scripts\python.exe -m emulator.menu --output .local/emulator/menu/menu.png --key DOWN --key UP
```

The first run stages and builds the menu runtime. Startup normally takes around one minute on this host, with a bounded 180-second readiness wait. The build requires the pinned local reference inputs and MSYS2 ARM GCC; subsequent launches reuse verified artifacts.

### Implementation and verification

- `emulator/build_menu.py` verifies the external R3 boundary, hashes every input against `emulator/menu_reference.json`, copies inputs into `.local/emulator/menu`, and builds there. It never imports or executes Python from the reference directory. The menu runtime remains entirely local after staging; no camera or physical storage is used.
- The profile uses the reference UI kernel, AP-only service selection (`target=qemu`, `dmode=3`), DMA330 stub, and supported CPU implementations of GPU/LDEC operations. Original Sony shared libraries and UI resources are hash-bound. See [adapter provenance](../../emulator/MENU_ADAPTER_NOTICE.md).
- `emulator/menu_osd.h` publishes the selected, retired native transaction's physical framebuffer to OSD0 (`0xf3441320`, pitch 1280, latch `3 → 2`). Menu pixels are not drawn by the host. The launcher pauses QEMU, captures scanout, reads the physical framebuffer, decodes RGBA4444 independently, and compares every RGB pixel.
- The explicit machine option `-M zve10,strict-cpu=off` selects the reference-compatible Cortex-A9 profile for this guest. The default remains the camera's VFPv3-D16/no-NEON profile. Both profiles are verified through live QOM CPU properties. The compatibility profile resolved the observed adapter startup exception; this does not establish the underlying renderer dependency or imply that the physical camera has NEON.
- `emulator/menu.py` waits for native glyph readiness and a stable completed framebuffer. The imported vertical wire labels were reversed; host mapping corrects Up/Down while preserving the original horizontal mapping. Input waits include a later after-draw frame, because event consumption alone precedes the deferred view action. Input acceptance is checked at the original UI consumer, not just queue submission.
- `tests/e2e_qemu/test_menu_runtime.py` checks the entire reviewed English menu framebuffer, title/File Format pixels, Down/Up navigation and Right to page 2/Left to page 1, guest-memory/scanout equality, runtime input hashes, external R3 integrity, no leaked QEMU process, and normal transport/QMP shutdown.

### English default and runtime lifetime

The generated menu CPIO overlays the original `string_english.uxc` and `string_english_f.uxc` banks at the bank paths selected by the captured Japanese locale. This routes the original Sony English text through the original renderer without translating strings or modifying captured settings. `--language captured` restores the capture's original text bank; `--language english` is the default. The build receipt records both source-bank hashes.

The inherited init script's per-process/per-thread diagnostic dump spawned hundreds of `cat` processes and exhausted this old UI kernel's ASID pool (`Cannot allocate ASID`, followed by PID 1 exiting). The generated runtime removes that dump and keeps PID 1 in a builtin wait on its application. Diagnostics remain in the UART log and QMP capture path without a guest process storm.

### Remaining normal-boot blocker

The stock `drivers2` table was decoded from the local `/sbin/init` ELF and loaded module by module. Modules 0–16, through `dmm.ko`, returned success. Module 17, **`upm.ko`**, did not return within the bounded diagnostic wait. The normal boot's power-management/FRONT initialization is therefore the next stock-path investigation. Local diagnostic UART log: `.local/emulator/module-probe/serial.log`.

Some focused-row redraws after vertical navigation remain incomplete; the regression verifies input consumption and frame changes, not every focused-row glyph. The initial English menu and the second page have reviewed pixel oracles.

The adapted menu result does not close the normal-boot issue or prove full camera functionality.

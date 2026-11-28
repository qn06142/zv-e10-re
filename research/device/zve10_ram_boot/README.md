# ZV-E10 GUI-triggered RAM handoff & ZVOS bare-metal runtime

**Current architecture (20–23 November 2026):** `boot.ko` (v3, `boot.c`) quiesces Linux and branches to the bare-metal ARM runtime (`crt0.S` + `zvrt_runtime.c` + `rtos_c.ld`), which takes over a self-owned 1 GiB `DDR0` L1 MMU table (`0x81000000` runtime, uncached `0x25000000..0x25ffffff` DMA/display window, `0x86000000..0x97ffffff` mode heap, optional `clip.bin` at `0x84000000`), dispatches GIC IRQs, and runs the interactive [ZVOS shell](os_shell.c) (`Bad Apple!!`, animated `Fire`, `LiveView`, and `BayerRAW`). See:

- Architecture & memory map: [ZVOS_SPEC.md](../../../docs/hardware/ZVOS_SPEC.md)
- Hardware & recovery handoff: [HANDOFF.md](../../../docs/hardware/HANDOFF.md)
- Canonical sensor pipeline reference: [docs/hardware/SENSOR_PIPELINE.md](../../../docs/hardware/SENSOR_PIPELINE.md)
- Live-view register monitor (`rtos_live_view.c`): [LIVE_VIEW.md](LIVE_VIEW.md)
- Bare-metal IMX284 + DFE Bayer RAW bring-up (`senser_bayer_runner.c`, `bayer_capture.h`): [BAYER_HANDOFF.md](BAYER_HANDOFF.md) · [SENSOR_PIPELINE.md](SENSOR_PIPELINE.md)

## Key ZVOS & Bayer source files

| File | Purpose |
| --- | --- |
| `boot.c`, `launcher.c`, `module_info.c` | Linux `boot.ko` v3 takeover module (`sys_sync`, `do_emergency_remount`, `kernel_restart_prepare`, `machine_shutdown`, `64 KiB` L1 arena) and Version-screen GUI launcher (`research/device/zve10_boot_bridge/` hosts the boot bridge helper). |
| `crt0.S`, `rtos_c.ld`, `zvrt_runtime.c`, `zvrt_runtime.h`, `zvrt_font.h` | Bare-metal quiesce, private 16 KiB L1 MMU takeover, VBAR fault handlers, GIC IRQ controller, uncached `OSD0` double-buffering, `ADC0`/`ADC1`/`GPIO` input polling, and 8×8 font. |
| `os_shell.c`, `os_mode.h`, `rtos_bad_apple.c`, `osd_fire.h` | ZVOS mode shell (`enter`/`tick`/`exit`), `Bad Apple!!` 320×240 24 fps decoder, and animated fire mode. |
| `bayer_capture.h`, `bayer_display.h`, `bayer_sensor_tables.h`, `generate_bayer_init.py` | ZVOS `BayerRAW` capture loop, debayered LCD preview, and firmware-extracted IMX284/DFE register tables. |
| `cxd90057_hw.h`, `cxd90057_pipeline.h`, `imx284_sensor.h` | Behavioral `CXD90057` MMIO/CRG/DFE/ComboPHY/SLVS-EC drivers, coalescing P2S SPI builder, and decoded `IMX284` register arrays. |
| `senser_bayer_runner.c`, `test_bayer_senser.py` | Userspace `/dev/mem` bare-metal Bayer RAW bring-up & extended register diff runner over USB Senser. |
| `build_rtos.py`, `stage_rtos.py`, `verify_os_shell.py`, `verify_bayer_capture.py` | ARM GCC build, guarded Senser staging, and Unicorn CPU/MMIO verification tests. |

```powershell
# Build ZVOS rtos.bin and run Unicorn verification
.venv/Scripts/python.exe research/device/zve10_ram_boot/build_rtos.py --display --source research/device/zve10_ram_boot/os_shell.c --out .local/out/zvos_shell_check
.venv/Scripts/python.exe research/device/zve10_ram_boot/verify_os_shell.py .local/out/zvos_shell_check/rtos.bin
.venv/Scripts/python.exe research/device/zve10_ram_boot/verify_bayer_capture.py .local/out/zvos_shell_check/rtos.bin
```

---

## Historical baseline: 18 November GUI-triggered RAM handoff trial

**Historical note (18 November 2026 baseline, superseded above by `ZVOS`):** Both initial reset/heartbeat files passed checksum verification and READY staging. [RTOS loader and ownership boundary](../../../docs/imaging/RTOS_ITERATION.md)

Original reset-profile result, 18 November 2026: package installed and fully read back; the owner subsequently attempted the GUI trial and reported that the camera restarts properly. The flashes were too fast to count, so RAM-image entry remains **unverified**. The module reached READY and unloaded on-camera in Senser. The existing GUI user-space loader separately displayed HELLO to the owner. See [hardware evidence](hardware-20261118.json).

## Original reset-profile trial

Disconnect USB and return to normal shooting. Open Setup → Version. Press and release Up → Down → Left → Right → Up. The first activation loads the module and displays BOOT RDY without starting takeover. Release the button and repeat the complete sequence to request GO; expected text is BOOTING. About one second later the intended result is three brief access-LED pulses followed by a hardware reset into stock firmware. Observe both pulses and restart: a reset alone does not prove image entry.

If the camera hangs, disconnect USB and briefly remove the battery before normal boot. No autoload or persistent alternate boot selection is installed. The old watchdog is not a guaranteed fallback once interrupts are masked. The owner reports restart after the trial. The exact image entry, reset path and post-restart file state have not been verified.

## What runs

launcher.c is a returning Thumb payload for the [existing GUI loader](../../ui/version_gui_ram_loader/README.md). It reads /log/zve10-ram-boot/boot.ko, calls init_module and returns BOOT RDY. A separate confirmed invocation writes GO to the module's root-only sysfs command. Module initialization only allocates its own code and stack; it neither queues takeover nor changes GPIO.

boot.c schedules CPU0 work, syncs storage, calls the stock kernel_restart_prepare and machine_shutdown paths, checks that other Linux CPUs stopped, masks IRQ/FIQ, refreshes the stock watchdog and branches to os.S with a private stack. The image retains the existing MMU, DRAM and board device mappings. It does not erase RAM, reinitialize all hardware, initialize a sensor/USB stack, or constitute a standalone replacement RTOS. Stock device shutdown behavior and old DMA ownership remain real takeover risks.

os.S writes only its entry marker, the bit-0 GPIO LED controls and the board reset-set register (0x11). GPIO details derive from the external zv-e10-toolkit fastboot LED implementation; reset and mappings derive from Sony's GPL board code. Existing kernel headers are read from the external zve10-qemu checkout, without changes or claiming its work.

## Evidence and reproduction

build.py produces os.bin and the ABI-guarded module against matching prepared Sony GPL headers and a stock reference module. verify_os.py executes the ARM image at two addresses with modeled GPIO/reset. verify_launcher.py executes the installed GUI and Thumb launcher at two load biases; module init and sysfs effects are modeled. These checks do not emulate Linux shutdown or validate hardware timing.

The final module is 7724 bytes, SHA-256 87d5ee9955cfe1229376b8cc36b804de11b8c6aacdeae14612ac5432d53235ad. It reached READY on hardware with a 124-byte RAM image, then unloaded cleanly without GO. The launcher is 840 bytes, SHA-256 9f4cccc252779e7d752fe5680b8c9e0f8624868257c3c4a3aabb3d1ca5a348ce. Full installed-file readbacks match both artifacts and the saved HELLO payload.

install_payload.sh is a single-use guarded deployment script. It requires the exact previous HELLO and GUI hashes, preserves HELLO under /log/zve10-ram-boot/previous-hello.payload.bin, verifies the module and launcher, and atomically replaces only the payload. It does not load the module or send GO. No av-cam.bin replacement or /usr write was performed for this package.

## Owner trial result

The camera restarted properly following the GUI trial. The owner could not count the fast flashes. This establishes an observed restart after activation, but does not distinguish the RAM image reset from the module's earlier reset path or another reset source. The reset binary was retained as the baseline. The subsequent resident runtime below supersedes this trial; its LED heartbeat was reported working by the owner.

## Resident runtime v02 (previous working baseline)

At the user's request, the active module now contains os_runtime.S rather than os.S. SHA-256: 279bc0718128b8dc832163314e4e360582ecf272642f68a679aa6ba0a684038a (7972 bytes; 244-byte ARM entry image). The launcher and GUI library are unchanged. The module reached READY in Senser, unloaded cleanly, and its final installed file was read back byte for byte. No GO was sent during installation. The previous blink/reset module is saved at /log/zve10-ram-boot/runtime-v02/previous-reset.ko.

After disconnecting USB, use the same full Version-screen sequence twice: first BOOT RDY, then BOOTING. The resident image masks IRQ/FIQ, uses its private stack, disables the board watchdog reset gate and stops/clears its timer using Sony's WDT_SET_STOP sequence. It installs an aligned private VBAR table and clears SCTLR.V while retaining the MMU. It then runs a self-contained slow LED heartbeat and increments a counter in its owned RAM. It makes no Linux calls after entry and requests no reset. Its synchronous fault vectors record FALT and show a solid LED; actual exception dispatch has not been hardware-verified. Other CPU watchdog events cannot be serviced after the stock stop path, which is why the board reset gate is disabled.

Normal GUI, USB and SSH are not available during this runtime. Disconnect USB and briefly remove the battery to return to stock boot. There is no automatic watchdog recovery in this profile. No alternate boot selection or av-cam.bin change is made. This is an initial resident CPU runtime using inherited hardware state, not a standalone RTOS or proof that all Sony hardware/DMA activity has stopped. It has no sensor, display or USB driver and no scheduler.

Build with build.py --profile runtime and the same --kernel, --reference-module and --out arguments as the reset profile. The default profile remains reset. verify_runtime.py executes five heartbeat cycles at two load addresses with high vectors initially on/off, checks the exact watchdog/GPIO writes and dispatches all seven private fault vectors. CP15 and MMIO effects are modeled. verify_launcher.py passes with the resident module bytes. install_runtime.py --out PATH records a single guarded Senser session; it requires the exact previous baseline, retains a backup, checks READY without GO, unloads and atomically replaces the module. It is intentionally single-use and refuses an existing runtime-v02 directory.

### Resident trial result

The owner reported blinking lights and that the camera was back in Mass Storage afterward. This is hardware evidence for resident-image entry and heartbeat execution after the GUI-triggered privileged handoff, based on owner observation rather than a register trace. Duration and exact exit method were not recorded. It does not establish a standalone RTOS or complete hardware ownership.

A subsequent read-only Senser session verified Linux CPUs 0–3 online, both test modules absent, /usr read-only, and unchanged av-cam.bin and GUI-library MD5 hashes. Full readbacks of the resident module, saved reset module and GUI launcher matched their host SHA-256 hashes. No camera files were written during that verification, and the service session closed cleanly.

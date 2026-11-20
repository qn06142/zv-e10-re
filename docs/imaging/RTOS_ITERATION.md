# RAM-loaded RTOS iteration

18 November 2026. The initial design below has progressed to an installed GUI trigger, an owner-confirmed returning HELLO payload and an owner-confirmed resident RAM heartbeat. Stock Linux and file readbacks passed afterward. The [current display trial](../../research/device/zve10_ram_boot/DISPLAY.md) is installed but awaits physical observation. This resident CPU runtime retains Sony MMU/device state; independent hardware initialization remains incomplete. The following sections preserve the original loader audit and plan. Goal: iterate on a replacement for av-cam.bin without using BootROM for every build. Keep Bayer RAW over USB as the eventual imaging goal.

## Proposed loop

Boot the installed stock system, upload a candidate into a dedicated RAM-backed filesystem, validate its length/hash and load contract, then explicitly launch it. Keep the installed stock image and boot selection intact. A failed test should require a genuine reset back to stock rather than a reflash; this fallback has not yet been demonstrated on this camera.

The existing UVC library is a possible launch trigger because it already executes our code. It is a Linux userspace library, not a replacement bootloader. Keep initialization passive and require an explicit command to request launch. Use SSH for uploading and diagnostics while available; an alternative USB protocol can be added separately. UVC video traffic alone is not an implemented firmware-upload protocol.

Do not wipe all RAM or reset all hardware. Any takeover must preserve its own code, stack, image, parameters and necessary DRAM state. DRAM reset/retraining would invalidate a RAM-resident loader. Device reset also removes the existing USB/Wi-Fi transport until the next software reinitializes it.

## Two execution targets

| Target | Handoff | Remaining boundary |
| --- | --- | --- |
| Replace the LiRo camera image, keep Linux | Existing liro.ko alternate fn parameter and delayed main gate | Establish a clean Linux environment without stock LiRo and preserve network access. Do not overwrite an active image. |
| Run a standalone system owning the machine | Kernel-mediated kexec-style handoff or a dedicated transition module | Verify kernel support, physical memory layout, CPU parking, DMA shutdown, interrupt/cache/MMU transition, DRAM preservation and payload boot ABI. This is not implemented. |

LiRo's inspected initialization creates a Linux kernel thread and waits for its completion. Replacing av-cam.bin through that interface retains Sony Linux and LiRo's host services; it does not establish an independent bare-metal RTOS. A userspace function pointer cannot substitute for the standalone transition.

## Checked local evidence

- Dumped liro.ko SHA-256: 72b77031f00679877ac04edf452e9f49e5fbca05cb4ee4554ddd2e5243e8e0cc.
- Earlier standalone hello-world sources and verifier are in the local workspace C:/Users/qn061/Documents/Codex/2026-11-16/chrome-plugin-chrome-openai-bundled-file-2/outputs/zve10-rtos. These are local prerequisites, not published source in this plan.
- Re-ran verify_hello.py against hello-av-cam.bin and the module above. Original loader file read, header checks, callback copy, entry paths and delayed start passed with mocked Linux services. This is offline evidence only.
- The earlier launcher uses fn=/tmp/hello-av-cam.bin, load=1, debug=1, delay=1, then /proc/liro/start. Pre-entry runs before the delay gate. It refuses an already loaded LiRo instance and guards the image, module and expected address.
- Inspected liro_init: positive adr is translated by +0x60000000; the earlier test uses raw adr 0x035c6000 for entry address 0x635c6000. Obtain the actual camera value before launch.
- liro_exit calls an image-provided callback and host cleanup. An unload entry point exists, but its presence does not prove safe hot replacement, device quiescence or termination of all image-owned work. No rmmod trial is authorized by this plan.
- Sony change_mode.sh describes mode 1 as global infrastructure before LiRo, and mode 2 as including LiRo. Independent SSH/Wi-Fi in mode 1 remains unverified. Changing persistent mode without a tested fallback defeats the intended recovery loop.

## First hardware milestone

1. Read-only capture of current boot ID, uptime, mounts, hashes, module state, kernel configuration if exposed, networking startup and watchdog/fast-boot behavior.
2. Establish whether a Linux-only environment can keep or independently initialize Wi-Fi and SSH. The installed SSH launcher binds to wlan0; that alone does not establish who configures Wi-Fi or when the launcher starts.
3. Develop and test one-shot selection with the stock default. Consume the selection before entering test code; do not depend on a failed payload to clear it. Do not enable a permanent replacement or persistent Linux-only mode to discover whether recovery works.
4. First payload only reports a greeting and returns. Check continued SSH, clean boot identity and original file hashes. Then deliberately test a bounded failure and a genuine reset back to stock.
5. Only after this loop works, expand into device initialization and display/sensor work. Full machine takeover is a separate milestone.

## Meaning of read-only

Upload test builds into verified tmpfs/RAM storage. The camera's /tmp is flash-backed VFAT in captured mounts, so /tmp is not automatically a RAM staging location. Avoid persistent file edits during each iteration. A one-time installed trigger or rescue environment, if required, is itself a persistent change and must be recorded separately.

Read-only mounts protect normal filesystem writes. They do not prevent privileged payloads or stray DMA from writing storage, protect against all device-state changes, or guarantee that fast boot discards failed RAM. Never promise recovery solely because the payload was loaded from RAM. Preserve the same-body recovery backup as the last fallback.

See [system overview](../CAMERA_OVERVIEW.md), [access and recovery](../ACCESS_AND_TOOLS.md) and [current checkpoints](../CURRENT_STATUS.md).


## 19 November checkpoint

The full-screen color bars confirmed that the Version trigger can hand off CPU execution and drive the rear LCD with inherited configuration. The current module still relies on Linux to allocate its image, stack and DMA backing before GO. Its call to `kernel_restart_prepare` runs reboot notifiers and device shutdown. On this kernel `machine_shutdown` only sends the SMP stop IPI. Neither path establishes ownership of DDR regions, LiRo work or outstanding DMA.

Develop the Version trigger into a loader for a separate replacement image. Keep Sony Linux as the normal host and recovery environment. Establish separately whether Linux remains live during replacement RTOS execution through LiRo or is parked by the loader during a standalone trial. For either mode, define an explicit DDR arena for the replacement, prove the Sony owners of that arena have relinquished it, and quiesce the DMA engines that could still access it. The first replacement image should install its own allocator and reserve its framebuffer from that arena. The LCD test can reuse panel timings while the independent display initialization is still being developed. The stock boot path remains the recovery target.


## Separate-image loader v1

The Version trigger now stages a kernel loader at `/log/zve10-ram-boot/boot.ko`. It reads the separate `/log/zve10-ram-boot/rtos.bin` file before GO. The loader checks the regular-file type, exact size, image ABI, aligned entry offset and CRC, then copies it into executable RAM. The CRC detects corruption in a trusted image. Native payloads run with the loader's CPU privileges.

The package format and arena handoff are in rtos_abi.h (local checkout: `research/device/zve10_ram_boot/rtos_abi.h`). The first image allocates two ranges from the 16 KiB arena, checks exhaustion, and writes a marker to both ends and to the result word. It performs no DMA or device writes. The trampoline returns to its heartbeat only when the probe returns success. A solid LED indicates probe failure or a fault.

Build the loader with `build.py --profile rtos-loader` using the existing kernel and reference-module arguments. Build an image independently with `build_rtos.py --out PATH`. The default image is `rtos_probe.S`. `verify_rtos_probe.py PATH/rtos.bin` runs the probe at two relocated addresses and exercises malformed handoffs. The packaged probe and trampoline also ran together offline at two load addresses with both high-vector settings.

Both files passed USB byte readback after the loader reached READY and unloaded. The v08 fire module is backed up at `/log/zve10-ram-boot/rtos-loader-v1/previous-fire-v08.ko`. GO was left for the owner. On **Setup → Version**, the first full direction sequence should show **BOOT RDY** and the second should show **BOOTING**. Expect a slow LED heartbeat and no new display pattern. Brief battery removal exits to stock.

The 16 KiB lease is loader-owned scratch RAM. The current trampoline still retains Linux's MMU and hardware state. The LiRo module's offline exit path calls an image callback and then `liro_remove_entry`, `malloc_exit` and `ltron_tsk_exit`. We have no evidence that the normal reboot path executes their equivalent or that other bus masters are idle. A replacement-owned DDR arena large enough for scanout, and proof that LiRo and DMA no longer touch it, remain required before enabling graphics in the separate image.

Staging receipt `ZVBOOT_STAGE_RTOS bytes=272 arena=4ff0000 size=16384 flags=owned-arena`. Loader SHA-256 `fb4ed7ed359a87a1511e29ae0348d047955a001ccbc31c6d36b3e0363e56c64d`. Image SHA-256 `3c412599fd74de9a73eade37fd5c0591884f070a276b1306202de4a0bb8ce975`.


### Owner-confirmed loader entry

The owner observed a black LCD and a slow access-LED blink after GO. This is the expected result for the arena probe. The slow loop is reached only after the separate image has run and returned success from the allocation and exhaustion checks. No display helper runs on this path.

### LiRo release path to verify next

In the body-matched `liro.ko`, the UDIF operations record at ELF `.data+0xd0` has `liro_exit` in the exit slot and `liro_suspend` in the shutdown slot. The latter is the relocation at `.data+0xe8`, corresponding to the GPL `UDIF_DRIVER_OPS.shutdown` field. Its indirect call at ELF `.text+0x3d0` uses the active image header pointer at +0x18. In the saved current-body image that pointer is `0x635c6068`, an ARM wrapper that invokes the Thumb routine at file offset `0x18ce8`.

The GPL suspend path calls the UDIF suspend dispatcher. The separate UDIF shutdown dispatcher has no caller in the examined kernel tree, so its existence does not demonstrate that our reboot-preparation path reaches this callback. The callback itself touches RTOS task/state tables. Its return alone cannot retire DMA or release the whole firmware reservation. The next ownership check needs to resolve the callback's downstream release calls, then observe the relevant bus masters at the handoff boundary.


### Read-only post-GO DMA probe

The ROM-independent loader can now swap an image by replacing `rtos.bin` alone. The installed DMA probe (local checkout: `research/device/zve10_ram_boot/rtos_dma_probe.S`) reached READY, unloaded and passed USB byte readback with the original loader unchanged. The first arena probe is saved at `/log/zve10-ram-boot/dma-probe-v1/previous-rtos.bin`.

The probe waits across 80 nominal 2 ms samples. It checks XDMAC XDDSD words for changes, DMA330 manager/thread state fields for nonzero values, and VPH AIF status bits and current addresses. It writes its final sample and activity flags into the owned arena. The only peripheral writes are to the established access-LED GPIO. A fast regular blink means a status/address changed or a busy mask matched. A slow blink means none of those conditions was observed during the sample window. A solid LED means a fault, rejected handoff or stalled timer. The result is scoped to those sampled words. It cannot certify that every bus master is idle or that any stock memory has been released.

The ARM fixtures modeled quiet state, XDMAC changes, DMA330 activity, VPH AIF busy, timer failure and a malformed ABI. They also checked that the payload writes only the arena, result word, stack and access LED. GO was left to the owner.

Resolving the body-matched shutdown routine's host calls through LiRo's relocated API table identified task delay/query, flag clearing, mailbox sends, fixed-pool release, and outer-cache control. These calls confirm that the routine changes RTOS state. Their presence does not identify a complete DMA shutdown sequence or an acknowledgement that the arena has been released.

Installed DMA probe SHA-256 `aab898cbb0596cadfbfd89ce43d05c646f114d1ea61e6b8daebea1782274dc2d`.


#### Owner observation and controller-specific probe

The owner reported a fast regular blink with the first probe. At least one sampled register changed or one busy mask matched after the Linux handoff. The first image combined all controller results.

The v2 image preserves separate changed-word and busy-field masks in the owned arena, then reports their combined mask as repeated groups of 350 ms flashes with a 2.8 s dark gap. Each controller contributes a value. Add the values when several controllers are flagged.

| Flashes | Controller contribution |
| --- | --- |
| 1 | XDMAC status changed |
| 2 | DMA330 manager or thread status changed or was nonzero |
| 4 | VPH AIF status or current address changed, or AIF reported busy |

The original steady slow blink indicates zero in the sampled mask. Solid indicates the probe failed to complete. A changed word or busy flag identifies where to investigate. In particular, a retained busy bit alone cannot establish that memory transactions are still progressing.

The v2 binary passed all eight mask cases, timer wrap, stalled timer and invalid ABI in the ARM fixture. On-device SHA-256 matched the host image, the same `boot.ko` loaded it to READY, and the module unloaded without GO. The v1 image is saved at `/log/zve10-ram-boot/dma-probe-v2/previous-rtos.bin`.

v2 SHA-256 `e5e9ed7c99102ed5120103164b880a19dd9ccf8e1baedaeb4e8d5552a4ca2bb9`.


#### Display AIF drain experiment

The owner reported four flashes from v2. Display AIF flagged a change or busy state after GO. XDMAC and DMA330 did not contribute to the sampled mask. Four flashes do not identify a specific AIF bank or distinguish a latched status word from an advancing transfer.

The drain payload (local checkout: `research/device/zve10_ram_boot/rtos_aif_stop_probe.S`) scans the eight VPH AIF banks for a set start bit or reported busy bit. It checks every candidate before issuing commands. It admits an active bank only when the control word and body-matched firmware sentinel at VA `0x643eb19c` select the native primary stop path. Banks needing the secondary handshake are left for a later experiment.

For each admitted bank, the payload clears bit 0 at +4 and +0, sets bit 30 at +4, and waits up to 80 ms for bit 31 at +4 to clear. It writes the native +8 completion command only after that clear. It then repeats the read-only DMA observation. The experiment neither starts a DMA transfer nor reuses the Sony buffer addresses.

Offline execution of the current-body stock routine confirmed the primary write order across all eight physical AIF banks. The payload fixture checked idle, successful drain, timeout, unsupported fill mode, a non-primary sentinel, and continued address changes after drain. The physical outcome remains to be observed.

The body firmware hash matched before staging. The drain image reached READY and unloaded without GO. Installed SHA-256 `7ff1b564da17c8f5729ed96bbee80e99bdf1d12f3e8f85b558f54dee280bf6a4`. The controller-specific read-only image is saved at `/log/zve10-ram-boot/aif-stop-probe-v1/previous-rtos.bin`.

The owner reported an even slow blink after the drain and supplied a photo showing a dark rear LCD with a narrow cluster of bright vertical lines at the left edge. The even blink means the guarded stop path completed and none of the sampled XDMAC, DMA330 or AIF conditions flagged in the following observation window. The probe leaves the panel enabled and supplies no frame. The photo records the resulting panel output and does not identify the source of the lines. No stock buffer was reclaimed. Photo SHA-256 `c08d916d7a5c47332fed8595ed7d4953c8c91baf5ed49988c9ad850e91e33110`, held with the conversation.

The next ownership step is a dedicated DDR lease with an exclusive allocation record and validated physical bounds. The existing DMM lifecycle work distinguishes a new allocation (command 1) from share/open references to an existing producer's buffer. Only a separately allocated, exclusive unit or an independently reserved boot arena can be handed to the replacement allocator. [DMM allocation and release commands](../usb/uvc_yc_source_recovery_20261025.md)


### Full-screen demo using the drained OSD0 slot

The full-width allocation attempt failed during staging on this boot. The installed replacement uses no new framebuffer allocation. The separate display image (local checkout: `research/device/zve10_ram_boot/rtos_display.S`) checks the live stock descriptor against the four previously observed OSD0 slots and the 640×480 RGBA4444 layout. It drains active AIF banks, rechecks their start/busy bits and current addresses across a 20 ms window, and requires the selected descriptor address to remain stable before painting. It fills only that 614,400-byte slot, performs cache maintenance, points OSD0 at it, and refreshes consumed start requests. No other Sony frame buffers are reused.

Offline execution verified all eight bars on all 480 rows, rejected a mismatched descriptor, and left the framebuffer untouched when an AIF address moved after the drain. The saved body hash matched, the loader reached READY, and both files were checksum-verified after install. No GO was sent. Backups of the previous loader and drain image are under `/log/zve10-ram-boot/rtos-reuse-demo`. Physical display output is pending the owner trial. This experiment targets one drained OSD slot and continues to use inherited panel timings and the stock MMU.


#### Display demo guard diagnostics

The first reuse demo showed a solid red LED. That build reported multiple failures with the same light, so the observation could not identify the stage. The diagnostic build keeps the framebuffer selection, drain, painting and scanout unchanged. It records the current stage and reloads its own GPIO and boot-information pointers in the fault handler, even when a separate-image instruction fault clobbered registers.

| Flashes between pauses | Stage |
| --- | --- |
| 1 | Handoff ABI or scratch bounds |
| 2 | Stock OSD descriptor, slot membership or current-address range |
| 3 | Inherited panel output configuration |
| 4 | Native AIF drain or primary-path check |
| 5 | Post-drain idle or descriptor-stability check |
| 6 | Painting or cache maintenance |
| 7 | Scanout configuration or first in-range observation |

The fixture exercised all seven codes on both a guarded return and a fault with clobbered registers. Both diagnostic files passed READY staging and on-camera SHA-256 verification. GO is left to the owner. The previous demo files are backed up under `/log/zve10-ram-boot/rtos-display-diagnostics`.

The owner reported two repeated flashes on the diagnostic build. The stop was in the descriptor size/layout, callback, slot, or pre-drain scan-address guard. The drain and framebuffer writes follow that guard. A read-only capture in stock Setup → Version is needed to distinguish its individual checks.

### Senser OSD0 comparison

The 20 November read-only Senser capture matched the queue-consumer fingerprint and found a 640×480 primary descriptor with callback `0x63733989`. The secondary descriptor was empty. The primary base was `0x22c48000`, with OSD0 current addresses `0x22c84e80` before and `0x22cb1200` after sampling the descriptors. Both were inside the 614,400-byte frame. The installed image would fail its stage-2 base check in Senser, and its current-address check also excludes that range. The actual two-flash failure occurred on a separate Version-screen launch. A Senser-targeted test needs a validated handoff that preserves the LCD state and stops the producer before reusing the live frame. [Capture](../../research/device/zve10_hardware_map/evidence/20261120-senser-osd-slots.json)

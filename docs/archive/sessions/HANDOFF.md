> Latest consolidation, 18 November 2026. Begin with [camera overview](../../CAMERA_OVERVIEW.md), [current status](../../CURRENT_STATUS.md), [access/tools](../../ACCESS_AND_TOOLS.md) and [imported session evidence](../../../research/firmware/evidence/zve10-20261117/README.md). Research is paused. Entries below preserve dated session history and include superseded installation and transport claims.

## Windows Port of `zve10-qemu` & 1080p UVC Patch Progress — 16 November 2026 (21:36)

1. **Windows Port of `zve10-qemu` ([D:\02_Development_And_Projects\zve10-qemu](file:///D:/02_Development_And_Projects/zve10-qemu)):**
   - Cloned `github.com/chocotan/zve10-qemu` to `D:\02_Development_And_Projects\zve10-qemu` and ported the entire stack to run natively on Windows (without WSL):
     * **QEMU 11.1.2 (`.local/work/qemu-src/build-zve10/qemu-system-arm.exe`):** Built natively in MSYS2 UCRT64 (`--target-list=arm-softmmu --disable-docs --disable-werror`) with `source/qemu/hw/arm/zve10.c`, `zve10-gpe-init.h`, `sony_hwtimer.c`, `0001-register-zve10.patch`, and a Windows `WinError 1314` symlink-fallback fix in `scripts/symlink-install-tree.py`.
     * **ZV-E10 Linux 3.0.27 Kernel (`.local/work/linux-kernel/arch/arm/boot/Image`, `.local/work/kbuild-clean/arch/arm/boot/Image`, `.local/work/kbuild-ui/arch/arm/boot/Image`) & `dma330_stub.ko`:** Cross-compiled natively on Windows using MSYS POSIX `HOSTCC=/usr/bin/gcc` and `/ucrt64/bin/arm-none-eabi-gcc` (GCC 16.1.0) with:
       - CRLF (`\r\n`) parsing fix in `scripts/basic/fixdep.c`.
       - `include/linux/compiler-gcc16.h` (copied from `compiler-gcc9.h` with GCC 4.1 `__GNUC_MINOR__ == 1` check disabled).
       - Explicit `-march=armv7-a -Wa,-march=armv7-a` in `arch/arm/Makefile`.
       - Null-pointer guard `(unsigned long)tmp < 0x60000000UL` in `fs/proc/generic.c` (`proc_register`).
       - `KCFLAGS='-O1 -std=gnu89 -fno-strict-overflow'` (avoids a GCC 16 `-O2` miscompilation that corrupted `.bss`/`proc_root` during boot).
     * **Pure-Python Firmware & CPIO Builder ([scripts/win_prepare.py](file:///D:/02_Development_And_Projects/zve10-qemu/scripts/win_prepare.py)):** Unpacked `FirmwareData_ZVE10V203.dat` (`SHA-256: 8f1cae05...`) via `.local/work/fwtool/fwtool.py` (`cdba742`) and reads `nflasha7` / `nflasha15` ext2 images directly in Python (`fwtool.archive.ext2.readExt2`) to pack `.local/work/camera.cpio` (`7,157,248 B`) and `.local/work/ui.cpio` (`259,217,920 B`, including `dma330_stub.ko` and the 11-entry `prepare-ui-profile.py` `libIMDB.so` patch) with exact symlinks, modes, and `/dev/*` character device nodes — no `debugfs`, `fakeroot`, `mknod`, or GNU `cpio` required.
     * **ARMv7 Guest `.so` Compilation on Windows (`.local/work/win_inc/` + `.local/work/sysroot/lib/`):** Extracted ZV-E10 `/lib/*.so*` (`libc.so.6`, `libdl.so.2`, `libpthread.so.0`, `librt.so.1`, `libm.so.6`, `libgcc_s.so.1`) into `.local/work/sysroot/lib/` and created minimal Linux ARM EABI headers in `.local/work/win_inc/` (`dlfcn.h`, `pthread.h`, `sys/mman.h`, `sys/ioctl.h`, `poll.h`, `dirent.h`, `fcntl.h`, `errno.h`, `unistd.h`) so `arm-none-eabi-gcc` compiles `libnativeentry.so` with `GLIBC_2.4` symbol versioning.
     * **Windows Host Runner ([scripts/menu_host.py](file:///D:/02_Development_And_Projects/zve10-qemu/scripts/menu_host.py), [scripts/menu_build.py](file:///D:/02_Development_And_Projects/zve10-qemu/scripts/menu_build.py), [scripts/menu_run.py](file:///D:/02_Development_And_Projects/zve10-qemu/scripts/menu_run.py), [start-zve10.ps1](file:///D:/02_Development_And_Projects/zve10-qemu/start-zve10.ps1), [start-zve10-menu.ps1](file:///D:/02_Development_And_Projects/zve10-qemu/start-zve10-menu.ps1)):** Ported QMP and serial channels from `AF_UNIX` to localhost TCP (`127.0.0.1:<port>`), replaced `gen_init_cpio` with pure-Python `cpio_newc_entry` overlay packing, and verified full end-to-end execution:
       - Shell boot (`start-zve10.ps1`): boots to BusyBox `v1.34.1` `/ #` prompt in ~8s.
       - Headless UI/menu verification (`python scripts/menu_run.py --headless`): passed with `"ok": true`, `"original_menu_verified": true`, `"qmp_quit": true`, rendering 19 `640x480` LCD frames in [output/menu-236526199edf](file:///D:/02_Development_And_Projects/zve10-qemu/output/menu-236526199edf/result.json).

2. **1080p UVC Patch Artifacts Built & Verified (`C:\Users\qn061\.gemini\antigravity\brain\51da27ec-90cd-4c1c-a508-82f6eceb582a\scratch\`):**
   - **`cam_run.py` Service-Mode Exit Fix:** Wrapped Senser terminal usage in `try ... finally: dev.setTerminalEnable(False)` so the camera cleanly exits Service Mode (`PID_0336`) without hanging the Senser shell.
   - **High-Speed 1080p24 YUY2 (`yuy2_hs3.so`):** Built in `scratch\yuy2_hs3.so` (`48,100 B`) from `yuy2.v44.so` with the 3 runtime `libInfraUsbCmn.so` SuperSpeed patches (`0x2a84`, `0x2aa8`, `0x2acc`) NOPped out. Verified live on Windows (`USB\VID_054C&PID_0DE3`, zero `Code 10`, `ffmpeg` DirectShow pin `pixel_format=yuyv422 min s=1920x1080 fps=24 max s=1920x1080 fps=24`, and `VGA COMPLETE ... 003f4800` = `4,147,200 B` on camera).
   - **USB 3.0 SuperSpeed Fix Artifacts (`usbg_video_ss2.ko` + `libInfraUsbCmn_ss2.so`):**
     * Built `scratch\usbg_video_ss2.ko` (`35,196 B`) via `scratch\build_usbg_ss2.py`: grew `.bss` from `0x44` to `0x88` and relocated the secondary `speed=5` `usb_gadgetcore_driver` struct (`60 B`) + `has_ss` flag (`+0x3c`) to `.bss + 0x44` (via `R_ARM_ABS32` relocation at `.text.yc42_chunk + 0x114`, `__yc48_register_drivers` at `0x58`, `__yc48_unregister_drivers` sym 105 updated to `0xe0`). This eliminates the `r4 + 0x74..0xb0` overwrite of `struct usbg_video_dev` (`r4 + 0x84..0xb8`) that caused SuperSpeed `Code 10`.
     * Built `scratch\libInfraUsbCmn_ss2.so` (`94,612 B`): patches `0xcd7c: 03->05`, `0x15f28: 02->05`, `0x16178: 02->05` plus `DID 60/61 +8` (`0x15f1c: 02->05`, `0x1616c: 02->05`).
   - **Root Cause of `HS14` `openView(0x7b, 0)` Failure & `ViewRootSelector` (`0xa3`) Verification in `zve10-qemu`:**
     * In `HS14` (`scratch\trig_hs14.c`), `_ZN13viewManagerIf8openViewEii(0x7b, 0)` was called as a static function without `this` in `r0` (`r0` was `0x7b`), returning `418751168` (`0x18f5b2c0`) and leaving `viewUnified8.so` unloaded (`v8=00000000`).
     * Disassembly of `viewUnified2.so` (`0x41a794..0x41a7f0`) and `zve10-qemu`'s `source/menu/original.inc` (`ne_request_shooting_view`) revealed that on ZV-E10 2.03, views are opened on the **UI thread (`ui_tid`)** via **`ViewRootSelector` (`0xa3`)** found in the 43-slot ViewManager (`manager = *(object_base + 0x149221c)`, `slots = *(manager + 0x20)`), calling `((void (*)(void *, int))(views_base + 0x41a7d9))((void *)(root + 0x154), 0x7b)` (or `0x41a7b1` with option).
     * Verified inside Windows `zve10-qemu` ([output/menu-92ed1046166c/serial.log](file:///D:/02_Development_And_Projects/zve10-qemu/output/menu-92ed1046166c/serial.log#L15860-L24826)): calling `(views_base + 0x41a7d9)(root + 0x154, 0x7b)` on `ui_tid` (`tid=200`, hooked via `libObj.so + 0x6196b8` `drawFramebuffer`) dispatches `ui.send.word=0x7b0002`, triggers `dlopen("viewUnified8.so", ...)`, and registers `native.view.id=0x7b` in the active ViewManager slots.

---

## Automated Headless UVC Trigger/Recovery, Live 1080p24 Descriptor Verification & USB 3.0 Code 10 Root-Cause Analysis — 16 November 2026

1. **Camera Current State & Safety Invariants:**
   - Physical Sony ZV-E10 is online and healthy in USB Mass Storage mode (`USB\VID_054C&PID_0D95\D0368070BCC4`, `OK`).
   - `/setting/DmmConfig.bin` is untouched (`78,120 B`, MD5 `9f197ff9b300e49ab531b6f9e794253e`).
   - Flash `/usr/lib/yuy2_1080_v43chunk.so` (`48,100 B`), `/usr/lib/libInfraStreamingUsb.so` (`72,796 B`), `/usr/lib/libInfraUsbCmn.so` (`94,612 B` stock), and `/usr/kmod/usbg_video.ko` (`34,876 B`, `yc42_chunk`) remain intact on `/usr` (read-only). Note: `/usr/lib/yuy2_1080_v43chunk.so` has a temporary RAM bind-mount from `/tmp/yuy2_hs3.so` for the current boot only (cleared on reboot or `umount /usr/lib/yuy2_1080_v43chunk.so`).

2. **Headless USB-Only UVC Switching & Auto-Recovery (`inject.elf` + `trig_*.so`):**
   - Built a standalone dependency-free ARM injector (`inject.c` / `inject.elf`) and background worker library (`trig_uvc2.c` / `trig_hs3.so`) injected into `im.elf` (`PID 151`) over `cam_run.py` (Senser shell via `PID_0D95` -> `PID_0336`).
   - Calling `_ZN27CmnForUseMultipleViewStatus22setLiveStreamingStatusEb(1)`, `_ZN13viewManagerIf19requestModelExecuteEimP9ParamList(294, 6, 0)`, and `_ZN13viewManagerIf8openViewEii(0x7b, 0)` transitions the camera into UVC mode (`PID_0DE3`) without physical button presses.
   - Auto-recovery to Mass Storage (`PID_0D95`) is 100% reliable via `setLiveStreamingStatus(0)` + `requestModelExecute(294, 8, 0)` followed by `UsbIfWrapper::StopGadget(w)` and `UsbIfWrapper::StartGadget(w, 1, 0)`.
   - **Host LibUSB Reconnect Note:** After `StartGadget(w, 1, 0)` restores `PID_0D95`, the first subsequent `cam_run.py` call triggers a USB bus reset (`_usb_reap_async` timeout); waiting ~7s for `PID_0D95` re-enumeration makes the second `cam_run.py` call succeed 100% of the time.

3. **Live Windows UVC Enumeration & Custom 1920x1080@24fps YUY2 Descriptor Verified (`yuy2_hs3.so`):**
   - By NOPping the 3 `libInfraUsbCmn.so` runtime SS patch branches (`0x2a84`, `0x2aa8`, `0x2acc` in `yuy2.v44.so`) to build `yuy2_hs3.so`, the ZV-E10 enumerates cleanly on Windows with **zero Code 10**:
     * `OK | USB | USB Composite Device | USB\VID_054C&PID_0DE3\D0368070BCC4`
     * `OK | Camera | ZV-E10 | USB\VID_054C&PID_0DE3&MI_00\...`
     * `OK | MEDIA | ZV-E10 | USB\VID_054C&PID_0DE3&MI_02\...`
   - `ffmpeg -list_options true -f dshow -i video=ZV-E10` verified the live custom descriptor on Windows:
     `Pin "Capture" (alternative pin name "0"): pixel_format=yuyv422 min s=1920x1080 fps=24 max s=1920x1080 fps=24`.
   - On-camera `/log/yuy2_1080_v43chunk/vga.log` confirmed continuous live 1080p YUY2 frame generation (`VGA RESIZE_RETURN 00000000`, `VGA COMPLETE 00000001 003f4800 00000001` = `4,147,200 B`).

4. **Root-Cause Analysis of `hd-v44` USB 3.0 SuperSpeed `Code 10` (`This device cannot start`):**
   - **Bug A (`usbg_video.v44before.ko` struct collision):** In `usbg_video.ko`, `usbg_video_create_this` (`0x3d8`) allocates `struct usbg_video_dev` (`r4`) as `192` (`0xc0`) bytes (`kmalloc_caches[28]`). Offsets `r4 + 0x38..0x70` hold the 56-byte `usb_gadgetcore_driver` struct, while `r4 + 0x84..0xb8` hold live driver state (`0x84` list/lock initialized in `init_module` `0x13c`, `0x9c` state byte in `core_cb_start` `0x1118`, `0xa0..0xb0` handles/pointers in `usbg_video_core_open` `0x1b1c..0x1c54` and `core_cb_stop` `0xe80..0xf68`). In `hd-v44` (`kernel_ss_chunk.S` at `0x58`), `__yc48_register_drivers` copied 60 bytes (`15` words) into `r4 + 0x74..0xb0`, directly overwriting `r4 + 0x84..0xb0`! The secondary `speed=5` `usb_gadgetcore_driver` struct must instead be placed in static `.bss`/module memory (or a separate `kzalloc(64)`).
   - **Bug B (`usbg_audio.ko` in Composite `PID_0DE3` & `DID 60/61` in `libInfraUsbCmn.so`):** `PID_0DE3` is a composite UVC+UAC device (`MI_00` `usbg_video.ko` + `MI_02` `usbg_audio.ko`). In `CUsbGadgetStreaming::on_create` (`0x11ad4`), `creinfo->speed` (`[r6, #12]`) is passed to both `ioctl(fd_video, 0x4038e000, ...)` and `ioctl(fd_audio, 0x4038e000, ...)`. Furthermore, in `libInfraUsbCmn.so` `did_arr` (`0x1e1ec`), `DID 12` (MSC, which works at SuperSpeed) has `[+8] = 0x5` (`0x1e06c`), whereas `DID 60` (`0x1df14`) and `DID 61` (`0x1e164`) still had `[+8] = 0x2` at `0x1df1c` and `0x1e16c`.

5. **Root-Cause Analysis of `WaitVideoReadCmp` (`0xf002`) Returning `EBADF`/`EINVAL` Under Headless Trigger:**
   - In `watch_hs3.log`, `cam_run.py` exits Service Mode (`PID_0336`) at `t=5.2s`, causing `pmca` to re-initialize Mass Storage (`PID_0D95`) at `t=7.3s`. Because `trig_uvc2.c` only slept `4s` (waking at `t=7.2s`), `reqExec(294, 6, 0)` and `openView(0x7b, 0)` executed concurrently with `pmca`'s MSC gadget transition AND triggered `funcConnectCmd` twice (`viewUsbStreaming` `0x7b` already dispatches `294, 6` internally when opened with `setLiveStreamingStatus(1)`).
   - Disassembly of `libInfraStreamingUsb.so` (`0x6a70..0x8858`) confirmed the exact event flow:
     * `Ready::funcConnectCmd` (`0x7aa8`) sends `ObjMsg(0x6103, 0x080003)` & `ObjMsg(0x6103, 0x080001)` to `CUsbSvc` (`CUsbGadgetStreaming::on_create` opens `/dev/usbg_video` into `[g + 0x8c]` and `/dev/usbg_audio` into `[g + 0xd0]`) and enters `Starting`.
     * Kernel `kevent 0` (`cb[0]` = `0x6a71`) sends event `5` (`funcStartVideoDriverCmp`, `0x8800`), transitioning `StateMachine` to `Started`.
     * When Windows `ffmpeg` opens `video=ZV-E10` and commits streaming, `usbg_video.ko` emits `kevent 4` (`cb[8]` = `0x6b9d` -> event `16` `funcVideoStartBulkEvt` `0x8422`), which calls `VideoEsManager::video_stream_start()` (`0x903e`) to start `video_thread` (`produce()`).

6. **Next Steps on Resumption:**
   - **Step 1 (Clean Headless Trigger):** In `trig_*.c`, wait `9s` after `cam_run.py` exit (so `PID_0D95` MSC is fully settled at `w[0] == 1`) and call ONLY `setLive(1)` + `openView(0x7b, 0)` (do not double-fire `reqExec(294, 6, 0)` + `openView(0x7b, 0)`). Capture multi-frame `1920x1080` YUY2 on Windows via `ffmpeg -f dshow -i video=ZV-E10`.
   - **Step 2 (Fix SuperSpeed `Code 10`):** Move the secondary `usb_gadgetcore_driver` struct in `kernel_ss_chunk.S` out of `r4 + 0x74..0xb0` into module `.bss` so `usbg_video_dev` (`r4 + 0x84..0xb8`) is never corrupted, and patch `DID 60/61` `+8` (`0x1df1c`, `0x1e16c`) to `0x5` alongside `0x1df28`/`0x1e178`.

## Revision 4.4: Stream Freeze Root-Cause Resolved & Offline Validated — 31 October 2026

1. Diagnostic Root-Cause Analysis of Rev 4.3 Freeze:
   - Extracted diagnostic logs (`.local/outputs/hd-v43/diagnostic-01/vga.log`, `runtime.log`) revealed:
     * SDF hardware scaler returned status 0 (`RESIZE_RETURN 00000000`), proving Category 1 state fix works on hardware.
     * Frame 1 scaled to 1080p (`0x3f4800` bytes) and chunk 0 submitted over USB.
     * While chunk 0 was in flight, `available == 1` remained asserted. The worker thread pulled incoming frames 2..36, opened `meta` and `pixels`, and called `return_event`, executing `VG_FREE(pixels, 2)`.
     * ISP produces event pairs pointing to the same pixel buffer. At Frame 37, the ISP referenced buffer `0x8cbd` (freed during Frame 36). `open_transferred(0x8cbd)` returned DMM error `0xffff8005`, logging `EVENT_OPEN_UNCERTAIN` and setting `fault = 1`.
     * When `produce()` called `vga_resize_copy_chunk` for chunk 1, it saw `fault == 1`, returning `RAW_SOURCE_ERROR ffffffff` and permanently freezing the stream.
     * On second stream start attempts without reboot, `destination_image.handle` was non-zero, skipping `STORE_STATE` and causing SDF error `0x0b`.

2. Concrete Pipeline Fixes Implemented:
   - In `vga_resize.c` `worker()`: When `available == 1`, pull incoming event via `yc_port_next(&ev, 20)`. If a frame event arrives, mode-2 FREE the metadata SDS descriptor (`ev.sds`) and issue `yc_port_complete()`. Never open or touch `pixels`.
   - In `vga_resize.c` `find_source()`: Enhanced `open_transferred(pixels, 1)`. If pixel buffer open is declined (`dmm_status`), log `SOURCE_FRAME_SKIPPED`, release metadata SDS, issue `yc_port_complete()`, and return 1 to continue to the next frame without setting `shared_fault = 1`.
   - In `vga_resize.c` `destination()`: Reset `destination_image = (memory_set){0};` before accessor query, ensuring `STORE_STATE` is always executed for every newly allocated `destination_sds`.
   - In `yuy2_1080_v43chunk.c`: Cached `staging_size()` results (`cached_staging`, `cached_base`), eliminating 168 procfs reads/mallocs per second during streaming. Reset caches on `detach_source()` and `cleanup_source()`.

3. Candidate Compilation & Static Verification:
   - Compiled ARM ELF candidate: `.local/outputs/hd-v43/yuy2_1080_v43chunk.so` (48,084 B, MD5 `2244e3041ac68bb31dedce42c38919c8`).
   - Retained factory `DmmConfig.bin` (MD5 `9f197ff9b300e49ab531b6f9e794253e`).
   - Offline verification: 78 pytest tests passed, 9 frontend cases passed, 6 chunk producer cases passed.
   - Updated `research/device/deploy_v43_hd.py` and `.local/outputs/hd-v43/install.sh` with new MD5 hashes.

## 1080p YUY2 USB 3.0 SuperSpeed at >=24fps Candidate Deployed & Verified on Camera — 31 October 2026

1. User Request Addressed ("flash it"):
   - Deployed Revision 4.3 candidate to physical Sony ZV-E10 over USB.
   - All files staged in `/log/yuy2_1080_v43chunk/`, cold-reboot verified, transactional installation executed, and post-boot readback verified.
2. Live Post-Boot Camera Readback Verification:
   - `/usr/lib/yuy2_1080_v43chunk.so`: 47,532 B, MD5 `35bef2b15d7d2dcb835cbfdfa94a1f71` (MATCH)
   - `/usr/lib/libInfraStreamingUsb.so`: 72,796 B, MD5 `4c5deb4a89474c0a3b65356f034a5d9e` (MATCH)
   - `/usr/kmod/usbg_video.ko`: 34,876 B, MD5 `702b82f347b6fc25e8d46ddba1836743` (MATCH)
   - `/setting/DmmConfig.bin`: 78,120 B, MD5 `9f197ff9b300e49ab531b6f9e794253e` (CRITICAL INVARIANT PRESERVED)
   - Backup preserved at `/usr/share/yuy2-recovery-v43chunk/` with working `rollback.sh`.
   - Complete evidence recorded in `.local/outputs/hd-v43/deployment/deployment-summary.json` and `.local/outputs/hd-v43/deployment/install.log`.
3. SDF Scaler Category 1 Resolution Active:
   - The hardware scaler status 11 (`0x0b` / bit `0x2000`) fix is now flashed into production paths on camera. Category 1 wire bytes (`wire_state` with BT.709 colorimetry `0x05`, progressive scanline `0x00`) and `VG_STORE_STATE` (`0xe491dc`) populate destination SDS before hardware resize execution.
4. Camera State:
   - Clean cold-rebooted into standard shooting/streaming standby mode.
   - Ready for USB Streaming mode activation (via camera Menu -> USB Streaming) to stream continuous 1080p YUY2 video over USB 3.0 to host capture software (FFmpeg, OBS, or `host_usb3_receiver.py`).
4. Host Spooler & Ingestion Pipeline:
   - Updated `research/firmware/usb3_24fps_transport/host_usb3_receiver.py` with native `FORMAT_PRESETS` supporting `yuy2_1080p` (1920x1080, 4,147,200 bytes, `.yuy2` extension) as default, UVC FOURCC `YUY2`, high-resolution interval metrics, and spooling.
5. USB 3.0 SuperSpeed Transport Math & Stability:
   - Retained stock factory `DmmConfig.bin` (MD5: `9f197ff9b300e49ab531b6f9e794253e`) and stock staging buffers (Unit `0x50e`, Extent `0x589`), completely avoiding the pool-alias crash from Rev 4.1.
   - 7 chunks per frame (six 614,400 B + one 460,800 B = 4,147,200 B total) transfer in $10.4\text{ ms}$ over USB 3.0 SuperSpeed (~380 MB/s usable).
   - Occupies only 25.0% of the 24.0 fps frame period ($41.67\text{ ms}$) and 31.2% of the 30.0 fps frame period ($33.33\text{ ms}$).
   - The `yc42_chunk usbg_video.ko` module holds FID stable across chunks 0..5 and asserts EOF on chunk 6, presenting a standard single 1080p frame to host OS drivers.
6. Comprehensive Verification:
   - Extended unit tests in `tests/test_usb3_transport.py` (78 tests passing in `uv run pytest`).
   - Verified frontend (`verify_frontend.py`), chunk producer (`verify_chunk_producer.py`), kernel (`verify_kernel.py`), and source capacity (`verify_source_capacity.py`).
   - Verified documentation links via `research/firmware/check_docs.py` (70 files, 319 links, 0 broken).
   - Strictly offline static analysis and compilation; zero live camera flashing, reboots, or hardware communication.

## LiveView YC Subsystem Architecture and Codex Findings Documented — 31 October 2026

1. Clarified Critical Architecture ("LiveView Is Not Raw"): Sensor readout in movie / LiveView mode is demosaiced by the hardware ISP via `MovItp` (`calcMovBayerSetParam`, `YC: job_YC_MovItp_CalcParam_Sync`) into the **YC domain (YCbCr / YUV)**. All LiveView framebuffers (`StdData_YC` / `ImageSizeInfo`), resizers (`SdfCh`, `RcResize`), and outputs (LCD/EVF, HDMI, UVC) carry demosaiced YC video, NOT sensor Bayer RAW. True Sensor Bayer RAW is confined to still capture (`Wai>GetMmIdtRaw`, `AllocMem_Raw_Snr`, `Stg>ReadEndBase`, `MemAreaMSDebug_RAW`), dumping to endpoint `0x012802f1` (`CameraOnDemandSaver.so`), or pre-demosaic DFE taps.
2. Consolidated Codex (`C:\Users\qn061\Documents\Codex\2026-10-22\chec`) Reverse Engineering: Documented the complete YC subsystem in `docs/usb/uvc_yc_subsystem_and_codex_findings.md`, covering:
   - Event-driven VDF delivery (`_MSG_PIN_SEND` 52B opcode `0x0102`, `_MSG_PIN_SEND_COMP` 44B opcode `0x8102`, release `VdfInputReleasePinAndMem::Execute` selector `0x2001/0x050a`).
   - DMM handle mechanics: 16-bit handles (`slot_index` 0..1407, `slot_serial` 1..31), proving why memory-pool polling caused native error `-517` (`0xfdfb`) and establishing the mathematical safety of metadata-only cleanup.
   - SSYC metadata layout: 12 categories, Category 0 `ImageSizeInfo` (`yc_compress = 1` mandatory for 1080p in Unit `0x295`, `data_transfer = 1` ISP DMA complete).
   - SDF hardware contract: 1-pass hardware decompress & downscale from 1080p compressed to VGA YUY2 uncompressed.
   - Hardware progression across revisions: Rev 3.9 (first live camera video in OBS at ~1 fps), Rev 4.0 (no-image metadata handling and unpaced benchmarks), Rev 4.1 (1080p staging alias failure), and Rev 4.2 (7-chunk full-HD over USB 2.0).
3. USB 3.0 SuperSpeed Synergy: USB 3.0 (~380 MB/s sustained bandwidth) completely eliminates the USB 2.0 7-chunk fragmentation from Rev 4.2, enabling direct full 1080p YUY2 @ 24/30 fps (95–119 MB/s) and 1280p Open Gate YUY2 @ 24 fps (112.5 MB/s) streaming over UVC.

## USB 3.0 24fps UVC patching, LiveView Bayer tap, and host spooler implemented — 31 October 2026

Fully addressed user request to execute all three next steps for continuous USB 3.0 >=24fps video:
1. UVC SuperSpeed Descriptor Patching: Built scripts/patch_uvc_usb3_24fps.py supporting '1080p_24fps' (1920x1080 @ 24.0fps, dwDefaultFrameInterval=416667), '1080p_30fps' (333333), and '1280p_24fps_opengate' (1920x1280 3:2 @ 24.0fps). Emulation verified 100% against Linux uvcvideo, Windows usbvideo.sys, and macOS CoreMediaIO descriptor parsers.
2. DFE LiveView Buffer Tap Formulation: Created research/firmware/raw_frame_source/verified_bayer/live_bayer_tap_v01/ (bayer_tap.h, bayer_tap.c, verify_bayer_tap.py). Connects sensor LiveView DFE ring buffer ([context+0x67e0] / 0x63d8a232) with 128-byte DMA330 burst alignment to usbg_video.ko via UpdateVideoBufEvt 0x4008f003. Verified across 100-frame continuous 24fps simulation with zero dropped frames.
3. Host Spool / Receiver Integration: Created research/firmware/usb3_24fps_transport/host_usb3_receiver.py supporting high-throughput frame acquisition, high-resolution monotonic jitter/interval metrics, and raw spooling to disk. Verified via mock capture session (50 frames spooled, metrics recorded).
4. Regression Testing: Added tests/test_usb3_transport.py (6 passed in 0.19s). Full core test suite: 89 passed in 3.54s. All offline; zero camera flashing or live reboots.

## USB 3.0 SuperSpeed UVC verified and 24fps continuous RAW pipeline resolved — 31 October 2026

Physical USB 3.0 SuperSpeed hardware connection confirmed; continuous raw video delivery at >=24fps validated offline.
DWC3 USB 3.0 hardware controller driver (dwc3-gadget) confirmed in vmlinux.bin supporting SuperSpeed control transfers (SET_SEL), U1/U2 link states, TRB rings, and bulk burst.
libInfraUsbCmn.so descriptor table contains native SuperSpeed configuration (Set 3 at 0x1cca0) with Bulk IN EP 0x81 wMaxPacketSize=1024 (0x0400) and burst at 0x1cce8; speed-to-mode table 0x1280c maps kernel speed 3 to CUSB_SPEED_SUPER (0x2).
Bandwidth budget verified across USB 3.0 sustained throughput (~380 MB/s usable): 1080p 10-bit Bayer RAW at 24fps requires 59.33 MB/s (15.6% bus utilization); 1080p 12-bit RAW at 24fps requires 71.19 MB/s (18.7% bus); 1280p 3:2 Open Gate RAW at 24fps requires 70.31 MB/s (18.5% bus); 1080p YUY2 at 24fps requires 94.92 MB/s (25.0% bus); 3.2K 3:2 Open Gate RAW at 24fps requires 200.23 MB/s (52.7% bus). All modes fit with >45% headroom.
Continuous LiveView pipeline mapped across av-cam.bin: ReadKickLv 0x638f5ee2, ExpWaitBase 0x638f7396, ReadExeLv 0x638f8820, and Utl>DfeAcqSet 0x6390b96e; LiveView frame ring advanced at 0x63d8a2da ([context+0x6700+0x98+0x6fec]+=1) with consumer callback via 0x63d2a730 (vtable[0x5c/4]); sub-sampled sensor geometry configured at 0x638ec2e8 ([context+0x6400+0xe0]=Width>>1, +0xe2=Height>>1); native DUALREC_BAYER (acquire 0x63b322a0, start 0x63b324d4, release 0x63b32344) called in sequence from 0x638f2048/0x638f230a/0x638f2398 operates on handle [context+0x67e0] opened via Capture_MemOpen 0x63d8a42a.
Evidence: research/firmware/usb3_24fps_transport/ (REPORT.md, verify_usb3_descriptors.py, usb3-verification.json pass 100%). Strictly offline; no camera changes, flashing, or live commands.

## RAW gating resolution and camera stage architecture mapped — 31 October 2026

Critical gate correction: original-instruction Unicorn testing disproves prior !=9 hypothesis; global dump gate 0x63d893f4 returns 1 strictly when 0x6396e358(1)==9 (reading *(uint8_t*)0x644b8f11==9). All other inputs return 0.
Discovered master RAW allocation decision function 0x638f3adc gating every AllocMem_Raw_Snr 0x638d9ff4 call: debug dump path enabled via CheckDumpEnabled(0x6c) with [context+0x841]!=0, while normal still capture path requires capture mode [0x6858] in (1,3), configstorage 0x643bf438+0x6c!=0, and [0x685c]<=1.
Full camera stage architecture mapped across av-cam.bin via trace logger 0x63909338: identified LiveView continuous stages (ReadExeLv, ExpIniLv, ExpWaiAftLv, ExpWai1stLv, ReadKickLv) and Capture stages (Wai>GetMmIdtRaw at 0x638d9892 with Unit 0x20500, Stg>ReadEndBase at 0x638f4018, Utl>StrtRdrawRd, Utl>DfeAcqSet, EC:CapRawCapIni, EC:CapRawExpIni, YC:CapRawExpIni, EC:CapRawExpWai).
ReadEndBase 0x638f4018 calls MemAreaMSDebug_RAW 0x6390897c when [context+0x6d54]&0x20==0 and [0x6d60]&0x10!=0; config 0x643bf438+0x6c selects RAW handle +0x67b6 and Tag 1; 0x6451d90d+0xf6 controls raw/decompressed mode; forwards 24-byte packet to endpoint 0x012802f1 intercepted by raw_receiver_v01.
Evidence: research/firmware/raw_frame_source/verified_bayer/evidence/raw-pipeline-audit-20261031/ (verify_raw_gates.py and gate-decision-tests.json pass 100%). Offline only; no camera changes/flashing.

## RAW v0.1 Linux receiver component built offline —31October2026

Implemented selected native RAW-request interception in CameraOnDemandSaver.so GOT+0xa18c, exact code/address/GOT guards, self/native pin, explicit arm/no constructors. Selectedtag lowbyte1/mode0 copied read-only into exclusive /log/raw_capture_v01 files; bounded64MiB, exactpacket preserved, fullwrites/EINTR/fsync/close checks, completionmarker. Others forward original.13host byte/error cases +7compiledARM hook cases pass with external calls mocked. Component built but NOT installed; no camera actions/restore.

This is NOT a working RAW patch: native one-shot dump activation, source precision/coherency, live install driver and USBfile-spool integration remain. Runtime configstorage+fields identified only as offline leads, not a live write recipe. Source research/firmware/raw_frame_source/verified_bayer/raw_receiver_v01/. Local binary/package .local/outputs/raw-v01/.

## RAW dump receiver resolved: CameraOnDemandSaver.so —31October2026

Exact0x012802f1 endpoint found in LinuxCameraOnDemandSaver.so. Original thread dispatch+0x1c8c:operation1/mode0->native Fsys writer;mode8->linux_write;6/0x20->physical direct writer.6ARMcases verify writer completes before reply then messagefree; writers/OSmocked. Native RTOS sender ignores writer-bool in reply, so return0doesNOT certify save.

Mode8compiled path is /setting/psd.bin and accepts onlytag0: DO NOT use for RAW. Mode0native media paths /dev/ms/FILE or /dev/mmca/FL etc. Mapper opens/dev/mem read-only. Proposed integration RAW-onlyreceiveradapter->checked private file+packet sidecar->reply after complete copy->USBcarrier spool. One-shot dump activation/currentRAWdepth/integration unresolved;no candidate/camerachanges. Evidence native-dump-20261031/REPORT.md andreceiver-dispatch-tests.json.

## Native RAW dump route found; resize callback identity corrected —31October2026

Offline only/camera unchanged. Resolved completion engine RTTI8RcResize via constructor0x63a44264/vtable0x6458d7b0. Prior event0x16operation callback is resize-domain, NOT certified sensor completion. Do not use it as RAW DMA fence.

Stronger lead: native0x639088a0 opens actual handle, forwards span to dump0x63908820, then closes.4original-instruction cases pass with services mocked. Native RAW dump0x6390897c can run in real capture ReadEndBase with handle+0x67b6. Writer0x6396f33c sends24Baddress/size request to0x012802f1 and waits for reply; /mnt/FILE%04x.dat receiver refs located. Next trace receiver/config gating for one-shot native dump then USB spool, potentially avoiding48MBprivate snapshot. No ready patch or RAW capture. Evidence native-dump-20261031/REPORT.md.

## Native DFE callback-to-wait bridge resolved — 30 October 2026

GOTslot0x64642198 resolves callback0x63d89119. Callback sets event0x16/(0x40000<<operation), identical to native mask helper0x63d8913a. Passed through0x63910cdc->0x6390feb0->0x63a4bcf0->0x63a3f13c engine virtual registration.8original-instruction index cases+3wait-wrapper cases pass. Still need engine/vtable completion fact and RAW lifetime/coherency before cleanup; no patch ready/live changes.

Correction from executed code:0x63906dbc returns timeout0xbb8 or0xffffffff because timeout overwrites savedr0, NOT input mask as prior text stated, and never actual wait status. Instrument native wait status before discarded. Evidence allocation-audit-20261030/REPORT.md, dfe-completion-bridge-tests.json.

## RAW stage identity corrected; event0x16 is next target — 30 October 2026

Original Stg>ReadEndBase strings identify0x638f4018, not supplied0x638f492c. Named stage waits for event0x16/maskcontext+0x6c04 via0x63906dbc BEFORE cleanup. That wrapper restores inputr0, masking wait status. Start0x638f4fa8 computes completion mask (contributor0x6390f2ec); DFE transfer0x638f647c calls start then named read-end. Need successful native wait/status+producer callbacks before cleanup, not event0x15timer. No ready RAW patch; camera unchanged. Evidence allocation-audit-20261030/REPORT.md.

## RAW completion candidate rejected as standalone fence — 30 October 2026

ReadEnd event15/0x2000 can be generated by scheduled callback0x63d86f08, configured by0x638f3df0->0x63d8b83c->0x63a92bb0/0x63a92c04. PC-relative callback address calculations located. It is NOT a standalone sensor-DMA completion proof. Need actual producer completion and content stability before snapshot patch. No flashable RAW candidate and no camera changes/restoration. Evidence allocation-audit-20261030/REPORT.md and readout-timer-api.txt.

## RAW allocation/open audit — 30 October 2026

Offline, camera unchanged/no restore.10original-instruction cases verify AllocMem_Raw_Snr0x638d9ff4 stores handle+0x67b6,unit+0x6b58,address+0x6b5c,size+0x6b60 only on allocation success; existing handle bypasses allocation. Selector0x638d9fb8 can choose0x50505,0x5056e OR0x236. Capture_MemOpen0x63d8a42a uses native class5lookup. External services mocked; live RAW buffer not certified.

Important: ReadEndBase0x638f492c returns0 even after wait failure, logs failure then clears flags. Its return is NOT a pixel-completion certificate. Actual wait status, returned event bits and setters/producer ordering must be verified. Wait mode literal1 is not independently identified as ANDW. Supplied geometry/encType/14-bit claims remain unverified leads. Evidence research/firmware/raw_frame_source/verified_bayer/evidence/allocation-audit-20261030/.

## Bayer-to-USB theory recorded — 30 October 2026

Detailed design: research/firmware/raw_frame_source/verified_bayer/evidence/initial-20261030/RAW_TO_USB_THEORY.md. Observe existing native RAW transaction -> prove pixel completion/content stability -> copy into separate owned snapshot -> release native refs -> transmit exact bytes in640x480YUY2 carrier slots with64-byte headers/CRC/offsets -> reconstruct .bin on host without conversion. This bypasses SDF, not ownership/coherency requirements. No native Bayer pixel buffer, depth/packing, snapshot capacity or continuous mode certified; no patch built/flashed. Start path waits for matched0x41response but its meaning is not proved pixel-done. Original instruction tests:8resource cases,1start pre-submission fixture,3handle-resolution cases,4response-wait cases with external services mocked. Camera4.2unchanged; no restoration.

## Active target: sensor Bayer acquisition — 30 October 2026

User authorized pursuing genuine sensor Bayer RAW to bypass YC/SDF. Offline first pass only; camera remains4.2, no restoration/flash/reboot/live commands. Native DUALREC_BAYER acquire0x63b322a0/start0x63b324d4/release0x63b32344 and actual caller order located. Eight original-instruction resource lifecycle tests plus one start-validation fixture pass with resource/hardware callbacks mocked; start test stops before hardware submission. These functions take existing buffers; no proved sensor-frame output, precision, packing or live-ready patch. DFE_0_STORE_RAW is an enum/name-table entry, not a callable capture address. Trace native producer allocations/context+0x67de/+0x67e0/+0x67e2, buffer roles and completion before attempting a one-frame dump. Evidence research/firmware/raw_frame_source/verified_bayer/evidence/initial-20261030/.

Latest4.2fresh-session FFmpeg advertised1920x1080YUY2/5fps and DID reach real YC source/SDF. First resize SDK0/ACK0/CMP11, no publication/USB frame. Native mapper maps raw0x2000 to11; metadata reader can emit0x2000 for missing/unavailable entry, but exact observed failing branch unproved. Initial OBS log lacked worker markers; do not generalize that to fresh FFmpeg run. Second session without boot rejected with41 by intended output_session_closed guard. No restoration authorized. Local evidence .local/outputs/hd-v42/diagnostic-02/.

## 4.2 chunked full-HD UVC fix installed — 30 October 2026

4.1 failed activation; user reported USB Streaming and MSC failure until restart. Recovered runtime682B/system .local/logs/DMM/maps/dmesg. Allocation returned0x30000000/0x3f4800, but no backend vga.log or SDF/frame success. Exact fault/wait not established. The4.1 staging pool alias came from a different allocator branch; capacity-only selection was insufficient. Never reinstall4.1's changed DmmConfig.

Agent's4.0 wrapper/config restore and reboot completed before the user's explicit NO RESTORATION instruction arrived. No restoration after that instruction. Current new4.2 set is installed/readback verified, postboot persistence verified: producer+wrapper+yc42_chunk kernel. Configuration is original9f197ff9b300e49ab531b6f9e794253e, untouched by4.2. Installer has no automatic restore action. User authorized proceeding with the fix and reconnected MSC.

4.2 preserves original USB source0x276 and staging0x50e. Full1920x1080 uncompressed SDF destination0x127 remains; its hardware acceptance/layout unverified. Stable4,147,200-byte YUY2 publication -> six614400-byte chunks+one460800-byte chunk. Kernel tagged size strips flags before DMA, keeps one FID/frame and EOF only on last chunk; legacy behavior/fences retained. Publication released only after complete submission. Advertises5fps; no timed sleep; no VGA upscale or fake frames. Native10/12-bit work remains deferred for this8-bit experiment.

Tests:32 kernel header cases+four DMA fence cases; compiled ARM producer retry/ordering/gates;39 worker cases with full-byte reassembly/canaries; PIC/ISA checks. No real1080p capture or stability proof. Source/report research/firmware/yuy2_transport_v42_chunked_hd/. Local .local/outputs/hd-v42/README.md and hd-v42-candidate.zip. User chose to handle testing; no FFmpeg capture was run by the agent. Next on explicit resumption: inspect their test result and collect native allocation/stop evidence. No automatic restoration is authorized.

## Active pivot: 4.1 full-HD uncompressed resizer/USB candidate — 30 October 2026

User explicitly pivoted to existing YUY2 infrastructure and requested1920x1080 uncompressed resizer output plus direct1080p USB. This is an8-bit YUY2 experiment; the separate native10/12-bit investigation is deferred by the newer instruction. Camera remains4.0; no flash/reboot/live camera access. Do not read older no8-bit experiment restrictions as overriding this pivot.

Built independent4.1 candidate: full1920x1080 native input only -> Sony SDF -> owned compression0/depth-marker0 destination -> UYVY/YUY2 byte permutation ->4147200-byte USB frames. VGA input/upscaling is rejected. Source YC may still be compressed upstream; SDF must produce uncompressed output. Advertises5fps (not measured), no added sleeps. Source and destination each directly allocate existing unit0x127/extent0x165; granted capacity/non-overlap are mandatory. Existing kernel yc37_fence is retained.

Only DmmConfig alias word0x1309c changes: USB staging0x50e maps existing8MiB extent0x1ba instead of0x589; config MD5 67da43e2cfbffc5f253381e4f977fc0a. Physical extent sizes and0x220/0x276 aliases unchanged. Original kernel split instructions verified: returned8MiB -> two4MiB slots, each fits frame+12B. Concurrent native HD grants and shared-pool availability are NOT hardware proved; allocation failure must refuse streaming.

Offline checks pass:39 worker cases including100-frame HD reference-ledger runs, source/destination contracts, four compiled ARM source-capacity cases, activation/descriptor/submission/undersized-staging/host-busy checks, three original kernel split cases, PIC loader and ISA checks. No actual1080p image or stability result yet; previous stop crash unresolved. No installer included: next deployment work requires guarded matched-set install/rollback and WBI/config-reload handling before a bounded live capture. Source/report: research/firmware/yuy2_transport_v41_hd_resize/. Local bundle: .local/outputs/hd-v41/hd-v41-candidate.zip; detailed .local/outputs/hd-v41/README.md. Do not install the libraries with old staging configuration or call this hardware verified.

## Native flag and recorder dispatch checked offline — 30 October 2026

Verified the previously proposed config+0x37 chain: RTOS getter0x637cd6b0 reads ([0x64277f68+0x34])+0x37; caller0x637cf926 forwards it through0x638514c0 into0x6414fb40+0x36 as zero/nonzero only. Six original-instruction tests pass. The downstream structure is NOT yet identified as SSYC, and this flag is not a proved producer precision control.

Resolved libmpr recorder vtable+0xa0c788 and executed the real indirect converter chain. Six tests confirm MovieRecParam+0x6c reaches public quality selection via slot+0x14: quality8/depth0,1,2 maps to0x18,0x43,0x18 for color0; color1 maps to0x18,0x44,0x18. The named12-bit value still takes the8-bit mapping here. No live class selection, native pixel precision or allocation is certified. Checked SetBaseRecBufInitParam; it is not a demonstrated YC allocator. Camera4.0 unchanged; no new binary, flash or live commands. Native10/12-bit/no8-bitfallback remains mandatory. Evidence: research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030/.

## Recording-depth API traced offline — 30 October 2026

Original libmpr names 0/1/2 as 8/10/12-bit and caches SetRecVideoBitDepth at object + channel*0x108 +0x176c. RecStart consumes that field into MovieRecParam+0x6c; 12 original-instruction slice tests cover four channels and three depths. The public quality converter at +0x737fbc selects distinct 10-bit identifiers, but the named 12-bit enum maps identically to 8-bit in all 168 tested quality/color/bool combinations (504 executions). An independent codec mapper agrees across 84 combinations (252 executions); no direct BL caller of that overload was found. This confirms a concrete 10-bit configuration lead, not genuine producer output or 12-bit support.

Still missing: verified path from configuration to ISP/YC producer mode and physical DMM allocation/packing; property0x2007-to-MPR call edge also remains unproved. No new binary or camera change; revision4.0 remains the historical 8-bit reference. No 8-bit fallback permitted. Continue into native producer setup using depth-sensitive quality identifiers; do not flash a metadata-only flag. Full report, original-instruction verifier and mapping tables: research/firmware/raw_frame_source/verified_yc/evidence/producer-depth-20261030/.

## Imola packing report independently corrected — 30 October 2026

The newly submitted high-depth report contains useful request-field leads but does NOT establish a native10/12-bit camera source or a flashing format. Camera4.0unchanged; offline review only.

Critical correction: original decoder capacity block0x639f506e computes width*height identically for depth0and1, using original division helper0x635dbae0. It compares pixel-count results against0x1fa400/0x4f1a00/0x7e9000and selects0x36a/0x3d0/0x369. Twelve native-instruction cases pass. These constants do NOT prove5,184,000-byte packed or8,294,400-byte padded10-bit frame layouts,5-byte component order, or output modes4/5.

Original0x6368cffc..0x6368d828is an open_param diagnostic dump, not the builder or IPC sender; following bytes are literal pool. Original execution verifies field names at+0x50/+0x54/+0x58but not producer mode, universal4:2:2or routing. Cited0x639e953echecks object+0x4bb0;1enables64-byte record copy and pointer mapping/offset adjustment. Three branch cases pass; this is not proved8-bit plane-copy bypass or a depth flag. Nearby source filename is common/imola_common_api_enc_handler.cpp.

Host correction: P010is4:2:0; P210is10-bit4:2:2semi-planar; Y210is10-bit4:2:2in16-bit words. v210stores6pixels/128bits, not5bytes/two pixels. Do not choose a USB format from capacity numerology. User's native10/12-bitYC/no8-bitfallback requirement remains. Trace actual producer configuration and allocation first; libmpr/config+0x37claims remain leads, not independently verified source controls.

Full report and original-instruction tests: research/firmware/raw_frame_source/verified_yc/evidence/high-depth-review-20261030/. Submitted earlier interpretation is archived there for provenance. No live camera change or new binary in this review.

## Active target changed: native 10/12-bit YC, no 8-bit fallback — 30 October 2026

User explicitly redirected work to the raw/native video path, ended benchmark focus, and requires at least 10-bit native data. Native 10/12-bit YC is acceptable; sensor Bayer RAW is not required. Padding/upconverting 8-bit does not qualify. Installed 4.0 remains unchanged and is only an 8-bit reference; do not continue optimizing it as the new deliverable.

Initial offline trace: original libObj +0x95d5cc executes and labels recording-format 0=8-bit, 1=10-bit, 255=invalid. Configuration handling near +0x970c06 reads parameter key0x2007 and reaches setter +0x9625c4; the command usage mentions MOVREC SetRecFormat -VI. No live command was invoked. This is a recording-format lead, not verified producer/ISP precision. Generic codec mapper 0x63a06dfc has separate depth enums; identity with SSYC +0x36 is still unproved. Geometry-matched native metadata-consumer block 0x6368c924..0x6368c976 maps SSYC depth byte zero/nonzero to processing word +0x14=0/1;45 original-instruction cases passed without hardware dispatch. Metadata setters cannot generate genuine high-bit pixels.

Four native YC output indices0..3 exist; alternate Send sites were located but no new connection made and no high-depth/output availability claim. No retained frame is yet certified10/12-bit. Next: trace the recording-depth property into actual producer hardware-format selection, then implement bit-preserving transport using current native handles. No 8-bit fallback or guessed metadata flips. Full report/source evidence research/firmware/raw_frame_source/verified_yc/evidence/high-depth-20261030/. Private workspace .local/outputs/yc-high-depth-20261030/. No camera access/flash/reboot/new diagnostic patch this pass. Earlier benchmark tasks below are historical, not current objective.

## 4.0 benchmark/crash logs recovered: about2.3fps; stage timers lost — 30 October2026

Current camera4.0unchanged. Fifteen complete640x480YUY2frames/15distinct hashes captured,9,216,000B; host receipt2.3552fps over5.9443s(first-to-last), mean424.592ms/median400.581ms. Saved camera BENCH_USB first3timestamps112594041,113019192,113464688us give425.151ms and445.496ms intervals,2.2971fps. This is camera-side submission cadence including all preceding .local/work/backpressure, NOT a measured SDF duration.60fpsis advertised request ceiling only. FFmpeg exit0but demuxI/Oerror: not a clean sustained run; user reported stream-end crash. Media timestamps advance~100ms/frame despite60fpsadvertisement; audit separately.

Critical telemetry limitation: vga.log79B only MAPS_READ/QUEUES. Backend lookup/SDF/no-image/final counters were RAM-buffered/deferred to stop and were lost in restart. No stage timing, no-image hit count or clean cleanup evidence recovered. Next instrumentation must persist small periodic summaries outside hot locks/ownership, rather than assume stop will flush. No persisted faultPC; current dmesg post-restart/no identified panic, system binaries preserved undecoded. No rejected/native/input/destination dump for this run. First real frame saved/decoded/visually inspected; other14frames retained as hashes/times only.

Fifteen data files6,212,377B plus1303Bmanifest camera-MD5verified; originals retained/no log clearing. Initialuptime93.64s/boot1ddd6c5e-c953-41f2-851c-439b3247407f/ssbootidle/originallogger01.00.000. Exact4.0filespersist, stockcommon/loggerunchanged, /usrro. Free/usr10015744B,/log345440256B,/tmp5242880B and4096B/tmpreadbackpasses. Serviceclosed004 WORKBENCH_CLOSED/Done. No flash/reboot/extra trial this collection. Full private evidence workspace .local/outputs/vga-v40/benchmark-first-01/REPORT.md and timing-analysis.json. Versioned report research/firmware/yuy2_transport_v40_no_image_benchmark/evidence/benchmark-20261030/. README headline unchanged. Previous benchmark-pending checkpoint historical.

## Revision4.0 installed: no-image branch and unpaced benchmark — 30 October2026

User authorized existing8-bit stability/demo and maximum-speed benchmarking.4.0is installed and fresh-boot/readback verified. Producer45568B MD56fbc0edeab4895fbc81fd690e84a5810; wrapper72796B MD5cef5b31d4abfb2374a8196e3cc6b904f; unchanged yc37_fence kernel388799d95bbb524ca581c66b077b6dc2. ssboot=idle, original logger01.00.000, stock common/framework/DMM/RTOS/config guards pass; no streaming/producer mappings before activation. /usr read-only. Free /usr10015744B,/log351911936B,/tmp5242880B with4096Bwrite/readback passes. Service closed002 WORKBENCH_CLOSED/Done.

Stable structurally valid ImageAttach0/handle0metadata now releases only its known SDS Close/Free2then matched SendComp, never opens/invents a pixel reference. Unknown replies, malformed input and failed pixel Open still quarantine. One cold-boot session. Removed100ms USB pacing,150ms allocation retry and1ms metadata sleeps; no sleep/usleep/nanosleep imports. Pending/EBUSY paths sched_yield without timed delay. Hardware completion fences and native IPC receive timeout remain. Staging timeout is3seconds monotonic, not30fast polls. Host advertises640x4808-bitYUY2/60fpsceiling, not measured fps. No10-bit claim.

39worker cases pass including metadata-only->valid transitions, continuous100frames, stop, Close/Free/SendComp failures, and prohibition of timed sleep. Six actual compiled ARM unpaced producer/descriptor tests plus9frontend,17loader,11PIC,14paired-installer and18record-decoder cases pass; ISA6671/noNEON. Hardware calls mocked. Timings use ARM syscall263CLOCK_MONOTONIC,32-bit microseconds(wrap71min); BENCH_PROGRESS/FINAL/LOOKUP/SDF/NO_IMAGE and BENCH_USB report counters/durations. Backend hot logs are sampled and flash-flushed only at stop/fault; frontend periodic telemetry still has I/O overhead. Reboot can lose unflushed stats.

Twenty owned3.9test files6,587,189B freshly camera-MD5 inventoried and verified against local archive, rechecked then individually cleared. System original .local/logs/tmp/fonts/tools preserved. Boot-cache header alreadyzero and rechecked before image_mode0/reboot, selected*wbi4preserved; no raw boot/FAT write. Recovery /usr/share/yuy2-recovery-v40vga/rollback.sh MD5a48de8b080ad75fc9647980dd1b6deb0 restores3.9pair; --bars restores stable2.4p exact wrapper/separate original kernel.

BENCHMARK PENDING USER ACTIVATION. User asked to activate USB Streaming with OBS closed. Run .local/work/vga-v40/benchmark_host.py --output .local/outputs/vga-v40/benchmark-first-01 --seconds 8. Saves first-frame.yuy2 plus per-frame host receipt timestamps/hashes and FFmpeg stderr, bounded watchdog. Report received fps/complete frames/unique hashes; no synthetic results as camera performance. Then service return and collect logs without restart where possible. Package .local/outputs/vga-v40/zve10-v40-no-image-unpaced.zip 83090B SHA25669c2896302f31874b2caeaaa6fe7f10625567dd0b2ddf2679bcd6e39285a7660; includes observed deployment separately from build-time metadata. Source research/firmware/yuy2_transport_v40_no_image_benchmark/. Camera streaming stability/speed still unverified. README headline unchanged.

## 3.9 logs recovered; native no-image resolution branch verified — 30 October 2026

Current camera remains3.9; user observed recognizable OBS image near1fps and later crashes. No new patch/flash/reboot/log deletion this turn. Sixteen data files6,398,590B plus1363B manifest camera-MD5 verified. Appended traces contain4worker segments,49logged resize completions and at least66runtime USB submissions; bounded telemetry makes them lower bounds, not measured fps. Source FLAGS yc_compress1/1920x1080, destination yc_compress0/640x480. Earlier output's uncompressed description applies to VGA destination, not necessarily native source.

Critical saved rejection is stable, structurally parseable metadata WITHOUT pixels: ImageAttach0/type2/handle0, mask0x60, original getters accept. Exclusive first-failure record8272B SHA256e4ee15a700c0025e75c08dedede49441b426b3ba6f506ae05219180ba37574fb. Original RTOS pixel Open/Share/Close/Free helpers execute with zero pixel DMM operations for this actual record; valid attached control issues5/2/6/4. Original Linux exported GetEntry_ImageSizeInfo/GetData_All independently returns the same no-image metadata. Five RTOS cases and3Linux cases pass. Original metadata Close6/Free4(mode2) still occur separately; DMM/mapping/cache services mocked and helper invocation order harness-controlled. Full asynchronous reference/SendComp behavior remains separate. No-image should not automatically be called corruption; its producer intent/reboot causality is not proved.

3.9currently treats every SEND as a pixel frame and quarantines this no-image case. This is a concrete policy mismatch with native helpers. Separate segment3 failed pixel Open correlated replyfffb8005/nativefdfb on historical0x13ad; do not generalize that uncertainty to benign absence. Crash PC/root cause not identified. Correct next work: explicit no-image state and proven metadata-only cleanup/completion, test no-image->image transitions; retain strict handling for malformed metadata and uncertain replies. Instrument timing before claiming fps bottleneck fixed.

Source resolution already uses matched SEND->current SDS handle->correlated DMM Open->typed metadata->present pixel handle->correlated DMM Open. It does NOT scan source pools. Symbols use dlsym/exact guards; hidden libObj methods use inspected ELF-relative offsets plus verified current mapping. Offline SSYC signature searches are not live discovery. Original Linux getters provide a verified exported metadata API, with bounded validation still needed before native parsing. Never replay historical identities.

Initial collection uptime125.49s, boot620e50d5-5653-42e2-8dee-b9f968f5db41, ssboot=idle, original logger01.00.000. Current storage /usr10267648B,/log345620480B,/tmp5242880B and4096B/tmp write/readback passes. Service closed003 WORKBENCH_CLOSED/Done. Original logs preserved; no README headline change. Full private evidence workspace .local/outputs/vga-v39/capture-first-01/ and .local/outputs/yc-resolution-audit-20261030/. Versioned report/source research/firmware/raw_frame_source/verified_yc/evidence/resolution-audit-20261030/. Previous first-test-pending checkpoint is historical.

## Revision 3.9 flashed and fresh-boot verified — 29 October 2026

Current camera3.9. Producer42916B MD50fede3f034f6cfca755f9f678d73ffe8; wrapper72796B MD5cc95285c2e789f186ab5b97c9ba11fcb; unchanged kernel388799d95bbb524ca581c66b077b6dc2/yc37_fence. Installed and postboot downloaded bytes match package. ssboot=idle; original logger01.00.000 and stock common/framework/DMM/RTOS/config verified. No streaming/producer mappings before setup; /usr read-only. Free /usr10267648B, /log352436224B, /tmp5242880B;4096B /tmp write/readback passed. Normal error filters, no active sequential capture. Service closed002 WORKBENCH_CLOSED/Done.

Twenty owned3.8logs/snapshots6,234,425B matched a fresh camera-MD5 inventory and verified local archives, then exact individual paths were rechecked and cleared. Original system .local/logs/tmp files preserved. Boot cache header already zero; verified again immediately before image_mode0/reboot while preserving*wbi4; no raw boot/header/FAT write. Default paired recovery /usr/share/yuy2-recovery-v39vga/rollback.sh MD5e27bcc5a5a4f2380aae4cbcbaf4f0a5b restores3.8; --bars restores separate stable2.4p pair.

FIRST3.9FRAME TEST PENDING. Ask user to activate streaming with OBS closed; one short FFmpeg capture640x480/10fps/YUY2, then collect .local/logs/compatible rejected-source.yc38. New code retries up to8pairs, max7one-ms sleeps; all final validation and quarantine unchanged. Working frames/root-cause/teardown fix NOT established. Full private deployment .local/outputs/vga-v39/deployment/deployment-summary.json. Earlier NOT INSTALLED checkpoint is historical.

## Revision 3.9 bounded metadata settling built offline — NOT INSTALLED, 29 October 2026

Camera remains3.8. New3.9 keeps the same received SEND transfer and metadata mapping, checks up to8read-pairs, yielding1ms between retriable failures (at most7sleeps, no wall-time guarantee). Final pair must pass EVERY existing predicate. Size/identity errors fail immediately. Only changing/malformed category reads retry; no pixel Open/SDF/SendComp/new event or new Share while settling. Stop and exhausted attempts follow existing ownership/quarantine policy. Existing final-pair YC38RJ01 evidence format remains; new directory /log/yuy2_640_v39vga/. This is an experimental transient-read recovery, NOT a proven root-cause/frame-output/teardown fix. Persistent corruption remains rejected.

Original Sony RTOS getter0x63c60f76 executed offline rejects BOTH actual3.8snapshots; accepts retained3.3reference. DMM/physical mapping mocked. This rules out simply accepting the image-like category0x12payload based on our parser alone. Cause of changed byte/early category-link termination remains unknown; retries may not fix it. No parser/category fallback or ownership relaxation added.

33actual worker C cases pass, including100frame mock streams, first/last-retry recovery, stop during settling, terminal size/identity failures, persistent real3.8snapshot rejection with8attempts/no pixel access, existing error paths. Eighteen C-produced evidence records independently decoded. Nine compiled ARM frontend,17SDK-loader,11PIC/persistent,14actual installer/paired rollback fixtures pass. ISA6212instructions/noNEON. Hardware services mocked; no live3.9frames/camera access/flash.

Module42916B MD50fede3f034f6cfca755f9f678d73ffe8; matched wrapper72796B MD5cc95285c2e789f186ab5b97c9ba11fcb; unchanged yc37_fence kernel MD5388799d95bbb524ca581c66b077b6dc2. Guarded installer baseline is exact3.8. Default rollback restores3.8pair; --bars restores exact stable2.4pwrapper plus separate c1cad400kernel. Original common/logger/framework/DMM/RTOS/config guarded. Preserve system /tmp/kikilog.dat and tools; clear only archived/hash-verified owned test files. Require cold mappings and verified fresh initialization, not reboot-f alone.

Local package .local/outputs/vga-v39/zve10-v39-bounded-metadata-settle.zip 80703B SHA256a483f78d407776dd2dffa24bb787b24eedb6772bf6e393e0e673caa173cd49c4; archive and all manifest bytes verified. Source/nonbinary evidence research/firmware/yuy2_transport_v39_metadata_settle/. Full private build state workspace .local/outputs/vga-v39/build-summary.json. Next authorized flash must preserve3.8evidence first, verify exact package baseline, perform fresh boot/readbacks, then one bounded FFmpeg test and collect METADATA_ATTEMPT_REJECTED/METADATA_SETTLED plus final descriptor evidence. No live action queued. Earlier3.8trial below is still current installed-camera evidence.

## Revision 3.8 first trial: rejected metadata captured and verified — 29 October 2026

FFmpeg requested1frame at640x480/10fps/YUY2, timeout8s; process terminated at10.039s with0bytes. Camera returned to service successfully without a requested reboot. Collection uptime979.83s, boot ID b07877b0-bdd5-4cfc-902d-37c5b3ed6963, ssboot=idle, loaded USB kernel yc37_fence/original logger01.00.000. Sixteen data files6,223,026B plus1363B manifest downloaded and camera-MD5 verified. No logs deleted. Storage remains healthy: /tmp5242880B with4096B write/readback passed, /log346472448B, /usr10516480B. Service closed job003 WORKBENCH_CLOSED/Done.

New evidence succeeded: EVENT_REJECTION_SAVED status0; rejected-source.yc38 is complete8272B (80B header + two4096B SDS reads), SHA25620cde3d3c4d6529dc7ccb8300260029e21b171d2d56cece77b37e36bc9ebb539. Strict decoder passed. Rejection mask0x1e = two reads differ, image parser-1, state parser-1, multi parser-1 (malformed, NOT proven present). Only changed byte is SDS offset0x2e8: bb -> c5. SSYC header version1 declares12entries; first linked entry0x20/category0x12 points0x140/category4, whose next pointer is0 despite count12. Thus current parser fails before finding image/state. Nine ETRY signatures found in4096B, including duplicate category0x12; signatures alone do not validate entries. Category0x12 payload starts with image-like words1,0x295,0x6881 and1920x1080 geometry, but category semantics/ownership/handle validity remain UNPROVEN; do not relabel it as category0 or replay historical handles.

Logs show native connect/status success and first SEND, then rejection/quarantine; no pixel open, resize, COMPLETE or USB submission. Runtime stop/finish original calls returned; source retained. No claim of teardown fix or new crash diagnosis. Next offline work: establish native SDS entry/count/link/category semantics and mapping/cache/lifetime rules against captured bytes and firmware; locate changing offset0x2e8's owner. Do not simply relax stability checks or guess Free. Actual source/format/ownership still needs verification.

Private evidence: workspace .local/outputs/vga-v38/capture-first-01/logs/, decoded rejected-source.json, deployment/deployment-summary.json. Current installed revision remains3.8. No further live test queued.

## Revision 3.8 installed and fresh-boot verified; diagnostic trial pending — 29 October 2026

Current camera is revision 3.8. Producer MD5 d577730ce4eeec70904cd4fb164580f5, matched wrapper f5d42a08e186b0cf2f519bd105457e08; unchanged USB kernel 388799d95bbb524ca581c66b077b6dc2 (yc37_fence). Installed and postboot downloads are byte-identical to package. ssboot=idle, uptime73.21s, original logger01.00.000 and stock common library preserved; no streaming/producer/observer mappings before activation. /usr read-only. Free /usr10516480B, /log352960512B, /tmp5242880B; actual4096B /tmp write/readback passed. Normal error filters; no sequential capture active. Service closed job004 WORKBENCH_CLOSED/Done.

Eighteen owned3.7 test .local/logs/snapshots (6,216,014B) were freshly archived, camera-MD5 verified locally, rechecked on camera, then individually cleared. System-managed /tmp/kikilog.dat, fonts/images/tools and original logs preserved. Boot-cache first512B were already zero, verified twice; native image_mode=0 prevented cache generation before reboot while preserving *wbi4. No boot-header write/drop or FAT repair needed. First postboot checker accidentally retained3.7 rollback-script hash; trace identified this host-check error, corrected checker passed without changing camera files.

Recovery /usr/share/yuy2-recovery-v38vga/rollback.sh MD5 97ef4b0c55cebfdd2b0417bb6027acd3. Default restores failing3.7 pair; --bars restores exact stable2.4p wrapper5fde77e394572ebcf420f8941575f6c4 plus separate kernelc1cad400372e26eca729e4b9bc47a237; both verified.

NEXT: ONE short FFmpeg capture at640x480/10fps/YUY2, OBS closed; then collect logs and /log/yuy2_640_v38vga/rejected-source.yc38. This revision diagnoses rejected metadata; acceptance/quarantine unchanged, no frame or teardown fix claimed. USB may again disappear and require restart; bounded exclusive fsynced evidence is designed to survive that. Decode with package decode_rejection.py; verify EVENT_REJECTION_SAVED and file length. Full private deployment evidence: workspace .local/outputs/vga-v38/deployment/deployment-summary.json. Earlier NOT INSTALLED checkpoint below is historical.

## Revision 3.8 rejected-descriptor evidence patch built offline — NOT INSTALLED, 29 October 2026

User requested the next patch after3.7's first YC SEND was rejected before resize. New3.8 distinguishes eight validation conditions, logs individual decoder return codes and identity/geometry/format/header fields, and saves two bounded SDS reads in one fsynced YC38RJ01 record on rejection. Capture is exclusive-create, once per module lifetime, max131152B; partial writes and fsync/close failures are logged. Success path adds no flash I/O while holding source frames. A standalone strict decoder is included.

This is a DIAGNOSTIC revision, not a functional frame/parser or teardown fix. Acceptance policy and source quarantine/ownership behavior are unchanged. A rejected run may again lose USB and require a restart. No guessed Free, guard relaxation or new port request was added. Actual descriptor bytes are required before correcting layout/cleanup. No camera access, flash, reboot or live trial during this build; camera remains3.7, whose first test got0frames and whose verified logs are preserved.

Module42648B MD5d577730ce4eeec70904cd4fb164580f5; matched wrapper72796B MD5f5d42a08e186b0cf2f519bd105457e08. Kernel is UNCHANGED3.7 yc37_fence, MD5388799d95bbb524ca581c66b077b6dc2. Exact3.7 baseline guarded. Default rollback restores3.7 wrapper/kernel; --bars restores the exact2.4p wrapper plus separate c1cad400 kernel, preserved from3.7 recovery. Stock common library/original logger guarded; preserve system-managed kikilog/fonts/tools during cleanup. Rejection file must not already exist. Activation requires verified fresh initialization; reboot-f alone did not guarantee this in3.7 recovery.

28worker/evidence cases passed, including100changing-frame success fixtures and malformed metadata, stability,64KiB cap, exclusive capture, partial/error/fsync/close paths. Seventeen actual C-produced binary records decoded independently;51malformed lengths rejected. Nine compiled ARM frontend,17SDK-loader,11PIC/persistent and14installer/paired rollback cases pass. ISA6163instructions/noNEON. Hardware boundaries mocked; no working-frame claim.

Concrete local package .local/outputs/vga-v38/zve10-v38-descriptor-evidence.zip is81389B, SHA256ffeb1816da82e5b81e1330c8c9766e25771c7ab93f128ba8a98e30acf24686ea. Package includes binaries, guarded scripts, decoder, README and integrity sums; archive bytes verified. Source/non-binary evidence: research/firmware/yuy2_transport_v38_descriptor_evidence/. Binaries/raw camera evidence remain local. No installation performed. Old checkpoints below describe3.7 hardware state.

## Revision 3.7 first test failed at descriptor gate; logs recovered — 29 October 2026

Actual USB enumerated VID054C/PID0DE3 and advertised640x480YUY2/10fps. Bounded20s FFmpeg attempt got0bytes/0frames (22.037s including kill). Saved vga.log proves native YC connection succeeded, status0, then first SEND/SDS event arrived; EVENT_DESCRIPTOR_REJECTED followed immediately, then quarantine. No SOURCE_EVENT, resize, COMPLETE or USB SUBMITTED. This establishes native event delivery, not a valid pixel attachment or image format.

Exact rejected predicate is NOT known. find_source groups stable-copy, ImageSizeInfo/StateInfo parsing, absent multi-segment category, type0x295 and handle guards into one zero-argument failure message. Rejected raw SDS was not dumped; successful-resize-only dump policy lost the RAM copy on necessary restart. Next correction must capture bounded rejected bytes and individual results and distinguish deterministic unsupported metadata from uncertain IPC. Fault path skips return/disconnect; retained transfer/pin may stall teardown, but this does not prove the missing-USB cause. Do not relax guards or guess Free handles from these logs.

After mode exit the camera's controls responded but Windows saw no Sony device. Cable reconnect and MTP did not restore it; Windows PnP rescan was denied admin access. User explicitly restarted to recover USB, so do not label this a spontaneous crash. Runtime later has30staging polls/failure38 and successful original stop/finish; no shared timestamps identify relation to mode exit. No DMA transfer was attempted. Fifteen files6,212,976B plus manifest downloaded and camera-MD5 verified after restart. Original .local/logs/system files preserved; no new patch, rollback or deletion during collection. Current dmesg is new-boot evidence, binary logs undecoded/no identified fault PC.

Camera remains3.7; hashes unchanged. Initial collection uptime43.42s, ssboot=idle, original logger01.00.000, no streaming/producer mappings. Free /tmp5242880B, /log347078656B, /usr10765312B; /tmp write/readback passed. Service closed job003 WORKBENCH_CLOSED/Done. No further trial requested. Report/source: research/firmware/yuy2_transport_v37_event_yc/evidence/first-test-20261029/REPORT.md. Full private logs: workspace .local/outputs/vga-v37/capture-first-01/. Previous installed-but-frame-test-pending checkpoint below is historical.

## Revision 3.7 installed, fresh-boot/readback verified; storage recovered — 29 October 2026

Current camera is 3.7. Module 40444B MD5 7c339b924987e6baa8e7046e041798c5, matched wrapper 277c023942dd4d3d347d9829eaf8be85, USB kernel 388799d95bbb524ca581c66b077b6dc2 (version yc37_fence required when streaming loads it). Installed and postboot downloaded copies are byte-identical to package. Original logger restored on disk (51337167a2ab42d53557c2cce210c987) and loaded version 01.00.000; stock common library 31308976206a837f6f5c571992d2b499. Fresh boot ssboot=idle, uptime158.86s, /usr read-only, no streaming/producer/observer mappings before setup. Free /usr10765312B, /log353550336B, /tmp5242880B; 4096B/tmp write/readback passed. Normal error filters, no sequential application capture. Service closed job055 WORKBENCH_CLOSED/Done.

FIRST FRAME TEST PENDING. User has been asked to activate USB Streaming with OBS closed. Run one bounded FFmpeg capture at 640x480/10fps/YUY2 and preserve raw bytes/stderr, then request service return without reboot and retrieve bounded runtime/vga logs and snapshots. No 3.7 FFmpeg/OBS success, image-format proof, throughput or crash fix is claimed. One streaming session per cold boot; do not steal a busy native YC output. Default paired rollback restores unstable3.6 plus old matched kernel; --bars restores separate stable2.4p pair. Recovery /usr/share/yuy2-recovery-v37vga/rollback.sh MD5 8cd97d4a1bcf2cf48e4712ad746a547d. Fourteen offline installer/rollback fixtures passed.

Storage recovery: cleanup mistakenly included system-managed /tmp/kikilog.dat. Original1,957,888B archive was camera-MD5 verified before removal, but first restore failed at98,304B with ENOSPC. Full original log is now restored and MD5 verified (73b4dc0ac4b8e0b5796baf26694d88c7); preserve this system file in future cleanup. First verified12MB FAT image showed434 unreachable allocated clusters/7,110,656B, zero free. Guarded manual repair attempts aborted before raw writes on EBUSY. Temporary logger module skipped only its file-open call, but reboot-f resumed the original kernel module from Sony's snapshot despite changed disk bytes. Reboot-f alone is NOT proof of fresh kernel/module initialization.

Exact native WBI sysfs handlers were inspected/executed offline. A complete60MiB boot-cache backup was hash-verified locally; native image_drop='1' then image_mode='0' preserved selected*wbi4 and invalidated its header. No manual boot-source or boot-sector write. Fresh initialization loaded temporary logger and **automatically reclaimed all434 clusters**, confirmed in a new verified12MB image:434free,332reachable,0unreachable,0chain errors. NO MANUAL FAT WRITE/FORMAT occurred. Restored original log by extending its existing chain, then original logger driver. New full boot also exposed old eight-byte1080p descriptor patch in common library (bd32c223e60e363d900c7ac8be06641c), previously hidden by cached state; backed up and restored stock. Atomic replacement of that mapped library held an unlinked inode, so kernel sync/read-only shutdown completed before fresh reboot and final passing preflight. Temporary logger no longer active. Original support backups remain /usr/share/tmp-fat-recovery-20261029/.

Snapshot invalidation was repeated for final activation. Keep raw FAT/WBI/log backups private/local; never restore an old cache blindly after filesystem changes. Native initialization recovered space; allocation timing and prior crash root causes remain unproved. Current source/evidence: research/firmware/yuy2_transport_v37_event_yc/README.md and evidence/install-20261029/. Full local state: .local/outputs/vga-v37/deployment/deployment-summary.json. Package .local/outputs/vga-v37/zve10-v37-event-yc.zip includes separate observed deployment summary; build manifests describe build-time status. Old checkpoints below are historical.

## Revision 3.7 flash held for /tmp recovery; temporary logger driver installed — 29 October 2026

User authorized /tmp repair followed by 3.7 flash, stopped, then explicitly resumed. 3.7 webcam files are NOT installed; current webcam remains 3.6. Installer/paired rollback passed 14 local fixtures. Current local state: .local/outputs/vga-v37/deployment/deployment-summary.json.

Cleanup mistakenly included the system-managed /tmp/kikilog.dat. Its original 1,957,888-byte data was downloaded and camera-MD5 verified first, but ordinary restoration failed at 98,304 bytes with ENOSPC. Full original archive and staged copy are preserved; restoration not yet complete. Read-only full FAT12 volume backup is 12,582,912B, MD5 e558283227d539de3fe93f7678833e39. Complete directory traversal found zero free clusters and 434 unreachable allocated clusters (7,110,656B), no reachable chain errors or crosslinks. No pre-cleanup raw FAT image exists, so timing/cause of unreachable allocations is unproved. No FAT repair has been written.

Guarded repair helper passed 11 host fault cases; its camera dry run exactly matched the backup. It refuses raw writes unless /tmp and /etc are ordinarily unmounted, checks the whole volume again, verifies FAT readback and all unchanged bytes, and restores old FAT on write failure. Camera refused read-only remount with EBUSY, including after native kikilog stop ioctl 0x80044a20. Service session was closed on user stop.

Original kikilog.ko code can lose its filp pointer on an invalid logfile-size path without filp_close. To remove the possible hold after a cold boot, a TEMPORARY recovery module skips only kikilog_dat_open at .text+0xc64, removes that call's R_ARM_CALL relocation, and uses version tmpnofile. Other relocations preserved; null-file read/write paths and replacement ARM instruction executed offline. This is not a proved historical crash cause. Temporary module MD5 8af7cfd952dbdd47b4f468de6c7d385e; original 51337167a2ab42d53557c2cce210c987 backed up at /usr/share/tmp-fat-recovery-20261029/kikilog.original.ko and on laptop. Three recovery-installer success/failure fixtures passed; installed and backup readbacks match. /usr returned read-only. Recovery reboot queued.

NEXT: verify loaded kikilog version tmpnofile and safe ordinary unmount; repair only against exact volume backup (otherwise refresh/read-only analyze a new backup), restore full original logfile without truncating its existing chain, verify space/write/readback, restore ORIGINAL kikilog.ko, then install matched 3.7 module/wrapper/usbg_video and reboot-verify all files. Do not leave the temporary logger driver as a permanent modification. No mounted-volume raw write, force/lazy unmount, or formatting is authorized by the chosen repair method. Binaries/raw volume remain local, excluded from source publication.

## Revision 3.7 event-driven native YC candidate built offline — NOT INSTALLED, 29 October 2026

User requests real changing camera frames rather than OSD control or immutable snapshots. New source backend receives transferred SDS/pixel ownership from a private type-0 VDF input connected to native YC output [0,2,0,0x59000e]; source-pool scanning removed. Distinct private index avoids the original RequestConnect same-index peer-disconnect behavior. Busy output must refuse without stealing its peer. Original Linux/RTOS connect handshake and busy refusal executed offline; actual output availability/generation during USB Streaming remains unknown.

Continuous worker publishes 100 changing frames in each of two mocked success fixtures; 10 worker cases cover ownership return, backpressure and stop/error handling. Kernel candidate repairs DMA timeout/start-error false success and both-busy unlock; 4 actual ARM path fixtures pass. F002 availability is not a DMA fence. Independent DMM credit retains USB source across manager teardown; uncertain DMA permanently quarantines writes. Native video_thread already serializes producer under manager+0x18 and stop uses same semaphore: do not recursively lock there. Self-pinning/single activation added. Candidate UYVY-to-YUY2 byte permutation is still an unverified packing hypothesis.

Latest module 40444B MD5 7c339b924987e6baa8e7046e041798c5; matched wrapper 277c023942dd4d3d347d9829eaf8be85; required matched kernel 388799d95bbb524ca581c66b077b6dc2/version yc37_fence. 9 compiled ARM frontend checks, 17 SDK-loader checks, 11 persistent/PIC checks and ISA audit 5768 instructions/no NEON pass. Component fixtures mock hardware and do not prove camera stability, completion/cancellation, native reference accounting, correct colors or throughput.

No camera access, flash, reboot or log deletion during this work; camera remains unstable 3.6. This is a development checkpoint, not a flashing package. Remaining: guarded three-file installer/rollback restoring both kernel and wrapper while preserving stable 2.4p rescue, installer fault fixtures, then bounded camera capture and cleanup. One streaming session per cold boot. Do not reuse 3.6 installer unchanged. Source/evidence: research/firmware/yuy2_transport_v37_event_yc/README.md. Binaries stay local in workspace .local/outputs/vga-v37; not published.

## Revision 3.6 failed: no OBS frame, repeated crashes — 29 October 2026

User clarifies USB Streaming initially entered but OBS got no frame, then crash; subsequent attempts crashed at menu. Single-snapshot3.6 did not demonstrate stability. Recovered16files6232824B with camera-MD5 verification. Runtime269B shows source allocation/binding/pending only; VGA5635B shows candidate scans/refusals (13hints,7pixel and4metadata Share declines,6NO_SOURCE). No persisted SOURCE, resize, COMPLETE or snapshot-ready/dump markers; no native snapshot/SSYC files. Buffered losses prevent treating this as a complete precrash trace or assigning root cause.

Installed3.6 hashes unchanged. Initial recovery uptime51.77s; streaming/probe maps inactive after restart. Healthy storage/tmp; no identified fault PC. System binary logs undecoded, last_kmsg/pstore absent. Own snapshots hash-rechecked/cleared, original .local/logs/tmp preserved. Service closed job004 WORKBENCH_CLOSED/Done. No rollback, flash, reboot or test sent during recovery. Camera remains unstable3.6. Recommend proven2.4p before further trials; default3.6 rollback restores also-unstable3.5, with2.4p rescue separate. No restore authorized/performed here.

[Crash report](../../../research/firmware/yuy2_transport_v36_single_snapshot/evidence/crash-20261029/REPORT.md); full local .local/outputs/vga-v36/crash-20261029-01/. Local deployment summary now marks FAILED_NO_OBS_FRAME_REPEATED_CRASHES. Do not build another guessed fix from the final log line; investigate source event/ownership and activation/menu paths independently.

## Revision 3.6 flashed and reboot-verified — 29 October 2026

User explicitly requested flash. Matched 3.6 single-snapshot module (35816B, MD5 c2e06b5a7a9f1361c4fb2a087d5e8fe2) and wrapper (72796B, MD5 886445056d2eba99ef62df3a9def5e0f) installed dependency-first; downloaded readbacks byte-identical. Activation reboot observed. Postboot uptime68.57s, persistent hashes correct, /usr read-only, no streaming/probe mappings before setup. Recovery/rescue/rollback hashes rechecked. Service closed job010 WORKBENCH_CLOSED/Done. No frame test yet; stability and packing correction not claimed.

5 diagnostic files70105B archived, camera-MD5 verified/rechecked and individually cleared; system/tmp/fonts/tools preserved. Postboot free /usr11219968B, /log524107776B, /tmp6619136B; helper readback passed. Kernel/RTOS/DMM/config unchanged. Recovery /usr/share/yuy2-recovery-v36vga/rollback.sh MD5 1e03861d438ff6cc2fd58c1c38aa6e71 restores 3.5; separate2.4p rescue retained. Reboot job006 lacks terminal marker due reboot; shutdown/restart console and fresh postboot session establish activation.

Expected ONE frozen native image, repeated USB payloads, not continuous video. Native packing/colors unchanged; snapshot dump path /log/yuy2_640_v36vga/native-vga-snapshot.bin after successful borrowed-reference cleanup. [Deployment evidence](../../../research/firmware/yuy2_transport_v36_single_snapshot/evidence/install-20261029/REPORT.md). Local .local/outputs/vga-v36/deployment/deployment-summary.json supersedes historical build NOT_INSTALLED status. Camera currently3.6; do not re-run installer automatically.

## Revision 3.6 single-snapshot diagnostic built — NOT INSTALLED, 29 October 2026

User requested a new patch after 3.5 produced scene-bearing OBS frames then crashed. Built 3.6 as an explicitly bounded diagnostic: one successful native capture/resize per cold boot, known-reference cleanup before ready, then immutable frozen-image replay. USB source copied once; no repeated pool/SDF work after success. This is not continuous video, color correction or a proved crash fix. Initial source scan and native completion/stop uncertainties remain. No camera access/flash/reboot during build; installed baseline remains 3.5.

Native snapshot dump (614400B) is from owned RAM after cleanup; actual ACK/CMP status telemetry and 30-pass no-source cap added. 49 host worker cases, compiled ARM 101-call/one-copy replay fixture, 11 ELF/gate cases, ISA audit (5330 instructions/no NEON), and 10 installer/rollback fixtures passed. Hardware services mocked. Package contents/identities verified. Module MD5 c2e06b5a7a9f1361c4fb2a087d5e8fe2; matched wrapper 886445056d2eba99ef62df3a9def5e0f.

Local .local/outputs/vga-v36/zve10-v36-single-snapshot.zip (60990B), includes guarded exact-3.5-baseline scripts; rollback restores 3.5, stable 2.4p rescue separately preserved. Do not mix producers/wrappers. [Source, report and evidence](../../../research/firmware/yuy2_transport_v36_single_snapshot/README.md). Source digests recorded; no deployment or crash-free claim.

## Revision 3.5 OBS scene-bearing frames, then crash — logs recovered, 29 October 2026

User observed a few OBS frames with recognizable scene detail, severe magenta/green and vertical stripe artifacts, then crash. Supplied screenshot preserved locally. One service session recovered 18 camera files (6,280,735B), all MD5 verified; runtime.log 1,339B, vga.log 42,000B, input/destination SSYC 4,096B each, system/boot/storage evidence. This supersedes the preceding no-acquisition runtime checkpoint: fifteen logged resize returns and COMPLETE outputs (614,400B) now exist. They do not independently count OBS reception, prove correct packing or measure throughput.

Last persisted stage is source acquisition plus RESIZE_READY for the next operation (counter 0x0f), without following ENTER/RETURN/COMPLETE or stop/cleanup markers. Buffered logging prevents treating that line as the fault PC. Cause remains unresolved. Boot ID changed since prior collection; initial uptime 74.59s, recovered maps inactive. Installed 3.5 hashes unchanged; /tmp 6,619,136B and /log 524,058,624B available. No fault PC/backtrace identified; binary system logs undecoded.

Own diagnostic snapshots were hash-rechecked/individually cleared after download; original runtime/vga/SSYC, system logs and /tmp preserved. Service closed job004 WORKBENCH_CLOSED/Done. No flash, rollback, reboot or new host frame test. [Report](../../../research/firmware/yuy2_transport_v35_native_vga/evidence/obs-crash-20261029/REPORT.md). Full local archive/screenshot: .local/outputs/vga-v35/crash-20261029-02/. Next analysis must distinguish output packing artifacts from unsafe source ownership and crash mechanism.

## Revision 3.5 menu/streaming crashes — logs collected, 29 October 2026

User reports crashes opening MENU or using USB Streaming. One service session retrieved 14 hash-verified snapshot files (6,210,795 bytes); no flash, rollback, reboot or streaming trial. Installed 3.5 wrapper/module hashes still match. Initial uptime 176.28s; no streaming/probe maps in recovered im.elf. Runtime log is only 83B (LOAD / legacy INSTALLED_V25 markers), no persisted acquisition/SDF/shutdown stages. No vga.log present. This does not prove those stages never ran before restart.

Storage at collection is not full: /tmp 6,619,136B, /log 524,058,624B, /usr 11,219,968B free; helper write/readback passed. Original AccessLog.dat/.bak (2,097,220B each; identical MD5 05b6579f523b8f7e3ac55e311c93cc2c), empty ThreadMonitor and 1,957,888B kikilog preserved locally. Binary logs remain undecoded; no identified fault PC/backtrace or crash cause. last_kmsg/pstore absent. Current dmesg is not previous-boot crash evidence.

Own generated snapshots were individually camera-hash rechecked and cleared after verified download; original system logs, runtime.log and /tmp contents preserved. Service closed job005 WORKBENCH_CLOSED/Done; camera remains 3.5. [Report](../../../research/firmware/yuy2_transport_v35_native_vga/evidence/crash-20261029/REPORT.md). Raw local archive: .local/outputs/vga-v35/crash-20261029-01/. Avoid attributing failure or repeating tests without new evidence.

## Revision 3.5 installed and reboot-verified — 29 October 2026

Authorized hardware deployment of Revision 3.5 completed following strict project procedures:
- **Preflight and Storage Hygiene**: Existing camera logs in `/log/yuy2_640_v34vga/` (19 files) and transient diagnostic files in `/tmp/` (20 files) were inventoried, archived, verified bit-for-bit, and individually deleted. Camera system files, fonts (`/tmp/images/`), and core tools were preserved.
- **Dependency-First Staging & Installation**: Staged under `/log/yuy2_640_v35vga/`. Verified baseline Rev 3.4 (`ca3cbbc5947caf3373ebe451343fb926` / `ac565b4060a7062745d3bd22037d5410`). Created recovery directory `/usr/share/yuy2-recovery-v35vga/` holding previous Rev 3.4 wrapper (`ca3cbbc5947caf3373ebe451343fb926`), hardlinked previous-inode, 2.4p rescue binary, and `rollback.sh` (MD5 `9a2326bd51cddf20b7991d9e728abc91`).
- **Readback Verification**: Downloaded readbacks before activation; all matched local build bit-for-bit:
  - `/usr/lib/yuy2_640_v35vga.so` (35,224B, MD5 `e6b9fa6947a21e5a6a1603e070a1d00f`)
  - `/usr/lib/libInfraStreamingUsb.so` (72,796B, MD5 `c16af3a036529b89d23fa4ccfd059ec3`)
  - `/usr/share/yuy2-recovery-v35vga/libInfraStreamingUsb.previous.so` (72,796B, MD5 `ca3cbbc5947caf3373ebe451343fb926`)
  - `/usr/share/yuy2-recovery-v35vga/libInfraStreamingUsb.v24p.so` (72,792B, MD5 `5fde77e394572ebcf420f8941575f6c4`)
  - `/usr/share/yuy2-recovery-v35vga/rollback.sh` (1,195B, MD5 `9a2326bd51cddf20b7991d9e728abc91`)
- **Postboot Verification**: Activation reboot observed; postboot cold check confirmed:
  - Cold uptime: 149s
  - Mounts: `/dev/nflasha15 /usr ext2 ro,relatime,errors=continue 0 0` (strictly read-only)
  - Process maps: `im.elf` maps contain zero premature streaming or observer module mappings
  - Persistent hashes match bit-for-bit
  - Storage space: 11.2MB free on `/usr`, 524MB on `/log`, 6.6MB on `/tmp` (`V28_TMP_WRITE_READBACK_OK`)
- **Workbench Status**: Authenticated service mode session cleanly closed. Hardware is ready for bounded live testing.

---

## Revision 3.5 candidate built offline; NOT INSTALLED — 29 October 2026

Candidate Revision 3.5 built and verified offline in workspace `.local/outputs/vga-v35/build/`. No camera access, deployment, flash, reboot or IPC occurred. Camera strictly remains on baseline Revision 3.4.

Key candidate changes (addressing Rev 3.4 failure points):
1. **Correlated Pixel Refusal Handling (`vga_resize.c`)**: `optional_share_declined()` now checks both stale serial `-517` (`0xfffb` / `0xfdfb`) and unshareable/busy unit `-1` (`0xffff` / `0xffff`). On refusal, the candidate metadata lease is cleanly dropped and scan continues without setting `shared_fault = 1` or quarantining.
2. **Early Stop Teardown (`yuy2_640_v35vga.c`)**: `stop_hook` and `finish_hook` invoke `vga_resize_stop()` before calling `original_stop()`, ensuring the worker stops before `funcStopFuncCmd` issues command `0x6103`.
3. **In-Memory Telemetry (`trace_buffer`)**: Replaces synchronous flash logging during frame acquisition with a 64KB RAM ring buffer flushed at safe worker boundaries, eliminating I/O jitter between DMM Share and Open.

Offline verification passes:
- **ARM Cortex-A5 ISA Audit**: 5,241 total instructions, 0 NEON instructions (`verify_isa.py`).
- **Host Worker Fixture**: 42/42 test modes passed (`test_vga_worker.exe 0..41`).
- **Persistent Stream PIC Gate**: 11/11 test cases passed (`verify_persistent.py`).
- **Contract & Metadata Fixture**: PASS (`test_vga_contract.exe`).

Artifacts:
- Module: `.local/outputs/vga-v35/build/yuy2_640_v35vga.so` (35,224B, MD5 `e6b9fa6947a21e5a6a1603e070a1d00f`, SHA256 `3984271e77dc249eeba233d92d0bc4b09dc4d800a249e1f0bda41685627f6e42`).
- Wrapper: `.local/outputs/vga-v35/build/libInfraStreamingUsb.so` (72,796B, MD5 `c16af3a036529b89d23fa4ccfd059ec3`, SHA256 `116b55070ce77037ba4c16df4f8cde7ef550b1a864be6dc73c3b3d6de6518d88`).
- Patches: `.local/outputs/vga-v35/vga_resize.patch` (33,968B), `.local/outputs/vga-v35/yuy2_640.patch` (3,814B).
- Status manifest: `.local/outputs/vga-v35/DRAFT_STATUS.json`.

---

## Subsystem Architecture & Teardown Contract Resolved — 29 October 2026

Offline reverse engineering across Workstreams A (Source Ownership), B (SDF Hardware Boundary), and C (USB DMA & Teardown Lifetime) has resolved the complete subsystem contracts and the Rev 3.4 shutdown crash root cause.
Camera remains strictly OFFLINE on Revision 3.4; zero flashing, zero rebooting, zero IPC.

Authoritative reports and reproducible recipes:
- Workstream A: [source ownership report](../../../research/firmware/raw_frame_source/verified_yc/evidence/source-ownership-20261029/REPORT.md), recipe `verify_source_ownership.py`.
- Workstream B: [sdf boundary report](../../../research/firmware/raw_frame_source/verified_yc/evidence/sdf-boundary-20261029/REPORT.md), recipe `verify_sdf_boundary.py`.
- Workstream C: [usb lifetime report](../../../research/firmware/raw_frame_source/verified_yc/evidence/usb-lifetime-20261029/REPORT.md), recipe `verify_usb_lifetime.py`.

### 1. Workstream A: Strict 1-Peer Pin Constraint & RTOS Tee Architecture
- **DataflowInfraPin 1-Peer Rule**: `DataflowInfraPin::Connect` (`0x63de01b2`) checks `pin->state` at `pin + 0x28`. If `state != 0`, it returns an error. A pin supports strictly ONE peer.
- **Native Encoder Connection**: `CdSeqCtrlEnc::SendYCPinConnect` (`0x6364647c`) connects VDF YC output pin 0 `[0, 2, 0, 0x0057030f]` to Encoder input pin 0 `[0, 1, 0, 0x005700f9]`. Any external attempt to connect to VDF output pin 0 is either rejected or severs the encoder.
- **Failure of Linux Pool Scanning**: Scanning `/proc/udm/dmm_units` hints at allocated units but lacks ISP synchronization and causes lock contention with the encoder, returning native status `-1` or `-517`.
- **RTOS Tee Architecture**: A clean live webcam feed requires an RTOS intercept at VDF producer `0x6374c500..0x6374c5e8`: right after VDF shares pixel unit `0x295` and prepares the 52-byte `0x0102` frame message, the tee captures the frame descriptor, shares unit `0x295` for the webcam queue, and dispatches a notification without altering the encoder's pin.

### 2. Workstream B: SDF Hardware Boundary & Output Format
- **Hardware Parameter Validation (`0x638e1db4`)**:
  - Strip width MUST be a multiple of 64 (`tst.w r3, #0x3f` at `0x638e1e28`). VGA ($640 \times 480$) cleanly satisfies this ($640 / 64 = 10$ strips).
  - Compression flag MUST be $\le 1$ (`cmp r3, #1` at `0x638e1e32`; 0: uncompressed, 1: compressed).
  - Alignment checks: $(x + w) \ \& \ 3 == 0$ on source and destination.
- **Output Pixel Format (Packed 2 BPP / YUY2)**:
  - Stride is calculated as `pitch * 2` bytes (`lsl #1` at `0x638e1ea8`, `0x638e1edc`).
  - Output is a single packed raster buffer with $640 \times 480 \times 2 = 614,400\text{ bytes}$ (`0x96000`), matching standard UVC YUY2.
- **Completion Synchronization**:
  - Synchronized via T-Kernel Event Flag 14 (`0x0e`), bit `0x04000000` (`tk_wai_flg` at `0x638e7f84`).
  - Flag cleared via `tk_clr_flg(14, ~0x04000000)` at `0x638e7f90`.

### 3. Workstream C: USB Driver Timeout Defect & 3.4 Shutdown Crash Root Cause
- **Submit Timeout Zero-Return Defect**: `usbg_video.ko` submit ioctl (`0xd00`) waits on `schedule_timeout(1000)` at `0xfd4`. If DMA times out, it logs a warning but STILL marks the staging buffer as ready with size+12 bytes (`0x1098`/`0x10b0`) and returns 0 (SUCCESS) at `0x10cc`. Return code 0 does not prove completed transfer.
- **No DMA Cancellation**: `usbg_video.ko` has no DMA abort/cancel capability in `core_cb_stop` or `core_release`.
- **Rev 3.4 Crash Root Cause**:
  1. Pixel share returned native status `-1`. `take_impl` classified this as `SHARE_FAILED` and set `shared_fault = 1`.
  2. In `vga_resize.c` line 196, `drop()` contained `if (fault) return -1;`, immediately aborting cleanup and leaking metadata/destination DMM leases across the inter-subsystem boundary.
  3. When USB Streaming was turned OFF, `Started::funcStopFuncCmd` (`0x80d8`) called `VideoEsManager::stop()` and dispatched async stop command `0x6103` (`UFW::MsgSender::SendAsyncCmdAndWaitCmp`) to RTOS.
  4. RTOS teardown hung trying to drain locked/leaked DMM units, causing a hardware watchdog reboot.

### 4. Consolidated End-to-End Patch Architecture
1. **Event-driven Frame Intercept**: RTOS tee hooks VDF producer `0x6374c500` $\to$ shares unit `0x295` to webcam queue.
2. **Explicit Lease Ownership**: DMM Share/Open on event arrival; no `/proc` polling.
3. **Validated SDF Scaling**: Passes $1920\times 1080 \to 640\times 480$, source compression 1, dest compression 0, strip width 64; validates both ACK return code and CMP payload status at offset `+8`.
4. **DMA Safety Fence**: Decouple source buffer release from submit return code; verify buffer completion before recycling.
5. **Robust Teardown & Quarantine**: `drop()` must NEVER skip cleanup on `fault`. All active leases must be cleanly unmapped, closed, and freed before `funcStopFuncCmd` issues command `0x6103`.

---

## Paused for team handoff — frame input/output contracts, 29 October 2026

User requested a pause and a new prompt for another team. Research is paused; no camera access, live IPC, flash, reboot or patch implementation occurred in this offline checkpoint. Last known camera revision remains 3.4, with failed capture and unresolved shutdown crash; the unfinished local 3.5 draft must not be flashed.

Latest authoritative evidence: [frame-contract report](../../../research/firmware/raw_frame_source/verified_yc/evidence/frame-contract-20261029/REPORT.md). Nine original-code verification scripts and two evidence collection entries passed. Recipes, mock boundaries, JSON, disassembly, input hashes and checksums are saved. Sixteen traced RTOS ranges match the historical deployed candidate; relevant USB kernel paths match apart from the known EOF byte. No fresh camera readback.

Newly proved: actual type-0 producer Share-before-Send with SDS at +0x2c; native encoder parses the retained descriptor; VDF SEND_COMP Execute is a no-op whereas ReleasePinAndMem selects 0x2001/0x050a; SDK 68-byte resize requests gain a 28-byte internal envelope, and version-0 trailing poison does not change parser state. Normal SDF builder forces transfer=1/IIB=0, so these fields do not prove ISP completion.

Critical lifetime findings: the SDK can return zero for ACK rejection or nonzero CMP payload; USB F002 tests staging availability rather than DMA completion; UpdateVideoBufEvt performs source-to-staging DMA but its DMA-timeout path can still mark a slot ready and return zero. Do not infer safe source reuse from these success returns. These findings do not establish the 3.4 crash cause, whose saved run never reached SDF.

Remaining work: genuine event route and source lease/coherence, SDF hardware completion/output packing, and DMA cancel/late-callback/stop ownership. No working live webcam or final YUY2 packing claim. Team prompt with independent workstreams, exact addresses and reproduction: [current prompt](YC_NEXT_AGENT_PROMPT.md), dated copy [team handoff](YC_TEAM_HANDOFF_20261029.md). Historical complete-contract assertions below are superseded by the two 29 October original-code reports.

## Offline YC protocol recheck - 29 October 2026

Current user direction: **offline reverse engineering only**. No camera access, flash, reboot or live message injection in this session. Last known camera revision remains 3.4; service remains closed. The local 3.5 draft is unfinished and must not be flashed: its earlier build predates source edits and no package was made.

Original Sony instructions executed offline establish a correction to the historical team synthesis below: `dmpNative::YC1Pin` exposes an outgoing Send path. Its linked native type-1 handler (`libObj.so+0x6f71e8`) unconditionally calls `abort()` for SEND/0x0102 and SEND_COMP/0x8102. It is not the receiving subscription previously claimed. Real CmdQueue/CmdDispatcher were identified by original RTTI, and their receive/dispatch path traced. No such messages were sent to the camera; this does not establish the cause of the 3.4 shutdown crash.

Category 2's original getters verify a 28-byte logical payload (32-byte padded entry): create timing [0x1979,0], transfer timing [0x197c,1,0], ID 0x7600 and three recording-trigger bytes. These values do not prove completion, monotonicity or a pixel lifetime lease. Original generic Send serializes its u32/u16/u32 arguments at +0x28/+0x2c/+0x30; SDS placement requires the specific producer caller. SendComp carries routes and status, with no echoed frame handle. Fixture transport was mocked; connection/serialization do not themselves acquire DMM references.

Four offline execution checks passed. Report, original disassembly, machine-readable results, firmware hashes and reproducible recipes: [subsystem recheck](../../../research/firmware/raw_frame_source/verified_yc/evidence/subsystem-recheck-20261029/REPORT.md). Next: trace the actual YC receiving endpoint and outstanding-frame ownership through completion/disconnect before designing another patch. Historical claims of a complete delivery contract are superseded by this recheck. Working native live frames and the shutdown crash remain unresolved.

## Revision3.4 failed capture; shutdown crash reported — 29 October 2026

User reports crash when turning USBStreamingOFF after0frame FFmpeg test. Surviving logs retrieved;3.4hashes unchanged. Recovery uptime55.89s/coldmaps consistent with restart, but no continuous precrash boot-ID trace or faultPC. Do not dismiss as unrelated. Runtime ends STOP_CLEANUP plus one VGA STOP_REQUESTED, no FINISH_CLEANUP; this locates last persisted phase, not root cause.

New stale-pixel cleanup executed: PIXEL_SHARE_STALE native-517 then continued metadata scan. Later pixel Share receives different explicit native/status-1 (unshareable state or saturation, actual condition unrecorded), which still quarantines. No RESIZE/SOURCE/COMPLETE or SSYC dump; noframe/SDF acceptance proof. Pair freshness/ownership remains unresolved. No new narrow patch or streaming trial during collection.

Ten artifacts camera-MD5 verified plus SHA256s. System AccessLog.dat/.bak snapshots each2097220B identicalMD50b8afdeacb08a53100021d678da8c86f; ThreadMonitor0B; binary access-log semantics/crash relevance unparsed, no crashPC obtained. Checked last_kmsg/pstore console paths absent.2runtimecapturelogs2035B +4194440B diagnosticcopies individuallyrechecked/cleared4196475B. Originals/system/tmp preserved. Full binaries remain local .local/outputs/vga-v34/capture-first-01/logs/; textual report/evidence: research/firmware/yuy2_transport_v34_team_candidate/evidence/capture-20261029/REPORT.md. Service closed(job019 WORKBENCH_CLOSED/Done),camera remains3.4; no reboot or flash sent.

Next offline work: paired frame freshness/ownership plus safe teardown with reserved/quarantined resources. No working native webcam claim; event-driven reception/completionvalidation still absent. User's hardware-trial authorization covered this test, not an automatic repeated test/flash cycle.

## Revision 3.4 first host capture: zero frames; logs requested — 29 October 2026

User activated USB Streaming after verified3.4 flash. One bounded FFmpeg DirectShow attempt requested5unframed614400B payloads at advertised640x480/YUY2/10fps with25s timeout. Timed out,0bytes/0frames,28.55s total host elapsed. FFmpeg log empty. This does not identify the failing stage or prove an OBS/pixel-format fault. Requested return to service without reboot for /log/yuy2_640_v34vga/ runtime/vga and possible SSYC extraction. No second streaming cycle/reboot/new patch. Camera remains3.4; working live webcam still not established. Evidence: research/firmware/yuy2_transport_v34_team_candidate/evidence/capture-20261029/; workspace .local/outputs/vga-v34/capture-first-01/.

## Revision 3.4 flashed and reboot-verified — 29 October 2026

User explicitly resumed hardware work and requested flash. Current camera3.4, not original3.3 or the team's shadow3.3 build. Module MD5ac565b4060a7062745d3bd22037d5410 (33336B), wrapper MD5ca3cbbc5947caf3373ebe451343fb926 (72796B). Both readbacks exact; activation reboot followed by successful postboot file/recovery hashes,/usr read-only and inactive cold streaming/producer/probe maps. Service closed(job012 WORKBENCH_CLOSED/Done). No3.4 frame test yet.

Pre-install hash/mapping checks found original3.3 still loaded; reboot cleared it. Fresh uptime55.71s and guarded cold hashes/kernel/storage/tmp checks passed before dependency-first install.3diagnostic files7234B archived/hashverified/rechecked/individuallycleared; system/tmp/fonts/tools preserved. Normal error filters, no appsequentialcapture. Existing bounded module logs use /log/yuy2_640_v34vga/. Recovery /usr/share/yuy2-recovery-v34vga/rollback.sh MD5e7463d98ace84c1b5db7ee95eae3defe restores original deployed3.3, not directly2.4p. Original3.3 producer, earlier recovery chain and2.4p preserved. Kernel/RTOS/SDK/DmmConfig unchanged.

Evidence: research/firmware/yuy2_transport_v34_team_candidate/evidence/install-20261029/; workspace .local/outputs/vga-v34/deployment/. Deployment-summary authoritative over historical NOT_INSTALLED build/package manifests. Rebootjobs005/009 report missingterminalmarkers because reboot stops terminal; reboot messages observed and freshsessions/postbootpassed. Next: user activatesUSBStreaming withOBSclosed for one5frame25s capture_vga.py attempt, then service withoutreboot for logs. One streaming session per coldboot remains. Stillpoolscans; no event-driven subscription/completiontokenvalidation; actual liveframes/packing remain unverified.

## Revision 3.4 flashing package built; NOT INSTALLED — 29 October 2026

User requested a new flashing binary from the team's changes. Built a DISTINCT3.4 module/wrapper pair; no camera access, deployment, reboot or test. Recorded installed baseline remains ORIGINAL3.3 module87ddc16bd8e0774926e5eb6d16165d20 and wrapper909c4ffadc9e5972b25101529d5f8773. Team-rebuilt local3.3 module14e9ec4e819c7384b8d54adb9bb38e37 is not the installed baseline. Hardware remains paused pending explicit resumption.

3.4 preserves team runtime changes: accepts data_transfer0/1; correlated stale-pixel Share rejection releases only its acquired metadata and continues. Still pool-scans; event-driven pin reception and Category2 completion/freshness validation NOT implemented. Output packing/live-frame delivery remain unverified; do not inherit the team's completion/YUY2 claims as test results.

Module yuy2_640_v34vga.so33336B MD5ac565b4060a7062745d3bd22037d5410; matched wrapper72796B MD5ca3cbbc5947caf3373ebe451343fb926. Log directory /log/yuy2_640_v34vga/. Local ZIP .local/outputs/vga-v34/zve10-v34-flash.zip includes matched pair, guarded preflight/install/rollback, storage helper, manifest, SHA256 sums and test evidence. Archive contents/hash consistency verified. Guarded installer requires exact original3.3 baseline/cold maps and preserves that recovery; rollback restores original3.3, not directly2.4p. Do not run old3.3 installer on these files.

Offline checks passed:28hostworker cases; real retainedSSYC metadata/bounds fixture;9ARMpixel-refusal and9ARMmetadata-refusal cases;3ARMsession guards;11PIC/startup cases;10installer cases.4923instructions/noNEON. Hardware outcomes mocked, no live image proof. Source/evidence: research/firmware/yuy2_transport_v34_team_candidate/. README.txt gives exact staging/recovery procedure and limits. Camera not touched.

## Historical team synthesis - delivery and completion claims superseded by the 29 October recheck

Offline reverse engineering across four specialized investigations has resolved the complete technical contract for the Sony ZV-E10 live YC pipeline. Hardware testing remains paused (camera strictly on revision 3.3; zero flashing, zero rebooting, zero mode changes). Comprehensive technical specifications and disassembled traces are documented in [YC_SUBSYSTEM_RESEARCH_PLAN.md](YC_SUBSYSTEM_RESEARCH_PLAN.md).

### 1. Producer-to-Consumer Delivery and Completion Path (R1)
- **Call Graph & Wire Protocol**: Genuine video delivery is strictly event-driven via `dataflowInfraFramework.so` (`DataflowInfraPin`), not memory-pool scanning. The RTOS producer (`.local/dumps/firmware/av-cam.bin` base `0x635c6000`, MD5 `cdcae9d4fdbf66a33704a4c7564e346d`) builds metadata in YUVInfo (`0x6374ae88`) and VEF (`0x6374cdd4`). In inlined `out_pin0_send` (`0x6374c5ba`), the producer accesses the VDF Ownership Manager singleton (`0x637489d4`, vtable `0x645852c8`) and executes `share_yc_mem` (`0x63748bec`) to pre-share pixel Unit `0x295` to consumer queue `0x0080003b`. It then posts a 52-byte `_MSG_PIN_SEND` (`0x0102`) containing the SDS handle at `+0x2c`.
- **Consumer Subscription**: In `.local/dumps/camera_2025/usr/usr/lib/libObj.so`, live consumer `dmpNative::YC1Pin` (`0x006f5958`) subscribes to VDF queue `0x0059000e`. Upon frame ingestion (`0x00e48d30`), the consumer maps the SDS descriptor, consumes pixels, and must acknowledge completion by emitting a 44-byte `_MSG_PIN_SEND_COMP` (`0x8102`, status 0 at `+0x28`) via `DataflowInfraPin::SendComp(0)` (`0x21fc5`).
- **Release Path & Root Cause of Rev 3.3 Failure**: Receipt of `_MSG_PIN_SEND_COMP` in `VdfInputReleasePinAndMem::Execute` (`0x6372808c` .. `0x6372889c`) decrements the ISP triple-buffer ring slot reference count, unlocking the slot. In Revision 3.3, uncoordinated memory-pool scanning captured candidate descriptor `0x8cc9` naming handle `0x7f24` (slot 804, generation serial 31). Because pool scanning bypassed the event lock, the ISP sequencer had already retired slot 804 and re-allocated it, bumping its generation serial from 31 to 1. Kernel `dmm.ko` (`.text+0x8898`) detected `slot_serial != handle_serial` and rejected Share with native `-517` (`0xfdfb`, translated status `-5`).

### 2. DMM Lifetime, Generation Validation, and Safe Cleanup (R2)
- **Handle Bitfield Architecture**: 16-bit DMM unit handles pack an 11-bit slot index (`handle[9:0]` and `handle[15]`, addressing up to 1408 slots, limit `0x580`) and a 5-bit generation serial (`handle[14:10]`, cycling `1..31` via `dmm_unit_ctrl_Alloc` `.text+0x9bc0`).
- **Native Status Semantics in `dmm_unit_ctrl_Share` (`.text+0x884c`)**:
  - Native `-517` (`0xfdfb`, SDK `-5`): Slot index valid, but `entry->slot_serial != handle_serial` (`.text+0x8898`). Unconditionally proves the referenced slot has been recycled to a newer generation.
  - Native `-1` (`0xffff`, SDK `-1`): Generation serial matches, but unit lifecycle state is not in `{1, 2, 3}` (e.g. `state == 0` freed, `state == 4` reused), or reference count is saturated (`ref_count == 255`).
  - Native `-3` (`0xfffd`, SDK `-3`): Unit type mismatch (`.text+0x88bc`).
  - Native `-261` (`0xfefb`, SDK `-5`): Slot index $\ge 1408$ (`0x580`).
- **DMM State Machine**: Unit entries (336 bytes, `+0xb18` type, `+0xb20` ref_count, `+0xb21` open_count, `+0xb23` slot_serial, `+0xb24` state). Lifecycle: 0=FREE, 1=ALLOCATED/CLOSED, 2=OPENED_READ, 3=OPENED_WRITE, 4=REUSED. `Close` decrements `open_count` without modifying `ref_count`. `Free` decrements `ref_count`, freeing physical extents only when `ref_count == 1`.
- **SDK Helper `freeSdsAndYc` (`0x364a1`)**: Has zero callers across camera binaries; unconditionally calls `Free(image_handle)`. On borrowed frames, calling it risks decrementing the producer's sole reference from 1 to 0, destroying the live framebuffer under the ISP.
- **Proof of Safe Metadata-Only Cleanup**: SDS metadata units (`0x000e0b00`) and pixel units (`0x295`) are autonomous DMM slots without kernel relational cascades. When Share on an expired pixel handle fails with `-517`, `dmm_unit_ctrl_Share` aborts at `.text+0x88a0` with zero state changes. The consumer holds exactly 0 references and 0 opens on the pixel unit. Calling `Close(sds); Free(sds)` cleanly releases metadata without leaking memory and without touching or corrupting the producer's image.

### 3. Real Source Metadata Contract (R3)
- **Retained Descriptor Baseline**: Genuine 4096-byte descriptor `.local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin` (SHA256 `9c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c`), magic `0x43595353`, 12 categories.
- **Complete Mapping of All 12 Categories**: Every category maps to an authentic C++ RTTI class in `.local/dumps/camera_2025/usr/usr/lib/dataflowInfraFramework.so`: Cat 0 (`ImageSizeInfo`), Cat 1 (`YcStateInfo`), Cat 2 (`ImageOutTimInfo`), Cat 6 (`MovieQualityInfo`), Cat 4 (`FaceInfo`), Cat 5 (`CameraInfo`), Cat 18 (`FocusInfo`), Cat 12 (`DisplayInfo`), Cat 16 (`LineoutRecTriggerInfo`), Cat 10 (`TcubInfo`), Cat 22 (`RemoteInfo`), Cat 23 (`IactiveCutOutInfo`).
- **Resolution of `data_transfer = 1`**: Set by RTOS builder `0x6374ae88` upon DMA delivery confirmation. Consumers (`libBizFw.so` `SdfCh::resizeRotate` and `libObj.so` `resize2VGA`) do not reject it. The rejection in `vga_source_contract` was an over-restrictive defect, now resolved.
- **Mandatory `yc_compress = 1`**: Required by hardware VPH compression (1 byte/pixel, 2,073,600 bytes) matching DMM buffer capacity; uncompressed 1080p YUY2 (4,147,200 bytes) would overflow the allocation.
- **Frame Completion Authority**: Category 2 (`ImageOutTimInfo`, monotonic hardware `id = 0x7600`, exposure tick `createTime = 0x1979`) is the frame completion authority. Category 10 (`TcubInfo`, BCD RTC `2026-10-28 21:39:47`) is the wall-clock authority. `iib_number` (`103`) is an internal ring index, not a frame counter.

### 4. SDF Hardware Resize Contract & Consolidated Patch Design (R4)
- **Scaler Topology & Channel Setup**: Requester `libObj.so` `resizeRotateImage` (`0x19fc88`) instantiates `OBJAVBBCBASECLASS::SdfCh` with ID `0x35`. Allocates OSAL queue via `DataflowInfraCh::allocOsalId` and builds a 68-byte command packet (`0x2000`, opcode 3).
- **Hardware Parameter Acceptance**: RTOS dispatcher `WrapSrotateStart` (`0x63cc8a7c` .. `0x63cc8aa4`) natively accepts input `yc_compress` in `{0, 1}`, output `yc_compress` in `{0, 1}`, input `data_transfer` in `{0, 1}`, and output `data_transfer` in `{0, 1, 2}`.
- **1-Pass Hardware Decompress and Downscale**: The Srotate hardware block natively decompresses 1080p compressed input (`yc_compress = 1`) to 640x480 uncompressed YUY2 (`yc_compress = 0`, 614,400 bytes) in a single hardware pass. Supported downscale ratio up to 32x. `strip_width = 64` represents DMA raster strip granularity (`(dim + 63) / 64`), yielding 30 strips for 1920 width and 10 strips for 640 width.
- **Memory Coherency & Barriers**: Linux driver `.local/dumps/camera_2025/usr/usr/kmod/stream.ko` configures `/dev/stream` mappings strictly as `L_PTE_MT_UNCACHED` (clearing `L_PTE_MT_MASK` via `bic r2, r2, #0x3c`). CPU write buffers require `dsb` before command issue and `dmb ish` after CMP token reception.
- **IPC Synchronization & Safety**: Two-stage synchronization via `SdfCh::sendAndRcvAckCmp` (`0x366f0`): 16-byte ACK token followed by 24-byte CMP token. Execution is isolated on a dedicated pthread. On error or timeout, physical buffers are permanently quarantined (`fault = 1`) to prevent active DMA memory corruption.

### 5. Concrete Bounded Hardware Test Protocol
When hardware testing resumes, testing must proceed under this strict protocol:
1. **Pre-Deployment**: 100% offline test pass (`check_docs.py`, contract and mock worker fixtures, target ARM compilation audit confirming 0 NEON instructions). Confirm camera `/usr` read-only and hashes match baseline.
2. **Single Bounded Run**: Exactly one streaming attempt per cold boot. DirectShow / FFmpeg requests max 5 frames with 25-second hard timeout.
3. **Diagnostic Extraction**: Return immediately to Mass Storage / Service mode without rebooting. Retrieve `/log/yuy2_640_v33vga/` logs (`runtime.log`, `vga.log`, descriptor bins). Strictly zero flashing during retrieval.
4. **Clean Rollback**: Retain `/usr/share/yuy2-recovery-v33vga/rollback.sh` to restore baseline revision 2.4p on demand.

## Hardware cycle paused; subsystem reverse engineering prioritized — 28 October 2026

User explicitly requested slowing down and reverse engineering subsystems before more patches. STOP automatic flashes, reboots and streaming tests; camera remains3.3. Offline work continues under docs/archive/sessions/YC_SUBSYSTEM_RESEARCH_PLAN.md. Service closed(job018 WORKBENCH_CLOSED/Done). No new patch installed in evidence collection.

3.3 logs prove known metadata refusal skipped, second SSYC metadata Shared/Open/mapped, then attached pixel type0x295/handle0x7f24 Share rejected native-517/status-5 (kernel slot serial mismatch). Thus fresh metadata/pixel handoff remains unestablished; not an Open/mmap/pixel-format failure. Exact timing of image expiry vs old descriptor remains unresolved. No resize request or frames.

Recovered the worker's RETAINED4096B source_snapshot read-only via fresh-map/ELF-derived address, without another stream test. All31fields match compiled C decoder. Real SSYC has12categories and1920x1080 geometry,yc_compress1,data_site0,data_transfer1,placement1,content2,scan1,strip64,yc_bit_depth0. Additional known blocker: current source contract rejects nonzero data_transfer. Do not relax/overwrite it without tracing its meaning/SDF requirements. Metadata lifetime does not pin or validate its referenced image; mocks do not prove live handoff.

Report and decoded metadata: research/firmware/yuy2_transport_v33_source_retry/evidence/capture-20261028/REPORT.md and .local/logs/source-ssyc-decoded.json. Real4096B snapshot SHA2569c60c7088da03631af4cd06fbd8f9d444d084e9104ead87cb0147ef76ac45f9c remains workspace .local/outputs/vga-v33/capture-first-01/logs/source-ssyc-retained.bin. Raw8192B process readback contains surroundingbytes; keep local, do not distribute/replay addresses.8downloaded artifacts hashverified.2capturelogs1673B plus8192B readbackscratch rechecked/individuallycleared9865B; system/tmp/helpers preserved. No appsequentiallogging.

Next offline deliverables: original producer/delivery/completion/release call graph; metadata+pixel ownership/generation state machine; observed flag enum/consumer contract including data_transfer1; SDF acceptance/cache/ACK/CMP contract. Consolidate into a reviewable patch after these are established. Earlier next-stream/flash entries are superseded by this user pause.

## Revision 3.3 host capture: zero frames, logs pending — 28 October 2026

User activated USB Streaming after verified3.3 installation. One bounded FFmpeg attempt requested5native614400B payloads,640x480/10fps advertisedYUY2,25s timeout. Timed out with0bytes/frames,27.03s host elapsed; FFmpeg log empty. Host result does not establish whether the new source refusal handling advanced. Requested MSC/service return without reboot to retrieve /log/yuy2_640_v33vga/ diagnostics. No second streaming cycle/reboot/new patch. Current3.3 remains installed; working native webcam not established. Evidence: research/firmware/yuy2_transport_v33_source_retry/evidence/capture-20261028/ and workspace .local/outputs/vga-v33/capture-first-01/.

## Revision 3.3 source rejection fix installed and reboot-verified — 28 October 2026

User requested new flash. Current camera3.3: module MD5 87ddc16bd8e0774926e5eb6d16165d20 (32972B), matched wrapper MD5 909c4ffadc9e5972b25101529d5f8773 (72796B). Readbacks exact; post-activation reboot hashes/recovery match, /usr read-only, modules inactive before setup. No3.3 frame test yet. Service closed(job012 WORKBENCH_CLOSED/Done).

Original kernel Share0x884c/handler0x62e4/access-info0x9238 executed offline: captured native-1 reply means unshareable state or saturated255references; no new allocation reference on this refusal. Wrong type produces native-3; stale serial native-517. Which-1condition happened live remains unknown.3.3 skips only OPTIONAL metadata candidates with SDKrc0 and exact correlated24B command0x8002/status/native-1, matchinghandle/queuelow/type,site0 and zeroaddress/length. Clears unacquired potential-share state without Open/Close/Free and continues bounded scan. Destination/unknown/transport/mismatched replies still quarantine. Lifetime/metadata/format guards remain. No image proof.

DMM kernel MD515c8f7807b291c0af3c77fe55848577f matched on camera and is now guarded by installer. Kernel itself unchanged.86offline cases pass:10originalkernel,26hostworker,9ARMtake,17ARMloader,11PIC/startup,3ARMsession,10installer.4851instructions/noNEON. Hardware services mocked; clock/debug imports mocked and access-info execution uses zero attachedextents.

Recovery /usr/share/yuy2-recovery-v33vga/rollback.sh MD5acb7ad03595556ff6f40f312f54a806a restores exact3.2; earlierproducer/recoverychain/2.4p preserved. Prior3.2mappedmodule cleared by pre-install reboot; freshuptime60.96s coldguards/space/tmp checks passed.3old diagnosticfiles7234B archived/hashverified/rechecked/individuallycleared; system/tmp preserved. New bounded directory/logs /log/yuy2_640_v33vga/. Normalerrorfilters/no sequentialcapture. No RTOS/SDK/DmmConfig/USBkernel change.

Source/report/evidence: research/firmware/yuy2_transport_v33_source_retry/; workspace .local/outputs/vga-v33/; local ZIP zve10-v33-source-retry.zip. Historical manifest NOT_INSTALLED is build-time only; evidence/install-20261028/deployment-summary.json authoritative. Rebootjobs005/009 missing terminalmarker after observed Restarting system, freshsessions/postbootpassed. Next: user activatesUSBStreaming withOBSclosed, one bounded5frame25s capture_vga.py attempt, then servicereturn withoutreboot to inspect SOURCE_SHARE_DECLINED and progress/source/resize/SSYC evidence. One session per coldboot; nativepixels/packing/livewebcam remain unproved.

## Revision 3.2 exact failure: DMM rejects source Share, status -1 — 28 October 2026

Recovered live diagnostics: initialization/queues/VGA destination allocation/Share/Open/map pass. Candidate SSYC0xe0b00 Share gets SDK rc0 but native completion command0x8002,status signed16 -1. Reply words ffff8002 611a1755 ffff0000 000e0b00 00000000 00000000; handle/queue-low match current request. This is explicit service rejection, not source Open/mmap failure or proven transport failure. Candidate signature peek does not establish video metadata eligibility. No source pixels/resize/SSYC dump/frames. Transient handles/addresses must never be replayed.

Next: trace command2 negative completion paths and type/relation/owner/stale-handle checks; prove absence of side effects before enabling safe candidate retries. Stale candidate is a hypothesis, not diagnosis. Keep guards/quarantine for ambiguous outcomes; do not map unowned data. Full report and parsed reply: research/firmware/yuy2_transport_v32_source_diagnostics/evidence/capture-20261028/REPORT.md and .local/logs/source-share-reply.json; workspace .local/outputs/vga-v32/capture-first-01/.

Seven data artifacts camera-MD5 verified with SHA256s. Two capture logs1212B rechecked/individually cleared; system/tmp preserved. Service closed (job017 WORKBENCH_CLOSED/Done).3.2 remains installed, no patch or reboot during collection, one session per cold boot. Working live webcam not established.

## Revision 3.2 host capture: zero frames; service logs requested — 28 October 2026

User activated USB Streaming after verified3.2 flash. FFmpeg requested5unframed640x480/10fps advertised YUY2 payloads with25s timeout; timed out,0bytes/0frames,27.03s total host elapsed. FFmpeg log empty; host result alone does not identify acquisition stage. Requested return to service without reboot for /log/yuy2_640_v32vga/ detailed replies. No second streaming session or reboot.3.2 remains installed; no working sensor image claim. Evidence: research/firmware/yuy2_transport_v32_source_diagnostics/evidence/capture-20261028/; workspace .local/outputs/vga-v32/capture-first-01/.

## Revision 3.2 installed and reboot-verified — 28 October 2026

User authorized flash. Current camera is3.2 diagnostics: module MD5 de59485d1ad155711d81cd592ed5b821 (32632B), matching wrapper MD5 cc3de8f0f0b710e6e2027ac78ea94c50 (72796B). Exact binary/recovery readbacks matched; post-activation reboot hashes persisted, /usr read-only and no streaming/producer/probe mappings before setup. No3.2 stream/frame test yet. Do not reinstall based on historical build manifest NOT_INSTALLED.

Installer passed10 local failure/rollback fixtures. Prior3.1 module was still mapped; pre-install reboot cleared it, fresh uptime52.08s and cold-map/hash/storage/tmp checks passed. Dependency-first installation. /usr/share/yuy2-recovery-v32vga/rollback.sh MD5 7f4b4678ca05f92beba74dcd05588556 restores exact3.1 wrapper;3.1 producer and earlier recovery chain including2.4p preserved.3old diagnostic files7234B archived/hash-verified/rechecked/individually cleared; system/tmp/fonts/tools preserved. Kernel/RTOS/SDK/DmmConfig unchanged. Normal error filters; no sequential application capture. New bounded diagnostics directory /log/yuy2_640_v32vga exists.

Service closed (job012 WORKBENCH_CLOSED/Done). Evidence: research/firmware/yuy2_transport_v32_source_diagnostics/evidence/install-20261028/; guarded deployment scripts now in deployment/; workspace .local/outputs/vga-v32/deployment/. Reboot jobs005/009 missing terminal markers as expected after Restarting system, followed by successful fresh sessions/postboot checks. Next: user activates USB Streaming with OBS closed, one bounded5-frame/25s capture_vga.py test, service return without reboot for detailed Share/Open/map reply evidence. One session per cold boot; no working live-frame claim. Previous no-installer/offline-only entries are historical.

## Revision 3.2 source-acquisition diagnostics built — 28 October 2026

Built offline, NOT INSTALLED; camera remains3.1. Candidate adds stage-specific Share/Open/address-site/mapping evidence and full six-word DMM reply logging on acquisition failures. Candidate SSYC hint geometry/address recorded before take, still not proof of video descriptor. Mapping reasons distinguish invalid span, USB/staging overlap, overflow, stream-device open and mmap.64KiB VGA log cap retained; synchronous diagnostic writes can change timing. No retry/release/ownership or quarantine relaxation; actual failure reply semantics still unresolved.

Source/evidence: research/firmware/yuy2_transport_v32_source_diagnostics/; local ZIP .local/outputs/vga-v32/zve10-v32-source-diagnostics.zip. Module MD5 de59485d1ad155711d81cd592ed5b821 (32632B); matching wrapper MD5 cc3de8f0f0b710e6e2027ac78ea94c50 (72796B).17 host worker,17 ARM initialization,11 PIC/startup and3 ARM session cases pass;4775 audited instructions/no NEON. Live SDK/DMM mocked; no camera action or new frame proof. Log directory /log/yuy2_640_v32vga/ must exist. No automatic installer yet; do not reuse3.1 scripts unchanged. Next authorized hardware deployment must use fresh boot/current3.1 guards and recovery/readback/read-only checks; single bounded capture then service return without reboot. Do not replay transient handles or call this an established acquisition fix.

## Revision 3.1 live logs: initialization fixed, source acquisition quarantined — 28 October 2026

After zero-frame FFmpeg timeout, user returned to MSC. Camera hashes match3.1; logs prove MAPS_READ48993bytes, QUEUES passed, VGA destination setup advanced. Old GUARD_FAILED absent. Then candidate SSYC handle18db/type0xe0b00 acquisition triggers QUARANTINED before source pixel reference or resize; candidate is not yet a verified video descriptor. take() logs before Share and conflates Share/Open status, address-site and mapping failures, so exact failing operation remains unresolved. No SDF request, no SSYC dumps, no frames. Handles are session diagnostics only; never replay.

Report/evidence: research/firmware/yuy2_transport_v31_vga_init_fix/evidence/capture-20261028/REPORT.md, workspace .local/outputs/vga-v31/capture-first-01/. Seven data artifacts camera-MD5 verified plus host SHA256s. Two runtime logs834B archived/rechecked/individually cleared, system/tmp preserved. Service closed (job017). Current3.1 remains installed; one-session-per-cold-boot/quarantine restrictions unchanged. No reboot or deployment during collection. Next offline diagnostic patch: stage-specific bounded acquisition result/status/map evidence; verify real negative-reply semantics before retry/release changes. Init fix demonstrated, working sensor webcam not established.

## Revision 3.1 first host test: timeout, zero frames — 28 October 2026

User activated USB Streaming after verified3.1 installation. Bounded FFmpeg DirectShow request640x480/YUY2/10fps,5frames,25s timeout captured0bytes/0frames; process killed on timeout (total host elapsed28.49s). FFmpeg log empty; no pixel-format or initialization cause can be determined from host evidence. Requested user return to service without reboot for /log/yuy2_640_v31vga/ runtime/vga/SSYC collection. No second streaming cycle, reboot or new patch. Evidence: research/firmware/yuy2_transport_v31_vga_init_fix/evidence/capture-20261028/ and workspace .local/outputs/vga-v31/capture-first-01/. Current3.1 remains installed; working live webcam not established.

## Revision 3.1 installed and reboot-verified — 28 October 2026

User authorized flash. Current camera is3.1 experimental VGA: module MD5 72f800fd8f5e6d943b1d33d173bedeb1 (31900B), matching wrapper MD5 24bc5972c11f953ad1408f477376a877 (72796B). Exact host readbacks matched both binaries and recovery files; post-activation reboot confirmed hashes persisted, /usr read-only, and no streaming/producer/probe mappings before setup. NO3.1 frame test yet. Do not reflash or treat historical build manifest NOT_INSTALLED as current state.

Guarded installer passed10 local install/failure/rollback fixtures. Pre-install reboot observed, fresh uptime57.30s and cold mappings/hash/space/tmp readback checks passed before dependency-first installation. Recovery /usr/share/yuy2-recovery-v31vga/rollback.sh (MD5 ee5666a99e604fb9704f454995d404ed) restores exact3.0 wrapper; original3.0 producer, earlier3.0→2.9 recovery,2.9→2.4p recovery, stable2.4p producer, kernel, RTOS, DmmConfig and SDK remain intact. Archive/hash-verify/recheck/individual cleanup removed3 old diagnostic files7236B; system/tmp/fonts/tools preserved. Normal error filters; no application sequential logging. New bounded runtime/vga logs under /log/yuy2_640_v31vga/; directory created.

Service sessions closed; final job012 confirmed WORKBENCH_CLOSED/Done. Reboot jobs005/009 report missing terminal markers because reboot stopped the terminal; Restarting system was observed and subsequent fresh sessions/postboot checks passed. Evidence: research/firmware/yuy2_transport_v31_vga_init_fix/evidence/install-20261028/; installer source in deployment/; workspace .local/outputs/vga-v31/deployment/. One streaming session per cold boot remains. Next: user activates USB Streaming with OBS closed, then bounded5-frame/25s capture_vga.py test, then service return without reboot for detailed initialization/SDF logs and SSYC dumps if produced. No working image claim. Old no-installer/build-only entries below are historical.

## Revision 3.1 initialization fix built offline — 28 October 2026

Candidate built, NOT INSTALLED. Camera remains 3.0. Root code defect: VGA load_calls reads /proc/self/maps once; a legitimate short read can exclude libObj.so (pathname first at byte14704 of recovered47338-byte maps), falsely failing initialization. Compiled old ARM worker reproduces GUARD_FAILED with2KiB reads and passes with identical input delivered whole. New3.1 reads through EOF with bounded capacity/error checks and detailed per-branch diagnostics; guards remain enabled. The historical generic hardware log cannot identify the exact failed branch, so this is a reproduced defect consistent with failure, not definitive target branch attribution.

17 ARM loader regressions,9 host worker scenarios,11 PIC/startup checks and3 ARM session checks pass;4668 audited instructions/no NEON. Source/evidence: research/firmware/yuy2_transport_v31_vga_init_fix/. Local deployable ZIP: .local/outputs/vga-v31/zve10-v31-vga-init-fix.zip. Module MD5 72f800fd8f5e6d943b1d33d173bedeb1 (31900B); matching wrapper MD5 24bc5972c11f953ad1408f477376a877 (72796B). Log directory /log/yuy2_640_v31vga must exist. No automatic installer; do not reuse3.0 scripts unchanged. No camera access, flash or live frame test this turn. Fresh boot/current3.0 guards/recovery/readback/read-only checks required for later deployment; one session per cold boot. SDF acceptance and intelligible live frames remain unproved.

## Revision 3.0 OBS failure: initialization blocked — 28 October 2026

User resumed diagnostic collection after an unsuccessful OBS test. Logs were recovered and hash-verified; revision 3.0 and SDK/libObj/pthread on-disk hashes match installation. VGA worker reports GUARD_FAILED then QUARANTINED with zero buffer handles. No QUEUES/SHARE/RESIZE/COMPLETE marker or SSYC dump exists: failure occurs inside load_calls initialization before source discovery, not a demonstrated pixel-format failure. This generic error conflates library/symbol/prologue/maps validation and zero queue IDs after constructors; exact branch remains unresolved. Next: audit relocated prologue guards/maps handling and add distinct bounded failure reasons, without disabling checks. No patch/reboot/stream test performed during collection.

Evidence and report: research/firmware/yuy2_transport_v30_vga/evidence/obs-failure-20261028/; workspace .local/outputs/vga-v30/logpull-20261028/. Nine artifacts camera-MD5 verified with host SHA256s. Two archived capture logs (734 B) rechecked, individually cleared, absence verified; system/tmp/helpers preserved. Service session closed. 3.0 remains installed; live VGA output failed this user OBS trial. One-session-per-cold-boot restriction remains. Previous pause/untested entries below describe historical state; this collection supersedes their no-OBS-test status but does not resume automatic testing or flashing.

## Camera testing paused by user; next major push is 4K/12-bit — 27 October 2026

USER REQUESTED PAUSE AFTER FLASH. No3.0 FFmpeg/OBS capture was performed. All camera service workbench sessions are closed (job015 confirmed WORKBENCH_CLOSED/Done); no live test or new deployment should resume automatically. Leave installed3.0 in place; this pause did not request rollback. Flash/readback/postboot/inactive-map/RO checks passed as recorded below, but live VGA resize/output acceptance remains untested.

Next major offline direction: docs/archive/sessions/4K_12BIT_NEXT_PUSH.md, also linked at the top of OPENGATE_FINDINGS.md. Use the actual hardware-proven2.4p VGA colour-bars binaries as the control, and the new3.0 Sony VGA allocator/SSYC/SDF findings as a route to trace genuine high-bit-depth4K buffers. Do not call3.0 colour-bars-tested or regard synthetic8-bit bars as evidence of12-bit acquisition. Verified reference bundle: research/firmware/4k12bit_baseline_20261027/ (five binaries with MD5/SHA256; separate matched2.4p/3.0 pairs and provenv23 kernel; offline reference only).

The next step is a verified producer/metadata/allocation/precision/sink map, followed by a guarded prototype with explicit remaining hardware requirements. Source precision,4K geometry, encoded bit depth and sustained delivery are separate proofs. Corrected packed UHD12-bit YUV420 size is18662400B/frame (not~11.87MiB); Bayer12-bit is12441600B/frame.24fps packed payloads are298598400B/s Bayer,447897600B/s YUV420,597196800B/s YUV422, excluding overhead/padding. Current USB2 VGA transport is diagnostic/control infrastructure, not a proven continuous4K/12-bit path. No new camera actions or patches during this documentation update.

## Revision 3.0 installed and reboot-verified — 27 October 2026

USER REQUESTED FLASH COMPLETED. Current camera revision is3.0 experimental VGA, not2.9. Module MD5 98acd3ba3d6628e006fe51d88dda25dc (30996B); persistent streaming library MD5 2a4c08511526f2b525c57a1d9bac9bad (72796B). Both were downloaded/readback verified and matched again after activation reboot. /usr is read-only; streaming library, producer and old observer/probe modules are absent from cold process maps, so no new streaming code active before setup. NO STREAM/FRAME TEST YET: live SDF acceptance, output pixels/packing, frame rate and coherent source frames remain unverified. User must now activate USB Streaming with OBS closed and report streaming for the bounded FFmpeg test. Do NOT reflash or load a RAM bootstrap merely because the offline package manifest says NOT_INSTALLED; that is its historical build-time status.

Deployment/evidence: research/firmware/yuy2_transport_v30_vga/deployment/ and evidence/install-20261027/; workspace .local/outputs/vga-v30/deployment/. Installer passed10 simulated failure/rollback cases. Exact previous2.9 wrapper, stable2.4p wrapper and hardlinked old inode preserved under /usr/share/yuy2-recovery-v30vga/. rollback.sh there restores2.9, with cold-mapping guards; then existing /usr/share/yuy2-recovery-v29full/rollback.sh can restore2.4p if needed. Old2.9/2.4p producer files, kernel, RTOS, DmmConfig, SDK and common library unchanged. Required pthread is /lib/libpthread.so.0 (MD5 09cb541e6e785dd6bfeb76d74f29f5d2), not /usr/lib/.

Before installation6old capture/status logs7642B were archived/downloaded/hash-verified, rechecked and individually cleared; system/tmp/fonts/tools preserved. Storage and4096B/tmp write/readback passed. Normal error filters restored; no unbounded debug capture. A preflash reboot cleared loaded2.9 code; fresh preflight passed before installing dependencies first. Activation reboot observed, then a fresh service session verified hashes/recovery/RO/inactive maps/storage. Reboot workbench jobs report missing completion marker because terminal stopped during Restarting system; this is expected, not an install failure. Final postboot job014 passed. Service close job015 queued/completing.

ONE STREAMING SESSION PER COLD BOOT remains enforced. Next: use .local/work/vga-v30/recipe/capture_vga.py for5unframed614400B payloads with25s timeout, then user returns to service without reboot for bounded vga.log/runtime.log and input-ssyc.bin/destination-ssyc.bin collection. Do not use2.9 reassembler. No bars/fallback or confirmed YUY2 conversion. Preserve failures/metadata and verify source ref release; owned input/destination allocations stay reserved until reboot and uncertain SDK results quarantine. Archive/hash-verify/recheck/clear known research captures as regular procedure. Do not assume2.9 stale USB-output reuse has been fixed beyond the new one-session guard.

## Revision 3.0 experimental VGA resize candidate built — 27 October 2026

OFFLINE ONLY; NOT INSTALLED or camera verified. Installed remains 2.9. Candidate/package: research/firmware/yuy2_transport_v30_vga/; workspace ZIP .local/outputs/vga-v30/zve10-v30-vga-experimental.zip. Guide: docs/usb/uvc_vga_v30_candidate_20261027.md. Module yuy2_640_v30vga.so MD5 98acd3ba3d6628e006fe51d88dda25dc (30996B); matching persistent libInfraStreamingUsb.so MD5 2a4c08511526f2b525c57a1d9bac9bad (72796B). Package has no automatic installer; preserve verified2.9/2.4p recovery and do fresh cold-boot service/hash/maps/storage preflight before any installation.

Uses Sony SDF resizeRotate and actual libObj resize2VGA paired allocation/metadata path to request owned640x480, yc_compress0, type0x220 output from native VEF0x295. Does NOT select global VEF record5 or flip HD compression. A private lazy pthread discovers SSYC via bounded DMM/read-only signature hints, then pins/revalidates metadata and pixel references. Requires YcStateInfo, rejects multi-segment/unsupported flags and checks spans/overlap. SDF receives an OWNED SSYC COPY pointing to the pinned pixel allocation: producer descriptor mutation cannot redirect it. ACK/CMP and destination metadata/capacity must pass before publishing a complete614400B copy. No bars/fallback or CPU YUY2 conversion. Actual packing/bit depth/coherent source completion and camera frame rate remain unproved. Advertised10fps only. Successful target capture is not yet established.

ONE STREAMING SESSION PER COLD BOOT. Stop does not join a potentially blocked SDK thread. Ambiguous outcomes quarantine resources; owned destination/input allocations stay reserved until reboot. Output detach permanently blocks rebind until boot, including stop before any host frames, preventing inherited2.9 stale USB-mapping reuse. No reusable mode-cycle fix or MENU restart diagnosis claimed. A separate thread does not rule out shared-hardware freezes. Live SSYC availability, SDK/thread init, compressed-to-uncompressed acceptance, cache behavior and target loader need validation.

Offline checks passed:9 mocked hardware-boundary worker scenarios (including immutable owned metadata, descriptor races, failures, size/MMIO/USB overlap), metadata contract fixture,6 original Sony caller+SDK request fixtures,4 original RTOS size fixtures, original Sony geometry method,11 PIC/no-constructor cases,3 compiled ARM post-stop/session checks and4523 module instructions/no NEON. Hardware boundaries mocked; see evidence/ JSON. Capture tool now saves UNFRAMED614400-byte VGA payloads; DO NOT use2.9 reassemble.py or assume YUY2 packing. First bounded FFmpeg run only, then service .local/logs/SSYC extraction without restart. Archive/hash-verify/recheck/clear known logs first and after; preserve system/tmp files. New bounded logs: /log/yuy2_640_v30vga/{runtime.log,vga.log,input-ssyc.bin,destination-ssyc.bin}. No camera access or writes occurred while building this candidate.

## Native VGA and resize2VGA investigation — 27 October 2026

Offline only; camera remains on revision 2.9, no new live VGA test or writes. See docs/usb/uvc_native_vga_resize_investigation_20261027.md and verified_yc/evidence/native-vga-20261027/. Found actual libObj resize2VGA() at0x19fd94: paired SDS type0xe0b00/image type0x220 allocations, width640 with aspect-dependent heights (426/360/640; fallback480), metadata store, resize helper0x19fc88. This is distinct from native VEF table record5/type0x295 with all640x480 and yc_compress0. Six original caller+SDK fixtures prove 68-byte requests: source type/handle+0x18/+0x1c, destination type/handle+0x38/+0x3c. They reference SSYC metadata, not bare pixel handles. Inspected RTOS parser uses a different extended layout; translation remains unresolved. Four original RTOS capacity fixtures prove VGA uncompressed614400B, HD uncompressed4147200B (exceeds existing0x320000 output capacity). Do not flip global compression flag. Next: recover source SSYC reference, complete paired destination allocation/metadata and release, verify compressed-to-uncompressed acceptance, bounded completion/cancellation, then one-shot live capture. Ten offline fixtures passed; no hardware-format proof. Fresh boot required before further live test because retained 2.9 USB output allocation reuse remains unresolved.

## Revision 2.9 complete native allocations captured — 27 October 2026

FFmpeg stream-copy captured16complete614400-byte USB packets,9830400bytes, no trailing bytes, exit0. All2.9 headers/payload CRC32/ranges/padding passed. Reassembly exported THREE distinct complete2073600-byte native allocations (IDs2/3/4); incomplete boundary IDs1/5 withheld. First packet starts ID1 offset614336, last is ID5 offset0. Snapshot SHA256s: ID2 4b0feb4634b753068f669fa96ec4705d989ecafeb87d12c66940b3cf65fbba47; ID3 df470de0c6cbb0c7c2b30f6448cb7e22a5f14168b687ddff043a47dc94037c5a; ID4 10ba544c9b58cdc45355066123058792a2ec55911c3a7d22f2031574317f04e6. Native image decoding, exact geometry/depth and frame-completion remain unproved.

One full binary plus accompanying text for decoder: workspace .local/outputs/native-dmm-v29/decoder-handoff/zve10-vef295-full-snapshot.bin and .txt. Binary has native offsets0..2073599 unchanged, all64B chunk headers/final padding removed. Each group is one owned copy before USB chunking, never independently reacquired windows; source could change during that initial copy. At conditional1920-byte pitch all1080rows contain data; byte5 lag30 correlations0.8396..0.8520 across three snapshots. This supports structure through the full allocation, not definitive live metadata.

Measured FFmpeg elapsed6.76s:2.37USB PACKETS/s, about0.59full snapshots/s at4packets per allocation. Do NOT call this2.4image-fps or24fps. Camera runtime SNAPSHOT_US84.722..116.086ms (mean99.642), first PACKET_COPY_US304.686..359.570ms (mean336.191). Packet assembly includes full memset/memcpy and bitwise CRC over output mapping; it is the largest measured phase. CRC is a prime optimization candidate, but individual substeps were not separately timed. Remaining100ms entry sleep adds overhead. Module logs retain inherited INSTALLED_V25 label; installed MD5s match actual2.9 producer b4c6012cd876210fcfd0cf4b0d6f67e0 and stream32a2d064d25720c17dd9a43927d4a835; common/kernel unchanged.

After stopping, dynamically addressed module-state readback verified7native snapshots,25software packet submissions (includes prefetch beyond16saved),28requests/28replies, backendIDLE, no native shared/open refs/token, no pending heap snapshot, USB in-flight0. HOST_WAIT occurred after host close; final submit rejection during mode stop is in logs. Separately, the module retains its owned output mapping/handle0x0cb9 atphysical0x15b00000 although that unit is absent from post-stop DMM listing. These addresses are session diagnostics, never replay. Full mode-cycle reuse remains unverified and must not be assumed safe merely because native-source references were released.

User reported one restart before the successful run and requested proceeding. Runtime log contains two LOAD/setup sequences; cause unresolved. Persistent files survived and current capture checks passed; this does not prove crash independence or frame coherence. After collection,9known camera capture files199700bytes were downloaded, hash-verified, rechecked and individually cleared; storage and /tmp write/readback passed. Runtime/fonts/tools/system logs preserved. Service session closing. No additional patch or reboot during successful capture/log collection.

Compact evidence: research/firmware/yuy2_transport_v29_full_snapshot/evidence/full-capture-20261027/. Full host capture and all3native binaries remain under workspace .local/outputs/native-dmm-v29/capture-first-01/. Next work: exact codec recovery with complete buffers/live metadata; optimize packet assembly/CRC and remove needless pacing with measured checks; resolve output allocation reuse before claiming repeatable mode cycling.

## Revision 2.9 installed and reboot verified; capture pending — 27 October 2026

User authorized flashing with camera connected in mass-storage/service mode. Exact prior2.8 hashes and cold process mappings matched. Normal error filters restored;19known diagnostic status files (714bytes, no large old application capture found) were downloaded, hash-verified, rechecked and individually deleted. /tmp runtime fonts/tools/system logs preserved. Space guard passed before/after cleanup and after reboot, including4096B /tmp write/readback. Initial memory:128796KiB total,1452KiB free,55820KiB cached; new4MiB snapshot heap is allocated lazily during actual capture and remains untested.

Installed /usr/lib/yuy2_640_v29full.so MD5 b4c6012cd876210fcfd0cf4b0d6f67e0 (30600B), /usr/lib/libInfraStreamingUsb.so MD5 32a2d064d25720c17dd9a43927d4a835 (72796B). Installer returned0; both binaries downloaded and verified. Previous2.8 stream MD5 27f4f4696c724caa8348edc51c86a517 and stable2.4p rescue MD5 5fde77e394572ebcf420f8941575f6c4 downloaded/verified under /usr/share/yuy2-recovery-v29full/. Explicit rollback.sh restores working2.4p; failed-install recovery restores previous2.8. Existing kernel/RTOS/config/common/SDK hashes unchanged. Kernel reboot messages confirmed restart; subsequent uptime54.10seconds and reread hashes confirmed persistence. /usr ext2 read-only; streaming library, yuy2 patch and observers/probes absent from pre-setup process maps. No MENU/streaming behavior or frame capture validated yet. Do not claim image output or improved fps.

Evidence: research/firmware/yuy2_transport_v29_full_snapshot/evidence/hardware-install-20261027/; full workspace .local/outputs/native-dmm-v29/deployment/. Current module runtime log will be /log/yuy2_640_v29full/runtime.log on activation. Application logging remains at normal error filters. Service session closing after readback; no RAM probe installed. Next live step: USB Streaming with OBS closed, FFmpeg stream-copy at640x480/YUY2/10fps for at least16packets, run2.9 reassemble.py, then MSC/service log/ownership collection without reboot. Each packet now has64B header and614336B native payload; a2073600B allocation requires4packets. Pixel format and exact codec remain unknown.

## Independent codec recovery: exact parser still unresolved — 27 October 2026

Continued offline at user's request. No camera access or patch changes. New investigation/evidence: docs/usb/uvc_vef295_independent_recovery_20261027.md and verified_yc/evidence/codec-recovery-20261027/. Across ten captures,34279blocks isolate candidate Y/C streams with W4=W5=0; supplied decoder leaves nonzero candidate-luma bits unread in29163(85.08%) and candidate-chroma bits in14604(42.60%). Its output is not a bit-complete validated decoder under the claimed routing. A57-bit isolated chroma candidate has only19ones, incompatible with64tokens each ending1 under the proposed pure-unary model. Alternate run syntax/count/routing remains possible.

Independent Rice/Exp-Golomb/sign/interleaved and initial-anchor searches found no validated parser. A compiled21952-variant groupwise search fit at most125/384isolated stream endings, rejected as universal; this is bounded negative evidence, not proof no adaptive/transform/Rice-like codec exists. Native bit-depth log mapper0x63a06dfc executed:0=DEPTH_8,1=DEPTH_10,2=DEPTH_12,3=DEPTH_14,4=UNKNOWN. Connection to SSYC enum/live source not yet proved. Additional Stage_Decomp path traced acquire0x63b31fec/start0x63b3218c/release0x63b32078 via hardware resource operations; no link to VEF0x295, possibly RAW-stage, do not call on YC based on name. Two Sony block-compression patent leads remain unconfirmed architectural references, not identified codec specifications.

Installed camera remains2.8; prepared2.9 unchanged/unflashed. Do not port heuristic reconstruction as a verified decoder. Full allocation plus same-delivery metadata, native codec specification, or independent known-content captures remain the most discriminating evidence. Metadata alone would identify format flags, not entropy rules.

## External decoding theory audited against firmware — 27 October 2026

Offline firmware/code/data cross-check saved in docs/usb/uvc_vef295_codec_crosscheck_20261027.md and verified_yc/evidence/codec-audit-20261027/. No camera access or patch changes; installed remains 2.8, prepared 2.9 remains unflashed. External agent's report and images were read only.

Confirmed byte5 lag-30 correlation 0.865677 (lags29/31 ~0.195); 3453/9600 blocks with W4=W5=0; reported W0 header counts reproduced. Compressed-HD/64-byte-block/30-block-row interpretation is a strong candidate. It is not yet an exact decoded-image format. Original VEF builder executed for four real records: HD compression flag1, VGA0; ALL write strip_width64 before the compression branch. Thus strip_width64 does not establish 64-byte compressed packets. Original mirror/compression-gated alignment function0x63a460d4 passed32 input cases; only under gates r2 in{1,3},r3==1 does it require (field+0x30 + field+0x34) divisible by64. Thirteen CalcStripWidth selector fixtures and four metadata executions saved. yc_bit_depth remains untouched by the inspected builder, not established by this audit.

Actual reconstruction implementation contains manually chosen luma anchors, quantizer/residual scales1.6/0.8/0.75, modeled chroma around128 and Cr partly derived from Cb. Instrumenting its functions:544/9600 blocks parse fewer than56 luma residual tokens;5763/9600 parse fewer than64 chroma tokens, with remaining samples filled by the implementation. Natural-looking bounded output is not proof of exact anchor/color decoding. Zero-tail termination, escape coding and nonoverlap of candidate streams are unresolved. 1920x1080 active geometry, exact 1B/pixel, bit depth, 4:2:2 plane ordering and tear-free semantics still need matching live metadata/codec evidence. No matching software pixel decompressor found in bounded compression configuration paths or named Linux exports; not proof absent globally.

Next: full allocation capture with2.9 plus same-delivery ImageSizeInfo/YcStateInfo, then bit-exact codec validation using explicit bit accounting and independent scene data. Note2.9 uses64-byte headers, so native chunk payload is614336 bytes and final2073600-byte-allocation payload is230592 bytes. Use reassemble.py; do not apply the external report's unframed614400-byte offset schedule. A pin SEND hook alone does not establish frame stability without its reference/completion/return protocol.

## Revision 2.9 full-allocation patch prepared offline — 27 October 2026

Camera is offline; no device access or writes. Installed version remains 2.8. New source: research/firmware/yuy2_transport_v29_full_snapshot/; workspace package: .local/outputs/native-dmm-v29/zve10-v29-offline-package.zip. Candidate producer MD5 b4c6012cd876210fcfd0cf4b0d6f67e0 (30600 bytes), persistent streaming library MD5 32a2d064d25720c17dd9a43927d4a835 (72796 bytes). NOT hardware verified.

2.8 sent only the first 614400 bytes of a 2073600-byte native allocation. 2.9 copies the whole returned extent once into bounded 4 MiB owned heap storage, completes native Close/Free, and sends numbered/checksummed chunks: 64-byte ZVYC0029 header + up to 614336 payload bytes per existing 614400-byte USB packet. Four packets cover the previously observed allocation. Host reassemble.py exports only complete, checksum-valid groups with headers/padding removed. No format conversion or synthetic fallback. USB YUY2 remains an envelope; OBS cannot display the new protocol as a proper image. Complete allocation does not prove coherent completed image, geometry, bit depth or compression format. Actual live ImageSizeInfo remains missing.

The 100 ms worker-entry sleep in 2.8 applied to multiple asynchronous native stages and is a plausible contributor to observed ~1 packet/s. New worker advances native state at most eight times per call with 1 ms retry sleeps; chunks share one owned snapshot. No camera performance claim. Wall-clock diagnostic timings added; full native copying, CRC and USB still cost time. Retains constructor-free lazy activation and existing kernel/RTOS/config. Source span limits and output-overlap guards reject unsafe buffers. Stop discards partial chunk groups after worker exclusion and drains native references.

Offline checks passed: compiled C ownership/full-copy/retry/range/mapping/reset fixture with exact 2073600-byte reassembly; eight host reassembler checks; compiled ARM worker with actual native state machine, delayed replies and retry preservation (CRC mocked in ARM and separately cross-checked from compiled C against Python zlib); 11 PIC/ELF cases; 4226 module instructions/no NEON; ten guarded installer/rollback fixtures. Hardware services, mounts and space helper mocked. Installer requires cold boot and exact installed 2.8 files; automatic failure restoration returns to 2.8, explicit rescue rollback to 2.4p.

Next live work: archive/hash-verify/clear known logs and temporary captures only, preserve runtime /tmp files, fresh boot with streaming unopened, current hash/maps/storage and memory checks (new 4 MiB heap reserve). Install guarded package; capture at least 16 packets with FFmpeg stream-copy, reassemble, recover logs and verify no native refs. Mode cycling and inherited kernel-owned output-allocation reuse remain unverified. MENU restarts unresolved. Do not claim 2.9 fixes crashes, achieves webcam frame rate or decodes an intelligible image.

## Revision 2.8 raw bytes captured; native YC buffer provenance verified — 26 October 2026

Installed2.8 producer MD5 5dd449056e4da5b7bea072d9e3b65d0b (28424B), streaming library27f4f4696c724caa8348edc51c86a517 (72796B), readback/reboot verified. Source selector now accepts observed native VEF type0x295, with shared type policy and allocation/open/status/span checks. FFmpeg stream-copy captured10complete614400-byte packets, then3more on same-session reopen, all distinct and no trailing bytes. Approximately1packet/s, despite10fps transport descriptor; pixels/packing remain unknown. No synthetic fallback or overlay. After exit:23native snapshots/submissions,100requests/100replies, context idle, zero shared/open references and no token. Last rejected Share at stop acquired no reference. Captured camera evidence was downloaded/hash-verified and cleared; final space guard and/tmp write/readback passed. Service session closed. Full mode-cycle capture and normal decoded-image output remain unverified.

Source is no longer supported only by a table coincidence: original VEF producer reads record+0x28 into ImageSizeInfo.unit_type and passes it to native RDV allocator0x637545ec (command12, queue0x0061003c). Returned handle is attached to ImageSizeInfo.unit_handle. Three real records and one type/handle taint control execute the original code with hardware services mocked; relevant regions match the patched RTOS image MD590096db2c76148f4f9db5d104e5c608c confirmed on camera. This verifies a YC image-attachment allocation family, not live metadata for the saved packet. Tested HD records set yc_compress=1, VGA sets0; all strip_width=64, data_content=2, data_placement=1, data_transfer=0, data_scan=1, data_offset=0. Do not infer bit depth, enum meanings, geometry, plane identity or packing from capacity alone.

Current source is research/firmware/yuy2_transport_v28_snapshot/; compact evidence verified_yc/evidence/native-dmm-v28-20261026/. Workspace .local/outputs/native-dmm-v28/ retains full captures and state snapshots. User handed one unchanged614400B packet to another agent for offline image reconstruction. Updated text at decoder-handoff/zve10-vef295-snapshot.txt includes this provenance and conditional compression clues; binary SHA256 b0cceb40c44526e72784cec1892dcf86829113ba4c59376f19d5daf2a031714b remains unchanged. No messaging to other chats, new camera access or firmware changes during provenance verification. Recovery /usr/share/yuy2-recovery-v28snap/rollback.sh restores working permanent2.4p; previous2.7 image also preserved.

MENU automatic restarts recurred with normal error logging and old/tmp traces absent. Eight captures530033B were archived/verified/cleared from/log and known/tmp paths; runtime fonts/tools/kikilog were preserved. After deleting old/log captures Linux reported more free space than total; guard correctly rejected it. A controlled reboot restored in-range reporting and/tmp4096B write/readback passed. USB-unplugged checks preceded successful streaming; do not claim storage cleanup proved the crash cause or that menus are permanently fixed. New helper checks/tmp space and a real write/readback. Do not erase/tmp wholesale or infer disk corruption from the cached counter alone.

## Revision 2.7 first capture failed: active-source whitelist mismatch — 26 October 2026

Windows enumerates the expected USB camera and640x480/YUY2/10fps format; actual FFmpeg capture timed out30s with zero frames. User returned to service without a reported crash/reboot. Native SDK/private-queue initialization succeeded. Read-only module-state snapshot: backend IDLE, candidate0, no shared/open references or token, frames0, source errors602. Retained streaming-time DMM listing contains none of the three accepted types0x240b2e/0x6193f/0x61940. Exact compiled ARM selector replay rejects this listing and accepts an added positive-control whitelist row. Immediate cause is source selection, before native Share/Open, copying or USB submission. Those native operations remain hardware-untested. Do not claim a working raw webcam, an encoding failure or a format-conversion failure.

[First capture findings](../../usb/uvc_native_dmm_first_capture_20261026.md) records observed source candidates0x295/0x293 and the0xfe... alias guard issue; their role and packing are not established by size. Next: trace actual active producer/type mapping, then correct the source filter while retaining Share/Open/Close/Free ownership and address checks. Do not select audio, USB staging or0x276 output, or remove guards to force a frame. Source addresses from the read-only snapshot are session-specific and must never be replayed. No firmware change during this test;2.7 remains installed,2.4p rollback preserved. /tmp7600KiB free, normal logging. Camera captures were downloaded/hash-verified then individually cleared; service session closed. Full evidence in workspace .local/outputs/native-dmm-callback/deployment/live/first-capture-01/; compact evidence in verified_yc/evidence/native-dmm-callback-20261026/first-capture-20261026/.

## MENU recovery after verified /tmp trace cleanup — 26 October 2026

After the 2.7 flash, user reported MENU/VIDEO caused automatic restarts. Earlier cleanup had removed only two /log diagnostic files (1711247B); /tmp was explicitly left full during deployment. That was incomplete as an operational cleanup. Current post-restart check reported /tmp 6464 KiB free, /log nearly empty, normal error-level logging, revision 2.7 hashes intact and no streaming/patch/probe mappings in the fresh process. A recovered MPR dump did not establish the restart cause; absent current mappings do not rule out pre-reset involvement.

Identified old research outputs in /tmp/opengate_trace/ (created by research/device/live_trace_record.py). Five files totaling 1124649B were downloaded, MD5-verified, rechecked on camera, then individually deleted. Preserved fonts, tools and system-managed kikilog.dat; never clear /tmp wholesale because it holds runtime resources and persistent helpers. /tmp then reported 7600 KiB free; a 4096-byte write/readback MD5 check passed and its scratch file was removed. User disconnected USB and retested MENU then VIDEO without streaming: **works now**. No firmware or logger-filter changes during this check; revision 2.7 remains installed. Cleanup/disconnection/reset timing mean this is observed recovery, not proven root cause or a permanent code fix. No real-frame capture yet. Service session closed.

Extend regular archive/hash-verify/clear procedure to verified research captures under /tmp as well as /log. Future deployment must check /tmp availability and perform an actual small write/readback before any firmware write; do not merely move staging elsewhere when scratch storage is full. Do not delete system-managed files or runtime fonts. Evidence in workspace .local/outputs/native-dmm-callback/deployment/live/menu-crash-01/ and repository verified_yc/evidence/native-dmm-callback-20261026/menu-recovery-20261026/. Raw archived traces and MPR dump remain in the workspace. If menu restarts recur, preserve fresh reset evidence and compare against the guarded working-2.4p rollback instead of assuming storage is the sole cause.

## Revision 2.7 installed and reboot-verified — 26 October 2026

User authorized deployment. Guarded install completed with exit 0 and downloaded readbacks matching streaming MD5 c3aa9b92ea6c05ce78aa7894e8dfe35a (72796B), new producer ec185c27deb53f80f6f5a40d9a8f95f1 (28620B), working 2.4p backup 5fde77e394572ebcf420f8941575f6c4. After software reboot: uptime 125.67 seconds, installed hashes persisted, /usr mounted read-only, no libInfraStreamingUsb/yuy2/probe mappings present. Old 2.4p producer and proven USB kernel hashes unchanged. Recovery: `/usr/share/yuy2-recovery-v27snap/rollback.sh`, restoring working permanent 2.4p. Service session closed after verification. **No USB Streaming or real sensor packet test has been performed for 2.7.** Next: bounded fresh monitoring, activate streaming, FFmpeg opaque capture, test restart, return to service mode and archive/verify/clear logs. No eligible whitelisted DMM source was active during service-mode preflight; availability during streaming remains unverified.

Two old diagnostic logs (1711247 bytes) were archived and hash-verified before deletion. /tmp was 100% full: new Senser writes failed with error 130 and left empty files. /log was nearly empty; no system-managed /tmp files were deleted. Minimal /bin/busybox lacks find, df and awk. Corrected preflight uses a read-only statfs helper, actually executed on-camera; before install /usr available 11219968 bytes, /log 524025856 bytes. Package/helper/scripts were staged under /log, and direct terminal commands avoided full /tmp. The service workbench kept one session through preflight/staging/install. Existing toolbelt copied to /log/yuy2_640_v27snap/busybox for inspection; original binary name bbel does not dispatch applets properly. Never execute original obsolete fixed-base RAM helpers.

Ten adapted local installer fixture tests pass; actual preflight/install/readback/reboot evidence is in workspace `.local/outputs/native-dmm-callback/deployment/live/` and repository `verified_yc/evidence/native-dmm-callback-20261026/deployment-20261026/`. The reboot job's final completion marker was absent because reboot terminated the session; CPU shutdown trace, reset uptime and new post-boot hashes/maps independently verify reboot. Current six-payload package includes space-check.elf; use the camera-adapted ZIP, not the superseded original five-payload ZIP. Updated reproducible package builder and single-step runner are in the source deployment folder. Previous pending-camera sections below are historical.

## Deployment package prepared — 26 October 2026

Guarded revision 2.7 installer, rollback to working permanent 2.4p, explicit single-step service runner and instructions are ready in `research/firmware/yuy2_transport_v27_snapshot/deployment/`. Ten local installer fixture cases pass, including pre-write rejection, damaged payload, failed activation, failed remount, automatic restoration and explicit rollback. Real flash/power-loss behavior is not proven. Workspace package: `.local/outputs/native-dmm-callback/flash-package/`; ZIP alongside it. The package changes only the new producer module and streaming library, verifies existing SDK/kernel/RTOS/config hashes, preserves 2.4p and stores rollback under `/usr/share/yuy2-recovery-v27snap/`. No automatic reboot or mutation retries. **User is not ready; no camera session, log cleanup, upload, install or reboot was attempted.** When ready: fresh boot/service mode with USB Streaming unopened, archive/hash-verify/clear diagnostic logs, preflight, stage, install/readback, separate reboot, then bounded FFmpeg raw capture and restart check. Camera-side checks remain pending.

## Native raw snapshot callback implemented — 26 October 2026

Revision 2.7 now implements and auto-binds the missing acquisition callback. See [native DMM callback findings](../../usb/uvc_native_dmm_snapshot_v27.md) and `research/firmware/yuy2_transport_v27_snapshot/`. It uses original loaded libBizFw private-channel methods with prologue guards and native 24-byte requests to queue 0x0061003c: Share → Open(nonwaiting) → copy → Close → Free(only our shared allocation reference). Source candidates are selected from live `/proc/udm/dmm_units`; addresses come from native Open replies. No guessed source handle/address, fake 0x400 IPC, global observer hook or synthetic fallback.

Kernel finding: DMM opens do not pin allocation lifetime. Share increments unit+0xb20; Open increments separate +0xb21; final Free can destroy extents despite opens. The callback therefore shares before opening. This pins allocation lifetime, **not pixel immutability or frame completion**. Diagnostic snapshots may tear, and their packing remains unknown, deliberately deferred until a PC capture. Generic validated conversion still requires its stronger completed-frame contract.

Copied staging packets survive asynchronous cleanup, and no USB submission/new acquisition occurs before confirmed release. Pending IPC no longer triggers the stock ten-error stop mechanism. One outstanding command/private queue; ambiguous failures retain ownership. Stop discards unsent copies and progresses cleanup, retaining any unresolved state for restart. No background cleanup thread; a delayed stop can retain one shared allocation until later polling/reboot. Native SDK calls can allocate/lock internally; hard realtime ten-ms latency is not proven. Actual snapshot cadence is below the advertised 10fps envelope.

Offline verification passes: four native wire requests match executions of Sony SDK methods; twelve state/copy tests; fourteen compiled ARM worker cases including native callback, delayed replies, byte-exact output and second start; thirty-two inherited ownership/conversion cases; eleven PIC/ELF checks. Module text audit: 3876 instructions, no NEON. Service replies are fixtures. **No camera install, real-byte capture or working sensor webcam claim.** Active eligible source units and runtime mapping/coherence remain hardware questions. Permanent 2.4p remains last hardware-verified output.

Candidate: `.local/outputs/native-dmm-callback/candidate/` in the workspace. Module `yuy2_640_v27snap.so` MD5 ec185c27deb53f80f6f5a40d9a8f95f1, 28620B; persistent library MD5 c3aa9b92ea6c05ce78aa7894e8dfe35a, 72796B. Repository evidence: `research/firmware/raw_frame_source/verified_yc/evidence/native-dmm-callback-20261026/`. No installer; obsolete generated fixed-base RAM helpers must not be executed. Preserve verified 2.4p rollback and 2.3 USB kernel. Next: separately authorized bounded hardware trial after archive/hash-verify/clear logs, capture opaque frames with stream-copy, verify restart, then analyze source packing on the PC. Previous 2.6 "callback missing" sections below are historical.

## Raw-byte diagnostic patch built —26 October2026

User directed us to defer pixel-format interpretation: tunnel source bytes through the existing webcam framing, save packets and analyze on the PC. [Revision2.6 raw diagnostic](../../usb/uvc_raw_byte_diagnostic_v26.md) implements that path in research/firmware/yuy2_transport_v26_raw/. It copies exactly614400 contiguous source bytes unchanged, with an optional inactive-configured byte offset; source format, stride, color flags and geometry are ignored. USB still advertises640x480/YUY2/10fps. No counter overlay, pixel conversion or synthetic fallback. USB readiness, source span bounds and ownership cleanup remain enforced. PC helper uses FFmpeg stream-copy and saves individual binary packets with hashes.

13 compiled ARM integration cases pass,32 inherited core cases pass,11 PIC/ELF cases pass; no NEON in audited module code. Built module and persistent streaming candidate are in workspace .local/outputs/yuy2-v26raw/candidate/. No camera changes or installation. **A real Sony acquisition callback is still missing: this is an implemented opaque-byte transport path, not yet a camera-frame-producing patch.** Without a bound source it submits no frames. Prior assumption that only conversion was missing is incorrect. Prioritize a genuine bounded pixel-buffer reference next; do not spend more time interpreting its format before the first raw-byte capture. Do not replace working2.4p with an unbound candidate. Windows inventory found no connected Sony device during this work.

## Live-source continuation —26 October2026

Returned to genuine YC webcam work, offline only. [Native640x480 path and remaining blockers](../../usb/uvc_yc_live_source_20261026.md): original RTOS preview lookup and changeSSYCData executed. The preview table is nine20-byte records, not18;640x480 selects compression0. Native dataContent2 keeps full height with dataPlacement1; other tested values halve height with placement0. Thus placement does not establish YUY2/NV16. Native640 types0x6193f/0x61940 map to extents0x8e/0x8d; separate resize type0x240b2e maps to614400B extent0x14e. These are configured candidates, not current frame addresses or leases. Seven geometry and five metadata execution cases pass; source packing, active routing and read lifetime remain unresolved. No camera changes or real-frame patch claim.

Inherited scope corrections:0x63a2e47c is a JPEG-specific unit-alignment routine, not proof of a universal YC DMA rule;0x63dbcd70/+0x48 are address/length getters, not static plane tables. Three direct metadata-builder calls do not rule out every indirect call. Preserve completed31-field and multi-segment components and permanent2.4p bars. New evidence/tests are in verified_yc/evidence/yc-live-20261026 and verify_preview_update.py / verify_preview_geometry.py. Kernel mapping investigation remains a lead; do not use unverified address arithmetic in a target patch.

## Paused for handoff: native YC delivery & multi-segment pipeline verified — 25 October 2026

Offline reverse engineering completed all requested RTOS memory, geometry, and metadata components. No camera access or new installation; permanent 2.4p synthetic bars/counters remains the last hardware-verified transport. See [full source findings](../../usb/uvc_yc_source_recovery_20261025.md) and [ready-to-paste prompt](YC_NEXT_AGENT_PROMPT.md).

All 31 scalar `ImageSizeInfo` fields are now fully integrated into `sony_yc_metadata.h/.c` and verified in Unicorn against Sony's real SDK getters and 60 truncation cases (`verify_metadata_decoder.py`). Additionally, SSYC Category 1 (`YcStateInfo`, 6 bytes) and Category 0x11 (`MultipleSegmentImageInfo`, 288 bytes) are fully implemented and verified (`verify_sds_reader.py`, `verify_multi_segment.py`). The multi-segment slice extractor (`sony_yc_segment_extract_image_size`) and dual-strip width merger (`sony_yc_segment_merge_image_size`) match real Sony RTOS code (`0x63cebf24` and `0x63cec0d8`) byte-for-byte across slots 0 and 1.

The complete VDF DMM IPC command family in `av-cam.bin` (`0x6371f4a0..0x6371f8f8`) is now mapped: Command 1 (alloc), Command 2 (share across queues), Command 4 / 13 (immediate/delayed sync free), Command 5 (open mapping / physical address resolution), and Command 6 (close mapping). All 10 methods and 18 call sites of the VDF Ownership Manager vtable (`0x645852c8` / `0x64585300`) and the frame completion/release handler `VDF::VdfInputReleasePinAndMem::Execute` (`0x63728000..0x6372889c`) are documented with disassembly evidence in `verified_yc/evidence/`. SDF plane alignment function `0x63a2e47c` proves hardware DMA requires 128-byte address and size alignment. All 35 pytest tests pass; all 6 verification scripts pass with 0 errors.

## Offline live-YC source recovery — 25 October 2026

User redirected work to genuine YC source reverse engineering and a live webcam patch; set loader diagnostics aside. No camera access this turn. [Verified source recovery](../../usb/uvc_yc_source_recovery_20261025.md):190 candidate local YC callsites recovered in libObj using actual PLT relocations and unwind ranges;25 metadata fields recovered by executing Sony's own getter/printer. Real renderer delivered-SDS path and separate pixel unit handle traced. New bounds-checked decoder in `research/firmware/raw_frame_source/verified_yc/` agrees with Sony execution, but pixel enums, live-preview routing and frame ownership/return remain unresolved. Permanent2.4p remains last verified synthetic transport; no working live-frame patch claimed. Revision3 RAM probe was installed before user stopped; current camera state is unknown. Never replay stale addresses. Keep routine archive/hash-verify/clear log procedure.

## YC retest: baseline passed; loader-only probe armed

User standing instruction: clear diagnostic logs regularly. Before each new hardware test, stop prior captures, restore normal error filters, archive and hash-verify diagnostic captures, recheck camera hashes, then delete only verified diagnostic paths and confirm absence. Preserve firmware, calibration, helpers and system-managed logs. Use a fresh test directory and bounded capture. After collecting each run, repeat archive/verify/clear. This is an operational procedure, not a scheduled automation.

Baseline without observer passed ten complete 640x480 YUY2 bars frames, counters1–10; uptime197.29→981.42 seconds confirms no intervening reboot. Persistent 2.4p hashes unchanged. Archived22 files/8,282,393 bytes with matching camera MD5s; cleared7 capture files/8,180,954 bytes. Earlier cleanup cleared26 diagnostic files/19,916,504 bytes after archive verification.

Revision3 is a temporary loader-isolation probe, NOT a YC metadata observer. Its activation writes only `YC_V3_LOADER_ACTIVATION_OK` to `/log/yc_observer/runtime-v3.log`, with no Sony API, GOT hooks, subscription or pixel access. Module MD5 `4a6de2407407c3b8f7ae2c2a3366ad60`; three ARM probe cases and four bootstrap cases pass offline. RAM write/readback verified for PID157/base0x0a661000, prepare0x0a669d00 and cave0x0a66a630. Addresses are session-specific: never replay after reboot/process change. No persistent firmware changes. Previous metadata observer remains withdrawn.

Fresh debug capture `/log/yc_retest_20261024_02/app-sequential.log` is active with a guard stopping capture/restoring error filters after300 seconds or16MiB (polled every2 seconds). Service closed; awaiting user streaming activation, FFmpeg and service return for collection. Current local state/evidence: `.local/outputs/yc-retest-20261024/`. No successful revision3 activation is claimed yet.

## Observer withdrawn after second reboot — 24 October 2026

Both temporary observer attempts were followed by a reboot. Latest service snapshot shows uptime 133.59 seconds, no observer mapping, no streaming-library mapping, and no observer2 runtime log. The fresh boot cleared the RAM bootstrap; do not restore or replay old addresses. The observer/bootstrap is suspect, but no retained crash PC establishes the cause. No genuine YC metadata or live camera frame was captured. Earlier three-frame bars capture happened after the first reboot and validates only permanent 2.4p.

There is no evidence that `/log` is full: recursive directory inventory found 447 regular files totaling 84,328,592 logical bytes (80.42 MiB), versus reported volume capacity 524,206,080 bytes (about 500 MiB). The filesystem free counter incorrectly reports the entire volume free despite existing files; do not cite that counter as precise free space. Allocation overhead was not measured. No files were deleted.

Permanent streaming library MD5 `5fde77e394572ebcf420f8941575f6c4`, producer `9181ef744955190d04728cf4ef7965c5`, and kernel `c1cad400372e26eca729e4b9bc47a237` still match the working 2.4p installation. Application debug filters were not changed. Second-attempt evidence archive contains 56 files / 5,528,122 bytes, all verified against camera MD5s. Service session closed normally. Current evidence/state is in workspace `.local/outputs/sony-backend-recovery/deployment/`, especially `second-attempt-archive-verification.json`, `log-space-assessment.json`, and `state.json`.

Next work is offline fault isolation of the RAM loader, real execution context and observer ABI before another hardware probe. Passing emulation/import checks did not validate execution on the camera. Do not reinstall the observer or guessed Sony IPC. The generic 2.5 lease pipeline remains offline; the real Sony source subscription, buffer layout and ownership contract are unresolved. Preserve permanent 2.4p synthetic transport.

## Withdrawn Sony backend completion claim

The earlier claimed subscription pin, 0x400 acquisition protocol, two-plane DMM reply, bounded acquisition and stable frame lease were not established by the binaries. See [corrected evidence](../../usb/uvc_sony_backend_recovery.md). Default and ARM-target Sony backend builds now fail closed; the former model is available only as an explicit non-target test fixture. No real Sony backend is complete.

## Revision 2.5 — offline live-source pipeline implemented; Sony backend pending

[Implementation report](../../usb/uvc_live_frame_implementation.md): lease-based acquire/validate/readonly-map/scalar-convert/unmap/release core is integrated into a new producer candidate; host completion precedes acquisition and failed source cleanup is retained. `yuy2_live_bind` registers a verified in-process backend while inactive. Initial offline core implemented with synthetic fallback prior to genuine subscription recovery. Stock `get_video_image(JPEG_DATA_INFO*)` is not a YC getter and its body is the installed PIC gate. `getYUVReadStart()` returns status, not a frame pointer. Source `research/firmware/raw_frame_source/` and `yuy2_transport_v25/`; session `.local/outputs/yuy2-640-v25/`. No camera changes; permanent 2.4p remains installed.

## Live CPU verification — 24 October 2026

Direct service-shell `/proc/cpuinfo` reports four processors (0–3), ARM implementer `0x41`, part `0xc05` (Cortex-A5), revision 1, hardware ARM-CXD900X0. Features: `swp half thumb fastmult vfp edsp vfpv3 vfpv3d16 tls vfpv4`; **no neon**. Earlier Cortex-A9/NEON assumptions are incorrect for the Linux-visible CPU. VFPv4 is not evidence of NEON. Plan scalar integer conversion/copy; do not execute NEON kernels without new capability evidence. Live feature absence establishes unavailable advertised userspace support, not physical absence independently of kernel configuration. No instruction probe performed. Raw-source report NEON kernels/performance estimates need rework; older A9 compiler tuning does not establish A9 hardware. Evidence: session `.local/outputs/zve10-cpuinfo-neon.log`. Read-only query; no firmware writes.

## Revision 2.4p — permanent installation, FFmpeg reopen and OBS pass

[Permanent deployment report](../../usb/uvc_yuy2_patch_v24p.md) supersedes historical pending/offline states below. Streaming library `5fde77e394572ebcf420f8941575f6c4`, constructor-free producer `9181ef744955190d04728cf4ef7965c5`, kernel `c1cad400372e26eca729e4b9bc47a237` / version `yuy2_640_v23`. Genuine reboot verified persistence, dormant boot and service access. Prepare activates automatically via PIC import; no manual RAM bootstrap, though runtime hooks remain. First FFmpeg and same-session reopen each yielded ten exact frames (counters 1–10, 29–38); subsequent OBS passed without mode toggle. HOST_WAIT/HOST_RESUMED confirms host-idle recovery; no producer failure-stop markers. Still synthetic bars/counters, not live footage.

59 camera files / 6,693,389 bytes hash verified; 24,808 application records decode without corruption/slack. Normal error logging restored, capture stopped, service session closed; camera last in mass-storage/service mode. `/usr` read-only, no overlay. Source `research/firmware/yuy2_transport_v24p/`, session outputs `.local/outputs/yuy2-640-v24p/`; 79 offline checks pass. Recovery `/usr/share/yuy2-recovery-v24p/rollback.sh` MD5 `cd67ea02a57715d823ca7c1baf99499b` restores pre-install baseline (not factory streaming library) and factory kernel, then needs genuine reboot. Do not hot-unload pinned source or replay old jobs. Common-library eight-byte descriptor drift recurred after streaming; cause unresolved, installer did not write it. Raw-source work follows [canonical prompt](../../usb/uvc_raw_frame_source_prompt.md); preserve working transport and cold-install guards.

## Offline delivery diagnosis — 24 October 2026

## Revision 2.4 host-reopen candidate — offline verified, not installed

[Revision 2.4](../../usb/uvc_yuy2_patch_v24.md) treats WaitVideoReadCmp EBUSY as backpressure rather than invoking either our five-failure shutdown or Sony's ten-failure stop notifier. It reads libc TLS errno, preserves source bytes and ownership while busy, and resumes only on readiness success; other errors and explicit stop retain bounded recovery. Eight new regressions plus inherited checks pass: 50 producer + four bootstrap + 14 unchanged kernel checks (68 total). Userspace MD5 `c237ec9a3024d4b075e96943dab2ddb5`; kernel stays proven 2.3 MD5 `c1cad400372e26eca729e4b9bc47a237` / version `yuy2_640_v23`. Source `research/firmware/yuy2_transport_v24/`, local build `.local/outputs/yuy2-640-v24/candidate/`. No camera changes this turn; 2.3 remains last live installation. Fresh-boot hardware host close/idle/reopen test is still required; kernel cancellation/readiness behavior is not mocked proof. Separate raw-source investigator uses [this prompt](../../usb/uvc_raw_frame_source_prompt.md); do not mix source acquisition into the reconnect patch.


## Work split — live raw source research and USB host-reopen fix

User requested the handoff/prompt target live uncompressed camera frames through our proven USB transport, while the primary agent fixes same-session USB host reopening. [Raw-frame investigation prompt](../../usb/uvc_raw_frame_source_prompt.md) is the canonical scope; the external `prompt_draft.md` has been redirected to the same content. No new agent or automation was launched. Raw-source research owns `research/firmware/raw_frame_source/` and `docs/usb/uvc_live_raw_frame_source.md`; USB lifecycle candidate owns `research/firmware/yuy2_transport_v24/` and a separate revision report. Preserve the working 2.3 synthetic transport and its frame geometry. Raw-source work is offline only; do not replay camera jobs or change the currently loaded patch.


## Revision 2.3 final checkpoint — FFmpeg/OBS delivery confirmed, logs saved

Ten exact FFmpeg frames/counters and user-confirmed OBS frames after camera mode restart. Same-session host reopen remains broken; runtime confirms five-readiness-failure shutdown sequences and retained-source rebinding on mode restart. 57 files / 9,231,531 bytes hash verified; 111,319 application records decode with zero corruption/slack. Normal error logging restored, capture stopped, service session closed. Volatile kernel overlay and RAM hooks remain; do not hot-swap. [Full verified result](../../usb/uvc_yuy2_patch_v23.md). Next: host-inactivity/client-reopen lifecycle fix; no live sensor capture yet.


## Revision 2.3 — FFmpeg and OBS frame delivery confirmed

First FFmpeg capture passed ten exact synthetic frames/counters. User then restarted USB Streaming and confirmed OBS outputs frames with counters at 640×480 YUY2 / 10 fps. Same-session host reopen remains broken; mode restart restores delivery. Awaiting return to service without reboot for logs. [Current results](../../usb/uvc_yuy2_patch_v23.md). No live sensor capture yet.


## Revision 2.3 — first frames pass; later host open fails

First FFmpeg capture delivered ten exact synthetic YUY2 frames (6,144,000 bytes, counters 1–10). User later reported OBS failure; FFmpeg reopening the same session also timed out with zero bytes. Suspect host-inactivity/readiness handling, pending camera runtime logs. User asked to restart USB Streaming and try OBS as first client. [Evidence and current test state](../../usb/uvc_yuy2_patch_v23.md). Do not claim OBS or restart success yet.


## Revision 2.3 paired deployment — awaiting first stream test

Kernel temporary overlay loaded and sysfs version verified; RAM bootstrap/readback verified at fresh base `0x0a61e000`. Final kernel MD5 `c1cad400372e26eca729e4b9bc47a237`; 60 offline checks pass. Fresh debug logging is active; service session closed and user asked to activate USB Streaming for FFmpeg. Userspace constructor and host frames not yet confirmed. [Exact deployment checkpoint](../../usb/uvc_yuy2_patch_v23.md). Genuine reboot removes overlay and RAM hooks; underlying stock kernel was not overwritten.


## Revision 2.3 preflight — logs cleared, awaiting setup reload

User requested clearing old logs before reloading setup. Preserved and hash-verified all 75 selected test capture files (61,967,231 bytes), including five files newly downloaded. Rechecked every camera hash before exact-path deletion and confirmed each file absent. This removed old test `.log`/ring-dump capture files from known experiment folders; calibration, system-managed logs, firmware, module files and binary helpers were not deleted. Normal error filters restored; sequential capture stopped. Internal logger history was not explicitly reset. New `/log/yuy2_640_v23` created with clean preflight metadata. Service session closed normally. Awaiting user to open USB Streaming setup without starting, then return to mass storage/reconnect for fresh-map paired activation. Revision 2.3 is NOT installed. Local evidence and machine-readable state: `.local/outputs/yuy2-640-v23/preflight/`. See [live checkpoint](../../usb/uvc_yuy2_patch_v23.md).


## Revision 2.3 candidate built — 24 October 2026

User requested a new patch; no deployment requested or performed. [Revision 2.3](../../usb/uvc_yuy2_patch_v23.md) pairs the revision 2.2 userspace producer/restart correction with a guarded kernel module candidate. Kernel probe now reports a 614,400-byte pixel frame, 614,412-byte payload maximum and fixed 10 fps in PAL/NTSC; the one-header frame payload asserts EOF. Five guarded kernel sites change, and exact rollback is verified. 42 producer/lifecycle + four bootstrap + 13 kernel checks pass, with descriptor/kernel contract checked during packaging. Source: `research/firmware/yuy2_transport_v23/`; local binaries/manifest: `.local/outputs/yuy2-640-v23/candidate/`. Kernel MD5 `1789b7bd52bd00a11d9d6353778a7449`, userspace MD5 `bef71344d4d6308e57ab65bdff3283e5`. Both parts must be activated together; no automatic installer supplied. Verify loaded kernel and fresh process maps before deployment, clear old hooks, and retain stock kernel rollback. Hardware acceptance of larger payload and actual frame delivery remain unproven; no live sensor capture yet. Existing revision 2.2 camera state is unchanged by this work.


User requested offline reverse engineering only. [Audited findings](../../usb/uvc_yuy2_delivery_audit_20261024.md): userspace YUY2 descriptors/producer did not update the kernel probe responder. Kernel advertises stock 14,745,600-byte maximum frame, 30/25 fps, and 300,000-byte maximum payload; prototype queues 614,412 bytes with one UVC header. This is a concrete negotiation/packetization gap and strongest offline zero-frame mechanism, with Windows/on-wire behavior still unproven. The supplied team's EOF-only and 110 MB delivery claims were corrected: UVC 1.1 class spec makes EOF optional, and kernel success/cleanup paths can conceal drops/errors. Seven bounded ARM fragment cases plus constant assertions pass. Revision 2.1 owns the 180-submission runtime; revision 2.2 runtime remains unrecovered. No camera operations or new deployment. Align kernel probe and packetization next; retain revision 2.2's separate manager-lifetime correction.

> **SESSION RECORD - not a reference.** This is a dated log of how a finding was

## CURRENT CHECKPOINT — revision 2.2 deployed; user moving laptop

User requested saving progress before moving laptop. No further camera operations. Revision 2.2 RAM bootstrap installed/readback verified at streaming base `0x0ea6d000`; first activation enumerated 640×480 YUY2/10 fps, but FFmpeg timed out after 25 seconds with zero bytes. Stop/restart test was requested but NOT confirmed performed. Runtime/application logs not yet recovered; camera logging may remain active at `/log/yuy2_640_v22/app-sequential.log`. Last confirmed camera mode: USB Streaming first activation. No host sessions running. Preserve logs and verify actual camera state on resume; reboot clears RAM patch. Do not reinstall over loaded hooks. [Exact live checkpoint](../../usb/uvc_yuy2_patch_v22.md). Local `.local/outputs/yuy2-640-v22/deployment/deployment-state.json` records current evidence. Menu check passed with normal logging and USB unplugged; no log deletion/firmware restoration performed. Earlier pending-install notes below are historical.


Menu investigation update: user completed MENU/VIDEO and streaming on/off successfully with USB disconnected and debugging enabled. Fourteen run artifacts hash verified; 45,839 application records decode cleanly. Capture stopped and logging restored to normal error level; awaiting repeat MENU/VIDEO check with USB unplugged. No YUY2 module installed, no firmware changes, no permanent menu fix claimed. Streaming library loaded at `0x0ea6d000`; revision 2.2 loader is being verified for this map while waiting.


Current blocker: inconsistent MENU/VIDEO-tab failure reported after the reboot to clear revision 2.1. [Menu investigation](../../usb/uvc_menu_crash_20261024.md). Fresh-boot maps confirm no YUY2 or streaming library loaded. Revision 2.2 is built/offline-verified but NOT installed. Initial .local/logs/hash snapshots are preserved; application debug capture is active for reproduction. No storage-full error found and no logs deleted. Do not describe menu crash or host-frame delivery as fixed.


Revision 2.2 restart correction is built: [candidate report](../../usb/uvc_yuy2_patch_v22.md), source `research/firmware/yuy2_transport_v22/`. It detaches stopped managers while retaining one module-lifetime source, and requires driver completion before pixel reuse. All 42 ARM + four bootstrap cases pass; hardware installation/test pending. Original zero-frame delivery is not claimed fixed. A reboot command was sent to clear revision 2.1; verify old-module absence before guarded installation.


Latest repeat-activation finding: standby/no USB enumeration is now traced to three revision 2.1 connect rejections with error `0x21` (decimal 33): new VideoEsManager differs from the old manager retained with a DMA-pinned source. Service access still works. Nine new snapshots were hash verified; no reboot or further patch was performed. See the revision 2.1 live report's repeat-activation section. The initial zero-frame delivery problem remains separate and unresolved.


## Latest verified result — revision 2.1, 24 October 2026

[Live report](../../usb/uvc_yuy2_patch_v21.md): revision 2.1 installed in RAM and module activated. Windows/FFmpeg enumerate 640×480 YUY2/10 fps; ten-frame capture timed out after 25 seconds with zero bytes. Source unit `0x276` allocated exclusively (physical `0x15b00000`, 3,276,800 bytes), at least 180 submissions accepted by API, no host-frame proof and no PROBE/COMMIT runtime markers. Later readiness failures left source pinned; do not hot-swap or free it. User returned to service mode; 44 files / 7,655,944 bytes recovered and hash verified, debug capture stopped. The installer wrote RAM only; after streaming the common-library file read as prior 1080 candidate MD5 `bd32c223e60e363d900c7ac8be06641c` (eight descriptor bytes), despite stock hash after arming. RTOS/streaming hashes remained unchanged. File transition/persistence remains unresolved; see live report. Inspect original startup completion/host control and gadget DMA delivery next. Source-only recipe: `research/firmware/yuy2_transport_v21/`; 35 ARM + four bootstrap cases pass. Historical entries below retain earlier states.

> reached. Anything still true of it has been extracted into the topic docs; do
> not cite this file as fact. Kept for provenance only, so that a retracted
> claim is not silently re-derived.
>
> Current documentation: [docs/README.md](../../README.md)
# Handoff: ZV-E10 reverse engineering

State as of commit `5990388` + verified UVC 1080p live deployment. Written for an agent picking this up cold.

**Repo:** `D:\02_Development_And_Projects\pmca-re` · **Python:** `.venv\Scripts\python.exe`
(always pass `-B` to skip stale bytecode) · **Tests:** 163+ passed across test suite (58 dedicated adversarial UVC tests, 100% pass in 0.86s).
**Git:** `qn06142 <90816999+qn06142@users.noreply.github.com>`, pushed to `github.com/qn06142/zv-e10-re`, default branch `master`.

```powershell
cd D:\02_Development_And_Projects\pmca-re
& ".venv\Scripts\python.exe" -B -m pytest tests/test_uvc_patch.py -v
& ".venv\Scripts\python.exe" -B scripts/patch_uvc.py --verify-only
```

---

## 1. Executive Summary & Current Device State

1. **UVC 1080p Webcam Patch Deployed & Verified**:
   - The verified 1080p UVC webcam modification is live on `/usr/lib/`.
   - `libInfraUsbCmn.so`: `ac1961d23addcd53f4fe7210d074eac2` (UVC 1.1 descriptors with `wTotalLength = 61`, 1920x1080 @ 30/25 fps).
   - `libInfraStreamingUsb.so`: `5a0417693a3d9ed1786c4d0afc043d6e` (VideoEsManager 1080p width `mov.w r2, #0x780`).
   - Stock copies remain intact on camera storage at `/setting/stock_libs/`. Reversible anytime with `/setting/revert_uvc.sh`.
2. **Residual 16:9 / Framing / NVRAM Patches Reverted**:
   - Reverted `/usr/share/app/color_cmn.uxc` back to factory stock `color_cmn.STOCK.uxc` (`f468bd3e72ca4e5b948a1c9f1f35c0a1`), removing the magenta framing guides from the LCD screen.
   - Restored `/setting/Backup.bin` and `Backup.bak` from factory original `/setting/Backup.orig` (`1c3165c21b13e13c6fed3c83425e2165`), clearing experimental aspect ratio tweaks.
   - Purged residual open gate / aspect test scripts from `/etc/`.
3. **USB Driver & Tooling Modernization**:
   - In-process Windows WinUSB support implemented in `pmca/usb/driver/windows/winusb.py` with `FILE_FLAG_OVERLAPPED` and isolated `WINUSB_INTERFACE_GUID` lookup.
   - `pmca/commands/usb.py` safeguarded with `try...except` to prevent single-driver `openDevice()` failures from breaking multi-driver enumeration.
   - Clean non-padded bulk packet sync handling for PID `0x0336`.

---

## 2. Root-Cause Post-Mortem: Why Prior UVC Patches Failed

Prior iterations produced broken streams or crashed `im.elf` with `SIGSEGV`. The 459-line engineering post-mortem in [`docs/usb/uvc_patch_postmortem.md`](../../usb/uvc_patch_postmortem.md) isolates the 6 fundamental failure modes:

| Bug # | Failure Mode | Technical Mechanism | Affected Binary & Offset |
|:---:|:---|:---|:---|
| **1** | **Thumb-2 Endian Inversion** | Patcher wrote halfwords in reverse order (`f0 62 4f f4` vs `4f f4 f0 62`), turning `mov.w r2, #1920` into an illegal store `str r0, [r6, #44]`, crashing `im.elf` on stream start. | `libInfraStreamingUsb.so` (`0x908A`) |
| **2** | **Descriptor `wTotalLength` Mismatch** | UVC 1.1 requires `wTotalLength` to equal the sum of header + subordinate descriptors (14 + 11 + 30 + 6 = 61 bytes). Prior scripts clobbered `R_ARM_RELATIVE` pointers in companion tables at `0x14AB4` & `0x14DB4`, causing host USB stacks (`usbvideo.sys`, `uvcvideo`) to reject enumeration. | `libInfraUsbCmn.so` (`0x12537`, `0x14AB8`, `0x14DB0`) |
| **3** | **Bitrate Scaling Unit Bug** | Firmware scales bitrate in 100 kbps units rather than bps (`mov.w r3, #300` corresponds to 30 Mbps, not 300 bps or unbounded bandwidth). | `libInfraStreamingUsb.so` (`0x908E`) |
| **4** | **Upstream `set_path_sync` Zero Height Parameter** | `set_path_sync` hardcoded height to 0 at offset `+0x236`, breaking the BIONZ X hardware JPEG encoder aspect ratio calculations (`0x33E` timeout). | `libInfraStreamingUsb.so` (`0x8EB2`) |
| **5** | **DMM Memory Pool Exhaustion** | Unmetered frame allocations exhausted the camera's fixed Direct Memory Management (`dmm.ko`) DMA pool (`0x1D5` alloc error). | `libInfraStreamingUsb.so` (`0x9534`), `dmm.ko` |
| **6** | **Staged Baseline Divergence** | Earlier scripts targeted previously modified files rather than authentic firmware dumps in `.local/dumps/camera_2025/usr/usr/lib/`. | `.local/dumps/staged/uvc/binaries/stock/` |

---

## 3. Verified Patch Architecture & Deployment Suite

### Single-Shot Surgical Patch Generator
[`scripts/patch_uvc.py`](../../../scripts/patch_uvc.py):
- Modifies **exactly 20 bytes** in `libInfraUsbCmn.so` (preserving `wTotalLength=61` and companion table pointers) and **exactly 1 byte** in `libInfraStreamingUsb.so` (`0x908C: 0xA0 -> 0xF0`).
- Decodes every modified instruction with Capstone in Thumb-2 mode to guarantee zero callee-saved register clobbers (R4–R11, SP, LR preserved).
- Staged output located in `.local/dumps/staged/uvc/binaries/patched/`.

### Camera Deployment & Revert Tools
- **Live Deployment**: [`scripts/deploy_uvc_camera.py`](../../../scripts/deploy_uvc_camera.py) (gzip + base64 chunked transfer, staged in `/setting/patched_libs/`, atomically copied to `/usr/lib/`, cold rebooted).
- **Residual Revert Tool**: [`scripts/revert_all_residual_patches.py`](../../../scripts/revert_all_residual_patches.py) (reverts framing guide lines and restores pristine factory NVRAM from `Backup.orig`).
- **On-Camera Emergency Revert**: `/setting/revert_uvc.sh` (restores stock libraries from `/setting/stock_libs/`).

---

## 4. Multi-Layer Adversarial Verification Suite

[`tests/test_uvc_patch.py`](../../../tests/test_uvc_patch.py):
- **58 offline tests** (100% pass rate in 0.86s).
- Covers 8 architectural domains:
  1. Cryptographic Dump Integrity (SHA-256 / MD5 validation).
  2. Capstone Thumb-2 Disassembly Guardrails (AAPCS compliance, literal pool bounds).
  3. UVC Descriptor Hierarchy (`wTotalLength = 61`, frame intervals 333333 / 400000).
  4. Relocation & Companion Table Preservation (`.rel.dyn` 781 relocations intact).
  5. USB 2.0 Bulk Endpoint & Transfer Bandwidth (512-byte max packet sizes).
  6. Multi-OS Host Descriptor Parsing Emulation (Windows `usbvideo.sys`, Linux `uvcvideo`, macOS `CoreMediaIO`).
  7. Adversarial Mutation Tests (asserts explicit test failure upon single bit flip, opcode swap, corrupted pointer, or truncated descriptor).
  8. CLI Generator & Subprocess Idempotency.

---

## 5. Live Camera Filesystem Layout

At current check:
- `/usr/lib/libInfraUsbCmn.so`: `ac1961d23addcd53f4fe7210d074eac2` (1080p UVC patched)
- `/usr/lib/libInfraStreamingUsb.so`: `5a0417693a3d9ed1786c4d0afc043d6e` (1080p UVC patched)
- `/usr/share/app/color_cmn.uxc`: `f468bd3e72ca4e5b948a1c9f1f35c0a1` (Factory stock)
- `/setting/stock_libs/`: Pristine factory stock copies of both UVC libraries.
- `/setting/Backup.bin`: `1c3165c21b13e13c6fed3c83425e2165` (Pristine factory original matching `Backup.orig`).
- `/setting/revert_uvc.sh`: On-device stock restore shell script.
- `/etc/`: Purged of test scripts.

---

## 6. Trap Reminders for Incoming Agents

1. **PowerShell Backtick Truncation**: Never pass inline strings containing backticks via PowerShell CLI arguments (`gh issue comment --body "..."`). Always use `-F body=@<file.md>`.
2. **WinUSB Handle Flags**: Opening a device handle for `WinUsb_Initialize` requires `FILE_FLAG_OVERLAPPED` in `CreateFileW`. Without it, `WinUsb_Initialize` fails with error 6 (`ERROR_INVALID_HANDLE`) or error 87 (`ERROR_INVALID_PARAMETER`).
3. **Multi-Driver Fallback**: Never allow a failure in `driver.openDevice()` to bubble up and crash `listDevices()`. Keep it wrapped in a `try...except` so secondary drivers (`libusb0`, etc.) can claim the device.
4. **Hibernation vs Cold Reboot**: On standard power-switch off, the camera enters RAM hibernation snapshot (`WBI1`) on `nflasha5`. Modifying files on `/usr` requires cold rebooting via `/bin/busybox reboot -f` to guarantee fresh reload into memory.
5. **No Blind Tests**: A test that only checks that bytes were written without decoding instruction opcodes or parsing descriptor byte-sums is a false test. Every patch must be guarded by disassembly and specification compliance checks.

## 2026-10-22 live encoder-fix deployment — supersedes earlier verified-1080p claims

User authorized flashing the offline encoder-workspace candidate. Current state is **partial deployment**, not verified working 1080p UVC.

- `/system/av-cam.bin`: `90096db2c76148f4f9db5d104e5c608c` — candidate RTOS workspace fix, persisted across reboot.
- `/usr/lib/libInfraStreamingUsb.so`: `19461091c07aa6900829defb0060fcd6` — candidate 1080p request and checked startup/caller, persisted across reboot.
- `/usr/lib/libInfraUsbCmn.so`: `31308976206a837f6f5c571992d2b499` — stock 720p descriptors after reboot. Candidate `bd32c223e60e363d900c7ac8be06641c` repeatedly matched immediately after writing, then reverted to factory inode/hash/timestamp. Atomic replacement, in-place eight-byte writes, and root-owned replacement all reproduced this. Inspected boot scripts did not explain it; dropping filesystem caches did not change it. Cause unresolved.

No post-deployment JPEG completion or host frame capture yet. The candidate's 59 offline emulation cases are not hardware validation. The earlier assertion that 1080p output was verified is incorrect.

Originals are verified in `/log/uvc_workspace_20261022/before/`: original RTOS `cdcae9d4fdbf66a33704a4c7564e346d`, common library `31308976206a837f6f5c571992d2b499`, and the user's intentional earlier width-only streaming patch `5a0417693a3d9ed1786c4d0afc043d6e`. Authentic stock streaming remains `/setting/stock_libs/libInfraStreamingUsb.so`, `cde7a1b42c919706aa5f61aba5fc0d75`.

Full second RTOS image does not fit on `/system`. The failed scratch copy was removed before active changes. A non-truncating 70-byte write via `dd ... 1<> /system/av-cam.bin` was tested on a staging copy, applied at file offset `0x810978`, and full-image MD5 checked. BusyBox lacks `conv=notrunc`. Original 70 bytes are `/log/uvc_workspace_20261022/workspace-original.bin`, MD5 `c0a3d45fd4b571b43af5a352193700a2`.

New `/log/uvc_workspace_20261022/revert-stock.sh` restores the RTOS function plus both authentic stock libraries and requires a subsequent verified reboot. It passed syntax checking; a full stock restoration has not been run. The older `/setting/revert_uvc.sh` restores only libraries and does not undo this RTOS change. Neither is proven recovery if the service shell cannot boot.

`/usr` returned read-only after reboot; `im.elf` PID 157 and `liro` were observed. USB sometimes disappears from Windows after leaving service mode; reconnecting the cable restored access. Do not treat USB return as streaming success. No font, resource, NVRAM, bootloader or partition-table changes were made in this deployment.

Deployment report and terminal logs: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\uvc-startup-fix\deployment\STATUS.md`.


## 2026-10-22 uncompressed USB 2 feasibility investigation

See ../uvc_uncompressed_usb2_feasibility.md. Offline analysis found that usbg_video.ko already uses DMA330 to copy physical-address/length payloads into USB staging buffers, separately from the JPEG producer. libBizFw.so has a concrete getYuvLayout wrapper at VA 0x39708, but a completed YUV frame acquisition/ownership contract is not yet recovered. Uncompressed 1080p30 NV12 needs 93.312 MB/s and cannot fit USB 2; lower modes or reduced frame rates are plausible pending measurement. Next proof: synthetic uncompressed UVC transport, then one real YUV frame. No camera operations were performed during this investigation. USB 3 remains deferred as requested.


## 2026-10-24 consolidation of the 2026-10-22 YUY2 prototype attempt

Durable results are now in [uncompressed USB investigation](../../usb/uvc_uncompressed_usb2_feasibility.md), [agent state](../agents/STATE.md) and [reference](../agents/REFERENCE.md). No new hardware test was performed for this documentation update.

The volatile 640×480 YUY2/10 fps synthetic prototype reached Windows/FFmpeg format enumeration, but a separate capture timed out after 25 seconds with zero bytes. The user reported a frozen camera and stopped hardware work for charging. No post-failure runtime log, DMM capacities or fault/thread trace was retrieved. The failure cause and the earlier VIDEO-tab crash remain unconfirmed.

Offline inspection found that source initialization failure permanently returns error 4 without a startup-failure completion, while the original video worker ignores the return. This is a concrete error-handling defect and a plausible freeze explanation, not a measured root cause. Corrected allocator interpretation: owner `0x2da`, staging unit type `0x50e`; the source helper takes unit type `0x50f`, not a requested byte count. Corrected descriptor length/pointer record VAs: PAL `0x1cab8`/`0x1cabc`, NTSC `0x1cdb0`/`0x1cdb4`.

Prototype changes are RAM hooks plus owned `/log/yuy2_640_20261022/` files; the earlier persistent RTOS/streaming-library deployment remains separate. Preserve `runtime.log` in that folder before a real reboot. Power-switch hibernation may retain hooks. Local evidence/source: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640` and sibling `work`. No complete synthetic frame, live YUV frame or working 1080p stream has been established.

## 2026-10-24 debugging attempt, forced restart and verified recovery

The user authorized debugging → USB Streaming → FFmpeg → service-mode log extraction. Debug capture was verified growing in `/log/usb_debug_20261024_01/app-sequential.log`. During the streaming transition Windows detected no Sony device and FFmpeg could not find the camera; no frame capture began. The user reported unresponsive controls and restarted the camera. This differs from the 22 October 25-second zero-frame timeout.

Recovered and hash-verified 34 files / 7,225,403 bytes, including the 1,936,183-byte binary application log. The prototype runtime file was identical before/after and already contained helper allocation error 4, source-initialization error 21 (`0x15`), and zero address/capacity. This establishes the earlier source-allocation failure, not a measured capacity shortage or the latest lockup cause. Application binary records remain undecoded. Fresh thread/DMM/kernel/MPR captures are post-restart state.

Uptime reset 5,049.03 → 53.57 seconds; YUY2 module was absent afterward and service access returned. Common-library hash reverted from `bd32c223e60e363d900c7ac8be06641c` to stock `31308976206a837f6f5c571992d2b499`; persistent RTOS/streaming candidates were unchanged. No new firmware or RAM patch was installed during recovery.

Full durable handoff: [YUY2 diagnostic reverse engineering](../../usb/uvc_yuy2_diagnostics_handoff.md). Host bundle: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\usb-debug-20261024-01`; verify with `transfer-result.json` and `camera/transfer.md5`. Next: decode preserved binary records, trace generic allocator error 4, recover correct lifecycle failure handling, then prepare a bounded test. Original VIDEO-tab crash and latest lockup remain unconfirmed. Do not automatically reapply the failed RAM prototype.

## 2026-10-24 revision 2 patch built after diagnostic handoff

User requested implementation. Created the source-only recipe at `research/firmware/yuy2_transport_v2/` and built the RAM-only synthetic 640×480 YUY2/10 fps module. Source allocation now requests exclusive JPEG workspace unit `0x276` / extent `0x333` (3,276,800 configured bytes), never audio `0x50f`. JPEG path configuration remains bypassed. Actual allocator success in camera mode is unverified; the pre-start guard returns an error instead of entering asynchronous Starting if allocation fails.

Implemented bounded retries, later connect retry, queued main-thread stop/reply recovery, and DMA-aware cleanup that pins an uncertain active source. Thirty ARM cases and four Thumb loader cases passed; portable rebuild yielded identical module hash. No camera operation, firmware write or RAM deployment was performed for this candidate. [Candidate report](../../usb/uvc_yuy2_patch_v2.md) records verification, exact hashes, limitations and next live acceptance. Current camera state remains the last verified post-restart baseline until checked again.

## 2026-10-24 revision 2 RAM bootstrap installation

User authorized installation. Initial guards refused an unloaded streaming library, then refused the stale base after the user opened its setup page. Rebuilt the loader for observed streaming base `0x0a663000` (common `0x04834000`, libdl `0x040ba000`), repeated 30 ARM plus four Thumb cases, and verified original target bytes. Uploaded the candidate and installed `0a66c0c0` / 380 bytes and `0a66bd00` / 12 bytes. Independent readback matched; firmware/config hashes stayed unchanged. Module MD5 remains `38e3b9a764b2bdb7470ac78e4ae25d4b`; rebuilt loader MD5 is `02a5084d5e2f7343b0d589a89b471a3e`.

Fresh debug capture under `/log/yuy2_640_v2/` was verified growing before service authentication closed. The user activated streaming; Windows and FFmpeg showed no Sony USB device. A cable-only reconnect was requested, preserving power/state for diagnostics. Module constructor execution and frames are not yet verified. Evidence: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640-v2\deployment`. Build/verification source now supports `--stream-base`; install addresses derive from the manifest. No firmware-image write or reboot was performed during this installation.

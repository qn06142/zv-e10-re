# UVC JPEG resize-workspace correction candidate

22 October 2026; knowledge consolidated 24 October 2026. Offline checks passed; the RTOS and streaming-library candidates were subsequently deployed and persisted, while the descriptor library reverted to stock after reboot. This is a partial deployment without verified 1080p frames. See the live deployment section below. The later [synthetic YUY2 experiment](uvc_uncompressed_usb2_feasibility.md) advertised its format but captured zero frames; it does not validate the JPEG fix.

Saved binary logs from the failed 1080p streaming session contain ScalarInfra JPEG completion status 5 and SDF buffer-capacity failures (internal status 0x10, diagnostic 0x4df, source location 0x541). The firmware maps 0x10 to public `SDF_ERR_PARAM` (5). The actual failing capacity check is at raw `av-cam.bin` offset 0x6de746. This supersedes the guessed 0x33e timeout explanation: that constant is a diagnostic immediate in a Linux logger call, not a measured hardware error.

The streaming JPEG builder at 0x810978 supplies a resize-workspace handle in packet +0x50, obtained from DMM unit type 0x276 by its caller. ApiEncodeJpegWithWork (0xfab8c) checks that workspace against width × height × 2. The requirement rises from 1,843,200 bytes at 720p to 4,147,200 bytes at 1080p.

The supplied workspace is the likely root cause. Its actual live capacity was not measured, and the recorded diagnostic is also used by other buffer checks. A hardware control is still needed to establish causality conclusively.

The firmware supports handle 0xffff for an internally allocated workspace. ModuleEncodeJpegWithWork selects this at 0x10b980; the allocator computes the dimensions and selects pool 0x0f for sizes up to 0x400000 at 0x6efd96. Cleanup at 0x6f051c releases that memory. The candidate uses this existing path only at width 1920. It preserves other request fields, JPEG size limits, and the original external-workspace behavior at other widths. No capacity check is bypassed.

The generator also checks both Linux configuration results and their immediate caller's started flag, and pairs matching 1080p USB descriptors with the encoder. A later asynchronous JPEG error is still distinct from a startup error. The old deployment tools' fixed hashes and patch offsets do not describe this candidate.

## Build and verify offline

```powershell
& '.venv\Scripts\python.exe' -B research/firmware/patch_uvc_encoder_workspace.py
& '.venv\Scripts\python.exe' -B research/firmware/verify_uvc_encoder_workspace.py
```

Dependencies: Capstone, Keystone and Unicorn in the existing research environment. The generator accepts `--repo`, `--width 1280|1920`, and `--output`. Default output is `dumps/staged/uvc/encoder-workspace-fix/candidate-1080p`. It validates the source hashes and produces three local files plus a manifest and disassembly. It never accesses a camera.

59 binary-execution cases passed: startup/caller success and errors, stack and register preservation, semaphore balance, original RTOS height inference and output limits, original/candidate request comparison, workspace capacity checks and public error translation, allocator selection, and allocation/cleanup routing. OSAL, DMM allocation and hardware services are controlled stubs. Injected capacities are not live measurements.

Original av-cam.bin MD5: cdcae9d4fdbf66a33704a4c7564e346d.

Candidate MD5s:

- av-cam.bin: 90096db2c76148f4f9db5d104e5c608c
- libInfraStreamingUsb.so: 19461091c07aa6900829defb0060fcd6
- libInfraUsbCmn.so: bd32c223e60e363d900c7ac8be06641c

The RTOS change is required to exercise the workspace correction; replacing only the Linux libraries does not apply it. No deployment or flash script is supplied. Hardware validation must confirm actual JPEG completion and decoded 1920×1080 frames, not just the camera's streaming indication.

## Corrections established by the original RTOS

With aspect enum 2 and height zero, width 1920 derives height 1080 at 0x4efa40. A forced-height patch is unnecessary on this path. The JPEG output request is clamped to 0x3f000 bytes with a 0x1000-byte area overhead at 0x810978. The parameter 300 is clamped to 256 and used with a left shift of 10 in the size-control path; earlier assertions that this establishes a 300 Mbps stream are unsupported.

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


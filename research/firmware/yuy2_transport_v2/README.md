# 640×480 YUY2 transport patch, revision 2

This is an **offline-verified RAM patch candidate**, not demonstrated camera output. It produces synthetic colour bars at 10 fps, not sensor footage. No firmware image is flashed by these build/verification tools. Generated binaries belong in local staging, not the repository.

## Changes

- Requests configured workspace unit `0x276` (extent `0x333`, configured 3,276,800 bytes) through the original DMM allocator. JPEG path configuration is bypassed. This replaces the incorrect audio-unit request `0x50f`. The allocator must grant exclusive ownership; this code never opens or overwrites an existing unit belonging to another owner.
- Checks actual source capacity/address, arithmetic overflow and non-overlap with USB staging before mapping or writing pixels. Requires 614,412 bytes in each USB staging half. Staging remains owned by the driver.
- Prepares source memory in `Ready::funcConnectCmd` before the original function stores a pending reply or enters `Starting`. Five failed attempts complete the original caller with a nonzero result, without entering the original connect path. A later request can retry.
- Queues terminal producer failures to the original streaming-main event queue. Stop/cleanup and asynchronous completion run on that thread after the producer releases its scalar semaphore. The worker never recursively stops itself.
- Hooks stop and finish for source cleanup. An uncertain DMA completion pins the source; it is never freed speculatively. A later successful completion/cleanup or real reboot releases that condition.
- Preserves 640×480 YUY2 descriptors and probe/commit interval. Uses guarded ten-byte Thumb trampolines to retain original connect/start/stop/finish behavior. All branch sites are checked before mutation.

## Build and verify offline

Requirements: the project's Python environment with Capstone, Keystone, Unicorn and pyelftools, ARM GCC at `C:\msys64\ucrt64\bin\arm-none-eabi-gcc.exe` (override `--cc`), original camera dump, and `build_sysroot/lib` from the inspected camera.

This patch explicitly targets the **checked-startup streaming candidate**, MD5 `19461091c07aa6900829defb0060fcd6`. Its start prologue differs from stock. Use the already generated candidate, or generate it with `research/firmware/patch_uvc_encoder_workspace.py`; do not replace the required image with stock or an old width-only patch. Common-library baseline is stock MD5 `31308976206a837f6f5c571992d2b499`.

Run these scripts from this recipe directory with explicit output paths. Example from the repository root after the recipe is installed under `research/firmware/yuy2_transport_v2`:

```powershell
$recipe = 'research/firmware/yuy2_transport_v2'
$repo = 'D:\02_Development_And_Projects\pmca-re'
$out = 'C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640-v2-rebuild'
$image = 'C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\uvc-startup-fix\candidate-1080p\libInfraStreamingUsb.so'
& '.venv\Scripts\python.exe' -B "$recipe/build.py" --repo $repo --output $out --streaming-image $image
& '.venv\Scripts\python.exe' -B "$recipe/verify.py" --repo $repo --output $out --streaming-image $image
& '.venv\Scripts\python.exe' -B "$recipe/verify_bootstrap.py" --output $out
& '.venv\Scripts\python.exe' -B "$recipe/package.py" --repo $repo --output $out
```

Expected: 30 ARM execution cases plus four Thumb loader cases. Tests execute the compiled module, compare all 614,400 image bytes, exercise actual trampoline prefixes, and verify AAPCS registers/stack. Hardware allocations, IPC, device mappings and scheduling remain mocked.

The output includes the module, bootstrap before/after blobs, exact-byte ptrace helper, descriptor/reference frame, verification results and manifest. `package.py` creates `install-ram.sh` only after both verification results exist. No script here accesses the camera automatically.

## Hardware boundary

Exclusive availability of workspace `0x276` during this camera mode remains unverified. It may be occupied or unavailable under current DMM rules. In that case the connect preflight must return an error; do not bypass allocator/size guards or steal another allocation. The preflight hook also needs hardware confirmation that gadget staging has been allocated by this stage of the mode transition.

Five source attempts contain four 150 ms delays **plus the existing IPC helper timeouts**, up to 3 seconds per request, and cleanup calls. This is a bounded retry count, not a 750 ms wall-clock guarantee. Original semaphore and OSAL calls retain their firmware behavior. Notification submission is attempted at most five times; broken firmware queues cannot be repaired by this patch. Stop/reply failures are logged without fabricating successful recovery.

`install-ram.sh` is an **unexecuted deployment artifact**. For a later service-mode test, preserve diagnostics first, re-check power/connection and all required hashes/maps, create `/log/yuy2_640_v2/`, and transfer the files named in `upload-files.json`. The script refuses different library bases, firmware/config hashes, or an already loaded YUY2 module. It arms only the two initial RAM bootstrap writes; on second-write failure it rolls back the first. The module loads on the next normal video prepare call. No `/system` or `/usr` firmware write is performed.

The expected configured bases in this loader are streaming `0x0a73d000`, common `0x04834000`, and libdl `0x040ba000`; a different map needs a rebuilt loader, not bypassed checks. Do not apply it while video is active. Once the module is loaded, its executable pages must remain mapped while hooks point to them; do not `dlclose` it or restore individual hooks during streaming. Collect `/log/yuy2_640_v2/runtime.log` and remove the complete volatile patch with a real reboot. A power-switch cycle may hibernate RAM.

First live acceptance remains a complete host-captured synthetic frame matching the reference, followed by repeated stop/restart and forced allocation-failure checks with responsive controls. Existing RTOS/streaming firmware candidates are separate persistent changes and are not restored by rebooting this RAM patch.

## 24 October deployment update

The guarded RAM bootstrap was installed and independently read back after rebuilding for the observed streaming base `0x0a663000`. The module image was unchanged. `build.py`, `verify.py` and `verify_bootstrap.py` now accept `--stream-base` (default is the historical `0x0a73d000`); `package.py` derives installer addresses from the build manifest. Supply the observed base to all three commands when rebuilding. Common and libdl bases retain their documented guards. The deployment candidate and evidence are in `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640-v2\deployment`.

Firmware hashes were unchanged after installation. Debug capture was armed. Following the user's streaming activation, the camera was absent from Windows USB/DirectShow; a cable-only reconnect was requested. Module activation and frame output remain unverified at this update. Do not treat bootstrap readback as a successful host-frame test.

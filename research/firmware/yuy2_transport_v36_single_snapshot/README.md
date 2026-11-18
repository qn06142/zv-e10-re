> **Hardware trial FAILED:** no OBS frame, then repeated crashes (29October2026). [Recovered evidence](evidence/crash-20261029/REPORT.md). Single-snapshot mode is not a demonstrated stability fix.

> Installed and reboot-verified29October2026; [deployment record](evidence/install-20261029/REPORT.md) supersedes the historical build status below. No frame test yet.

# Revision 3.6 — single-snapshot diagnostic candidate

Built offline 29 October 2026. NOT INSTALLED; camera remains last-recorded revision 3.5. No device access, flash, reboot or IPC occurred during this build.

## Problem and intended behavior

The observed 3.5 run displayed scene-bearing but color-corrupted output in OBS; logs preserved fifteen completed VGA worker outputs followed by another RESIZE_READY, then a restart. No fault PC proves the crash cause. Earlier offline analysis also proved USB F002 is slot availability, and a submit timeout can still return zero. Rewriting the USB source based only on those returns is not a safe exceptional-path DMA fence.

This candidate therefore changes the test scope explicitly: ONE successful native source/resize transaction per cold boot, followed by repeated transmission of the same immutable image. It is a frozen snapshot diagnostic, not continuous video or a proved crash fix. The first acquisition still uses DMM pool scanning; live source-event ownership, stop races and hardware completion remain unresolved.

## Changes

- Retain the native output in module-owned RAM. Publish capture-ready only after known borrowed-reference cleanup succeeds. Failed Close/Free or an uncertain outcome prevents publication and quarantines.
- Exit the capture worker after success. A one-start latch prevents worker restarts. Subsequent USB requests never acquire another frame or issue another SDF resize.
- Copy the USB source exactly once. Later calls for the same target/binding return the same sequence without overwriting it; changed target pointer/physical bindings are refused. This removes repeated source writes from the test; it does not make the driver's DMA cancellation behavior proven.
- Save exactly the requested 614400 native bytes to /log/yuy2_640_v36vga/native-vga-snapshot.bin after borrowed-reference cleanup. A dump failure is logged and does not imply capture ownership failure. Input/destination descriptors remain available. Pixel format/color conversion is deliberately unchanged pending raw-byte analysis.
- Log actual SDK return, ACK status and CMP status in RESIZE_RETURN. Source searches terminate after 30 unsuccessful polling passes instead of scanning indefinitely. Native synchronous IPC itself still has no proved timeout/cancel mechanism.
- Distinct module dependency/SONAME and /log/yuy2_640_v36vga directory. Guarded installer accepts only exact installed 3.5 baseline, installs dependency first, keeps recovery copies and remounts /usr read-only. Rollback restores 3.5, which has reported crashes; stable 2.4p rescue remains separately retained.

## Verification

49 host worker cases pass, including ACK/CMP rejection despite SDK success, cleanup failures preventing publication, publication lock failure, bounded no-source search, pointer/binding rejection, and 100 immutable replays. Sony, memory mapping and hardware services are mocked.

Compiled Cortex-A5 ARM instructions also pass the captured-state replay fixture: 101 successful calls, exactly one memcpy (614400 bytes), zero Sony IPC calls, no worker restart; a changed pointer/address and stop are rejected. This initializes captured state in the emulator, so it does not validate native capture or DMA.

11 persistent ELF/gate cases pass. ISA audit: 5330 instructions, zero NEON. 10 translated installer/rollback fixtures pass, including recovery after staged-copy, activation and read-only remount failures. Real mounts/storage/device services are mocked in those fixtures. First local installer attempt failed due MSYS sandbox access and was rerun successfully with permission; no target attempt occurred.

Package ZIP byte contents were compared with every packaged file. SHA256SUMS and manifest identify the exact pair; source-sha256.json identifies the recipe sources. The module has no load-time constructor; lazy activation path remains inherited. No camera test or menu/streaming crash-free claim.

## Artifacts and reproduction

Local package: .local/outputs/vga-v36/zve10-v36-single-snapshot.zip. Module and wrapper are under build/ and flash-package/. See flash-package/README.md for limitations and manifest.json for identities. Use both matched binaries; do not mix a wrapper from 3.5.

Source recipes are .local/work/vga-v36/recipe; verify_worker.py and verify_arm_snapshot.py are alongside them. Build with recipe/build.py --repo D:/02_Development_And_Projects/pmca-re --output .local/outputs/vga-v36/build --streaming-image .local/outputs/uvc-startup-fix/candidate-1080p/libInfraStreamingUsb.so, using the repo venv Python and the installed ARM compiler. Run verify_worker.py, verify_arm_snapshot.py, recipe/verify_persistent.py, recipe/verify_isa.py, then package.py (the latter runs installer fixtures). No script is to be run against the camera merely to reproduce offline checks.

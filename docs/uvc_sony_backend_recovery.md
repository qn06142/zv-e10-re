See [offline live-YC source recovery](uvc_yc_source_recovery_20261025.md) for the current direction. Earlier loader checkpoints below are historical; no new camera access.

## YC retest: baseline passed; loader-only probe armed

User standing instruction: clear diagnostic logs regularly. Before each new hardware test, stop prior captures, restore normal error filters, archive and hash-verify diagnostic captures, recheck camera hashes, then delete only verified diagnostic paths and confirm absence. Preserve firmware, calibration, helpers and system-managed logs. Use a fresh test directory and bounded capture. After collecting each run, repeat archive/verify/clear. This is an operational procedure, not a scheduled automation.

Baseline without observer passed ten complete 640x480 YUY2 bars frames, counters1–10; uptime197.29→981.42 seconds confirms no intervening reboot. Persistent 2.4p hashes unchanged. Archived22 files/8,282,393 bytes with matching camera MD5s; cleared7 capture files/8,180,954 bytes. Earlier cleanup cleared26 diagnostic files/19,916,504 bytes after archive verification.

Revision3 is a temporary loader-isolation probe, NOT a YC metadata observer. Its activation writes only `YC_V3_LOADER_ACTIVATION_OK` to `/log/yc_observer/runtime-v3.log`, with no Sony API, GOT hooks, subscription or pixel access. Module MD5 `4a6de2407407c3b8f7ae2c2a3366ad60`; three ARM probe cases and four bootstrap cases pass offline. RAM write/readback verified for PID157/base0x0a661000, prepare0x0a669d00 and cave0x0a66a630. Addresses are session-specific: never replay after reboot/process change. No persistent firmware changes. Previous metadata observer remains withdrawn.

Fresh debug capture `/log/yc_retest_20261024_02/app-sequential.log` is active with a guard stopping capture/restoring error filters after300 seconds or16MiB (polled every2 seconds). Service closed; awaiting user streaming activation, FFmpeg and service return for collection. Current local state/evidence: `outputs/yc-retest-20261024/`. No successful revision3 activation is claimed yet.

## Observer withdrawn after second reboot — 24 October 2026

Both temporary observer attempts were followed by a reboot. Latest service snapshot shows uptime 133.59 seconds, no observer mapping, no streaming-library mapping, and no observer2 runtime log. The fresh boot cleared the RAM bootstrap; do not restore or replay old addresses. The observer/bootstrap is suspect, but no retained crash PC establishes the cause. No genuine YC metadata or live camera frame was captured. Earlier three-frame bars capture happened after the first reboot and validates only permanent 2.4p.

There is no evidence that `/log` is full: recursive directory inventory found 447 regular files totaling 84,328,592 logical bytes (80.42 MiB), versus reported volume capacity 524,206,080 bytes (about 500 MiB). The filesystem free counter incorrectly reports the entire volume free despite existing files; do not cite that counter as precise free space. Allocation overhead was not measured. No files were deleted.

Permanent streaming library MD5 `5fde77e394572ebcf420f8941575f6c4`, producer `9181ef744955190d04728cf4ef7965c5`, and kernel `c1cad400372e26eca729e4b9bc47a237` still match the working 2.4p installation. Application debug filters were not changed. Second-attempt evidence archive contains 56 files / 5,528,122 bytes, all verified against camera MD5s. Service session closed normally. Current evidence/state is in workspace `outputs/sony-backend-recovery/deployment/`, especially `second-attempt-archive-verification.json`, `log-space-assessment.json`, and `state.json`.

Next work is offline fault isolation of the RAM loader, real execution context and observer ABI before another hardware probe. Passing emulation/import checks did not validate execution on the camera. Do not reinstall the observer or guessed Sony IPC. The generic 2.5 lease pipeline remains offline; the real Sony source subscription, buffer layout and ownership contract are unresolved. Preserve permanent 2.4p synthetic transport.

# Sony backend recovery and passive YC observer

24 October 2026. The previous completion claim is withdrawn: opcode 0x400/subcommands 3 and 4 are diagnostic records built after real DMM operations, not evidence of an acquisition IPC protocol. No real YC acquisition backend is established yet. Revision 2.4p remains the camera's permanent patch.

## Verified evidence

RTOS base is 0x635c6000 for firmware MD5 cdcae9d4fdbf66a33704a4c7564e346d. FC wrapper 0x63b4e70c calls the real open at 0x63970228 at instruction 0x63b4e724, then builds its 0x400/3 record and emits through 0x63e02a8a at 0x63b4e75a. Close wrapper 0x63b4e78c calls 0x63970380 at 0x63b4e794 before building its 0x400/4 record. The emitter enters 0x63e0299c, tests diagnostic category/filter bits and forwards record pointer/length to 0x63b4f4a8. Sending those log bytes to a guessed frame queue is unsupported.

Linux `DataflowInfraUtility::OpenMemFromDmmSync` at dataflowInfraFramework.so 0x20cc0 prepares a 24-byte command-5 structure. Completion offset +0x10 goes to its `int *` output at 0x20d2e, offset +0x14 to its `unsigned *` output at 0x20d34. These are an address/capacity pair; they do not establish two YC plane pointers. libBizFw.so DmmCh::open at 0x360a4 independently uses a 24-byte request/reply and command 5. The team's 40-byte multi-plane structure is a mock schema, not this recovered DMM-open ABI.

## Guarded code

`raw_live_sony.c` now fails closed in default and ARM-target builds: no simulated subscription, no invented physical addresses, no 0x400 request and no automatic bind. The historical model is preserved only behind explicit SONY_ENABLE_LEGACY_TEST_FIXTURES on non-target host builds so old mock tests remain recognizable as fixtures. Even setting that flag cannot enable it with RAW_LIVE_TARGET_ARM. New guard tests verify no callback is invoked, no fake address is returned and unresolved tokens are retained. This is protection while recovering the real source, not a completed live backend.

## Historical observer1 design and pre-test checkpoint (superseded)

[Observer source](../research/firmware/yc_observer/yc_observer.c) uses existing writable, non-RELRO GOT slots to observe `C_DataflowInfra_StdData_YC` construction and `ImageSizeInfo::GetData_All`. It makes no subscription, DMM-open, pixel-read or release call. It logs at most 16 constructors and 32 raw 60-byte metadata copies to `/log/yc_observer/runtime.log`. Aligned GOT stores preserve the original function code. The module must stay loaded until reboot; do not hot-unload callbacks.

Seven offline observer checks pass using real libBizFw ELF relocations and the actual framework Thumb GetData_All function. Four bootstrap checks preserve arguments/stack/LR and always chain the original permanent gate on load/lookup/activation failure. ISA scan reports zero NEON. Target dynamic-loader trace resolves all imports.

Temporary RAM bootstrap installed/readback verified for PID157, streaming base0x0a61e000, at prepare0x0a626d00 (12 bytes) and bypassed old producer body0x0a627630 (204 bytes). It preserves the permanent gate at offset0x90c0 and all on-disk firmware files. These addresses are session-specific and MUST NOT be replayed after a process change. Before/after bytes and checked-write helper are retained in `/log/yc_observer/` and session outputs.

First host attempt detected no USB device. A later streaming activation enumerated and FFmpeg captured three exact bars frames, counters1–3, exit0. No crash cause is established. Awaiting return to mass-storage/service without reboot to recover the observer log and confirm activation/metadata. Normal application debug logging was not enabled. Camera remains powered; temporary observer bootstrap may remain active until restored or rebooted.

Session root: C:/Users/qn061/Documents/Codex/2026-10-22/chec. Evidence and current state: `outputs/sony-backend-recovery/deployment/`. Service jobs in `work/yc-observer-jobs/`; 001–005 completed, 006 collection queued. Never replay completed jobs. After log collection, restore prepare/cave bytes only if PID/maps and current RAM guards still match; GOT callbacks remain valid until reboot.

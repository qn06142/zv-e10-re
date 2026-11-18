# RAW v0.1 receiver adapter — offline component, not a working camera patch

Built31October2026. No camera access, flash, restoration or real RAW capture. Camera remains4.2. This implements the Linux receiver portion of the native-dump proposal; native RAW request activation and USB spool are NOT implemented.

## Implemented

raw_capture_v01.so is an ARM Cortex-A5 shared library, no constructor/init-array, no sensor/config writes. Explicit raw_v01_install(currentCameraOnDemandSaverBase) checks two16-byte original-code guards, exact original writer address resolved by dlsym, and exact existing GOT value (resolved or native lazy initializer). It pins receiver/helper libraries then redirects only receiver PLT/GOT slot+0xa18c to our adapter. No other module/RTOS/kernel/firmware file is edited. This is a RAM hook; its live installer driver is NOT provided. Caller must verify exact native file MD5, current process mapping and idle receiver before passing base. Do not scan memory or reuse a historical base.

raw_v01_arm selects native RAW dump tag lowbyte1, exactly once. Before arm and for unrelated operation/mode/tag, calls original fsys_write. Selected request is copied as an immutable24-byte packet, requires operation1/mode0, nonzero span below physical0x40000000, bounded to64MiB without wrap. Source is mapped read-only through/dev/mem using the receiver's native page-offset convention. Format/depth is unknown and not changed.

Outputs are exclusive files under/log/raw_capture_v01:request.bin (24-byte original packet),frame.bin (exact bytes),complete.bin (matching24-byte packet only after request/payload writes,fsync andclose). Handles EINTR and short writes; zero/failing write, fsync, mmap or close fails capture. Existing files are never overwritten/deleted. Partial files remain without completion marker. No reset/rearm after success or failure in that process. Directory metadata durability across sudden power loss is not certified. Native cache coherency and actual source validity are still hardware requirements.

States:0unbound,1ready,2armed,3copying,4complete,5failed. Dispatch returns native bool1only after a successful selected copy. Existing receiver sends response afterward. RTOS sender ignores writer bool; host MUST require complete.bin, matching request/complete records and exactframe.bin length. Do not interpret a camera-side return0 as proof of capture.

## Verification

13native-host C cases compare copied bytes including low bits against an offset source pattern, exercise13-byte shortwrites/EINTR, open/write/fsync/zero-write failures, no-overwrite rejection, invalid spans, disabled mode and unrelated tag/mode passthrough. Built-Wall-Wextra-Werror. Syscalls mocked: no actual device/file I/O.

7actual compiled ARM installer cases cover resolved/lazy GOT, guard/slot/symbol mismatch, self-pin failure and mprotect failure; failed cases do not change slot. Loader/libc calls mocked. No live unloading/concurrency/native RAW activation verified.

## Remaining integration, before camera testing

1. Prove a one-shot native RAW request is emitted from the original still capture boundary, with authoritative encType/geometry and no8-bit conversion. Candidate selection bytes are configstorage0x6451d90d +0xf0..0xf6; configstorage0x643bf438+0x6c influences source-handle choice in ReadEndBase. These are offline address leads, NOT an approved live write recipe. Check real initialized objects, semantics and competing flags before any write.
2. Native RAW handler must provide the source form wanted: optional decompression is currently a separate native configuration branch. Do not manufacture10/12/14-bit claims from container size.
3. Implement a guarded service-side install driver for current mappings/files, and a bounded capture/retrieval procedure. No permanent modification or auto restoration.
4. Add USB carrier publication from the saved immutable file. Existing adapter stops at a local snapshot and does not yet feed webcam transport.
5. Live one-frame validation, host hashes and native release/storage checks are required before calling this working.

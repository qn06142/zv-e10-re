# Revision 2.4p — permanent YUY2 transport verified

24 October 2026. Persistent files survived a genuine reboot and activated automatically on USB video prepare. First FFmpeg capture and same-session reopen each delivered ten exact synthetic frames. The user then confirmed OBS works without toggling USB Streaming. No live camera image source has been implemented.

## Installed files and activation

| Camera file | Bytes | MD5 |
| --- | ---: | --- |
| `/usr/lib/libInfraStreamingUsb.so` | 72,792 | `5fde77e394572ebcf420f8941575f6c4` |
| `/usr/lib/yuy2_640_v24p.so` | 16,100 | `9181ef744955190d04728cf4ef7965c5` |
| `/usr/kmod/usbg_video.ko` | 20,668 | `c1cad400372e26eca729e4b9bc47a237` |

[Source recipe](../research/firmware/yuy2_transport_v24p/README.md). Streaming prepare at offset `0x8d00` enters a 380-byte PIC gate at `0x90c0`, calls dynamically relocated `yuy2_activate`, and continues through the original prologue only after success. Dependency basename is `yuy2_640_v24p.so`. Dynamic tables move into an extended RW PT_LOAD while preserving original symbol indices, existing relocations/hash and original BSS zero initialization; overlapping nonallocated section-name metadata moves to EOF. No absolute process/libdl base is embedded in the gate.

The producer is constructor-free. It can be mapped when streaming setup loads the library, but only video prepare activates guarded runtime hooks. A cold post-install reboot showed neither library mapped and no runtime log at 74.25 seconds uptime; service access worked. This establishes observed dormant boot behavior, not a guarantee about every recovery path. Persistence removes manual service RAM bootstrap; runtime memory patching remains part of activation.

Kernel is proven revision 2.3, sysfs version `yuy2_640_v23`: frame 614,400 bytes, one-header payload 614,412 bytes, fixed interval 1,000,000 in 100 ns units, EOF asserted, PAL/NTSC override bypassed. A sixth guarded edit adds the version marker without changing runtime parameter registration. No temporary kernel bind overlay remains; `/usr` is read-only.

## Host-reopen correction and live results

[Revision 2.4](uvc_yuy2_patch_v24.md) reads libc TLS errno after WaitVideoReadCmp. EBUSY (16) preserves the in-flight source and retries at the existing 100 ms producer delay, without invoking our five-failure stop or Sony's ten-failure notifier. Other errors retain bounded recovery; readiness success remains required before modifying pixels.

- First FFmpeg: exit 0, 6,144,000 bytes, ten exact bars frames, counters 1–10.
- Same-session FFmpeg reopen: exit 0, ten exact frames, counters 29–38.
- OBS after both FFmpeg clients without mode toggle: user reported “works!”. Use Custom 640×480 / 10 fps / YUY2.
- Runtime HOST_WAIT/HOST_RESUMED after 128 and 283 polls; no WAIT_ERROR or FAILURE_EVENT. One source allocation, physical `0x15b00000`, capacity `0x320000`, handle `0x88b2`. Actual streaming base `0x0ea82000` differs from the offline verification base; activation succeeded.
- User returned to mass-storage/service mode. Stop/finish retained the pinned source as designed; do not hot-unload or free it.

This proves the tested client close/idle/reopen and OBS sequence, not sustained throughput or arbitrary mode-cycle endurance. Output is still synthetic. Live processed frame acquisition is the separate [raw-source investigation](uvc_raw_frame_source_prompt.md).

## Evidence and verification

Session root: `C:/Users/qn061/Documents/Codex/2026-10-22/chec`. Artifacts: `outputs/yuy2-640-v24p/candidate/` and `deployment/`. Final streaming artifact is **`libInfraStreamingUsb.persistent.so`**; earlier similarly named `libInfraStreamingUsb.so` is superseded and was not installed.

Offline: 54 compiled producer/activation cases, 11 ELF/PIC checks, 14 kernel checks, all pass (79). Tests include PIC success/failure at three arbitrary bases, dormant mapping, and idempotent activation. Target LD_TRACE_LOADED_OBJECTS with LD_BIND_NOW resolved the staged producer and activation import. Original standalone library has 66 unresolved application imports, candidate 32, no new unresolved symbols; normal im.elf supplies these globals. Trace is not proof of standalone execution.

Post-test archive: 59 files, 6,693,389 bytes, each checked against camera MD5 manifest (`deployment/evidence-verification.json`). Sequential application log: 822,118 bytes, 24,808 decoded records, zero corruption/slack. Decoder counts 79 generic error-category records; that count alone does not establish a crash. Runtime log is 1,011 bytes. Archive includes preflight/install/rollback traces, binary readbacks, maps, kernel/application logs. Normal error logging restored, debug capture stopped, service session closed. Final state: `deployment/deployment-state.json`.

## Recovery and installation lessons

Camera recovery script: `/usr/share/yuy2-recovery-v24p/rollback.sh`, final MD5 `cd67ea02a57715d823ca7c1baf99499b`. Target syntax checked and read back byte-for-byte. It verifies known hashes, retains mapped patched-file inodes via hardlinks, restores baseline streaming library and factory kernel atomically, removes producer pathname, and requires a genuine reboot. On-disk restoration cannot clear current RAM hooks. Final hardened rollback has not been executed end-to-end; earlier failure rollback was exercised and verified.

Backups: `libInfraStreamingUsb.baseline.so` MD5 `19461091c07aa6900829defb0060fcd6`, 52,524 bytes (pre-install checked-startup/1080 candidate, **not factory stock**); `usbg_video.baseline.ko` MD5 `5b59c2e62c80683d754955ab5de0467d`. `libInfraStreamingUsb.original-inode.so` retains the original inode.

First install replaced a mapped streaming inode; ext2 read-only remount failed EBUSY because the old mapped inode became deleted. Failure trap restored exact baseline hashes. After genuine reboot, revised installer required cold/unmapped streaming code and retained its inode; install/remount succeeded. A second reboot verified persistence and dormant boot. Future updates must honor the cold/unmapped guard.

Installer did not write shared `libInfraUsbCmn.so`, RTOS, DMM config or boot scripts. RTOS remains `90096db2c76148f4f9db5d104e5c608c`; DMM config `9f197ff9b300e49ab531b6f9e794253e`. Common library was stock `31308976206a837f6f5c571992d2b499` immediately after install and reboot, then the known eight-byte 1080 descriptor variant `bd32c223e60e363d900c7ac8be06641c` after streaming. Recurring drift remains unexplained; do not attribute it to this installer or claim common stayed stock after streaming. Recovery intentionally restores only the persistent transport files.

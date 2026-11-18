**Latest hardware result: zero frames; first native YC SEND reached the receiver but its descriptor was rejected before resize. Logs recovered and service closed. See evidence/first-test-20261029/REPORT.md.**

# Revision 3.7: event-driven native YC

29 October 2026. **Installed and verified after fresh initialization. First frame test pending.** Three camera readbacks after reboot exactly match the built binaries. This establishes persistence and cold activation state, not working video or a crash fix. Service session closed normally (job 055, WORKBENCH_CLOSED / Done). The user has been asked to activate USB Streaming with OBS closed for a bounded FFmpeg test.

## Installed files and recovery

| File | Bytes | MD5 |
|---|---:|---|
| /usr/lib/yuy2_640_v37vga.so | 40444 | 7c339b924987e6baa8e7046e041798c5 |
| /usr/lib/libInfraStreamingUsb.so | 72796 | 277c023942dd4d3d347d9829eaf8be85 |
| /usr/kmod/usbg_video.ko | 27588 | 388799d95bbb524ca581c66b077b6dc2 |

Kernel version required by the producer is yc37_fence; actual kernel module loading is still to be exercised by USB Streaming. Before setup there were no streaming, producer or observer mappings. Fresh boot reported ssboot=idle, original kikilog version 01.00.000, /usr read-only, free /usr 10,765,312 B, /log 353,550,336 B, /tmp 5,242,880 B. The /tmp 4096-byte write/readback test passed. Logging filters were restored to normal error level, with no sequential application capture active.

Recovery is /usr/share/yuy2-recovery-v37vga/rollback.sh (MD5 8cd97d4a1bcf2cf48e4712ad746a547d). Default restores the preceding **unstable 3.6** wrapper (886445056d2eba99ef62df3a9def5e0f) and matched previous USB kernel (c1cad400372e26eca729e4b9bc47a237). --bars selects the separately preserved stable 2.4p wrapper (5fde77e394572ebcf420f8941575f6c4) and that previous kernel; producer 9181ef744955190d04728cf4ef7965c5 remains installed. Cold mappings are required for rollback. Keep module, wrapper and kernel matched.

The original diagnostic driver /usr/kmod/kikilog.ko is restored (51337167a2ab42d53557c2cce210c987), confirmed both on disk and loaded after fresh boot. USB common library is stock 31308976206a837f6f5c571992d2b499. Recovery artifacts for those dependencies are in /usr/share/tmp-fat-recovery-20261029/. No temporary diagnostic driver remains active.

## Frame path

The goal is continuously changing 640x480 camera frames. The source backend replaces pool scanning with a private generic VDF input pin requesting native type-0 YC output [0,2,0,0x59000e]. OSD control is not used. Original RTOS RequestConnect at 0x63ac1e38 was executed offline for free and occupied outputs. A distinct private input index 0x7fffff37 and dynamically allocated queue avoid the same-index behavior that can disconnect an existing peer. Occupied output must return -25 without changing that peer. Original Linux generic Pin.Connect, RTOS ConnectComp and Linux SendComp were executed across a complete fixture handshake.

The worker receives the producer's 52-byte SEND messages, opens transferred SDS and pre-shared type-0x295 pixel references, validates their metadata, resizes into owned VGA storage, closes and returns known transferred references with native Free mode 2, then sends completion separately. No speculative source Share or source-pool scan remains. USB staging is still identified through the DMM listing; that is not an image-source lookup. Backpressure drops incoming transfers while returning their credits. Unknown ownership or unconfirmed disconnect quarantines the run.

F002 reports staging availability, not DMA completion. The matched USB kernel repairs DMA start-error/timeout false success and the both-busy unlock path. EBUSY is retryable; another submission error retains the USB source and prevents future mutation. An independent DMM Share retains that allocation until boot, protecting it from manager teardown. Original video_thread already holds manager+0x18 around producer calls, and stop uses the same semaphore; no recursive lock was added. Self-pinning/single activation keep installed hooks alive.

The byte permutation assumes UYVY input and converts it to advertised YUY2. **Native packing remains unproved.** First native VGA bytes and bounded input/output SSYC copies are held in owned RAM and dumped only after confirmed shutdown. A crash before clean shutdown can lose these RAM snapshots. No synthetic fallback is sent. USB advertises 10 fps; no hardware rate is measured for this revision. At most one streaming session per cold boot remains supported.

## Verification

Original-code busy/free connection and two-domain handshake fixtures passed. The worker passed 10 host success, backpressure, stop and failure cases; two success cases each published 100 changing frames with transferred-reference accounting. The private-port fixture covered 100 SEND events, routing errors, connect/disconnect and late stop. Kernel execution covered four actual ARM completion/error paths and ELF relocations. Nine compiled ARM frontend, 17 SDK-loader and 11 persistent/PIC checks passed. ISA audit decoded 5768 instructions across 40 regions with no NEON. Fourteen local installer/rollback fixtures passed, including both-file restoration after failures and stable-bars rollback. These fixtures mock hardware and do not replace the pending integrated camera test.

The three-file installation ran dependency-first after exact baseline preflight; each staged and installed identity was guarded. Backups of wrapper and kernel were verified before activation. /usr returned read-only normally. Installed and postboot copies plus rollback script matched package bytes. Native boot-cache invalidation forced fresh initialization before final persistence verification. No FFmpeg or OBS capture of 3.7 has occurred yet.

## Storage recovery and boot-cache findings

This flash required recovery before installation. Seven old files (1,983,766 B) were archived and camera-MD5 verified. Cleanup mistakenly included system-managed /tmp/kikilog.dat, which should have been preserved. Restoring its original 1,957,888-byte archive initially hit ENOSPC at 98,304 B. The full original was preserved on the laptop and staged on the camera throughout. This mistake was disclosed and corrected. Fonts, tools, AccessLog and ThreadMonitor were preserved.

The first full FAT12 backup was 12,582,912 B, MD5 e558283227d539de3fe93f7678833e39. All 766 clusters appeared allocated: 332 directory-reachable and 434 unreachable (7,110,656 B), with no traversed chain errors/crosslinks. A guarded repair helper passed 11 host fault cases and the camera's exact-volume dry run. All apply attempts aborted before a FAT write because read-only remount returned EBUSY. Native kikilog suspend ioctl 0x80044a20 did not remove the hold. No manual FAT write, format, force unmount or lazy unmount was performed.

Original kikilog code can lose its retained filp on invalid-size failure without closing it; this was a possible hold explanation, not proof of the historical crash cause. A temporary recovery module skipped only kikilog_dat_open at .text+0xc64, removed that call's relocation, and used version tmpnofile (MD5 8af7cfd952dbdd47b4f468de6c7d385e). Ordinary reboot -f preserved the new disk file but resumed the original loaded module from Sony's snapshot. **Do not equate reboot -f with a fresh kernel/module initialization.**

Live snapshot state was snapshot, image_mode=2 and selected backend *wbi4. This exact kernel's image_drop_store (6011c248), image_mode_store (6011b4bc) and backend-dispatch path were inspected and executed offline with mocked storage. The complete 62,914,560-byte WBI partition backup was camera-MD5 verified (cfdf33a43ec8cf2f222d85c87318d3c9). Native one-byte writes image_drop='1', then image_mode='0', preserved the backend selection and zeroed the verified first cache sector. No manual boot-sector or boot-source-selector write was used. One initial eMMC read timed out and recovered on retry; header verification succeeded.

Fresh initialization then loaded tmpnofile and reported ssboot=idle. The newly backed-up /tmp volume (MD5 47884e816abcc85c17a855fd9128b82c) had **434 free clusters, zero unreachable allocation and no chain errors**. Native initialization recovered the 7.1 MB; the manual FAT proposal was not applied. No pre-cleanup raw volume exists, so the timing/cause of the prior unreachable chains and previous camera crashes remain unproved.

The original full logfile was restored by extending the existing chain without truncation, and its MD5 73b4dc0ac4b8e0b5796baf26694d88c7 verified. Original kikilog.ko was restored. Fresh initialization also exposed an old eight-byte 1080p descriptor patch in libInfraUsbCmn.so (bd32c223e60e363d900c7ac8be06641c), previously hidden by cached state. The exact descriptor-only difference was backed up and stock restored. Atomic replacement of this mapped library left an unlinked inode held by im.elf, so ordinary read-only remount was busy; the kernel's sync/read-only shutdown completed before another fresh boot. Avoid replacing a mapped inode when an ordinary remount-read-only is required. Final preflight passed against stock common library and original loaded logger.

Final activation again invalidated the native boot cache so neither the temporary logger nor old loaded USB components survived. Original module, stock dependency, recovered storage, clean cold mappings and /usr read-only were all confirmed after that boot. The recovery backup and logfile data remain local only; never publish these volume/RAM images.

## Current continuation

Wait for user activation of USB Streaming with OBS closed, then attempt one bounded FFmpeg capture. Query advertised format and request 640x480, 10 fps, YUY2. Save raw bytes and stderr; require complete changing frames before declaring success. Then request return to mass-storage/service mode without restarting and preserve bounded runtime/vga logs and retained native snapshots. If output 0 is busy, trace the actual producer/consumer route rather than stealing its pin. Real source accounting, SDF completion/cancellation, shutdown races, format, rate and camera stability remain hardware unknowns.

Current local artifacts: .local/outputs/vga-v37/deployment/deployment-summary.json, .local/outputs/vga-v37/flash-package/, .local/outputs/vga-v37/zve10-v37-event-yc.zip. Build manifests retain build-time observations; deployment-summary.json and this checkpoint describe the actual camera. Code and non-binary evidence are retained here; generated Sony binaries and raw .local/captures/backups are excluded.

Research lead for snapshot behavior: https://github.com/lzh2016zzz/a7cr-fl23-research (different camera; actions above were independently traced against the ZV-E10 kernel). Linux shutdown-interface documentation: https://kernel.org/doc/html/next/admin-guide/sysrq.html. Neither external source substitutes for target-specific guards.

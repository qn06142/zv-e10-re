# Revision 2 patch candidate — 24 October 2026

**Superseded live result:** the module did load, but its pre-connect staging check rejected both connection attempts before allocating source memory. The user could return to mass storage. Recovered 45 files with verified hashes. A real reboot cleared revision 2. [Revision 2.1](uvc_yuy2_patch_v21.md) fixes this order and enumerates, but its FFmpeg test still captured zero frames. The build description below is historical.

It retains the synthetic 640×480 YUY2/10 fps transport proof. It does not yet acquire live sensor YUV.

The patch replaces audio-unit allocation with an exclusive request for configured JPEG workspace unit `0x276` (extent `0x333`, 3,276,800 bytes), while bypassing JPEG configuration. The source must be owned, sufficiently large and disjoint from driver staging. Availability of that workspace under the real camera's current allocation rules remains a hardware question.

Source initialization now runs before the original Ready connect handler enters asynchronous startup. Five failed attempts complete the original request with a nonzero result. Subsequent connects can retry. Producer failures are handed to the streaming-main queue; original stop/cleanup and pending-reply completion happen after the producer releases its scalar semaphore. Stop/finish perform guarded cleanup. Unconfirmed DMA completion retains the source allocation instead of freeing a possibly active buffer.

## Verification

- **30 compiled ARM execution cases:** constructor guards/protection failure, exact descriptor bytes, four real trampoline prefixes/continuations, all 614,400 golden frame bytes, counter changes and allocation reuse, transient/permanent allocation failures, short/overlapping/overflowing source ranges, failed mapping/device access, later connect retry, deferred runtime error completion, DMA ownership pinning, failed frees/stops/replies, bounded event submission and probe/commit controls. AAPCS callee-saved registers and stack are checked on calls.
- **Four Thumb loader cases:** success, `dlopen` failure, `dlsym` failure and module-status failure.
- The portable recipe rebuilt an identical module and reproduced the same checks against the checked-startup streaming candidate. A trial verification against stock was rejected by the start-entry guard, as intended; the stock and candidate prologues differ. Build/verify now require the exact streaming image explicitly.
- Largest compiler-reported function stack frame: 216 bytes (`log3`); source/config buffers use heap storage.

Camera services, memory allocation, mapping, IPC and scheduling are mocked in these checks. This is not proof of camera output or mode-switch responsiveness.

## Files and next test

[Source recipe](../research/firmware/yuy2_transport_v2/README.md) contains the source-only build, verification and installation-boundary instructions. `manifest.json` records firmware/config requirements, hashes, checks and limitations. `install-ram.sh` and `upload-files.json` were executed for the historical revision 2 test described above. The installed RTOS/streaming candidates and all recovered logs remain unchanged by this work.

The loader is guarded to the previously observed library bases and exact firmware/config hashes. It rejects an already loaded YUY2 module. A different base map requires a rebuilt loader. Collect diagnostics and verify current service-mode state before any live application.

Acceptance still requires a real captured reference frame, followed by stop/restart and error-recovery tests with responsive camera controls. Retries include firmware IPC timeout costs; they are not a 750 ms deadline. If OSAL notifications fail or DMA completion cannot be established, logs explicitly report incomplete recovery and the source may remain pinned until a later cleanup or real reboot.

Local candidate/evidence folder: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640-v2`. Original diagnostic evidence remains in the sibling `usb-debug-20261024-01` and `yuy2-640` folders.

Deployment evidence and current rebased manifest: `C:\Users\qn061\Documents\Codex\2026-10-22\chec\outputs\yuy2-640-v2\deployment`. The original candidate manifest predates installation; use `deployment/candidate/manifest.json` for the installed loader bytes and `deployment/STATUS.md` for live observations.

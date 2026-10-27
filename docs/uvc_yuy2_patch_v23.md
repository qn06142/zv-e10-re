# YUY2 revision 2.3 — kernel negotiation candidate

## Final verified result — 24 October 2026

Revision 2.3 delivers synthetic 640×480 YUY2 frames to Windows. FFmpeg captured ten complete frames (6,144,000 bytes), every static bar region matched, and counters advanced 1–10. After exiting/re-entering USB Streaming, the user confirmed OBS displayed frames with counters at Custom 640×480, 10 fps, YUY2. Camera-mode restart restored delivery without a reported reboot. Live sensor capture and sustained measured frame rate remain outside this result.

Remaining defect: a later host client in the same camera streaming session can receive no frames. OBS initially failed after FFmpeg; a standalone FFmpeg reopen also timed out with zero bytes. Recovered runtime now confirms the producer invokes failure/stop after five consecutive readiness failures: 15 WAIT_FAILED entries and three FAILURE_EVENT entries across the run, with corresponding stop/finish cleanup. Mode restart then rebound the retained source and resumed submissions. This supports correcting host-idle/readiness handling. Exact failure timing relative to individual host disconnects is not timestamp-correlated in the module log; do not claim a timestamp-proven single-cause trace. The combined kernel corrections permit delivery, but individual edits were not isolated experimentally.

Evidence archive: **57 files / 9,231,531 bytes**, all camera hashes verified. Application capture: **111,319 records**, zero corrupt records or unparsed bytes. Runtime confirms INSTALLED_V23 at streaming base `0x0a61e000`, one successful exclusive source allocation at physical `0x15b00000`, capacity `0x320000`, handle `0x8d57`, reuse across mode starts, and no CONNECT_REJECTED entries. The final source is conservatively retained/pinned; do not free it or hot-swap hooks. Logger error-area labels are generic categories, not independently established fatal events.

After tests, kernel version still reads `yuy2_640_v23`; the bind overlay still hashes `c1cad400372e26eca729e4b9bc47a237`. RTOS, common library, streaming library and DMM configuration retain expected baseline hashes. Debug capture was stopped; filters 131/135/136 restored to normal error level and confirmed. Service session closed normally after the user returned to mass storage. The kernel overlay and RAM patch remain volatile; a genuine reboot removes them. No further patch changes were made during evidence collection.

Current machine-readable checkpoint: `outputs/yuy2-640-v23/deployment/deployment-state.json`. Preserved captures: `captured-01.yuy2`, `first-frame.png`, FFmpeg logs/JSON and OBS device-log excerpt. Full camera evidence: `camera-after-tests/`; decoded application log: `app-decoded.txt`. Next engineering work is a separate host-inactivity/client-reopen lifecycle correction, followed by fresh-boot guarded deployment. Earlier checkpoints below document the sequence and are superseded where statuses differ.


## OBS and mode restart confirmed — 24 October 2026

After exiting and re-entering USB Streaming, the user opened OBS as the first capture client at 640×480 YUY2 / 10 fps and reported: “success! it is outputting frames properly, with counters”. This confirms user-observed OBS preview and camera-mode restart without a reported reboot, alongside the independently verified ten-frame FFmpeg capture. No live sensor image is implemented; the source remains synthetic bars/counters. This result does not prove sustained measured frame rate or arbitrary repeated host-client opens.

The remaining reproducible defect is same-session host reopening: after the first FFmpeg client disconnected, OBS failed and an FFmpeg reopen timed out with zero bytes. A camera USB Streaming mode restart restored delivery in OBS. Producer shutdown on repeated readiness failures remains a likely explanation, awaiting camera logs. Do not describe OBS compatibility or the mode restart as still failing; do not describe same-session host reconnect as fixed.

User asked to close OBS, return to mass-storage/service mode and reconnect without reboot for evidence extraction. No additional code or firmware changes were made after the successful paired deployment. Current authoritative local state: `outputs/yuy2-640-v23/deployment/deployment-state.json`.


## First frame delivery confirmed; client reopen fails — 24 October 2026

Revision 2.3's first FFmpeg capture succeeded: exit 0, ten complete 640×480 YUY2 frames, 6,144,000 bytes, all static colour bars match exactly, counters 1–10. This demonstrates camera-to-Windows synthetic frame delivery with the paired kernel/userspace candidate. The first-frame PNG and raw capture are preserved locally. It does not establish live sensor capture or measured sustained 10 fps.

User then tried OBS and reported it did not work. OBS's latest device log first records configuration failures, then correct 640×480 / 10 fps / YUY2 settings; settings alone do not explain all subsequent failure. With OBS closed and no camera-mode restart confirmed, an FFmpeg host-reopen attempt also timed out after 25 seconds with zero bytes. Thus later-client failure is reproducible outside OBS. Most likely producer readiness/failure lifecycle needs correction: current code stops after five consecutive WaitVideoReadCmp failures, including possible host inactivity. Camera runtime logs are needed before declaring that exact sequence proven. The successful capture proves the combined kernel changes permit delivery, not which single edit was independently necessary.

User asked to exit/re-enter USB Streaming, then open OBS directly as the first client with Custom 640×480, 10 FPS, YUY2. Awaiting whether bars appear. Stop/restart and OBS success remain unverified. Current service session is closed; do not overwrite the loaded patch. Evidence: `outputs/yuy2-640-v23/deployment/capture-01.json`, `captured-01.yuy2`, `first-frame.png`, `capture-host-reopen-01.json`, and `obs-device-log-excerpt.txt`.


## Latest live deployment — 24 October 2026

The paired revision is now installed for a hardware test. Kernel file MD5 `c1cad400372e26eca729e4b9bc47a237`, live module version `yuy2_640_v23`, userspace MD5 `bef71344d4d6308e57ab65bdff3283e5`. Fresh streaming base is `0x0a61e000`; bootstrap at `0x0a6270c0` and prepare hook at `0x0a626d00` were read back byte-for-byte. The userspace constructor will run on the next normal video prepare; activation itself is not yet confirmed.

Kernel activation uses a temporary bind mount from `/log/yuy2_640_v23/usbg_video.ko` onto `/usr/kmod/usbg_video.ko`, followed by a non-forced module unload/reload after checking reference count zero. The underlying stock module was not overwritten. The module version was read back through sysfs; firmware disables `/dev/kmem` reads and has no `/proc/kcore`. The final kernel includes a sixth edit placing this version marker into optional `.modinfo` documentation storage; runtime `__param` bytes are unchanged. The original five functional edits are unchanged. All 42 producer + four bootstrap + 14 kernel checks pass for the live-map build. Earlier untagged offline artifacts under `candidate/` are preserved but superseded by `live-candidate/`.

Installation verified baseline RTOS/common/streaming/config hashes and exact source blobs, had rollback on failure, and succeeded. A genuine reboot removes both bind overlay and RAM hooks. Do not hot-swap loaded code. Fresh debug capture is active at `/log/yuy2_640_v23/app-sequential.log` (grew 477,392 to 477,738 bytes). Service session closed normally. User was asked to activate streaming, with OBS closed, for the first FFmpeg capture. No host frame result exists yet. Local authoritative state: `outputs/yuy2-640-v23/deployment/deployment-state.json`. Build manifests retain build-time not-installed fields; live deployment state overrides them.


Built 24 October 2026. **Deployed temporarily; FFmpeg and OBS synthetic frame delivery confirmed.**

The previous userspace prototype advertised YUY2 but did not update the kernel's probe responder. Revision 2.3 pairs the existing producer/restart correction with a guarded `usbg_video.ko` patch. It uses one UVC payload per frame, matching the existing staging/queue implementation.

| Setting | Stock kernel | Revision 2.3 |
|---|---|---|
| Maximum pixel frame size | 14,745,600 bytes | 614,400 bytes |
| Maximum UVC payload | 300,000 bytes | 614,412 bytes, including the 12-byte header |
| Interval | 333,333 or 400,000 in 100 ns units | 1,000,000 (10 fps) in all tested camera modes |
| Payload header | 0x8c / 0x8d | 0x8e / 0x8f; EOF set, FID retained |

Five guarded four-byte sites change: three probe constants, the branch bypassing the PAL/NTSC interval override, and the header arithmetic. The patcher resolves ELF section offsets and confirms no loader relocation touches these sites. It checks the full stock fingerprint, rejects unrelated changes/reapplication, and can restore the exact stock module. The kernel file stays 20,668 bytes long. EOF is an interoperability improvement; its absence was not a proven cause of the original failure.

The userspace component retains revision 2.2's module-lifetime source allocation and restart behavior. It is renamed to revision 2.3 with a separate runtime log path. The unused userspace probe/commit hooks remain for compatibility with the inherited producer tests; they are not the mechanism that changes kernel negotiation.

## Artifacts

Generated binaries are in the session workspace at `outputs/yuy2-640-v23/live-candidate/`:

- `usbg_video.ko`: MD5 `c1cad400372e26eca729e4b9bc47a237`.
- `yuy2_640_v23.so`: MD5 `bef71344d4d6308e57ab65bdff3283e5`.
- `usbg_video.patch.json`: exact before/after bytes, offsets and hashes.
- `manifest.json`: paired requirements, checksums, test results and activation constraints.
- Bootstrap blobs and checked process-memory helper, built against live stream base `0x0a61e000`. Rebuild for actual maps before deployment.

Reproducible source is in repo `research/firmware/yuy2_transport_v23/`. Follow its `README.md`. The kernel baseline is stock MD5 `5b59c2e62c80683d754955ab5de0467d`; RTOS/common/streaming/config baseline requirements are retained in the manifest.

## Verification

- 42 compiled ARM producer, lifecycle, ownership and restart cases pass.
- Four Thumb bootstrap cases pass.
- 14 kernel checks pass, including actual ARM probe construction in camera modes 0–3, both header variants, guard failures, exact rollback and changed-byte scope.
- Packaging checks that both PAL/NTSC userspace descriptors match kernel geometry, frame size and interval.

These checks simulate state/services. They do not emulate the UDC, DMA hardware or Windows UVC driver. Existing queue/completion error propagation and zero PTS/SCR header fields remain unchanged. No kernel delivery instrumentation was added in this revision.

## Activation and remaining test

This is a paired candidate. Activating only the userspace library leaves the original mismatch; activating this kernel alone with the stock MJPEG producer also creates an inconsistent stack. No automatic installer is included. Kernel activation and rollback must be selected from the actual camera boot/module state and verified in loaded memory; hashing a file alone does not prove the running module changed. Clear old RAM hooks through a genuine reboot and derive fresh process maps before arming the producer. Keep the stock kernel available for rollback.

The first hardware test must verify host acceptance of the larger 614,412-byte payload limit, then capture synthetic colour bars and counters, followed by stop/restart. If Windows rejects that limit, use explicitly headered smaller payloads; changing USB packet size alone will not implement UVC segmentation. This patch remains synthetic 640×480/10 fps and does not yet provide live sensor footage.

See [offline diagnosis](uvc_yuy2_delivery_audit_20261024.md) for the evidence and limits behind this change.

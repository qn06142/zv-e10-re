# YUY2 revision 2.4 — USB host-idle/reopen correction

Built 24 October 2026. **Offline verified; not installed or hardware tested.**

Revision 2.3 delivered ten exact synthetic YUY2 frames to FFmpeg and user-confirmed frames/counters to OBS after a USB Streaming mode restart. Reopening a host client without changing camera mode could stall. Its recovered runtime records three groups of five readiness failures followed by failure/stop events. This revision corrects the producer's treatment of busy staging buffers; it does not change raw-frame acquisition or the transport kernel.

## Change

The common library wrapper reduces negative ioctl results to 1, while libc preserves the error in thread-local errno. The inspected WaitVideoReadCmp kernel ioctl returns -EBUSY when both staging slots remain pending. The new producer reads the actual errno, retries EBUSY at the existing 100 ms polling interval and leaves the source buffer/manager binding intact. It resumes counter updates/submissions only after a successful readiness query. HOST_WAIT/HOST_RESUMED markers are rate limited; other errors use WAIT_ERROR and the existing bounded failure path.

Both previous shutdown routes are suppressed only for EBUSY. Our producer previously called request_failure after five failures. Independently, stock judge_notify_start_stop_evt (`libInfraStreamingUsb.so + 0x9578`) resets its count on success/failure transitions and sends event 10 after ten failed notifications once started (`0x95d8–0x95e6`). The busy branch now neither calls that notifier nor requests failure. Nonbusy errors, invalid staging/source checks, failed submits and explicit camera stop retain recovery/exclusion behavior.

This addresses a demonstrated software shutdown mechanism. It is not yet proof that every host reconnect recovers: cancelled USB requests or driver readiness flags may require further kernel work. No completion is fabricated and no pending source bytes are overwritten to force progress. The raw-image-source task is isolated in the [live-source prompt](uvc_raw_frame_source_prompt.md).

## Build and verification

Source-only recipe: `research/firmware/yuy2_transport_v24/`. Local artifacts: `outputs/yuy2-640-v24/candidate/`. Userspace module is 15,560 bytes, MD5 `c237ec9a3024d4b075e96943dab2ddb5`. Kernel remains the tested revision 2.3 binary, MD5 `c1cad400372e26eca729e4b9bc47a237`, loaded version `yuy2_640_v23`.

All **68 offline checks pass**: 50 compiled ARM producer/lifecycle tests, four bootstrap tests, 14 unchanged kernel checks. The eight new producer cases cover 100 busy polls without either stop notification, immutable source/counter preservation until readiness, resumed counters with one source allocation, three client cycles, prestart idle without fabricated completion, nonbusy errors (including missing errno), error-streak reset, and explicit stop during idle. Packaging checks both user descriptors against the kernel geometry/interval. Mocked services do not emulate Windows, UDC or actual DMA completion.

The bootstrap was built at the last observed `0x0a61e000` streaming base for offline verification. That is not an installation assumption: derive new process maps and rebuild before arming a fresh camera session. No revision 2.4 code was written to the camera. Revision 2.3 remains the last live installation, with normal logging restored and its service session closed.

## Required hardware test

After a genuine reboot clears old hooks and retained source ownership, restore/verify the temporary revision 2.3 kernel overlay and arm the guarded new bootstrap against fresh maps. Do not install over the loaded module. Capture synthetic frames, close the client and leave the camera in USB Streaming for more than both old shutdown thresholds, then reopen the client repeatedly without changing camera mode. Confirm valid bars/counters and HOST_WAIT → HOST_RESUMED with no busy-triggered failure event. Also test OBS close/reopen and explicit camera stop/restart, then recover and hash-verify logs and restore normal filters. A source still pinned by the driver must remain immutable.

Until that test passes, describe revision 2.4 as a built/verified candidate, not a demonstrated hardware reconnect fix. See [revision 2.3 live result](uvc_yuy2_patch_v23.md) for the proven transport and current camera state.

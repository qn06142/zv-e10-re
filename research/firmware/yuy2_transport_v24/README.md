# Revision 2.4 — host-idle/reopen lifecycle candidate

This is a userspace correction atop revision 2.3's proven 640×480/10 fps synthetic YUY2 transport. Keep kernel MD5 `c1cad400372e26eca729e4b9bc47a237`, sysfs version `yuy2_640_v23`; there is no new kernel behavior in this revision. The included kernel patch recipe reproduces that exact dependency.

The source now reads the worker's libc TLS errno after WaitVideoReadCmp. EBUSY (16) indicates pending staging buffers and causes a rate-limited retry without calling the stock failure notifier, enqueueing a failure event, mutating pixels, or freeing memory. The original 100 ms producer delay bounds polling to at most ten polls/second before other work. Only a later successful readiness result permits pixel/counter reuse. Other errno values retain bounded failure/recovery, and explicit mode stop retains the original lifecycle. HOST_WAIT and HOST_RESUMED markers distinguish backpressure from WAIT_ERROR.

Why both paths matter: the old producer requests failure after five busy results; Sony's stock judge_notify_start_stop_evt at 0x9578 also sends event 10 after ten failed notifications once started. Removing just the five-attempt threshold would still stop the stream. This revision avoids both stop paths for EBUSY, without fabricating start/stop completion.

Use the same build environment as revision 2.3. Commands, from this recipe directory:

```powershell
python -B build.py --repo <repo> --output <new-output> --streaming-image <checked-startup-image> --stream-base <actual-base>
python -B kernel_patch.py --input <repo>/dumps/camera_2025/usr/usr/kmod/usbg_video.ko --output <new-output>/usbg_video.ko
python -B verify.py --repo <repo> --output <new-output> --streaming-image <checked-startup-image> --stream-base <actual-base>
python -B verify_bootstrap.py --output <new-output> --stream-base <actual-base>
python -B verify_kernel.py --stock <repo>/dumps/camera_2025/usr/usr/kmod/usbg_video.ko --candidate <new-output>/usbg_video.ko
python -B package.py --repo <repo> --output <new-output>
```

Expected: 50 compiled ARM producer/lifecycle cases, four bootstrap cases and 14 unchanged kernel checks. Eight new cases model long EBUSY periods, immutable source ownership, resumed counters, three host-client cycles, idle before start, nonbusy errors, error-streak reset and explicit stop during idle. Hardware services are mocked. These do not establish that Windows clears/consumes queued requests when reopening the pin.

Do not hot-swap a loaded revision. A genuine reboot is required to clear old RAM hooks/source ownership; it also removes the temporary kernel overlay, which must be reinstated and verified. Rebuild for fresh im.elf mappings. The source remains synthetic bars/counters; live frame acquisition is a separately scoped task. Hardware acceptance requires first capture, host close/idle/reopen without camera mode changes, OBS reconnect and a mode stop/restart. Diagnose remaining kernel completion/queue behavior if readiness never returns after host reopening; do not bypass the completion check or force free uncertain buffers.

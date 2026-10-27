# Revision 2.7 deployment package

Installed on the camera on 26 October 2026, downloaded readbacks verified, reboot persistence verified, and /usr confirmed read-only. Both streaming library and new module remain unmapped before streaming. Working permanent 2.4p is preserved for rollback. No sensor capture has been attempted yet. Ten adapted local installer fixture tests pass; the on-camera preflight, install and reboot evidence is in outputs/native-dmm-callback/deployment/live/.

## Scope and guards

Only /usr/lib/yuy2_640_v27snap.so and /usr/lib/libInfraStreamingUsb.so are installed. The existing 2.3 kernel, 2.4p producer, SDK, RTOS, descriptors library and DmmConfig are hash-checked and retained. The new streaming library is activated last, after the module and rollback are verified. Existing unknown files, recovery state, bind mounts or loaded streaming/probe mappings cause an abort. Required free space: 8 MiB on /usr and /log. A fresh power-on with USB Streaming unopened is required to exclude old RAM probe state; process maps alone cannot prove every byte in memory is pristine.

Verified backup and rollback are stored in /usr/share/yuy2-recovery-v27snap/. This rollback restores working permanent 2.4p (MD5 5fde77e394572ebcf420f8941575f6c4), not the older pre-2.4p baseline. The original /usr/share/yuy2-recovery-v24p/ remains intact. Atomic pathname replacement and verified backups reduce interruption risk; no power-loss guarantee is claimed. On a write/verification failure, the install trap attempts to restore 2.4p and remount /usr read-only; any recovery/remount failure is reported explicitly. The package contains no obsolete RAM helper artifacts.

## Operator sequence

1. Charge the camera and power on freshly. Connect in mass-storage/service mode; leave USB Streaming unopened. Close OBS/FFmpeg.
2. Stop old diagnostic logging, restore normal error filters, inventory only known diagnostic capture paths, download them, verify every file against camera hashes, then delete only the individually verified diagnostic files. Preserve firmware, system-managed logs and helpers. This is the standing archive/verify/clear procedure; it has NOT yet run for this deployment.
3. Run the explicit preflight job below. Review its hashes, maps/overlay guards, free space and DMM inventory. Eligible units may appear only during streaming, so the inventory is a lead rather than proof of capture readiness. Resolve any failed guard before staging; never change expected hashes just to make it pass.
4. Stage the package. Stage only uploads and verifies; it never installs. It uses the diagnostic directory created by preflight. Interrupted stages are inspected manually, not overwritten automatically.
5. Run install. It repeats preflight, checks every staged hash and performs guarded writes. The host then downloads and verifies both installed binaries and the 2.4p backup. A USB drop is an ambiguous result: inspect the files/evidence before deciding what ran. There are no automatic retries.
6. Reboot as a separate, recorded action. The runner never reboots. Reconnect to service mode and run readback, confirming that the patch survived boot and remained inactive. Keep fresh bounded logging for the subsequent test.
7. Switch USB Streaming on only when prompted for capture. Use capture_opaque.py from the source recipe with OBS closed. Collect exact 614400-byte packets using FFmpeg stream-copy, then test a second start and return to service mode for logs. Archive/verify/clear again afterward. Sensor format, cache coherence and active producer availability remain hardware questions; no bars fallback is supplied.

Explicit job examples (run from the workspace; use a new evidence directory each time):

```
python -B work/native-dmm-callback/deployment/run_job.py preflight --package outputs/native-dmm-callback/flash-package --output outputs/native-dmm-callback/deployment/preflight-01
python -B work/native-dmm-callback/deployment/run_job.py stage --package outputs/native-dmm-callback/flash-package --output outputs/native-dmm-callback/deployment/stage-01
python -B work/native-dmm-callback/deployment/run_job.py install --package outputs/native-dmm-callback/flash-package --output outputs/native-dmm-callback/deployment/install-01
python -B work/native-dmm-callback/deployment/run_job.py readback --package outputs/native-dmm-callback/flash-package --output outputs/native-dmm-callback/deployment/readback-01
```

Use the repository .venv Python. `--repo` defaults to D:/02_Development_And_Projects/pmca-re. The runner stages shell jobs under /log (not /tmp), and opens one authenticated session for exactly one named step, checks both an anchored success marker and exit status, records output, and closes the terminal. It does not poll an install queue, advance to another step, retry a mutation or reboot. It is adapted from the established service workbench; the actual deployment used the established interactive workbench with explicitly queued, reviewed jobs.

## Recovery

If a test fails, cold-boot back into service mode without entering USB Streaming. The guarded recovery script refuses live streaming mappings. Either run `/bin/busybox sh /usr/share/yuy2-recovery-v27snap/rollback.sh` through the service shell, or use the runner's explicit rollback step with a fresh evidence directory. Verify its success marker, then reboot separately. The inert new module is retained for audit; the streaming library again depends on 2.4p. If either image or its backup has an unexpected hash, stop and inspect instead of bypassing guards.

Raw source recipe and offline evidence: research/firmware/yuy2_transport_v27_snapshot/ and docs/uvc_native_dmm_snapshot_v27.md in the repository. This package is experimental; it has not produced a real sensor capture yet.

## Actual deployment notes

The camera /bin/busybox lacks find, df and awk. Inventory used bounded shell globs. The package now includes a read-only ARM statfs helper, checked by MD5, to require 8 MiB available on both /usr and /log. It ran successfully on-camera: /usr available 11219968 bytes, /log available 524025856 bytes before installation. /tmp was 100% full and Senser file creation there failed with error 130, leaving empty temporary files. No system-managed /tmp files were removed. /log staging and direct terminal commands resolved transfer failures. A copy of the existing soft-float toolbelt was retained at /log/yuy2_640_v27snap/busybox for inspection. Two diagnostic logs totaling 1711247 bytes were downloaded, hash-verified and deleted.

Installed streaming MD5 c3aa9b92ea6c05ce78aa7894e8dfe35a; new producer ec185c27deb53f80f6f5a40d9a8f95f1; working 2.4p backup 5fde77e394572ebcf420f8941575f6c4. Old producer 9181ef744955190d04728cf4ef7965c5 and USB kernel c1cad400372e26eca729e4b9bc47a237 remained unchanged. Boot uptime recorded 125.67 seconds, all patch/streaming/probe mappings absent, /usr mounted read-only. Reboot job reports a missing terminal completion marker because reboot intentionally disconnected before that marker; CPU shutdown output, new uptime, post-boot hashes and process maps independently confirm the reboot.

No eligible whitelisted DMM units were active in service mode. This does not establish whether they will appear during USB Streaming. Next action is fresh bounded monitoring plus an actual raw packet capture and restart test.

## MENU recovery and required scratch-space check

After deployment the user reported automatic MENU restarts. Five verified old /tmp/opengate_trace logs (1124649B) were archived and cleared. /tmp then reported 7600 KiB available and a 4096-byte write/readback succeeded. User retested MENU/VIDEO successfully with revision 2.7 still installed. Cause remains unproven. Before a future deployment, inspect /tmp as well as /usr and /log and require a successful small write/readback; moving staging to /log does not resolve full application scratch storage. The packaged helper currently checks only /usr and /log; the additional /tmp check is an explicit operator requirement. Preserve system-managed files, fonts and tools.

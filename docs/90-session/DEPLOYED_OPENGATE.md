# Live Hardware Deployment: Open Gate 3:2 Video Unlock (Sony ZV-E10)

> **HARDWARE DEPLOYMENT RECORD — 2026-10-03**
> Target Device: Sony ZV-E10 (Serial `07388356`, Firmware `2.02`, Product code `0032852840`)
> Environment: Linux 3.0.27_nl-rt106+ #1 SMP PREEMPT RT armv7l

---

## 1. Deployment Summary

The Open Gate 3:2 Video Unlock patch has been compiled and deployed directly to the camera's persistent `/setting` partition (`/dev/nflasha2`).

### Verified Files on Device:
```
-rwxr-xr-x    1 0        0             9024 Jan  1 00:04 /setting/opengate.so
-rwxr-xr-x    1 0        0              375 Jan  1 00:05 /setting/opengate.conf
-rw-r--r--    1 0        0                3 Jan  1 00:05 /setting/mode/dmode
-rw-r--r--    1 0        0               21 Jan  1 00:05 /setting/mode/preload
```

### Verified Checksums & Content:
- `/setting/opengate.so`: MD5 `da99a9e29bce2d644ed5e9e07a23eadd` (Verified identical to `out/opengate.so`)
- `/setting/mode/dmode`: `3p` (Developer boot mode with LD_PRELOAD active)
- `/setting/mode/preload`: `/setting/opengate.so`
- `/setting/opengate.conf`: `enable=1`, `aspect=2` (DefStruct::MOVIE_ASPECT_3_2)

---

## 2. Boot Chain Execution Flow

1. On camera power-on, the bootloader starts `/sbin/init`.
2. `/usr/bin/bootin.elf` reads `/setting/mode/dmode` (containing `3p`).
3. Because `dmode` contains `p`, `bootin.elf` reads `/setting/mode/preload`.
4. `bootin.elf` sets `LD_PRELOAD=/setting/opengate.so` in the environment of `/usr/bin/im.elf`.
5. The dynamic linker loads `opengate.so` into `im.elf`.
6. `opengate_init()` executes before `im.elf` starts:
   - Locates `libObj.so` via `/proc/self/maps`.
   - Locates `InfraMovieEncoderSeqSetAspect` at offset `0x2d229c`.
   - Patches `movs r3, #1` (`0x2301`) to `movs r3, #2` (`0x2302`).
   - Flushes ARM CPU cache.
   - Logs status to `/setting/opengate.log` and `/dev/kmsg`.
7. When MOVIE recording begins, `av-cam.bin` receives aspect ratio `2` and dispatches to `0x636cdc00`, reading the **full $6000 \times 4000$ active 3:2 sensor area**.

---

## 3. How to Check Live Status After Reboot

In camera shell:
```sh
cat /setting/opengate.log
```

Expected log:
```
[opengate] Hook initializing in PID ...
[opengate] Found libObj.so at 0x...
[opengate] Target instruction at 0x...: current=0x2301
==========================================================
[opengate] SUCCESS: 3:2 Open Gate Video Unlocked!
[opengate]   Patched: 0x2301 -> 0x2302 (aspect mode 2)
[opengate]   Sensor readout will engage Full 6000x4000 Area
==========================================================
```

---

## 4. Revert / Uninstall Procedure

To completely remove the hook and revert to 100% factory behavior:
```sh
echo "3" > /setting/mode/dmode
rm -f /setting/mode/preload
rm -f /setting/opengate.so /setting/opengate.conf /setting/opengate.log
sync
```
Reboot camera.

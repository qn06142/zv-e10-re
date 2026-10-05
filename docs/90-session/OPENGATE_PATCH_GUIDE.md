# Sony ZV-E10 Open Gate (3:2 Video Unlock) Patch Guide

This document details the complete, tested, and staged **Open Gate 3:2 Video Unlock Patch** for the Sony ZV-E10.

---

## 1. How the Patch Works

### The Mechanism
1. **Physical Sensor Readout:** The Sony ZV-E10 APS-C sensor has a native active area of **$6000 \times 4000$ (3:2)**.
2. **Firmware Built-in 3:2 Support:** In the BIONZ X RTOS camera module (`av-cam.bin`), function `ModuleCalcAspectImageArea` (`0x636cde88`) branches on aspect ratio enum `= 2` (`DefStruct::MOVIE_ASPECT_3_2`) to jump directly to `0x636cdc00`, which activates **un-windowed, uncropped full-sensor readout ($6000 \times 4000$)**.
3. **The Artificial Lockout:** In `libObj.so`, method `InfraMovieEncoderSeqSetAspect` (`0x2d229c`) hardcodes `movs r3, #1` (`0x2301`), forcing 16:9 mode and discarding 624 vertical sensor lines (15.6% of the frame).
4. **The In-Memory Fix (`opengate.so`):**
   * Loaded into `/usr/bin/im.elf` on camera boot via Sony's native developer preload hook (`/setting/mode/preload`).
   * Locates `libObj.so` in `/proc/self/maps`.
   * Unlocks memory permissions via `mprotect(..., PROT_READ | PROT_WRITE | PROT_EXEC)`.
   * Patches `0x2d229c` from `movs r3, #1` (`0x2301`) to `movs r3, #2` (`0x2302`).
   * Flushes instruction cache via ARM `cacheflush` syscall (`0xf0002`).
   * Restores memory permissions to `PROT_READ | PROT_EXEC`.
   * When video recording begins, the encoder dispatches aspect mode 2 to `av-cam.bin`, engaging **full 3:2 optical sensor readout**.

---

## 2. Safety & Zero Flash Risk

* **Zero physical modifications to `/usr` or flash:** `/usr` is LZP compressed read-only and remains 100% untouched.
* **Persistent via `/setting`:** The payload lives on the standard FAT16 partition `/dev/nflasha2` (`/setting`).
* **100% Reversible:** Removing `/setting/mode/preload` or setting `/setting/mode/dmode` back to `3` instantly returns the camera to 100% stock factory behavior.

---

## 3. Staged Files & Artifacts

All files are staged and ready in [`dumps/staged/opengate/`](file:///D:/02_Development_And_Projects/pmca-re/dumps/staged/opengate):

| File | Purpose | Size / MD5 |
| :--- | :--- | :--- |
| `opengate.so` | Compiled ARMv7-A shared library hook | 9,024 bytes<br>`da99a9e29bce2d644ed5e9e07a23eadd` |
| `opengate.conf` | Configuration file (aspect mode selector) | 338 bytes |
| `install_opengate.sh` | Automated deployment script for camera shell | 1,489 bytes |
| `uninstall_opengate.sh` | Safe uninstaller / revert script | 794 bytes |

Source and build files:
- Source: [`research/device/opengate_hook.c`](file:///D:/02_Development_And_Projects/pmca-re/research/device/opengate_hook.c)
- Build script: [`scripts/build_opengate.py`](file:///D:/02_Development_And_Projects/pmca-re/scripts/build_opengate.py)
- Unit tests: [`tests/test_opengate_patch.py`](file:///D:/02_Development_And_Projects/pmca-re/tests/test_opengate_patch.py) (4 passed)

---

## 4. Installation Instructions

### Method A: Via Camera Service Shell (Recommended)

1. Copy `dumps/staged/opengate/` to the camera (e.g. onto SD card or via toolbelt transfer).
2. In the camera's ash shell, run:
   ```sh
   # 1. Copy binary and config to /setting
   cp /path/to/opengate.so /setting/opengate.so
   cp /path/to/opengate.conf /setting/opengate.conf
   chmod 755 /setting/opengate.so

   # 2. Configure developer boot mode (dmode 3p + preload hook)
   mkdir -p /setting/mode
   echo "/setting/opengate.so" > /setting/mode/preload
   echo "3p" > /setting/mode/dmode

   # 3. Flush writes to eMMC
   sync
   ```
   *(Or simply run `sh install_opengate.sh`)*

3. Power-cycle / reboot the camera.

---

## 5. Verification on Camera

After the camera boots:
1. Inspect the persistent log:
   ```sh
   cat /setting/opengate.log
   ```
   Expected output:
   ```
   [opengate] Hook initializing in PID 1234...
   [opengate] Found libObj.so at 0x40120000 (size 0x01360000)
   [opengate] Target instruction at 0x403f229c (rel +0x2d229c): current=0x2301
   ==========================================================
   [opengate] SUCCESS: 3:2 Open Gate Video Unlocked!
   [opengate]   Patched: 0x2301 -> 0x2302 (aspect mode 2)
   [opengate]   Sensor readout will engage Full 6000x4000 Area
   ==========================================================
   ```

2. Check kernel log (`dmesg`):
   The log messages are mirrored to `/dev/kmsg` and can be inspected via `dmesg | grep opengate`.

---

## 6. Configurable Modes (`/setting/opengate.conf`)

You can change aspect modes on the fly by editing `/setting/opengate.conf` without rebuilding:

```ini
# /setting/opengate.conf
enable=1

# Aspect mode:
# 0 = 4:3 (Anamorphic Video)
# 1 = 16:9 (Stock Sony Video)
# 2 = 3:2 (Open Gate Full Sensor Readout - Default)
# 3 = 1:1 (Square Video)
# 4 = 17:9 (DCI Cinema)
aspect=2
```

---

## 7. How to Revert (Uninstall)

To restore 100% factory behavior:
```sh
echo "3" > /setting/mode/dmode
rm -f /setting/mode/preload
rm -f /setting/opengate.so /setting/opengate.conf /setting/opengate.log
sync
```
*(Or run `sh uninstall_opengate.sh`)*

On the next reboot, `im.elf` will boot without preloading and operate in standard 16:9 factory mode.

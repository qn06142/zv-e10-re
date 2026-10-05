# Buried Treasure — Hidden Capabilities in the ZV-E10 Firmware

> **SESSION RECORD — 2026-10-03.** Everything here was derived from offline
> analysis of `dumps/`. Nothing has been pushed to the camera in this session.
> Cross-references to living docs are noted inline.

---

## 1. Why Writes to `/usr` Vanish After Reboot

### 1.1 The LZP Compressed Block Device

`/usr` is served from `/dev/dnflasha15` (Major 252, Minor 143), **not** from
`/dev/nflasha15`. The `dn` prefix means "decompressed-nflash": Sony's eMMC
driver (`dumps/initrd_extracted/kmod/emmc.ko`) contains a hardware LZP
(Lempel–Ziv Partition) decompressor that decompresses the physical flash block
into RAM on read. The write path is a stub:

```c
// uz_emmc_do_compress() — offset 0x5cf8 in emmc.ko
mov r0, #0    // return 0 — no-op
ldm sp, {fp, sp, pc}
```

Error strings confirm this:

```
Error : Unsupported write on compressed partition...[%d]
Error : Can not erase the decompressed partition %s
```

`mount -o remount,rw /usr` only dirties the **RAM page cache**. On reboot,
`init` re-reads the factory LZP image from physical eMMC and discards all
in-memory changes.

### 1.2 The ext2 Dirty-Flag Rollback

If `mount -o remount,rw` somehow lands a write (e.g. on a non-LZP partition),
init's `mount_partition()` (Thumb at `0x9244` in `dumps/staged/audit/init`)
checks the superblock's dirty flag (`state 0x0002`). On a dirty mount it runs:

```c
umount(mp);
"/sbin/dosfsck -Y %s"   // or e2fsck -y for ext2
```

This rolls back uncommitted blocks. The safe write always requires
`sync; mount -o remount,ro` before power-cycle.

### 1.3 What Actually Persists

Verified from `docs/07-modification.md`:

| path | survives reboot |
|---|---|
| `/usr/bin` | **yes** |
| `/usr/share` (non-app) | **yes** |
| `/usr/share/app` | **NO — wiped** |
| `/setting/**` | **yes** (`/dev/nflasha2`, plain VFAT) |
| `/system/**` | yes |

`/usr/share/app` is the directory the firmware **re-populates** from the LZP
image on every boot. It is not a wipe — it is simply overwritten by the
decompressor's fresh load.

---

## 2. The Official Developer Boot Hook System

Sony shipped a complete developer mode toolkit on every retail ZV-E10.

### 2.1 `change_mode.sh` — Boot Mode Switcher

`/usr/bin/change_mode.sh` writes to `/setting/mode/dmode` and
`/setting/mode/preload`, which `bootin.elf` reads before launching `im.elf`.

| Param | dmode | Effect |
|---|---|---|
| `0` | `0` | Halt after kernel boot |
| `1` | `1` | Halt after global infra |
| `2` | `2` | Halt after RTOS (LiRo) boot |
| `3` | `3` | **Normal** — full appFw boot |
| `7` | `3L` | Boot with **LeakTracer** (`LD_PRELOAD=/usr/tool/LeakTracer.so`) |
| `8` | `3w` | Boot with sslibc write-free check |
| `9` | `3k` | Boot with KMC ICE |
| `a` | `3g` | Boot with **target GDB** |
| `b` | `3s` | Boot with **gdbserver** |
| `d` | `3d` | Boot with **DUMA** memory debugger |
| `e` | `3e` | Boot with **Electric Fence** |
| `f` | `3p` | Boot with **jemalloc** profiler |
| `p <path>` | `3p` | Boot with **any custom `.so`** via LD_PRELOAD |

### 2.2 The `preload` Hook — Persistent LD_PRELOAD

`bootin.elf` at `0x9996`–`0x9a18` (Thumb):

```c
// Pseudocode
if (flags & 0x40) {   // set when dmode contains 'p' or 'L'
    strncpy(buf, dmode_argv, 512);
    fd = open("/setting/mode/preload", O_RDONLY);
    read(fd, buf+11, 498);      // appends after "LD_PRELOAD="
    close(fd);
    putenv(buf);                // exports to im.elf's environment
}
```

**Implication:** Write any `.so` path to `/setting/mode/preload` and set
`dmode` = `3p` to permanently inject a shared library into `im.elf` on every
boot, with **zero firmware flash risk**.

### 2.3 `set_oreore_env` — Custom Environment Variables at Boot

`init` calls `set_oreore_env()` when `/setting/mode/dmode` contains `'e'` or
`'E'`. It opens `/setting/env.txt` and calls `putenv()` for each `KEY=VALUE`
line. All services (`im.elf`, `bootin.elf`, `sen.elf`) inherit these.

### 2.4 Boot Mode Sequence (`/setting/mode/dmode` values)

Decoded from `check_mode_file()` in `init` (`0x93b0`):

| char in dmode | Flag set | Meaning |
|---|---|---|
| `0` | `is_qemu` | QEMU emulation mode |
| `k`/`K` | `is_kmode` | Kernel-only mode |
| `g`/`G` | `is_gdb` | GDB attached |
| `d`/`D` | `is_duma` | DUMA allocator |
| `e`/`E` | `is_oreore_env` | Load `/setting/env.txt` into environ |

---

## 3. Persistent Theming via `/setting`

Full flow for a zero-flash-risk retheme:

1. Place patched assets in `/setting/theme/`:
   - `color_cmn.uxc` — 28-entry palette (see §4)
   - `Sony_DI_Icons.ttf` — 1732-glyph icon font
   - `fontlist.dat` — redirect font paths to `/setting/theme/`
   - `logo.bin` — plain JFIF JPEG startup splash
   - `style_cmn.uxc` — font sizes, padding, margins

2. Compile `retheme.so` (hook `open()`/`fopen()` to redirect
   `/usr/share/app/<name>` → `/setting/theme/<name>`).

3. Enable:
   ```sh
   echo "3p" > /setting/mode/dmode
   echo "/setting/theme/retheme.so" > /setting/mode/preload
   ```

4. Reboot. Theme persists permanently. Revert by deleting the preload file.

---

## 4. UXC Color Palette (`color_cmn.uxc`)

File: `/usr/share/app/color_cmn.uxc` (312 bytes)

Format: 28 records × 8 bytes at offset `0x58`:

```
u16 id  |  u16 0x3a09  |  u8 R  |  u8 G  |  u8 B  |  u8 A
```

Key IDs confirmed on hardware:

| ID | Stock | Effect |
|---|---|---|
| `0x400c` | `333333 @ 0x80` | Framing guide / grid lines (50% alpha grey) |
| `0x4009` | `0000dd @ 0xff` | Primary blue accent |

Proved on live camera: changing `0x400c` → `ff00ff@80` turned framing guides
magenta (the control proving the mechanism; magenta appears nowhere in Sony's
stock palette). Full colour map in `docs/90-session/RESULT_PALETTE.md`.

The same `remount-rw → write → verify → remount-ro` workflow applies to ALL
290+ `view*.uxc` screen files and `style_cmn.uxc`.

---

## 5. The NVRAM/Backup Tool — `bk.elf`

`/usr/bin/bk.elf` is Sony's official CLI for reading and writing camera
settings from `/setting/Backup.bin` and `/setting/Backup.bak`.

```sh
bk r <BackupID>          # Read item (hex ID) → prints current value
bk w <BackupID> <hex>    # Write item
bk list                  # Dump ALL backup items with IDs, sizes, values
bk sync                  # Flush to flash
bk rst_r <BackupID>      # Read reset-default value
```

`libbackup.so` exports: `Backup_read`, `Backup_write`, `Backup_sync_all`,
`Backup_read_rst_attr`, `Backup_write_setting_attr`, `Backup_get_datasize`.

> **Next action:** Run `bk list` on a live camera to map backup IDs to camera
> settings (record limit, region lock, model flags, etc.).

---

## 6. Region / Model / Version Spoofer — `up.sh` + `ud_datcnv.elf`

`/usr/bin/up.sh` wraps `ud_datcnv.elf` to modify identity fields stored on
`/dev/nflasha1`.

| Command | Target | Device |
|---|---|---|
| `up.sh modreg <8-char>` | Region code → `dat3` | `/dev/nflasha1` |
| `up.sh modmod <8-char>` | Model code → `dat2` | `/dev/nflasha1` |
| `up.sh modver <4-char>` | FW version → `dat4` | `/setting/updater/dat4` |

**Version-skip mode** (bypass updater version/model checks):

```sh
touch /setting/updater/mode /setting/updater/mode6
# Forces the updater to flash any image regardless of version mismatch
```

**Service mode** (USB shell accessible without app booting):

```sh
touch /setting/updater/mode /setting/updater/mode3
```

---

## 7. Direct Hardware Diagnostics — `adjstctl.elf`

`/usr/bin/adjstctl.elf` routes messages to RTOS endpoints via `libtestcmd.so`.
Selected commands extracted from `.rodata`:

| Command string | What it does |
|---|---|
| `SET_SDI_RAW_MODE` | Enables raw sensor output routing to SDI path |
| `S_IMAGER_CURTAINMODE` | Toggles mechanical vs. electronic front-curtain shutter |
| `S_LC_SET_ALENS_PINT_ADJ` | Lens AF micro-adjustment calibration write |
| `S_LC_GET_ALENS_PINT_ADJ` | Read current AF fine-tune offset |
| `CODEC_ADJ_MODE_ON/OFF` | Hardware encoder adjustment mode |
| `CTP_SENSOR_TEST` | Touch digitizer raw inspection |
| `JIRITSU_TEST_UI_VIEW` | Triggers Jiritsu factory UI test screen |
| `A_EXECUTE_AUTOWHITESHD` | Auto white-shading calibration |
| `A_EXECUTE_AUTOBLACKBALLANCE` | Auto black balance execution |
| `MPR_CMD_GSENSOR_ADJUST_START/STOP` | IMU/gyro calibration |
| `SET_FACTORY_MODE` | Full factory mode enablement |

Usage (on camera shell):

```sh
adjstctl.elf [options] [adjust_block] [adjust_code] [size]:[data]
```

---

## 8. Automated Scenario Engine — `scenario.elf`

`/usr/bin/scenario.elf` loads plugins from `/usr/scenario/*.so` and calls
their `scenario_run()` export.

Discovered scenario plugins:

| File | Purpose |
|---|---|
| `CAMERA_SCN_EXTERNAL_RAW_RECORD.so` | External RAW output: `cam_scn_raw_output_on()`, `cam_scn_raw_device_acquire()` |
| `CAMERA_SCN_MOVIE_REC_START.so` | Programmatic movie recording trigger |
| `CAMERA_SCN_EE_START_STOP.so` | Electronic exposure (EE) mode control |
| `CAMERA_SCN_SET_ZOOM_DRV.so` | Direct power-zoom actuator |
| `CAMERA_SCN_VIDEOLIGHT_SW.so` | Video light control |
| `AVBB_SCN_START_HDMI_INPUT.so` | HDMI input ingest (proves hardware HDMI-in capability) |
| `AVBB_SCN_START_PANELEVF.so` | External EVF panel start sequence |
| `MPR_SCN_EXEC_FACTORY_MODE.so` | Full factory test mode activation |
| `MPR_SCN_FORMAT.so` | Media format procedure |
| `MPR_SCN_INSTALL_MAP_DEMOMOVIE.so` | Install demo movie to internal storage |
| `MPR_SCN_SET_FACTORY_MODE.so` | Write factory mode flag |

Usage:

```sh
scenario.elf --ifile payload.txt [scenario_name] [size:data ...]
# Example: loads /usr/scenario/CAMERA_SCN_MOVIE_REC_START.so
```

---

## 9. GPIO Hardware Control — `gpioctrl.elf`

Full SoC GPIO register access:

```sh
gpioctrl dump               # Dump all GPIO register states
gpioctrl read <PIN_NAME>    # Read a named pin
gpioctrl write <PIN> 0|1    # Drive pin HIGH or LOW
gpioctrl intread <PIN>      # Read interrupt registers
gpioctrl intwrite <PIN>     # Write interrupt config
gpioctrl mselwrite <BLOCK> 1.8|3.3   # Set bus voltage level
```

Known pin names: `GPIO_S_0` through `GPIO_S_16`, `GPIO_SB_0` through
`GPIO_SB_6`, and XCS aliases (`GPIO_SB_0_XCS1`, etc.).

---

## 10. Kernel Command Line — `/setting/KEMCO.TXT`

Stored on `/setting` (FAT16, cluster 168), read by the bootloader. Contains
the raw Linux kernel cmdline. Key fields:

| Key | Value | Meaning |
|---|---|---|
| `console=` | `ttynull` | Serial disabled — change to `ttyAM0` for UART console |
| `tmonitor.addr` | `0xF00000` | RTOS task monitor ring buffer PA |
| `tmonitor.size` | `0x8000` | 32 KB monitor buffer |
| `klog.addr` | `0x035A5000` | Kernel dmesg buffer PA |
| `alog.addr` | `0x03524FC0` | Application log buffer PA |
| `alog.size` | `0x60040` | ~384 KB app log |
| `wdt.timeout` | `500` | Watchdog 500 ms |
| `exception.reboot` | `1` | Auto-reboot on kernel panic |
| `mem=` | `1G@0` + `256M@0x80000000` | 1.25 GB total RAM |
| `memrsv=680M@0x15800000:uc` | — | 680 MB uncached for BIONZ DSP |
| `pm.resume` | `0x20021054` | Warm-boot resume vector |

> **To get a serial console**: Edit KEMCO.TXT, change `console=ttynull` to
> `console=ttyAM0,115200n8`. This routes all kernel log output to the hardware
> UART test pads. The config persists on `/setting`.

---

## 11. Hidden Network & Security Tools

Pre-installed in `/usr/bin`, no sideloading needed:

| Binary | Purpose |
|---|---|
| `wl` (1.1 MB) | Broadcom Wi-Fi engineering CLI: monitor mode, packet injection, TX power, raw 802.11 |
| `iperf` (62 KB) | Network throughput measurement |
| `openssl` (738 KB) | Full OpenSSL CLI — encrypt, decrypt, generate keys, TLS |
| `wpa_supplicant` (766 KB) | WPA supplicant for connecting to external APs |
| `uuidgen` | UUID generation utility |

Pre-installed libraries (linkable in any sidecar):

| Library | Provides |
|---|---|
| `libpcap.so` | Raw packet capture |
| `libssh2.so` | SSH2 client protocol |
| `libssl.so` / `libcrypto.so` | OpenSSL 3.0 |
| `libcurl.so` | HTTP/HTTPS client |
| `libopus.so` | Opus audio codec |
| `libjsoncpp.so` | JSON parsing |
| `libqrencode.so` | QR code generation |
| `libncurses.so` | Terminal UI |

---

## 12. Codec / Format Capabilities Hidden in `libmpr.so`

The full codec profile table embedded in `libmpr.so` reveals that the
**firmware supports** (not necessarily the UI exposes) these formats:

### Video Codecs

| Codec | Resolutions | Notes |
|---|---|---|
| AVC (H.264) | up to **7680×4320@L6** | 8K AVC |
| HEVC (H.265) | **1080p, 4K, 8K** MP/HP@L41+ | Including Tier High |
| XAVC-S (AVC) | All retail modes | Exposed in UI |
| XAVC-S HEVC | 4K HEVC variant | `REC_CODEC_TYPE_XAVCSHEVC` |
| AVCHD | HD modes | Legacy |
| DNxHD | 145/220 8bit, 220x 422 10bit | Professional NLE format |
| **ProRes** | ProRes4444, ProRes422HD, ProRes422, ProRes422LT | Apple ProRes! |
| XAVC Class100/300 | High-end XAVC | Broadcast |
| DVCAM | SD legacy | |
| MPEG-2 MP4 | SD/HD | |
| MXF (AVC Intra, HD422, HD420, DNxHD, ProRes) | Broadcast MXF | |

### Colour Science Profiles (all defined in `libmpr.so`)

```
s-log        s-log2       s-log3       s-log3-cine
s-gamut      s-gamut3     s-gamut3-cine
rec709       rec709-800   rec709-xvycc
rec2020      rec2020ncl   rec2100-hlg     (HDR HLG!)
s-cinetone
nxcam-std    nxcam-still  nxcam-cine1  nxcam-cine2
scene-linear
hg3250g36    hg4600g30    hg8009g40    (Hypergamma variants)
sd-std-x35   smpte240m
```

### Bitrate Modes (Quality enum, `libmpr.so`)

Selected higher-end modes discovered beyond what ZV-E10 normally exposes in UI:

| Quality | Bitrate |
|---|---|
| Q16 | P240MBPS |
| Q17 | P300MBPS |
| Q18 | **P600MBPS** |
| Q20 | P500MBPS |
| Q25 | P440MBPS |
| Q39 | P260MBPS |
| Q40 | P400MBPS |
| Q41 | **P520MBPS** |

### Streaming Quality Modes

| Quality | Mode |
|---|---|
| Q27 | Proxy 9 Mbps |
| Q28 | Proxy / LiveStreaming 3 Mbps |
| Q29 | LiveStreaming 6 Mbps |
| Q30 | LiveStreaming 2 Mbps |
| Q31 | LiveStreaming 1 Mbps |

### Resolution Table

All confirmed in `libmpr.so` string table:
`480×270`, `640×360`, `640×480`, `720×480`, `720×512`, `720×576`, `720×608`,
`800×480`, `1280×720`, `1440×1080`, `1920×1080`, `3840×2160`, `4096×2160`,
**`7680×4320`** (8K).

---

## 13. USB Streaming Architecture — `libInfraStreamingUsb.so`

UVC-class USB webcam streaming is implemented as a full C++ state machine:

```
StateMachine:
  Idle  →  Ready  →  Starting  →  Started
```

States handle: `HostStartVideoEvt`, `HostStopVideoEvt`, `ProbeReqVideoEvt`,
`CommitReqVideoEvt`, `VideoStartBulkEvt`, plus audio equivalents.

Key classes:
- `VideoEsManager` — `video_stream_prepare()`, `video_stream_start()`,
  `video_stream_stop()`, `alloc_video_memory()`, `set_path_sync()`
- `AudioEsManager` — `audio_stream_start(j)`, `audio_stream_stop()`

Kernel modules loaded on demand:
```
/usr/kmod/usbg_video.ko   — UVC video gadget
/usr/kmod/usbg_audio.ko   — UAC audio gadget
```

> This is the implementation behind the ZV-E10's "PC Remote" / streaming webcam
> mode. The state machine exposes hooks for intercepting and redirecting the
> video stream source.

---

## 14. The Jiritsu Factory Test System — `libJiritsu.so`

"Jiritsu" (自立 — "self-sustaining / autonomous") is Sony's internal factory
automation framework. The `libJiritsu.so` library registers a full lifecycle
daemon (`jiritsu_init`, `jiritsu_sus`, `jiritsu_res`, `jiritsu_act`,
`jiritsu_inact`, `jiritsu_exit`) and runs as a background RTOS thread.

Factory commands it accepts (`adjstctl.elf` routes):

| Command | Function |
|---|---|
| `JIRITSU_MODE` | Enter Jiritsu automation mode |
| `JIRITSU_MOUNT` | Mount media for factory write |
| `JIRITSU_FORMAT` | Trigger media format |
| `JIRITSU_START` | Start automated test sequence |
| `JIRITSU_FIRMUP` | Trigger firmware update |
| `JIRITSU_SET_FILE` / `GET_FILE` | Transfer files in/out |
| `JIRITSU_COMPARE_MEDIA` | Media validation check |
| `JIRITSU_FACTORY` | Full factory reset/calibration |
| `JIRITSU_GET_FILELIST` / `GET_FILE_HASH` | File audit |
| `JIRITSU_TEST_UI_VIEW` | Show factory test screen on LCD |
| `JIRITSU_PARSER_CONTROL` | Automation script parser |
| `A_EXECUTE_AUTOWHITESHD` | Auto white-shading run |
| `A_EXECUTE_AUTOFLARE` | Auto flare compensation |
| `A_EXECUTE_AUTOBLACKBALLANCE` | Auto black balance |
| `A_EXECUTE_AUTOBLACKSHD` | Auto black-shading |

---

## 15. IMDB Module Registry — Complete List

`libIMDB.so` is the Image (Module) Database — it tracks every loadable
component, its `.so` path, and lifecycle symbol names. 160+ modules registered.
Notable ones not previously documented:

| Library | Registers |
|---|---|
| `libInfraHdmiInput.so` | `HDMI_Input_init/exit/sus/res` — HDMI **input** ingestion |
| `libInfraRtmpLiveStreaming.so` | RTMP live streaming |
| `libInfraOpusLiveStreaming.so` | Opus-encoded live streaming |
| `libInfraSavonaServer.so` | "Savona" — Sony's internal streaming server protocol |
| `libInfraMDnsControl.so` | mDNS/Bonjour service discovery |
| `libInfraEyeFiControl.so` | Eye-Fi wireless SD card support |
| `libInfraNfc.so` | NFC (! — ZV-E10 has no NFC hardware but the driver is there) |
| `libInfraLanc.so` | **LANC** control protocol (camera remote control bus) |
| `libInfraCec.so` | HDMI CEC control |
| `libInfraInterchipDatatrans.so` | Inter-chip data transfer bus |
| `libInfraKikiLogGenerator.so` | "Kiki" — Sony cloud log/telemetry sender |
| `libInfraTcsync.so` | Timecode sync |
| `libgps.so` / `libgps_rsrc.so` | GPS (no GPS hardware, but full stack) |
| `libcompass.so` | Digital compass |
| `libgeo.so` | Geographic/location services |
| `libIMSample.so` | Sample module template (for Sony devs) |
| `libIMStress.so` / `libIMStress2.so` | Stress-testing harness |
| `/usr/local/lib/libVssApp.so` | VSS (Video Surveillance System?) application |

---

## 16. View Engine Architecture — `viewUnified*.so`

The camera UI is split across 7 shared libraries (409 total view factories):

| Library | Views | Scope |
|---|---|---|
| `viewUnified2.so` (14.3 MB) | 224 | Core shooting, menus, playback |
| `viewUnified4.so` (3.3 MB) | 83 | Network, connectivity, advanced settings |
| `viewUnified3.so` (941 KB) | 35 | FTP, calibration, advanced playback |
| `viewUnified8.so` (283 KB) | 13 | Maintenance (cleaning, repair, recovery) |
| `viewUnified5.so` (749 KB) | 22 | Delete, protect, DPOF, pairing |
| `viewUnified6.so` (589 KB) | 21 | Format, USB modes, settings reset |
| `viewUnified7.so` (580 KB) | 11 | AF, WB, focus, exposure, zoom |

`CmnViewFeatureManager` gates capability exposure at runtime:

```cpp
isAVCHDFormatSupported()
isAVCHDFormatNotSupported()
isPhaseDetectSensorAvailable()
isGPMAPhaseDetectSensorAvailable()
isFFLensNoLimitSupported()     // focus range limiter bypass
isPcRemoteWifiSupported()
isWiFiMultiSupported()
isWiFiDiademSupported()        // "Diadem" = multi-device WiFi protocol
isTouchPanelPadSupported()
isShutterSpeedBulbAvailable()
isZebraToggleSupported()
```

These are boolean reads from `libSysDef.so` property tables. Patching the
backing property values (via `Backup.bin` or a preload hook) can enable gated
features.

---

## 17. The `IroiroCon` Control — Hidden Manual Iris Dial

`viewIroiroCon.uxc` + `CmnViewIroiroConDataMgr` class ("iroiro" = Japanese
for "various/miscellaneous"):

This is a **manual iris control overlay** with:
- `getCategoryCurrentEPNS_19IROIRO_CON_CATEGORYE` — enum-based category
  selector
- `setCurrentRangeIrisValueEii` / `getCurrentRangeIrisValueEPiS0_` — direct
  iris position range set/get
- `getValueFromFNumberEi` / `setCameraRangeFNumberEiii` — F-number
  ↔ encoder-step bidirectional conversion
- `getStepNumFNumberEv` — total F-stop step count
- `setManualEv` / `setAutoEv` — toggle between full auto and manual iris

This is the mechanism behind third-party lens / manual-iris support. It's
accessible from the software level without touching the physical lens mount.

---

## 18. Summary: Priority Investigation Targets

| Target | Risk | Potential |
|---|---|---|
| `bk list` on live camera | **None** (read-only) | Full NVRAM map — region/limit flags |
| `change_mode.sh p /setting/retheme.so` | **Low** (reversible) | Persistent GUI theming |
| `KEMCO.TXT` `console=` edit | **Low** | Serial console on test pads |
| `up.sh modreg` | **Medium** | Region unlock, NTSC↔PAL |
| `adjstctl.elf SET_SDI_RAW_MODE` | **Medium** | External raw output |
| `scenario.elf CAMERA_SCN_EXTERNAL_RAW_RECORD` | **Medium** | Raw frame routing |
| Patching `CmnViewFeatureManager` returns | **High** | Feature gate unlocks |
| `libInfraRtmpLiveStreaming.so` activation | **Low** (already present) | Native RTMP streaming |
| Editing HEVC/ProRes quality enum in Backup | **Medium** | Unlock ProRes/600Mbps |

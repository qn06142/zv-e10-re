# 02 — The service-mode environment: what the shell can reach

Everything reachable from the authenticated root shell, as measured. Passes are
scripted in `research/device/audit_surface.py`; raw output is filed under
`%TEMP%\opencode\app_res\audit\`.

**The service filesystem carries the camera's rendering engine, its view layer and
its 81 MB of resources, but not the application that uses them.** `camuser.elf`,
`gui.so`, `appFw.so`, `libNVM.so` and `libInfraWebApi.so` are named by the
manifest and simply not present. That single fact explains most of what looks
like a dead end below.

Related: [01-hardware.md](01-hardware.md) ·
[03-binaries.md](03-binaries.md) · [04-messaging.md](04-messaging.md) ·
[07-modification.md](07-modification.md) · [08-camera-interfaces.md](08-camera-interfaces.md)

- [Filesystems](#filesystems)
- [Persistence](#persistence)
- [The settings store](#the-settings-store-setting)
- [The firmware partition](#the-firmware-partition-system)
- [Processes, devices, modules](#processes-devices-modules)
- [Commands and plugins](#commands-and-plugins)
- [procfs](#procfs)
- [av-cam.bin is the live firmware image](#av-cambin-is-the-live-firmware-image)
- [The boot chain](#the-boot-chain)
- [Network surface: nothing is listening](#network-surface-nothing-is-listening)
- [im.elf loads the firmware](#imelf-loads-the-firmware)
- [Boot mode](#boot-mode)
- [Allocator and preload hooks](#allocator-and-preload-hooks)
- [camuser.elf and libObj.so](#camuserelf-and-libobjso)
- [The application is not deployed](#the-application-is-not-deployed)
- [Code execution: writable /usr/lib -> dlopen -> root](#code-execution-writable-usrlib--dlopen--root)
- [im.elf: the real target](#imelf-the-real-target)
- [Negative results](#negative-results-find-and-the-usrshareapp-source)
- [Gaps](#gaps)

## Filesystems

Eleven mounts. Only `/` is read-only, and it is a ramdisk, so that costs
nothing.

| mount | device | fs | access | holds |
|---|---|---|---|---|
| `/` | nflasha7 | ext2 | **ro** | `/bin` and `/initrd` are empty; `tmp_*` dirs |
| `/usr` | nflasha15 | ext2 | rw after remount | `bin`, `sbin`, `lib`, `share`, `kmod` |
| `/tmp` | nflasha10 | vfat | rw | also mounted at `/etc` — same device |
| `/etc` | nflasha10 | vfat | rw | `toprc`, `bbel`, `h.bin`, `big1.bin`, `mtab` |
| `/system` | nflasha3 | vfat | **rw** | **the firmware blobs** |
| `/setting` | nflasha2 | vfat | **rw** | **the settings store** |
| `/lens` | nflasha18 | vfat | rw | `VX9202*_lensfile.bin` and siblings |
| `/cert` | nflasha12 | vfat | rw | empty |
| `/log` | nflasha11 | vfat | rw | `AccessLog.dat`, `head.bin`, `allmaps.txt` |
| `/tmp/sd` | mmca1 | vfat | rw | the SD card, not mounted by the camera |
| `/proc` | proc | proc | rw | incl. `/proc/osal/` |

Mounting the card needs `mkdir -p /tmp/sd; mount /dev/mmca1 /tmp/sd`.
`/proc/partitions` calls it `mmca10p1`; `/dev/mmcca1` is a different controller
and does not work.

## Persistence

Marker files were planted in six directories and checked after `reboot -f`:

| path | survived |
|---|---|
| `/setting/_audit1` | yes |
| `/system/_audit2` | yes |
| `/usr/bin/_marker3` | yes |
| `/usr/share/_marker4` | yes |
| `/usr/share/pmbp/_marker2` | yes |
| `/usr/share/app/_marker1` | **no** |

**Only `/usr/share/app` is rewritten at boot.** Everything else is durable
writable storage, including the two partitions that matter most:

- `/setting` — the settings NVRAM
- `/system` — `av-cam.bin`, the main firmware, 17,289,388 bytes, **writable**

That is a much more direct route to the firmware than the updater, and it is the
answer to "where can a change actually stick".

## The settings store: /setting/

```
-rwxrwxrwx  1235740  Backup.bak        md5 e68da8c5…   mode 777
---x------  1235740  Backup.bin        md5 bdc524e5…   magic "BK4"
-rw-r--r--   78120  DmmConfig.bin
-rw-r--r--   51200  facedmy.bin        0x21 fill — a blank template
-rw-r--r--      120  filter.bin
-rw-r--r--   1925   kemco.txt
-rw-r--r--      656  ioctl.bin
-rw-r--r-- 4820992  psd.bin            magic "PF"
-rw-r--r--   3796   ulogio.bin
drwxr-xr-x          appfw_infra/       empty
drwxr-xr-x          mode/              empty
drwxr-xr-x          updater/           comp (0), dat4 (2)
drwxr-xr-x          gps/
```

`Backup.bin` is readable as root despite mode `---x------`, and its header is a
structured table:

```
0000  0000 e802 aaaa aaaa 0100 0000 424b 3400   ............BK4.
0010  3303 0000 9a81 0000 e01d 0300 3cbd 0f00
```

**`Backup.bak` differs from `Backup.bin`** (different md5, same size), so it is a
genuine earlier snapshot rather than a copy — useful as a known-good settings
restore point.

The API around it is attribute-based and exported, not reverse-engineered:
`libbackup.so` provides `Backup_read`, `Backup_write`, `Backup_get_attribute`,
`Backup_write_setting_attr`, `Backup_nread_multi`, `Backup_get_datasize`, and
`libIMDB.so` provides `IMDB_find_entry`, `IMDB_get_entries`,
`IMDB_find_target_bit` — an index for locating settings by id. The kernel side
is `/dev/backup` (251,208) with the `backup` module loaded.

## The firmware partition: /system/

```
17289388  av-cam.bin      <- the LIRO firmware, writable
 4117760  vmlinux.bin
 2183168  initrd.img
  172144  bonobo.bin
   61787  bt_firm.hcd
   65536  dfe_dat.bin
    7012  ldr_drv.bin
    6716  lif_app.bin
   10848  wole_app.bin
    1956  dfe_app.bin
        dir  lensbin_lensproperty/
        dir  sabin/
```

## Processes, devices, modules

### Processes — 263

```
139  liro-kliro_*        the LIRO RTOS (av-cam.bin), on this kernel
  1  uipc_dumper         kernel thread, 8K stack -> PID 93
  2  RMCMND-UIPC
  2  ULOGIO_LOGREC
  1  memmgr
  8  userspace: launch_shell.elf, bootin.elf, im.elf, bsa_server,
     dhcpd, wpa_supplicant, busybox x3, busybox-armel x5
```

## Devices — 346 entries in /dev

The ones worth naming:

```
crwxrwxrwx  251,208  backup      settings NVRAM
crw-------   10,191  bootimg     boot image (misc)
crwxrwxrwx  251,250  boss-t1     unknown
crwxrwxrwx  251,251  boss-t2
crwxrwxrwx  251,252  boss-t3
crwxrwxrwx  248, 28  ca
crwxrwxrwx  248, 27  cec         HDMI CEC
crw-rw-rw-    1,  5  zero
             plus /dev/uipc, /dev/console, and vcsa2..9, vcsa18, vcsa19
```

### Kernel modules — 47 loaded, 103 in `/usr/kmod`

The authoritative list and load order is under
[the 47 loaded modules](#the-47-loaded-modules-in-load-order).

`/usr/kmod/` holds 103 `.ko` files including `liro.ko`, `mcmn_drv.ko`,
`ms_drv.ko`, `accel.ko`, `mag.ko`. **`/sbin/insmod` and `/sbin/rmmod` are
present**, so modules can be loaded. Note `liro.ko` is in `/usr/kmod` yet the
running `liro` threads are not attributed to a loaded module — worth resolving.

## Commands and plugins

### Commands — 49 in `/usr/bin`, 7 in `/usr/sbin`, 17 in `/sbin`

Documented CLIs, read live:

```
scenario.elf  <options> [scenario_name] [size]:[data] ...
             scenario_name: "/usr/scenario/xxxx.so"
adjstctl.elf  <options> [adjust_block] [adjust_code] [size]:[data] ...
             --ver  --ifile  --ibfile  --obfile  --abid
sndcmd.elf / rcvcmd.elf / testcmd.elf   the same [size]:[data] convention
```

`adjstctl.elf` is a block-level adjust tool that reads and writes files
(`--ifile`/`--obfile`) and takes an id (`--abid`).

Also present and runnable: `iptables` + `iptables-multi/save/restore`,
`tcpdump`, `dhcpd`, `pump`, `iperf`, `openssl`, `wpa_supplicant`, `bsa_server`,
`soundstretch`, `sysctl`, `lsmod`, `ifconfig`, `route`, `pivot_root`, `init`,
plus scripts `compat_firmware.sh`, `doemparse.sh`, `swap_prepare.sh`,
`usb_insmod.sh`, `us_remove_modes.sh`, `change_mode.sh`, `startBTCore.sh`, and
`common.src`.

**Hazard found:** `sen.elf` with no arguments produces no prompt and appears to
block. Usage strings for the remaining binaries were not captured because of it;
they need one at a time with a timeout.

### Plugins

- `/usr/scenario/` — 35 `.so`, each exporting exactly `scenario_run`, dispatched
  by name through `scenario.elf`. Includes `MPR_SCN_SET_FACTORY_MODE`,
  `MPR_SCN_EXEC_FACTORY_MODE`, `MPR_SCN_FORMAT`, `MPR_SCN_EXEC_WIFI_TEST`,
  `CAMERA_SCN_MOVIE_REC_START`, and the `AVBB_SCN_START/STOP_*` family.
- **165 readable shared objects**, of which **123 are not `DT_NEEDED` by
  anything** — 35 are the scenario plugins, 40 are the `libInfra*`/`viewUnified*`
  block loaded by `libOnDemandLoader.so` (`OnDemandLoaderInitialize`), and 48 are
  distro runtime and updater tools. Each library attaches via its
  `Obj*_RegisterCommand`.

  > **Corrected figure.** An earlier count said *"391 shared objects catalogued,
  > 313 not DT_NEEDED"*. That total included two classes of entry which are not
  > shared objects at all: **231 carved fragments** recovered from a raw image
  > dump (`elf_XXXXXXXX.so`, `*_0xXXXXXXXX.bin`), which the camera does not have
  > as files, and **134 degenerate entries** carrying no imports, no `DT_NEEDED`
  > and no exports — `camuser.elf` among them, whose section table is unreadable.
  > Reproduce with `research/firmware/dep_graph.py`; the counts are pinned by
  > `tests/test_dep_graph.py`.

## procfs

`/proc/osal/` has `minfo` (read-only), `uipc` (read-write), `ulogio`
(read-write). `cat /proc/osal/uipc` dumps the bus: OSAL 4.2, 860 message queues,
198 semaphores, 16 messages, 1168 callbacks, pool sizes, and per-process
sections. `LMSGQ` and `LSEM` are empty, so the bus is idle in service mode. The
module also has `__k_uipc_proc_write` and `__k_cmd_debug`, so the node is
writable — the command grammar is unknown and has not been probed.

## av-cam.bin is the live firmware image

`/system/av-cam.bin` has md5 `cdcae9d4fdbf66a33704a4c7564e346d`, **byte-identical
to the `fw/av-cam.bin` this project has been analysing.** The file is on a
writable vfat partition and survives reboot, so it is both the source of the
running firmware and modifiable in place — no updater, no forged body, no
signature to defeat.

`/proc/cmdline` gives the boot chain:

```
cmpr.path=/system/sabin/ssboot.bin  cmpr.path2=/system/sabin/ssboot_any.bin
root=/dev/ram0  rootfstype=ext2  init=/sbin/init  initrd=0x700000,8M
mem=1G@0   memrsv=680M@0x15800000:uc   mem=256M@0x80000000@1
tmonitor.addr=0xF00000 tmonitor.size=0x8000 tmonitor.mask=0
klog.addr=0x035A5000 klog.size=0x20000   alog.addr=0x03524FC0 alog.size=0x60040
cxd900x0.bam=N   xrstreq=1   wdt.mode=1   ip=off
```

**`/` is a ramdisk** (`root=/dev/ram0`), which is why `/bin` and `/initrd` read as
empty and why `/` being read-only costs nothing. `/usr`, `/system`, `/setting`,
`/lens`, `/log`, `/cert` are flash partitions. The kernel also publishes log and
trace buffer addresses, and `tmonitor` is a 32 KB region at `0xF00000` currently
masked off.

`/system/sabin/` holds `ssboot.bin` (11,280), `ssboot_any.bin` (9,648),
`idt_cam.bin` (176,528), `sa_dfdet.bin` (156,292). And
`/system/lensbin_lensproperty/LensAberrationData.bin` is 161,766 bytes.

## The boot chain

`/sbin/init` is a 28,580-byte **ELF** (not a shell script), and its string table
is a complete, readable description of the boot. It loads modules in this order,
with parameters:

```
/kmod/devno.ko   /kmod/dmac.ko  pri_mode_ch_0_3=1 pri_mode_ch_4_7=0
/kmod/ldec.ko    /kmod/emmc.ko  tbl=0x80000000
/usr/kmod/osal_utm.ko  /usr/kmod/osal_uipc.ko  /usr/kmod/utimer.ko
/usr/kmod/backup.ko     Backup_load=0
/usr/kmod/osal_ulogio.ko  ulogio_initfile=/setting/ulogio.bin
/usr/kmod/input.ko  /usr/kmod/udate.ko  /usr/kmod/indctr.ko  /usr/kmod/i2c.ko
/usr/kmod/sircs.ko  /usr/kmod/stream.ko  /usr/kmod/stream2.ko
/usr/kmod/usb_portMonitor.ko  /usr/kmod/usbg_sen.ko  /usr/kmod/usb_extcmd.ko
/usr/kmod/kikilog.ko
/usr/kmod/dmm.ko    DmmConfig=/setting/DmmConfig.bin
/usr/kmod/upm.ko  /usr/kmod/nfc.ko
/usr/kmod/grm_ma.ko  /usr/kmod/grm_gles.ko      <- DMP SUGILITE graphics path
/usr/kmod/accel.ko  /usr/kmod/mag.ko  /usr/kmod/compass.ko
/usr/kmod/mcmn_drv.ko  /usr/kmod/ms_drv.ko  /usr/kmod/mmc_drv.ko
/usr/kmod/sata_drv.ko  /usr/kmod/msen_drv.ko    <- sensor
/usr/kmod/dma330.ko  /usr/kmod/codec_drv.ko
```

Two things fall out of that list. `grm_gles.ko` is the graphics path, and
`msen_drv.ko` is the sensor driver, so the capture path is reachable in
principle.

> **Corrected — this entry previously said "`grm_ma.ko` and `grm_gles.ko` are the
> renderer, the UI draws through OpenGL ES". That was an inference from the
> letters in a filename and it is wrong in a way that matters.** Read from the
> modules themselves (`research/firmware/grm_modules.py`):
>
> **`grm_gles.ko` is a character-device and MMIO driver for DMP's SUGILITE
> imaging coprocessor.** Its own `.modinfo` reads
> `description=SUGILITE Driver`, `author=DMP/Sony`, `version=0.6`. Its symbols
> are `sugilite_open`, `sugilite_ioctl` (2,584 B — the bulk of it),
> `sugilite_mmap`, `sugilite_interrupt`, `sugilite_clock_up_internal`,
> `sugilite_clock_down_internal`, and `sugilite_ioread8/16/32` /
> `iowrite8/16/32` register accessors. It logs
> `!!! GPE HW: bar remapped 0x%08x->0%p size %x` — **BAR** remapping is a PCIe
> concept, so SUGILITE is a separate chip on a PCIe link, not an on-chip block.
> Its `.text` is **6,092 bytes**, three orders of magnitude too small to be any
> kind of GL implementation. Sources: `sugi_hw.c` and `sugi_dev.c`.
>
> **`grm_ma.ko` is the matching memory allocator**, not a renderer: a `mspace_*`
> zone allocator (`mspace_malloc`, `mspace_free`, `mspace_memalign`,
> `mspace_mallinfo`, …) plus `ma_dmm_open_send_recv`,
> `ma_findbyphys_impl` / `ma_list_findbyphys`, `ma_compact_*`, and
> `ma_cache_flush_impl` / `ma_cache_invalidate_impl`. That is what lets a
> Linux-side buffer be addressed by the DMP chip — physical/logical translation
> and cache maintenance. It exports `udif_MA_MOD_NAME`. Sources: `allocator.c`,
> `dmm_if.c`, `compact.c`, `list.c`.
>
> Both build under `BuildWorkSpace/**Guiengine_161H**/driver/` — Sony's GUI
> engine for this platform.
>
> **The UI *API* is GLES2; the renderer is not on the Cortex-A9s.**
> `libObj.so` is the only userspace consumer of either module. It opens
> **`/dev/dmpgles2`** (and reports `"failed to open sugilite device"` if that
> fails), and carries DMP's EGL extensions: `eglAsyncSwapBuffersDMP`,
> `eglSuspendDMP`, `eglResumeDMP`, `eglSetHardwareStateDMP`,
> `eglDrawFrameModeDMP`, `eglQueryFrameDMP`, `eglInvalidateImageDMP`,
> `eglQueryDisplayDMP`, plus `EGL_KHR_image` and `EGL_DMP_display_query`.
> So `libObj.so` is the GL *client*; the GLES2 implementation runs on the DMP
> chip, reached through `grm_gles.ko`.
>
> Two supporting negatives, both checked properly:
>
> - **No library in `/usr/lib` links GLES or EGL.** 201 files, zero. So the
>   implementation cannot be a Linux shared object.
> - `libObj.so` also contains a `dmpNative::` layer — `vdf_if_port_send_exec/
>   mute/update/break`, `FbContainer`, `WindowImpl::begin_swap`, `CmdProcessorDmm`,
>   `OSDPin`, `YC1Pin`, `SenserCommunicator*`, `UIPCMsg::send`. That is the
>   bridge to the **VDF display port** analysed in [03-binaries.md](03-binaries.md)
>   and to the same MWF pin vocabulary (`OSDPin`, `YC1Pin`).
>
> **A trap worth recording, because it went into this file before the test
> caught it.** Counting files that "contain GLES" gives three different wrong
> answers depending on how loosely you match:
>
> | filter | files |
> |---|---:|
> | case-insensitive raw bytes (PowerShell `-match`) | **10** |
> | case-sensitive raw bytes | 2 — `libObj.so`, `wpa_supplicant` |
> | + printable ASCII run of ≥4 chars | 2 — unchanged |
> | + word boundaries | **1** — `libObj.so` |
>
> PowerShell's `-match` is case-insensitive, which is what produced the 10; it
> matches lowercase `gles` anywhere. `wpa_supplicant` survives the second filter
> because its MIT licence text literally contains those capitals in
> "NEGL**IGL**ENCE". Only `libObj.so` is a real hit.
>
> The chain is pinned by
> `tests/test_grm_modules.py::test_gles_hits_are_not_byte_coincidences`, so an
> intermediate stage's number cannot be quoted as a finding again. Same shape as
> the `0x400c` count: a search that cannot fail, reported as a result.

Its mount table names a filesystem not otherwise visible: **`/usr/upgrade`** on
nflasha9, with `/usr` as ext2 on nflasha15. It also carries the string
`mounting compressed /system failed(%d), trying vfat` — so `/system` is *meant*
to be a compressed filesystem and falls back to vfat, which implies a compressed
variant may exist somewhere.

Environment it sets: `HOME=/`, `PATH=/sbin:/bin:/usr/sbin:/usr/bin`,
`TOPRC=/etc/toprc`, `LT_ABORTREASON=0`, and
`MALLOC_OPTIONS=gfffffffff MALLOC_MMAP_THRESHOLD_=32768 MALLOC_TRIM_THRESHOLD_=32768`.

Its functions are the boot's control flow: `parse_cmdline`, `parse_and_set_env`,
`set_oreore_env`, `insmod_drivers`, `check_forced_senser`, `check_bootmode`,
`check_qemu`, `check_nfs`, `mount_partition`, `ko_insmod`, `set_stack_size`,
`run_bg_process`, `is_oreore_env`, `is_duma`, `is_bis`, `is_usbj`, `is_kmcenv`,
`is_kernel_only`, `is_nfs`, `is_efence`, `profile_entry/exit`, and `main` ending in
`pivot_root`, `chroot`, `execl` and `/bin/ash --login`. The two boot modes are
**"oreore" and "senser"**, and `check_forced_senser` is how service mode is
selected — the flag that makes the camera boot into the launcher instead of the
application.

**Still unresolved:** nothing in `init` references `av-cam.bin`, and greps of
`launch_shell.elf` and `ldec.ko` found no reference either. So what loads it is
not yet identified. `ldec.ko` is loaded third, immediately after `dmac.ko`, which
makes it the most likely candidate — "ldec" for LIRO decoder — but that is a guess
from position, not evidence.

## Network surface: nothing is listening

```
26: p2p-p2p0-0   inet 192.168.122.1/16   scope global
192.168.0.0/16 dev p2p-p2p0-0 scope link src 192.168.122.1

Proto Recv-Q Send-Q Local Address   Foreign Address   State
udp        0      0 0.0.0.0:67      0.0.0.0:*
```

**One listening socket: `udp/67`, the DHCP server.** Nothing on TCP at all.
`wlan0` and `p2p0` carry only IPv6 link-local. So although the code for a remote
stack plainly exists — `libInfraRemote.so` at 8.7 MB, `ObjRemote`,
`ObjRemoteAsync`, `libcurl`, `libssh2`, strongswan, and an `openssl` binary
exporting `app_http_tls_cb` — **none of it is listening in service mode.** The
WiFi Direct group owner at `192.168.122.1` exists and hands out DHCP leases, and
that is all.

This is consistent with everything else observed: the application is not started,
`LMSGQ`/`LSEM` are empty, and no camera process appears in `comm`. The HTTP
surface would be reachable in normal mode, not here.

Also noted: `/usr/upgrade` appears in init's mount table but **does not exist on
the running camera** — `ls: /usr/upgrade/: No such file or directory`.

### The 47 loaded modules, in load order

The earlier figure came from `/proc/modules` **as rendered on the console**, and
the shell wrapper truncates console output at 25 lines. Reading the same file
through a filter that emits one line gives the true count:

```
/tmp/sd/tools/busybox-armel cat /proc/modules | cut -d' ' -f1 | tr '\n' ' '
```

47 modules, in load order:

```
devno dmac ldec emmc osal_utm osal_uipc utimer backup osal_ulogio input udate
indctr i2c sircs stream stream2 usb_portMonitor usbg_sen usb_extcmd kikilog
dmm upm grm_ma grm_gles accel mag compass mcmn_drv ms_drv mmc_drv
usbg_stillimage dma330 codec_drv liro usbg_buspower usb_darwin usb_buspwr hdmi
cec wlanMemoryAllocator usbg_storage wlanIrq compat cfg80211 mmc_core
mmcioWrapper bcmdhd
```

`/sys/module/` additionally lists 108 entries, including built-ins.

**`liro` is loaded**, which closes the attribution gap — but note *where* in the
order: it comes **after `codec_drv`**, which is the last module `init` insmods.
So `liro`, `usbg_stillimage`, `usbg_buspower` and `usb_darwin` are loaded by a
later stage, not by `init`.

This is the fourth time in this project that a console-truncated read was taken
for a complete one (after `find` silently returning nothing, after `cmp -l`
producing no output, and after a `MARK_` filter hiding three surviving markers).
The rule that follows: **never trust a count taken from wrapped console output —
re-read through a filter that emits one line, or read the wrapper's log file.**

## im.elf loads the firmware

`/usr/bin/im.elf` (23,240 B) contains the literal string:

```
fn=/system/av-cam.bin load=1 debug=1
```

That is a module-parameter format string. `im.elf` is what insmods `liro` and
points it at the firmware, with **`debug=1`**. It also references `/dev/dnflasha3`
and `/system`, and links `libosal_uipc.so`, and carries a second string
`stm_system`.

So the load chain is:

```
ssboot.bin (bootloader, /system/sabin)
  -> vmlinux + initrd, root=/dev/ram0
  -> /sbin/init          mounts partitions, insmods /kmod/* then /usr/kmod/*
  -> im.elf              insmod liro fn=/system/av-cam.bin load=1 debug=1
  -> bootin.elf          mounts /tmp/lt as tmpfs, references LIRO
  -> launch_shell.elf    unmounts /initrd and /dev/ram0, frees the ramdisk,
                         execs /bin/ash --login
```

`launch_shell.elf` is only 5,140 bytes and does **not** load the firmware — its
functions are `reopen_fds`, `do_umount`, `shell_loop`, `do_freeramdisk`, and its
only paths are `/dev/ttycons`, `/dev/console`, `/initrd`, `/dev/ram0`,
`/bin/ash`. `bootin.elf` (15,336 B) references `LIRO` and runs
`/bin/mount -t tmpfs none /tmp/lt`, which does not exist in service mode.

`ldec.ko` is **not** in `/usr/kmod`. `init` loads it from `/kmod/ldec.ko`, which
is on the ramdisk and is freed after boot — so it cannot be dumped from a running
camera. That also explains why the `ldec` greps found nothing: the file is not on
the flash at all.

The live liro module exposes one parameter, `liro_resume_async` (value 0), and
`refcnt` 0.

`im.elf` and `bootin.elf` are already in the local dumps, which is how the
`fn=/system/av-cam.bin` string was found.

## Boot mode

`init` decides its mode from three sources, all of which are now known:

| source | read by | state on the camera |
|---|---|---|
| `/setting/sen/smode` | `check_forced_senser` | **does not exist** (`/setting/sen/` absent) |
| `/setting/mode/dmode` | `check_bootmode` | **absent** (`/setting/mode/` is empty) |
| `/proc/udm/upm_bootmode` | `check_bootmode` | **`NORM`** |
| kernel cmdline | `parse_cmdline` | no `senser`/`usbj`/`kmcenv`/`is_*` parameter |

`BOOTMODE=NORM`, no forcing file, no kernel parameter — and yet only the launcher
is running: no camera application in `comm`, `LMSGQ` and `LSEM` empty, the
scenario runner silent, and no TCP listener.

**The application is not being suppressed by a mode flag. It is being suppressed
by the service USB connection itself.** Every apparently-inert result follows from
that one fact:

- **A patched icon font produces no visible change because the process that draws
  labels is never running.** The file can be patched and md5-verified at the exact
  path the application reads; the application is simply not there to read it.
- The same holds for `OPENCODE` in the string table, and for `9.9.99.99999` in
  `DeviceInfo.xml`. A whole-file `md5sum` is not evidence that a string is drawn.
- The UIPC bus is empty because nothing on the application side is connected to
  it — not because the bus is broken.
- `scenario.elf` returning 0 is consistent with a message queued to an endpoint
  nobody is listening on, exactly as the empty `LMSGQ` predicted.

The PC's own enumeration lists `Windows-MSC`, `Windows-MTP`,
`libusb-MSC`, `libusb-MTP` and vendor-specific backends, so the camera
exposes an ordinary USB device personality as well as the service terminal.
**Hypothesis, untested:** service-mode USB and normal USB are mutually exclusive,
and the application runs in normal mode.

If that holds, the sequence is: make file changes through the service shell,
power down, remove the service cable, power on, let the camera boot into the
application. The UIPC bus, the scenario plugins, the PTP/MTP server,
`libInfraRemote` and the HTTP surface all become live at once, and `/setting`
and `/system` are persistent and writable so the changes survive.

**Testing it means giving up the shell for the duration.**

## Allocator and preload hooks

`/usr/tool/` is not empty:

```
-rwxrwxrwx  LeakCheck              689
-rwxrwxrwx  LeakTracer.so       31,128
lrwxrwxrwx  libjemalloc.so   -> libjemalloc_tsh.so.1
lrwxrwxrwx  libjemalloc_tsh.so -> libjemalloc_tsh.so.1
-rwxrwxrwx  libjemalloc_tsh.so.1  115,504
```

`LeakTracer.so` exports `malloc`, `free`, `realloc`, `lt_malloc`, `lt_calloc`,
`new_slot`, `del_slot` — an interposing allocator that tracks every allocation by
slot. And `init` contains the conditional `LD_PRELOAD` machinery for exactly this
kind of thing:

```
LD_PRELOAD=/usr/tool/libsonyefence.so
LD_PRELOAD=/usr/tool/libduma.so
DUMA_MALLOC_0_STRATEGY=1  DUMA_PROTECT_FREE=1  DUMA_ALIGNMENT=4
DUMA_OUTPUT_FILE=/root/dumaLog.txt
```

So the camera ships with `libduma.so` (a malloc debugger) and
`libsonyefence.so` (an electric-fence allocator) and `init` will `LD_PRELOAD`
either of them depending on its checks. `/usr/tool/` is on the persistent,
writable `/usr` partition, so which allocator the application runs under is a
file-level decision, not a rebuild.
## camuser.elf and libObj.so

Two 21 MB files, and they are not the same thing. The hypothesis that they were
— they are 72 bytes apart in size — was tested and **refuted**: 20,214,068 of
21,305,456 bytes differ. Size similarity was a bad proxy.

`camuser.elf` (21,305,528) is **the application executable**:

| evidence | result |
|---|---|
| `main` | present (30 occurrences) |
| `_start` | present (49) |
| `/lib/ld-linux.so.3` | present — it has a dynamic linker |
| `libc.so.6`, `libstdc++.so.6` | linked |
| `libObj` | referenced — **it links libObj.so** |
| `Application_System_Init` | present |
| `libosal_uipc.so` | not linked directly |

`libObj.so` (21,305,456) is a **library, not a program**: `e_type=ET_DYN`,
`e_entry=0x10fee0`, but **no `main`, no `_start`, and no `.interp`**. It is
`dlopen`ed by `camuser.elf`. So the shape is:

```
camuser.elf            the application program
  -> libObj.so         21 MB object/command registry, 1,953 exports
       -> viewUnified2..8.so, CautionConfig.so, libmpr.so, libInfraRemote.so
  -> libc, libstdc++
```

`camuser.elf`'s section table cannot be walked by pyelftools
(`expected 4, found 0`), which is why it read as a container earlier; a raw byte
search shows it is an ordinary dynamically-linked ARM ELF.

**And it is not on the running camera.** A `find /usr /system /setting -size
+15000k` returns exactly four files:

```
/usr/lib/libObj.so              21,305,456
/usr/lib/CautionConfig.so       17,694,160
/usr/share/app/image_cmn_43.uxc >15,000,000
/system/av-cam.bin              17,289,388
```

No 21 MB executable anywhere on the mounted filesystems, and the initrd is only
8 MB (`initrd=0x700000,8M`) so it cannot hold one. **So in service mode the
application program is simply not deployed on this filesystem.** The most likely
explanation — and it is a hypothesis, not a result — is that the main firmware
pushes it across at boot through the `dmm` shared-memory manager configured by
`/setting/DmmConfig.bin`, rather than it being read from flash.

## Negative results: `find`, and the `/usr/share/app` source

**`find` on the toolbelt busybox works.** It was dismissed twice on bad evidence.
The control `find /usr/bin -name 'crypter.elf'` matches correctly. The two
failures had mundane causes: `-maxdepth` appears to be unsupported by this build
(so it errored to `/dev/null`), and `-xdev` from `/` does not cross into `/usr`,
so `find / -xdev` legitimately found nothing. The tool was fine; the invocations
were wrong.

**`/usr/share/app` is not restored from `av-cam.bin`.** Searching the firmware
for `Sony_DI_Icons`, `fontlist`, `share/app`, `.uxc`, `string_english_f`,
`image_cmn`, `FONT_ICONS` and the Compressed-ROMFS magic returns **zero hits for
all of them**. So whatever rewrites the font at boot is not the main firmware.
That question is still open, and it is now a sharper one: the directory holds
81 MB of resources including a single 15 MB `.uxc`, and it is restored from
somewhere that is not on any mounted filesystem.

## The unmounted partitions

`libObj.so` carries a build-time device table that lists all 32
`/dev/nflasha*` nodes the imaging layer knows about, plus seven
`/nondev/` pseudo-devices with no kernel node behind them. That accounts for
the partitions that kept appearing with nothing in the mount table referring
to them. The device table is in [04-messaging.md](04-messaging.md).

Raw header reads, since `mount` refused them all with `EINVAL` even with explicit
`-t cramfs` and `-t ext2`:

| partition | size | first bytes | what it is |
|---|---|---|---|
| nflasha4 | 12,288 | `CMMeX` | unknown; "CMM" is also the `dmm` shared-memory manager's name |
| nflasha5 | 61,440 | `WBI1` | **warm boot image** — matches `wbi_cmpr.waddr`/`warm.mode=2` on the cmdline |
| nflasha16 | 143,360 | all zero | allocated but empty |
| nflasha24, nflasha25 | — | `No such device or address` | device nodes exist, backing does not |

None of these is the `/usr/share/app` source.

## The scenario runner is fire-and-forget

*The 35 plugins themselves are decoded — their command vocabulary is in
[04-messaging.md](04-messaging.md). What follows is about the runner.*

Verified properly rather than by eye. The first attempt was confounded: the pty
echoes input, so a 32-byte `ABCDEF…` payload appeared to come back as a "reply".
Re-run with `stty -echo` first:

```
/tmp/sd/tools/busybox-armel stty -echo; echo ECHO_OFF_DONE      -> ECHO_OFF_DONE
/usr/bin/scenario.elf MPR_SCN_GET_CONTENT_COUNT 16:4142…; echo SCEN_RC_DONE
                                                               -> SCEN_RC_DONE
```

**No output at all.** And `/setting/ulogio.bin` is byte-identical before and
after (md5 `a401b16a…`). So there is no reply on stdout and none in the log; the
data buffer is not an in/out channel. Combined with an empty `LMSGQ`, the
scenario path currently sends into a void — the application that would answer is
not running.

## Staged for offline analysis

On the SD card at `/tmp/sd/RE_DUMP/audit/`, because the terminal is lossy at
volume — it dropped 162 of 355,344 characters on a 266 KB payload:

| file | size | why |
|---|---|---|
| `Backup.bin` | 1,235,740 | the `BK4` settings store, format unparsed |
| `DmmConfig.bin` | 78,120 | shared-memory layout for the `dmm` module |
| `init` | 28,580 | the boot chain as a binary, not just its strings |
| `liro.ko` | 65,212 | the firmware loader, and it runs with `debug=1` |

## libIMDB.so is the application manifest

`libIMDB.so` (37,044 B) exports only `IMDB_find_entry`, `IMDB_get_entries`,
`IMDB_find_target_bit` and one data symbol, `imdb_raw` — which reads as a
database. It is not a settings index. Its string table is **the complete load
manifest for the camera application**, in order, naming each library and the
`init` / `suspend` / `resume` entry points to call on it.

Extracted: **174 libraries, 16 kernel modules, 22 absolute paths.** The full
list is in `research/firmware/app_manifest.txt`.

The order is the boot order, and the head of it is the interesting part:

```
libIMDB.so               the manifest itself
libosal_uipc.so          the message bus
libosal_utm.so
libosal_ulogio.so
libInfraInterchipDatatrans.so
libNVM.so                NVM_Initialize          <- the settings store
libbackup.so             backup_user_suspend
libSaveLoadSettings.so   infra_saveLoadSettings_init
libbkdmn.so              BkDmn_init
libOnDemandLoader.so     odl_init                <- the plugin loader
libInfraKikiLogGenerator.so  libInfraAccessLog.so ...
```

Two application entry points appear in it:

- **`appFw.so` -> `Application_System_Init`** — the same symbol `libObj.so` exports
- **`gui.so` -> `DPro_App_UI_init` / `_sus` / `_resume`** — the UI

and the remote stack, which is what the earlier "no listening socket" finding was
about, is all here and all initialised from this one list:

```
libInfraRemote.so            InfraRemote_Init
libInfraRemoteControlNet.so  InfraRemoteControlNet_Init
libInfraWebApi.so            InfraNetWebApi_init        <- the web API
libInfraWebApiClient.so      InfraWebApiClient_init
libInfraRemoteCtrlCGI.so     InfraRemoteCtrlCGI_Init
libInfraRemoteCtrlProxy.so   InfraRemoteCtrlProxy_Init
libInfraLiveViewClient.so    LiveViewClient_init
libInfraNetLiveStreaming.so  InfraNetLiveStreaming_Init
libInfraOpusLiveStreaming.so / libInfraRtmpLiveStreaming.so / libInfraUstream.so
libInfraFtpClient.so  libInfraFileTransfer.so  libInfraSavonaServer.so
```

The manifest also names six mode strings — `IMDB:default`, `IMDB:qemu`,
`IMDB:nfs`, `IMDB:set`, `IMDB:USBJ`, `IMDB:RE-SUB` — plus bare `usbj`, `resub`,
`adjust`, `test`. So the same binary builds the service, factory and normal
images, selected by mode.

## The application is not deployed

### But the display pipeline is alive — narrower than "everything is absent"

**Observed by the author, not yet measured here, and worth confirming when the
camera is next attached: in service mode the LCD falls back to playing back media
from the SD card.**

That matters, because it separates two things this document had been running
together. The *display* pipeline works in service mode — something decodes SD
media, composes it and drives the panel. What is absent is specifically the
**camera application**: `camuser.elf`, `appFw.so`, `gui.so`, `libNVM.so`,
`libInfraWebApi.so`.

So the correct reading of the "application is not deployed" finding is not
"nothing is running". It is:

| | service mode |
|---|---|
| display pipeline | **running** — SD playback on the LCD |
| DMP/SUGILITE graphics path | loaded (`grm_gles.ko` in the 47), client unconfirmed |
| camera application | absent |
| sensor / imaging | idle — nothing drives `msen_drv.ko` |
| UIPC bus | idle — `LMSGQ`/`LSEM` empty |
| network | one DHCP socket |

That is a much more tractable system than "the machine is dead", and it is why
an OSD injection is worth considering: the compositing path is evidently up
without the application, so the question becomes whether the DMP 2D engine
(`GRM_gpermRectblit`, `DMP_2D_RectBlitParams`, `utilDMP2D_rectBlitDraw`) and the
VDF OSD port (`vdf_if_port_send_update(update_osd_record*, int*)`) can be
reached from a process that is *not* the application.

**Three checks would settle it**, and all three need service mode:

```sh
busybox ls -l /dev/dmp*                      # is the node there?
busybox grep -c grm /proc/modules            # is the module loaded?
busybox grep -i dmp /proc/iomem              # did the BAR remap succeed?
# and the decisive one: which process has the node open
busybox ls -l /proc/*/fd/ 2>/dev/null | busybox grep dmp
```

The last one names the process that is driving the display right now, which is
the entry point to the whole path. `libObj.so` also exports
`GRM_bitmapGetPhysicalAddress` and `GRM_screenGetOnBitmap`, so if the answer is
a process with `libObj.so` mapped, the application library is in use after all
and the "not deployed" finding needs narrowing further.

### The absence itself

This is the finding that ends the search. Of the 174 libraries the manifest
names, the ones actually present in `/usr/lib` are the **assets**:

```
/usr/lib/libObj.so          21,305,456
/usr/lib/CautionConfig.so   17,694,160
/usr/lib/viewUnified2.so    14,284,732
/usr/lib/libmpr.so          13,021,036
/usr/lib/libInfraRemote.so   8,708,516
```

and the ones that would **drive** them are absent:

| file | manifest symbol | on the camera |
|---|---|---|
| `appFw.so` | `Application_System_Init` | **absent** |
| `gui.so` | `DPro_App_UI_init` | **absent** |
| `libNVM.so` | `NVM_Initialize` | **absent** |
| `libSaveLoadSettings.so` | `infra_saveLoadSettings_init` | **absent** |
| `libInfraWebApi.so` | `InfraNetWebApi_init` | **absent** |

Also absent: everything the manifest names under `/usr/local/lib/`
(`libVssApp.so`, `AdjChkConfig.so`, `libVssAppMain.so` — `/usr/local/lib` is
empty), and `/usr/bin/WebApiLauncher.sh`, `/usr/bin/qsi.elf`,
`/usr/bin/network.sh`, and every `/kmod/*.ko` (those are on the ramdisk, which
is freed after boot).

**The service filesystem carries the camera's rendering engine, its view
layer and its 81 MB of resources, but not the application that uses them.** The
program, the settings store and the web API are simply not there. That is not a
permissions problem or a mount problem — the files do not exist.

Consequences:

- A patched icon font cannot appear, because `gui.so` — the thing that draws
  labels — is not installed. The same for the string table and `DeviceInfo.xml`.
- The UIPC bus is empty, the scenario runner is silent, and there is no TCP
  listener, because none of the peers on the other end of those interfaces are
  loaded.
- `libOnDemandLoader` explains the orphaned shared objects: 40 of the 123 are
  the `libInfra*`/`viewUnified*` block, a plugin set that in service mode nothing
  loads.

**The housekeeping core cannot reach the camera application, because the
application is not on its filesystem.** Everything reachable from here is
diagnostic: the message bus, the settings NVRAM, the bootloader, the firmware
image, the service tools and 47 kernel modules. That is a real and fairly
complete surface — but it is a different machine from the one that draws the
screen.

The one remaining lever is `check_forced_senser` and the mode selection in
`init`. `BOOTMODE=NORM` already, no forcing file present, yet the application is
not loaded — which means either the mode that is actually in force is not being
reported through `/proc/udm/upm_bootmode`, or the service USB personality is
what holds the system in the launcher. Testing it means giving up the shell.
## Code execution: writable `/usr/lib` → `dlopen` → root

This is the first code execution on the camera, and it needed no exploit — no
memory corruption, no kernel bug, no race. The camera loads its own libraries
by name from a directory the service shell can write to, and that directory
persists across reboot.

### The primitive

`/usr/lib` is ext2 on `nflasha15`, remountable rw, and **not** wiped at boot
(only `/usr/share/app` is). It holds 201 shared objects, including
`libtestcmd.so`, which `scenario.elf` links. Replacing one of those files with
a different ELF of the same name means the dynamic loader runs my code as root
the next time anything loads it.

### The proof

`libtestcmd.so` exports `cmdline_show_revision` — 68 bytes at vaddr `0x1a48`,
and for that object vaddr == file offset. It is a leaf whose last 28 bytes are
its own literal pool, so the whole function is self-contained and can be
replaced wholesale. `--ver` is its only caller.

The replacement is 66 bytes of ARM Thumb-2 that uses **raw Linux syscalls
only** — `open`/`write` via `svc #0`, no PLT, no libc, no new relocations, so
the loader has nothing extra to bind:

```
push {r7, lr}
sub  sp, sp, #16
movw r1, #0x742f ; movt r1, #0x706d ; str r1, [sp, #0]   "/tmp/ox\0"
movw r1, #0x6f2f ; movt r1, #0x0078 ; str r1, [sp, #4]
movw r1, #0x504f ; movt r1, #0x0a58 ; str r1, [sp, #8]   "OPX\n"
mov  r0, sp ; movw r1, #0x0241 ; mov r7, #5 ; svc #0     open(path, O_WRONLY|O_CREAT|O_TRUNC)
add  r1, sp, #8 ; mov r2, #4 ; mov r7, #4 ; svc #0       write(fd, body, 4)
mov  r0, #0 ; add sp, sp, #16 ; pop {r7, pc}              return 0, as the original did
```

Built by `research/firmware/opx_payload.py` with keystone, applied to
`dumps/camera_2025/usr/usr/lib/libtestcmd.so`, and diffed: **66 of 10,128
bytes changed, all inside `0x1a48..0x1a8b`; file length unchanged; all 25
exports still resolve; the object still parses.**

Transferred without the SD card, in 66 bytes of `printf` octal escapes plus
two `tail`/`dd` slices, and checked at every step:

| stage | size | md5 |
|---|---|---|
| payload built locally | 66 | `f1dd9279ac5406559efd0df51d7876a6` |
| `/tmp/p.bin` on the camera | 66 | `f1dd9279ac5406559efd0df51d7876a6` |
| `/tmp/lt.so` reassembled on the camera | 10128 | `5d776c95847022dbc343e00519289b5f` |
| `libtestcmd.OPX.so` built locally | 10128 | `5d776c95847022dbc343e00519289b5f` |

Installed, then `scenario.elf --ver`:

```
===== $ ls -l /tmp/ox; cat /tmp/ox =====
OPX
```

The file did not exist before. It was created by the injected code, in the
`scenario.elf` process, as root, by a library I had replaced with an md5-
different but otherwise identical file.

Restored immediately and verified: `-r-xr-xr-x 1 57285 1000 10128`,
md5 `f370de888ae662e7f509f2274846eac6` — byte-identical to stock, original
mode and ownership (`cp` had reset both; `chown`/`chmod` put them back). The
`.orig` copy was removed. **The camera is as it was found.**

`im.elf` does not link `libtestcmd.so`, so nothing running was touched. That
was checked before installing, not after.

## im.elf: the real target

`im.elf` is not a launcher. It is the imaging manager, and it is **running as
PID 157**, owning **417 message queues, 134 semaphores and 310 callbacks** —
the whole Linux side of the OSAL bus. Its imports:

```
dlopen dlsym dlclose dlerror        IMDB_find_entry IMDB_get_entries IMDB_find_target_bit
mount umount mmap munmap statfs      Backup_read Backup_write
fork waitpid putenv syscall signal   osal_* (snd/rcv/reg/valloc/free, osal_snd_sync_direct)
```

and its `.rodata` is the control plane in plain text. It **mounts every
filesystem on the device**:

```
/proc   /sys   /setting (/dev/dnflasha3)   /system (/dev/nflasha3)
/tmp    /usr (/dev/nflasha15, cramfs)      /rootfs    /usr/upgrade
/log    /dev/ms1   /lens   /cert   /etc
```

note that `/setting` and `/system` come from the **`dnflasha3`/`dnflasha15`**
"decrypted" devices while `/system` also lists `nflasha3` — two different
backing stores for the same mount point, which is a new lead on the
`/usr/share/app` restore mystery. It also runs `/sbin/dosfsck -Y` for vfat and
`/usr/bin/e2fsck -y` for ext2, spawns `/usr/bin/sen.elf &`, and can trigger a
reboot through `/sys/power/state` (`warm`, `mem`).

It selects a build with these keywords, read from the kernel command line or a
config: `boot=` `bootall` `target=` `app_argv=` `cipa` `qemu` `usbj` `cho`
`normal` `nodebug` `notrace` `test` `killall` `imdb` `jem` `imssi` and the
`lazy-global` / `lazy-local` / `now-global` / `now-local` variants.

And the manifest it loads libraries from is **`libIMDB.so`'s own string
table**. The exported data symbol `imdb_raw` is 132 bytes: eleven u16 offsets
into `.rodata`, resolving to the nine mode names

```
default  qemu  sim  nfs  set  usbj  resub  adjust  test
```

(`IMDB:default`, `IMDB:qemu`, … are the same strings five bytes later). The
174 library names and their `init`/`exit`/`sus`/`res`/`act`/`inact` entry
points are the surrounding `.rodata`, walked in order. `im.elf` prints the
record it is working on:

```
IMDB @ %p   .type=0x%08x  .taregt=0x%08x  .flag=0x%08x
            .me=0x%04x    .psid=0x%04x
            .file : "%s"   .init : "%s"   .exit : "%s"
            .sus  : "%s",  .res  : "%s"   .inact: "%s"  .act : "%s"
```

`.me` and `.psid` are 16-bit, and they are exactly the small queue indices
that appear in `/proc/osal/uipc` (`4C`, `114`, `16F`, …). So the manifest
records name the message-queue ids their owners serve. Validation is only
`strchr(name, ' ')` — it rejects NULL and names containing a space, nothing
else.

**Replacing `/usr/lib/libIMDB.so` would execute code inside PID 157, at startup,
on the next boot, as root, in the process that owns the message bus and mounts
the filesystems.** That is the attack path to the subsystems, and the primitive
proved above is all that is required.

**This is a one-way door and has deliberately not been done.** If the replacement
is wrong, `im.elf` does not start, the service shell never appears, and recovery
means the SD card. The `libtestcmd.so` demonstration above was chosen precisely
because `im.elf` does not touch that file.

### The scenario protocol, read out of the code

`scenario.elf` does **not** `dlopen` the plugin. `libtestcmd.so` imports no
`dlopen` and no `dlsym` — only `osal_*`. `testcmd_run_scenario` (440 bytes)
builds a message and sends it:
```
message header, 16 bytes
  +0x00  0x00940021
  +0x04  0x000000dc
  +0x08  0x00000003
  +0x0c  0x00dc0292            destination
payload
  +0x00  char name[0x20]        32 bytes, memcpy'd
  +0x20  u32  name_len
  +0x24  u32  data_len
  +0x28  u8   data[data_len]
```

`name_len` is `strlen`, `data_len` is the 4-byte value from the caller, and the
two endpoint ids are `0x00dc0292` (register) and `0x00dc0293` (send). The
descriptor struct that `testcmd_sndmsg`/`testcmd_rcvmsg` use is `u32 id` at
`+0`, a flags byte at `+0x0c` whose bit 0 selects the synchronous call, and a
source id written back at `+0x14`. Return codes are `0xfffffb01`–`0xfffffb06`
and `0xfffffc00`/`0xfffffc01`.

so the scenario name is a **UIPC message payload, and the `dlopen` happens on
the far side** — in a peer that is not loaded in service mode. That is why
`scenario.elf` is fire-and-forget and why the 35 plugins in `/usr/scenario/`
never ran. The name is also truncated at 32 bytes by that `memcpy`, and
validation is only "no spaces", so a 32-character name containing `../` is
accepted by the sender — whether the receiver joins it into a path is the
question that would make this an injection rather than a message.

*How this was read, and the four decoding traps involved, is in
[06-method.md](06-method.md).*

### The bus has two disjoint node spaces

`/proc/osal/uipc` (`OSAL Version 4.2`, compiled Mar 15 2025) lists 860 msgqs
and 198 sems globally, and per process:

| pid | process | msgqs | sems | cbs |
|---|---|---|---|---|
| 157 | **`/usr/bin/im.elf`** | 417 | 134 | 310 |
| 149 | — | 0 | 0 | 0 |

Local queue indices are small (`4C`, `74`, `114`, `160`, `16F`), the global
table carries a node column, and the node ids fall into two families:

- `0x0094xxxx` — 89 occurrences. The Linux-process side.
- `0x00dcxxxx` — **0 occurrences.**

`0x00dc0000` is the liro/RTOS endpoint, and the RTOS keeps its own queues
(the 139 liro threads), so it does not appear in the Linux dump at all. That
is why `sndcmd` reports RC=0 when it posts to `0x00dc0000` — the message is
accepted by firmware that is alive and running, even though no Linux peer
exists. Anything in the `0x00dc` space is therefore addressed straight at the
camera's real subsystems, and the enumeration question becomes: what else
lives in that space. `libObj.so` (1953 exports) and the `libIMDB` manifest
are the index; the RTOS side of the bus is the next place to read.

## How the transfer was done without the SD card

The card was in the PC, so the object was moved 66 bytes at a time:

- `printf` with three-digit octal escapes writes the payload directly. Note
  `busybox xxd -r -p` is **not** usable — it is present in the applet list but
  mangles 132 hex chars into 30 bytes. `xxd`, `tr`, `tail`, `wc`, `head` are
  listed by `busybox --help` but are not linked as applets; `busybox <applet>`
  reaches the ones that exist. `md5sum` is reachable as `busybox md5sum`, and
  plain `md5sum` fails.
- `dd if=... of=... bs=1 count=6728` for the head, `busybox tail -c +6795` for
  the tail — `dd skip=` produced a 0-byte file.
- Hash each stage against the locally built object before installing anything.

## Gaps

Gaps 1, 4, 5 and 7 are closed above. What remains:

1. **The `BK4` format in `Backup.bin`.** Header is structured but unparsed.
   `Backup.bin` is staged on the card; the `libIMDB` index
   (`IMDB_find_entry`, `IMDB_get_entries`, `IMDB_find_target_bit`) is the
   obvious way in.
2. **`/proc/osal/uipc` write grammar.** The most promising unexplored knob; the
   node is read-write and the module has `__k_cmd_debug`.
3. **Usage strings for most binaries.** `sen.elf` with no arguments produces no
   prompt and appears to block; needs a per-binary timeout.
4. **Which library provides which `Obj*` group**, and whether the compressed
   `/system` variant exists — `init` carries
   `mounting compressed /system failed(%d), trying vfat`.
5. **`camuser.elf`** (21,305,528 B) is a container with an unreadable section
   table; unidentified.
6. **`ldec.ko`** is unrecoverable — it lives on the ramdisk at `/kmod/ldec.ko`,
   which is freed after boot, so it cannot be dumped from a running camera.
7. **`liro.ko` internals.** Staged on the card. It loads the firmware with
   `debug=1`, so it may expose a debug interface that has not been looked for.
8. **`tmonitor`** at `0xF00000`, 32 KB, currently masked off — a kernel module
   is loaded under that name, so the facility exists and is unused.
9. **`DmmConfig.bin`** — the shared-memory layout for the `dmm` module, staged
   on the card, unparsed.

## Negative results: truncated reads

Four claims in this project were wrong because a truncated or filtered read was
taken for a complete one:

| what | how it misled |
|---|---|
| `/proc/modules` read off the console | wrapper caps output at 25 lines; "24 loaded" was really 47 |
| `find` on the toolbelt busybox | silently returned nothing, so "no archive exists" was unfounded |
| `cmp -l` on the camera | produced no output through the wrapper; the differing-byte count was never obtained |
| a `MARK_` grep over marker files | hid three surviving markers whose contents were `M3`/`M4`, nearly producing a false negative |

The rule: **never trust a count or an absence taken from wrapped console output.**
Re-read through a filter that emits a single line, or read the wrapper's log
file, which keeps everything.

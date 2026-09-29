# Audit: what the service shell can reach

Run against a live ZV-E10 in service mode. Passes are scripted in
`research/device/audit_surface.py` and their raw output is filed under
`%TEMP%\opencode\app_res\audit\`.

## Why this was done as an audit

Three claims about the *extent* of the reachable surface have now been
overturned by measurement, each in the direction of assuming less was reachable
than actually was:

- `av-cam.bin` was recorded as encrypted; it is 2,459 of 4,221 4K blocks below
  6.5 bits/byte and the readable region spans the whole file.
- `/usr/bin` was recorded as read-only squashfs; it is ext2 and
  `mount -o remount,rw /usr` works.
- The camera firmware was inferred to be on a different CPU, from
  `ls -l /proc/*/exe` showing no application — but `ls -l` skips entries it
  cannot read, and of 263 processes only 8 executables appeared. `/proc/*/comm`
  shows 139 `liro-kliro_*` threads on this kernel.

So the remaining risk is not "what else is there" but "what was never looked at".
This records coverage, so gaps are visible.

## Filesystems — 11 mounts, and only `/` is read-only

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

## Persistence — tested with one reboot

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

## Processes — 263

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

## Kernel modules — 47 loaded, 103 in /usr/kmod

See "Correction: 47 modules are loaded, not 24" below for the authoritative list and load order.

`/usr/kmod/` holds 103 `.ko` files including `liro.ko`, `mcmn_drv.ko`,
`ms_drv.ko`, `accel.ko`, `mag.ko`. **`/sbin/insmod` and `/sbin/rmmod` are
present**, so modules can be loaded. Note `liro.ko` is in `/usr/kmod` yet the
running `liro` threads are not attributed to a loaded module — worth resolving.

## Commands — 49 in /usr/bin, 7 in /usr/sbin, 17 in /sbin

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

## Plugins

- `/usr/scenario/` — 35 `.so`, each exporting exactly `scenario_run`, dispatched
  by name through `scenario.elf`. Includes `MPR_SCN_SET_FACTORY_MODE`,
  `MPR_SCN_EXEC_FACTORY_MODE`, `MPR_SCN_FORMAT`, `MPR_SCN_EXEC_WIFI_TEST`,
  `CAMERA_SCN_MOVIE_REC_START`, and the `AVBB_SCN_START/STOP_*` family.
- 391 shared objects catalogued, 313 not `DT_NEEDED` by anything — loaded at
  runtime by `libOnDemandLoader.so` (`OnDemandLoaderInitialize`), each attaching
  via its `Obj*_RegisterCommand`.

## procfs

`/proc/osal/` has `minfo` (read-only), `uipc` (read-write), `ulogio`
(read-write). `cat /proc/osal/uipc` dumps the bus: OSAL 4.2, 860 message queues,
198 semaphores, 16 messages, 1168 callbacks, pool sizes, and per-process
sections. `LMSGQ` and `LSEM` are empty, so the bus is idle in service mode. The
module also has `__k_uipc_proc_write` and `__k_cmd_debug`, so the node is
writable — the command grammar is unknown and has not been probed.

## Gap 5 closed: /system is the firmware's home

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

## The boot recipe: /sbin/init is readable

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
/usr/kmod/grm_ma.ko  /usr/kmod/grm_gles.ko      <- graphics / OpenGL ES
/usr/kmod/accel.ko  /usr/kmod/mag.ko  /usr/kmod/compass.ko
/usr/kmod/mcmn_drv.ko  /usr/kmod/ms_drv.ko  /usr/kmod/mmc_drv.ko
/usr/kmod/sata_drv.ko  /usr/kmod/msen_drv.ko    <- sensor
/usr/kmod/dma330.ko  /usr/kmod/codec_drv.ko
```

Two things fall out of that list. **`grm_ma.ko` and `grm_gles.ko` are the
renderer** — the UI draws through OpenGL ES, which is what `libObj.so`'s
`GRM_bitmap*` and `GRM_fbrmPrepareUpdateYUV` exports talk to, and therefore where
`TextRM_drawText` ultimately lands. And `msen_drv.ko` is the sensor driver, so the
capture path is reachable in principle.

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

## Gap 1 closed: there is no network surface right now

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

## Correction: 47 modules are loaded, not 24

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

## Gap 4 closed: im.elf loads the firmware

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

## Staged for offline analysis

Pulled to `/tmp/sd/RE_DUMP/audit/` on the card, because the terminal is lossy at
volume and these are too large to push through it:

| file | size | why |
|---|---|---|
| `Backup.bin` | 1,235,740 | the `BK4` settings store — format unparsed |
| `DmmConfig.bin` | 78,120 | shared-memory config for the `dmm` module |
| `init` | 28,580 | the boot recipe as a binary, not just its strings |
| `liro.ko` | 65,212 | the firmware loader, and it runs with `debug=1` |

`im.elf` and `bootin.elf` are already in the local dumps, which is how the
`fn=/system/av-cam.bin` string was found.
## The finding that reframes everything: bootmode is NORM

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

**So the application is not being suppressed by a mode flag. It is being
suppressed by the service USB connection itself.**

That closes the loop on every dead end in this session, and it is worth stating
plainly because it was not obvious and cost the whole afternoon:

- **The icon-font patch produced no visible change because the process that draws
  labels was never running.** The file was patched and md5-verified at the exact
  path the application reads; the application simply was not there to read it.
- The same applies to `OPENCODE` in the string table. Every "check" of it was a
  `md5sum` on a camera that had no UI to show it.
- The UIPC bus is empty because nothing on the application side is connected to
  it — not because the bus is broken.
- `scenario.elf` returning 0 is consistent with a message queued to an endpoint
  nobody is listening on, exactly as the empty `LMSGQ` predicted.

The PC's own enumeration lists `Windows-MSC`, `Windows-MTP`,
`libusb-MSC`, `libusb-MTP` and vendor-specific backends, so the camera
exposes an ordinary USB device personality as well as the service terminal.
The hypothesis to test is that **service-mode USB and normal USB are mutually
exclusive**, and that in normal mode the application runs.

If that holds, the right sequence for everything found in this audit is: make
file changes through the service shell, power down, remove the service cable,
power on, and let the camera boot into the application. The UIPC bus, the
scenario plugins, the PTP/MTP server, `libInfraRemote` and the HTTP surface all
become live at once, and `/setting` and `/system` are persistent and writable so
the changes survive.

**This is a hypothesis, not a result.** It has not been tested, because testing it
means giving up the shell for the duration.

## Also found: a malloc/alloc tracer

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
## Not covered — the honest gaps

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

## A pattern worth recording

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

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
## The application, and where it is not

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

## Corrections to earlier notes in this project

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

## Staged on the card, for offline analysis

`/tmp/sd/RE_DUMP/audit/` — too large for the terminal, which loses bytes at
volume (it dropped 162 of 355,344 characters on a 266 KB payload):

| file | size | why |
|---|---|---|
| `Backup.bin` | 1,235,740 | the `BK4` settings store, format unparsed |
| `DmmConfig.bin` | 78,120 | shared-memory layout for the `dmm` module |
| `init` | 28,580 | the boot recipe as a binary, not just its strings |
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

## The application is not deployed on the service filesystem

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

**So the service filesystem carries the camera's rendering engine, its view
layer and its 81 MB of resources, but not the application that uses them.** The
program, the settings store and the web API are simply not there. That is not a
permissions problem or a mount problem — the files do not exist.

It ties together every dead end in this session:

- The patched icon font produced no visible change because `gui.so` — the thing
  that draws labels — is not installed.
- `OPENCODE` likewise. Every check of it was an `md5sum` on a camera with no UI.
- The UIPC bus is empty, the scenario runner is silent, and there is no TCP
  listener, because none of the peers on the other end of those interfaces are
  loaded.
- `libOnDemandLoader` explains the 313 "orphaned" shared objects: they are a
  plugin set, and in service mode nothing loads them.

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
## An attack path exists, and it is proved: writable `/usr/lib` → `dlopen` → root

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

## The real target: `libIMDB.so`, loaded by `im.elf`

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

**So replacing `/usr/lib/libIMDB.so` would execute code inside PID 157, at
startup, on the next boot, as root, in the process that owns the message bus
and mounts the filesystems.** That is the attack path to the subsystems, and
the same primitive proved above is all that is required.

I did not do that, because it is a one-way door: if the replacement is wrong,
`im.elf` does not start, the service shell never appears, and recovery means
the SD card. The demonstration above was chosen precisely because
`im.elf` does not touch `libtestcmd.so`.

## The scenario protocol, read out of the code

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

So the scenario name is a **UIPC message payload, and the `dlopen` happens on
the far side** — in a peer that is not loaded in service mode. That is why
`scenario.elf` is fire-and-forget and why the 35 plugins in `/usr/scenario/`
never ran. The name is also truncated at 32 bytes by that `memcpy`, and
validation is only "no spaces", so a 32-character name containing `../` is
accepted by the sender — whether the receiver joins it into a path is the
question that would make this an injection rather than a message.

## The bus has two disjoint node spaces

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

## Camera state after this work

Unchanged. `/usr/lib/libtestcmd.so` stock, mode and ownership restored, no
`.orig` left, `/tmp` scratch removed. The five earlier persistence markers
(`/setting/_audit1`, `/system/_audit2`, `/usr/bin/_marker3`,
`/usr/share/_marker4`, `/usr/share/pmbp/_marker2`) are still in place.


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

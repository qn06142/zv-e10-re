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

## Kernel modules — 24 loaded, 103 available

Loaded: `devno dmac ldec emmc osal_utm osal_uipc utimer backup osal_ulogio
input udate usb_buspwr hdmi cec wlanMemoryAllocator usbg_storage wlanIrq compat
cfg80211 mmc_core mmcioWrapper bcmdhd`

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

## Not covered — the honest gaps

1. **Network.** Interfaces, routes and listening ports were not enumerated. The
   camera runs a WiFi Direct group owner on `192.168.122.1`; whether the main
   firmware's HTTP service is reachable from the PC is untested.
2. **Usage strings for most binaries.** Blocked by `sen.elf` hanging; needs a
   per-binary timeout.
3. **`/proc/osal/uipc` write grammar.** The most promising unexplored knob.
4. **The `BK4` format in `Backup.bin`.** Header is structured but unparsed. The
   `libIMDB` index is the obvious way in and has not been applied.
5. **Which library provides which `Obj*` group**, and whether `av-cam.bin` is
   loaded from `/system` at boot — which would make that partition the firmware's
   source of truth.
6. **`camuser.elf`** (21,305,528 B) is a container with an unreadable section
   table; unidentified.
7. **`liro` module attribution** — 139 threads, no loaded `liro.ko`.

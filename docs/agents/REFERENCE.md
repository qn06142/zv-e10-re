# REFERENCE — ZV-E10, consolidated durable facts

**Self-contained.** One file, no links to follow. Everything here is measured and
round-trips or md5-verifies. For *how* any of it was obtained see
[`../06-method.md`](../06-method.md); for state and blockers see
[`STATE.md`](STATE.md).

---

## 1. Platform

| | |
|---|---|
| SoC | Sony CXD900X0, quad ARM Cortex-A9 (ARMv7 rev1, NEON/VFPv4), ~1 GHz |
| RAM | `mem=1G@0 memrsv=680M@0x15800000:uc mem=256M@0x80000000@1` — but `MemTotal` reports 128 MB |
| Kernel | `3.0.27_nl-rt106+` (PREEMPT RT) |
| Userspace | BusyBox 1.34.1 ash |
| Wi-Fi/BT | Broadcom BCM4339, driver `bcmdhd`; `bt_firm.hcd` = `"BCM4339 37.4MHz Sony DI 152H-0178"` |
| Storage | raw NAND via `nflasha*` nodes; SD via `/dev/mmca1` |
| UI renderer | `grm_ma.ko` + `grm_gles.ko` — **OpenGL ES** |

**Two operating systems on one SoC.** Linux is the housekeeping OS (USB, Wi-Fi/BT,
HDMI/CEC, SD/MMC, GUI, buttons, IR). The camera — sensor, ISP, AF, AE, AWB, encode —
runs in the `liro` RTOS alongside it. 139 `liro-kliro_*` userspace threads plus ~90
`liro-NN` hardware IRQs.

`/proc/iomem` shows **no** sensor/ISP registers, so Linux cannot touch the ISP
directly. Everything goes through `osal_uipc` (messages) and `dmm` (3.1 MB
shared-memory buffer manager).

### Kernel command line

```
cmpr.path=/system/sabin/ssboot.bin  cmpr.path2=/system/sabin/ssboot_any.bin
root=/dev/ram0  rootfstype=ext2  init=/sbin/init  initrd=0x700000,8M
mem=1G@0   memrsv=680M@0x15800000:uc   mem=256M@0x80000000@1
tmonitor.addr=0xF00000 tmonitor.size=0x8000 tmonitor.mask=0
klog.addr=0x035A5000 klog.size=0x20000   alog.addr=0x03524FC0 alog.size=0x60040
cxd900x0.bam=N   xrstreq=1   wdt.mode=1   ip=off
```

`/` is a **ramdisk**, so `/bin` and `/initrd` read empty and `/` being read-only
costs nothing. `tmonitor` is a 32 KB region at `0xF00000`, currently masked off.

## 2. Mount table

```
/dev/nflasha7  /    ext2 ro,relatime,errors=continue 0 0
/dev/nflasha15 /usr ext2 ro,relatime,errors=continue 0 0
/dev/nflasha10 /tmp      vfat rw    12 MB
/dev/nflasha10 /etc      vfat rw    12 MB
/dev/nflasha3  /system   vfat rw    48 MB
/dev/nflasha2  /setting  vfat rw    20 MB
/dev/nflasha18 /lens     vfat rw    20 MB
/dev/nflasha12 /cert     vfat rw    40 MB
/dev/nflasha11 /log      vfat rw   500 MB
/tmp/sd        mmca1     vfat rw    the SD card, not mounted by the camera
```

`mount -o remount,rw /usr` **succeeds**. `/usr` is **ext2, not squashfs** — an
earlier note saying otherwise is stale.

| path | survives power cycle |
|---|---|
| `/usr/bin`, `/usr/share`, `/usr/share/pmbp` | **yes** |
| `/usr/share/app` | **no** — wiped at boot |

`nflasha15.img` (300 MB) superblock: magic `0xef53`, state `0x0001` clean, block
size 1024, 242,416 blocks (236.7 MB), 10,957 free blocks, 59,700 free inodes,
inode size 128, `feature_incompat=0x2` RECOVER, `feature_ro_compat=0x3`.
`color_cmn.uxc` at `@0x0e47e618`, inode 4299.

### Unmounted partitions

| partition | size | first bytes | what |
|---|---:|---|---|
| nflasha4 | 12,288 | `CMMeX` | unknown; "CMM" is also the `dmm` manager's name |
| nflasha5 | 61,440 | `WBI1` | **warm boot image** — matches `warm.mode=2` |
| nflasha16 | 143,360 | all zero | allocated, empty |
| nflasha24, nflasha25 | — | `No such device` | nodes exist, backing does not |

## 3. Process and device census

263 processes: 139 `liro-kliro_*`, 1 `uipc_dumper` (kernel thread, 8 K stack,
PID 93), 2 `RMCMND-UIPC`, 2 `ULOGIO_LOGREC`, 1 `memmgr`, and 8 userspace
(`launch_shell.elf`, `bootin.elf`, `im.elf`, `bsa_server`, `dhcpd`,
`wpa_supplicant`, busybox ×3, busybox-armel ×5).

`ls -l /proc/*/exe` silently skips unreadable entries, so it showed 8 executables
instead of the real picture. `/proc/*/comm` is world-readable — **use that.**

**47 modules loaded**, in load order:

```
devno dmac ldec emmc osal_utm osal_uipc utimer backup osal_ulogio input udate
indctr i2c sircs stream stream2 usb_portMonitor usbg_sen usb_extcmd kikilog
dmm upm grm_ma grm_gles accel mag compass mcmn_drv ms_drv mmc_drv
usbg_stillimage dma330 codec_drv liro usbg_buspower usb_darwin usb_buspwr hdmi
cec wlanMemoryAllocator usbg_storage wlanIrq compat cfg80211 mmc_core
mmcioWrapper bcmdhd
```

`/usr/kmod/` holds 103 `.ko`; `/sys/module/` lists 108 including built-ins.
`/sbin/insmod` and `/sbin/rmmod` are present.

`liro` is loaded **after** `codec_drv`, the last module `init` insmods — so
`liro`, `usbg_stillimage`, `usbg_buspower` and `usb_darwin` are loaded by a later
stage, not by `init`.

### Boot chain

```
ssboot.bin (bootloader, /system/sabin)
  -> vmlinux + initrd, root=/dev/ram0
  -> /sbin/init          mounts partitions, insmods /kmod/* then /usr/kmod/*
  -> im.elf              insmod liro fn=/system/av-cam.bin load=1 debug=1
  -> bootin.elf          mounts /tmp/lt as tmpfs, references LIRO
  -> launch_shell.elf    unmounts /initrd and /dev/ram0, frees the ramdisk,
                         execs /bin/ash --login
```

`/sbin/init` is a 28,580-byte **ELF**, not a script. Its control flow:
`parse_cmdline`, `parse_and_set_env`, `set_oreore_env`, `insmod_drivers`,
`check_forced_senser`, `check_bootmode`, `check_qemu`, `check_nfs`,
`mount_partition`, `ko_insmod`, `set_stack_size`, `run_bg_process`,
`is_oreore_env`, `is_duma`, `is_bis`, `is_usbj`, `is_kmcenv`, `is_kernel_only`,
`is_nfs`, `is_efence`, `profile_entry/exit`, `main` → `pivot_root`, `chroot`,
`execl`, `/bin/ash --login`.

The two boot modes are **"oreore"** and **"senser"**; `check_forced_senser`
selects service mode.

Environment it sets: `HOME=/`,
`PATH=/sbin:/bin:/usr/sbin:/usr/bin`, `TOPRC=/etc/toprc`, `LT_ABORTREASON=0`,
`MALLOC_OPTIONS=gfffffffff MALLOC_MMAP_THRESHOLD_=32768 MALLOC_TRIM_THRESHOLD_=32768`.

Its mount table names **`/usr/upgrade`** on nflasha9, which **does not exist on
the running camera**, and carries the string
`mounting compressed /system failed(%d), trying vfat` — so a compressed `/system`
variant may exist somewhere.

`ldec.ko` is loaded from `/kmod/ldec.ko`, **on the ramdisk, which is freed after
boot.** It cannot be dumped from a running camera at all.

## 4. Boot mode

| source | read by | state |
|---|---|---|
| `/setting/sen/smode` | `check_forced_senser` | **does not exist** |
| `/setting/mode/dmode` | `check_bootmode` | **absent** |
| `/proc/udm/upm_bootmode` | `check_bootmode` | **`NORM`** |
| kernel cmdline | `parse_cmdline` | no `senser`/`usbj`/`kmcenv`/`is_*` parameter |

`BOOTMODE=NORM`, no forcing file, no kernel parameter — and yet only the launcher
is running. **The application is not suppressed by a mode flag; it is suppressed
by the service USB connection itself.** Untested, and testing costs the shell.

## 5. The message bus

`osal_uipc.ko` (38,960 B) → `/proc/osal/{minfo,uipc,ulogio}`. Handlers:
`__k_uipc_proc_read`, **`__k_uipc_proc_write`**, `__k_cmd_debug`, `msgq_dump`,
`fblock_dump`, `vpool_dump`, `bsem_dump`, plus the `uipc_dumper` kernel thread.

Live: `OSAL Version 4.2`, `Compiled at Mar 15 2025 03:07:32`, proxy threads=4.
Globally: 860 msgqs, 198 sems, 16 msgs, 1168 cbs, 377 misc.

| pid | process | msgqs | sems | cbs |
|---|---|---:|---:|---:|
| 157 | **`/usr/bin/im.elf`** | 417 | 134 | 310 |
| 149 | — | 0 | 0 | 0 |

**Two disjoint node spaces:** `0x0094xxxx` (89 occurrences, Linux side) and
`0x00dcxxxx` (**0 occurrences** in the Linux dump — the RTOS keeps its own
queues). `0x00dc0000` is the liro/RTOS endpoint, default `--sid` for `sndcmd`.

Local queue indices are small (`4C`, `74`, `114`, `160`, `16F`).

### The scenario message, read out of the code

`testcmd_run_scenario` (440 bytes) builds a 16-byte header plus a payload:

```
header, 16 bytes
  +0x00  0x00940021
  +0x04  0x000000dc
  +0x08  0x00000003
  +0x0c  0x00dc0292        destination
payload
  +0x00  char name[0x20]    32 bytes, memcpy'd
  +0x20  u32  name_len
  +0x24  u32  data_len
  +0x28  u8   data[data_len]
```

Endpoints `0x00dc0292` (register) / `0x00dc0293` (send). The descriptor struct
`testcmd_sndmsg`/`testcmd_rcvmsg` use: `u32 id` at `+0`, a flags byte at `+0x0c`
whose bit 0 selects the synchronous call, source id written back at `+0x14`.
Return codes `0xfffffb01`–`0xfffffb06`, `0xfffffc00`/`0xfffffc01`.

The name is truncated at 32 bytes by that `memcpy`, and validation is only
`strchr(name, ' ')` — so a 32-character name containing `../` is accepted by the
sender. Whether the receiver joins it into a path is the open question.

## 6. `im.elf` — the control plane

`/usr/bin/im.elf` (23,240 B), **PID 157**. Imports:

```
dlopen dlsym dlclose dlerror        IMDB_find_entry IMDB_get_entries IMDB_find_target_bit
mount umount mmap munmap statfs      Backup_read Backup_write
fork waitpid putenv syscall signal   osal_* (snd/rcv/reg/valloc/free, osal_snd_sync_direct)
```

It **mounts every filesystem on the device**, using `dnflasha3`/`dnflasha15` for
`/setting` and `/system` while also listing `nflasha3` — two backing stores for
the same mount point. It runs `/sbin/dosfsck -Y` for vfat and `/usr/bin/e2fsck -y`
for ext2, spawns `/usr/bin/sen.elf &`, and can reboot via `/sys/power/state`
(`warm`, `mem`).

Build-selection keywords: `boot=` `bootall` `target=` `app_argv=` `cipa` `qemu`
`usbj` `cho` `normal` `nodebug` `notrace` `test` `killall` `imdb` `jem` `imssi`
plus `lazy-global` / `lazy-local` / `now-global` / `now-local`.

### `libIMDB.so` is the application manifest

37,044 B. Exports `IMDB_find_entry`, `IMDB_get_entries`,
`IMDB_find_target_bit`, and the data symbol `imdb_raw` — **132 bytes of `u16`,
66 words, nine of which are offsets into `.rodata`:**

```
0x3512 -> "sim"      0x3516 -> "usbj"     0x351b -> "resub"
0x3521 -> "adjust"  0x3528 -> "test"     0x3532 -> "default"
0x353f -> "qemu"     0x3549 -> "nfs"      0x3552 -> "set"
```

(The tenth non-zero word, `0x0002`, is a count, not an offset — reading strings
there yields `LF`.)

**174 libraries, 16 kernel modules, 22 absolute paths**, in boot order. Full list
in `research/firmware/app_manifest.txt`. Head:

```
libIMDB.so               the manifest itself
libosal_uipc.so          the message bus
libosal_utm.so
libosal_ulogio.so
libInfraInterchipDatatrans.so
libNVM.so                NVM_Initialize
libbackup.so             backup_user_suspend
libSaveLoadSettings.so   infra_saveLoadSettings_init
libbkdmn.so              BkDmn_init
libOnDemandLoader.so     odl_init
```

Two application entry points: **`appFw.so` → `Application_System_Init`** and
**`gui.so` → `DPro_App_UI_init`**. The remote stack is all initialised from the
same list: `libInfraRemote.so`, `libInfraRemoteControlNet.so`,
**`libInfraWebApi.so` → `InfraNetWebApi_init`**, `libInfraRemoteCtrlCGI.so`,
`libInfraLiveViewClient.so`, `libInfraNetLiveStreaming.so`, `libInfraFtpClient.so`,
`libInfraFileTransfer.so`.

`im.elf` prints the record it is working on:

```
IMDB @ %p   .type=0x%08x  .taregt=0x%08x  .flag=0x%08x
            .me=0x%04x    .psid=0x%04x
            .file : "%s"   .init : "%s"   .exit : "%s"
            .sus  : "%s",  .res  : "%s"   .inact: "%s"  .act : "%s"
```

`.me` and `.psid` are 16-bit and are exactly the small queue indices in
`/proc/osal/uipc`. So the manifest records name the message-queue ids their owners
serve.

## 7. The application is not deployed

Present in `/usr/lib` — the **assets**:

```
libObj.so          21,305,456
CautionConfig.so   17,694,160
viewUnified2.so    14,284,732
libmpr.so          13,021,036
libInfraRemote.so   8,708,516
```

Absent — the things that would **drive** them:

| file | manifest symbol |
|---|---|
| `appFw.so` | `Application_System_Init` |
| `gui.so` | `DPro_App_UI_init` |
| `libNVM.so` | `NVM_Initialize` |
| `libSaveLoadSettings.so` | `infra_saveLoadSettings_init` |
| `libInfraWebApi.so` | `InfraNetWebApi_init` |

Also absent: everything under `/usr/local/lib/` (which is empty),
`/usr/bin/WebApiLauncher.sh`, `qsi.elf`, `network.sh`, and every `/kmod/*.ko`.

`libObj.so` is a **library, not a program**: `e_type=ET_DYN`, `e_entry=0x10fee0`,
no `main`, no `_start`, no `.interp`, 1,953 exports. `camuser.elf` (21,305,528)
is the program: `main` (30), `_start` (49), `/lib/ld-linux.so.3`, `libc.so.6`,
`libstdc++.so.6`, links `libObj`, exports `Application_System_Init`. Its section
table is unreadable by pyelftools (`expected 4, found 0`) but a raw byte search
shows an ordinary dynamically-linked ARM ELF.

## 8. The command vocabulary

Two id spaces, and conflating them is what stalled the work:

```
0x00dc0000   bus endpoint (liro/RTOS)  <- what sndcmd addresses
    +-- 0x2004, 0x0101, 0x0301 ...     <- command ids inside the message
```

### Scenario plugins: 96 ids from 35 `.so`

`/usr/scenario/*.so` — 35 shared objects, 543 KB, each exporting one function
`scenario_run`. Not `/usr/share/scenario/`.

| framework | plugins | shape |
|---|---:|---|
| `DataflowInfra*` | 18 | raw OSAL messages; `SendASync(uint, DataflowInfraMsg*)` — one id |
| `MWF::*` | 8 | `ObjIf`, `ObjMsg`, events, pins; **two** ids, category + message |
| neither (thin) | 9 | dispatch, or straight to `libtestcmd`/`libIMDB` |

| group | uses | values |
|---|---:|---|
| `0x0___` | 139 | `0x101` `0x115`(6) `0x141`(4) `0x295`(4) `0x301`(16) `0x303`(8) `0x313`(12) `0x401`(12) |
| `0x1___` | 54 | `0x1001`(10) `0x1002`(8) `0x1005`(4) `0x1102`(5) `0x1106`(6) `0x1317`(2) |
| `0x2___` | 93 | `0x2001`(17) **`0x2004`(76)** |
| `0x3___` | 10 | `0x3001`(2) `0x3003`(5) `0x3006` `0x3023` |
| `0x8___` | 55 | `0x8001`(7) `0x8102`(10) `0x8301`(7) `0x8313`(6) `0x8401`(6) |

**`0x2004` — 76 uses, the most common id in the entire vocabulary — is
`PIN_SOUND`**, the audio dataflow pin. Not derivable from the numbers.

### `libSysDef.so` tables (3.2 MB, 18 exports)

| table | stride | shape |
|---|---:|---|
| `m_cateTbl` | 8 | `{u32 id, u32 name}` |
| `m_objTbl` | 12 | `{u32 id, u32 CATEID_*, u32 Obj*}` — **two** names per record |
| `m_pinTbl` | 16 | `{u32 id, u32 aux, u32 name, u32 name}` |

**33 categories.** `0x1000`–`0x1600` is the application layer; `0x6100`–`0x6112`
is infrastructure, and it is the remote stack from the manifest — including
**`CATEID_INFRA_WEBAPI` at `0x610e`**.

**45 objects**, joining exactly against `libObj.so`: **25 implemented** (one
`Obj*_RegisterCommand`/`_UnregisterCommand` pair each) and **20 declared-only**,
with **zero orphans in either direction**.

**12 pins:** `0x2001` YC, `0x2002` PANEL, `0x2003` LINE, `0x2004` SOUND,
`0x2005` REC_CNT_INFO, `0x2006` PB_CNT_INFO, `0x2007` MEDIA_STATUS,
`0x2008` STILL_DATA, `0x2009` EDIT_INFO, `0x200a` CAMERA_STATUS,
`0x200b` IMPORT_CNT, `0x200c` EXPORT.

**`0x2000` is `CATEID_PIN`**, established from the dispatch code in
`MWF::ParamDump::ConvMessageId` (vaddr `0x24176`):

```
00024190  cmp.w r6, #0x2000    ; category == 0x2000?
00024194  beq   #0x2419e       ; -> MwfTbl::PinMsg2Name(msgId)
00024196  cmp.w r6, #0x3000
0002419a  bne   #0x241b2
000241a0  blx   #0x1bdd0       ; -> MwfTbl::PinMsg2Name
```

### `libMWF.so` core tables

`m_baseMsgTbl` (12) — lifecycle for category `0x3000`: `0x1000` UNKNOWN,
`0x1001` NONE, `0x1002` START_OBJ_CMD, `0x1003` STOP_OBJ_CMD, `0x1004`
KILL_OBJ_CMD, `0x1005` START_OBJ_CMP, `0x1006` STOP_OBJ_CMP, `0x1008`
RESUME_OBJ_CMD, `0x1009` SUSPEND_OBJ_CMD, `0x100a` RESUME_OBJ_CMP, `0x100b`
SUSPEND_OBJ_CMP, `0x100c` ALL.

`m_pinMsgTbl` (11): `0x1000` OPEN, `0x1001` CLOSE, `0x1002` DELIVER, `0x1003`
NOTIFY, `0x2000` REQ_OPEN, `0x2001` REQ_STOP, `0x2002` REQ_DELIVER, `0x2003`
REQ_NOTIFY, `0x3000` CONNECT, `0x3001` DISCONNECT, `0x3002` DISCONNECTPIN_CMP.

`m_pinParamTbl`: `0x1000` PIN_TYPE, `0x1001` PIN_NUMBER, `0x1002`
PIN_DIRECTION, `0x1003` PIN_DATA. `m_pinDirTbl`: 0 IN, 1 OUT, 2 INOUT.

### The `APICD_*` registry

File offset **`0x13ec720`** in `libObj.so`, `{u32 id, u32 name_vaddr, …}` at
**stride 36**, **115 records**, contiguous from `0x1000`. Selected:

```
0x1000 APICD_CREATE_HNDL           0x1014 APICD_END_CHANGE_HNDL_STATUS
0x1001 APICD_DESTROY_HNDL          0x1015 APICD_SET_CONTENT_CONDITION
0x1002 APICD_GET_HNDL_ATTRIBUTE    0x101e APICD_GET_DCF_FILE_TYPE
0x1003 APICD_GET_ITEM_ATTRIBUTE    0x1022 APICD_GET_CONTENT_PROPERTY
0x1004 APICD_SET_RESUME_POS        0x1024 APICD_GET_CONTENT_EXTENT
0x1005 APICD_GET_RESUME_POS        0x102a APICD_END_GET_LOCATION_ITEM_IN_RECTANGLE
0x1006 APICD_CLEAR_RESUME_POS      0x1036 APICD_GET_CONTENT_FILE_TYPE
0x1008 APICD_GET_CONTENT_POS       0x103c APICD_GET_CONTENT_PROFILE
0x100a APICD_GET_CREATED_HNDL_PARAM 0x1048 APICD_CHECK_CONTENT_EXIST
0x100b APICD_CONV_HNDL2ENTRYID     0x1054 APICD_GET_FOCUSED_CONTENT_POS
0x100c APICD_REG_AVAILABLE_MEDIA   0x2001 APICD_CONTENTLIST_DESTROY_ID
0x100d APICD_UNREG_AVAILABLE_MEDIA 0x2003 APICD_CONTENTLIST_DEL_ENTRYID
0x100e APICD_COPY_HNDL             0x2005 APICD_CONTENTLIST_DEL_ALL_ENTRYID
0x100f APICD_GET_HNDL_STATUS       0x2007 APICD_CONTENTLIST_IS_EXIST_ENTRY
0x1010 APICD_REG_NOTIFY_TARGET     0x2009 APICD_CONTENTLIST_GET_ENTRY_POS
0x1011 APICD_UNREG_NOTIFY_TARGET   0x3001 APICD_CREATE_CONTENT_POS_HNDL
0x1012 APICD_BEGIN_CHANGE_HNDL_STATUS
0x1013 APICD_RUN_CHANGE_HNDL_STATUS
```

The database category `0x6000` maps 48 `libNetContUtil.so` client methods onto
these; `0x81000` = `createRootHandle`/`createChildHandle`, `0x81002` =
`getObjectNum`/`getMediaId`/…, `0x81003` = `getContentType`/`getItemDate`/…,
`0x82008` = `getHandleFromContentList`.

### The IMCFG device table in `libObj.so`

Found by searching for `0x1001`, which returned three hits exactly 20 bytes
apart — a table, not code. 16 `u32` ids followed by ASCII, then **70 device
names**:

```
IMCFG   VER:109 CATEGORY:MAIN TYPE:COM CXD:COM

/dev/ms    3     /dev/mmc  13     /dev/sata  9
/dev/nflasha  32   /dev/sd  4     /dev/sr  2     /nondev/  7
```

The `/nondev/` entries — `dvdmenu`, `simulate`, `pcremote`, `air`, `streaming`,
`iptc`, `ipremote` — are **media sources with no block device behind them**.

The id array contains `0x1001` but **not** `0x1022`, `0x102a`, `0x81000` or
`0x81003` — a different, overlapping space, not the registry the plugins draw
from. It also holds an unnamed `0x4xxx` group (`0x4000`, `0x4100`, `0x4200`,
`0x4300`, `0x4400`).

### `DefInh::sm_refTbl` geometry

3,158,400 B — 96.7% of `libSysDef.so`, an exported data symbol.

```
DefInh::GetFactorIdMax()   -> movw r0, #0x18fd   = 6381 factor ids
DefInh::GetFactorTblMax()  -> movs r0, #0xc8     = 200 table slots
```

Neither divides the size, but **3,158,400 / 800 = 3948 exactly**, and 800 is
visible in the data: the first non-zero byte after the leading word is at
`+0x320`, then `+0x640`, then `+0x960`.

- 3,948 records of 800 bytes; 88.2% populated; 2.1% of bytes non-zero
- 24 field offsets in use, none above 20.5% of records
- fields-per-record is **bimodal**: 1,610 records carry one non-zero word,
  thinning to a minimum near 40, then rising to a second cluster at 64–70, one
  record with all 200 → **tagged union**

> **Retracted:** reading record 1's `+160`/`+164` pair as a signed 24-bit
> min/max range. Records 39–44 put `0x01000000/1`, `0x02000000/2`,
> `0x04000000/4` there — a doubling sequence. The fields are independent.
> **Pattern-matching a single record is the error this project keeps making.**

## 9. `av-cam.bin`

17,289,388 B. **A raw binary, not an ELF** (`0a 00 00 ea 4f 52 49 4c` — ARM code
then `ORIL`), no relocations, no section headers. 4 KB plaintext LIRO header
stub; `size mod 16 = 12`, not AES-ECB aligned. 2,459 of 4,221 4 KB blocks are
below 6.5 bits/byte and the readable region spans the whole file.

**Load base `0x635C6000`** (VDF range), solved from RTTI name pointers
(375/400 validated) and corroborated by the ORIL init table.

A pointer to a string or table is built in two instructions:

```
ldr  rX, [pc, #imm]      ; pool word is a FILE offset, not an address
add  rX, pc              ; rX = pool + pc  ->  the file offset
```

**Do not apply the load base** (both are file offsets), and **`pc` is `addr + 4`,
not `Align(PC,4)`** — the aligned value lands 2 bytes low.

161,595 strings. Subsystem counts: sen=920, codec=445, DFE=286, LIF=271, face=317,
mag=476, hdmi=83, cec=90, backup=222, lens=268, iris=186, zoom=165, dmm=162,
stream=147, SEC=115, sign=89, key=62, diag=441, Ver=374, liro=414.

`CMD_ID_SDF_*` (12) is a media/still/codec pipeline lifecycle:
`_OPEN _CLOSE _EXEC _INPUT _OUTPUT _START _STOP _PAUSE _CANCEL _RESTART _ALL
_UNKNOWN`, with `SDF_ERR_*` / `SDF_INTRA_ERR_*` / `SDF_RECMODE_*` (57 codes).
**`_EXEC` is the obvious target** and what it accepts is unvalidated/unknown.
164 `Exec*` dispatch symbols across `ExecApi* ExecSens* ExecSdf* ExecJpeg*
ExecMovie* ExecRc* ExecTanz* ExecVfx* ExecPin*` plus `ExecGuard`/`ExecGard`
(guarded execution). **No numeric opcode table exists in the plaintext strings** —
the ids live in code.

### VDF display methods, string-resolved

| method | file offset | insn |
|---|---|---|
| `VdfDisplayCmdSetOsdAlpha::Execute` | `0x00150A9C` | 74 |
| `VdfDisplayCmdSetOsdAlpha::Activate` | `0x0015091E` | 1 |
| `VdfDisplayCmdSetPanelOsdLuminance::Execute` | `0x00151360` | 75 |
| `VdfDisplayCmdSetPanelOutPin::Execute` | `0x00151450` | 386 |
| `VdfDisplayCmdSetPanelReverse::Activate` | `0x00151CBA` | 52 |
| `VdfSrvcDrawOsdManager::Execute` | `0x00178892` | 86 |
| `VdfInputCmdUpdateYuv::Execute` | `0x001681A0` | 32 |
| `SystemCmdPinSend::Execute` | `0x00184938` | 468 |
| `SystemCmdSysv::Execute` | `0x00185534` | 331 |
| `SystemCmdDebug::Execute` | `0x001803AE` | 1447 |

`SetPanelBrightness` is at `0x00150BA8` (313 insn, 30 calls) — strong but not
string-proven.

A display command needs **two live interface objects** and walks vtable offsets
`0x44c / 0x454 / 0x45c / 0x4bc / 0x4d4 / 0x670 / 0x6cc / 0x858`. The vtable is
therefore >`0x858` bytes. **Fabricating those is a hard hang, not a visible
effect.** The message-post helper is `0x0072F47C`; callers pass
`r0 = 0xEEEEEEEE` as a "no sender" sentinel, `r1 = value`, `r2 = context`,
`r3 = command id`.

Brightness is a **table lookup**: `table[brightness]` at file `0x0087D7E4`, 16.16
fixed point, +`0x10000` per entry in 16-entry rows — a colour/scale LUT, **not** a
monotone curve.

**Vtable slots do not identify methods.** The vtables at `0x00FBB0F8` decode
cleanly at `(stored & ~1) - BASE` and slot `[-1]` matches the typeinfo, but
`SetPanelReverse` slot `[5]` is `0x0071E632` while its `Activate` is `0x00151CBA`.

## 10. File formats

### `.uxc` / `.uxb` / `.uxa` container

```
0x00  3 bytes  magic 'uxc' | 'uxb' | 'uxa'
0x03  u8       format version (7)
0x04  3 bytes  zero
0x07  u8       zero
0x08  u16      stream version: 8 for .uxc, 9 for .uxb/.uxa
0x0A  u16      0x004a  (file-specific, NOT a checksum)
0x0C  u16      control = one past the highest id
0x0E  u16[]    sparse id->slot index, 0xffff = absent
```

```
index_count = control & 0xff
data_start  = align4(0x10 + 2*index_count)        .uxc/.uxb
data_start  = 0x10 + 4*index_count                 .uxa/.uxb (four-byte index)
```

Verified: 302/302 files, and **12,082 of 12,082 non-absent index entries land
inside the file** (727 absent). **`0x0c` is the control; `0x0a` is `resource_id`.**

Hierarchy: header → u16 index → 4-byte-aligned body → 60-byte section descriptor
(`w10 == w9`, 1,240 descriptors, 0 exceptions) → object offset table
(`offset[0] == 1 + 2N`) → 14-byte object header → properties.

### `color_cmn.uxc` — the palette, 312 bytes

28 records of exactly 8 bytes at `0x58..0x137`:

```
+0  u16  id       sequential 0x4000..0x4022
+2  u16  const    0x3a09 in every record
+4  u8   r  +5 g  +6 b  +7 a
```

| id | rgba | | id | rgba |
|----|------|-|----|------|
|4000|`ffffff`| |400f|`33333380`|
|4001|`dddddd`| |4010|`dd5500`|
|4002|`00000099`| |4011|`dd5500`|
|4003|`00000088`| |4012|`dddddd`|
|4004|`dddddd`| |4013|`dd6600`|
|4005|`dddddd`| |4015|`dddddd`|
|4006|`dddddd`| |4017|`00000099`|
|4007|`dd0000` red |4018|`00000044`|
|4008|`00dd00` green |401b|`000000cc`|
|4009|`0000dd` blue |401f|`dddddd`|
|400a|`cccccc80`| |4020|`dddddd`|
|400b|`cccccc80`| |4021|`ffffff`|
|400c|`33333380`| |4022|`0000004c`|

**No checksum exists** in the file, so a single-quad edit cannot be rejected on
integrity grounds — the only risk is semantic. There are 28 non-absent index
entries into a 28-record body: a 1:1 map.

**Hardware-verified authoritative:** `0x400c` `333333`@80a → `0000dd`@80a changed
the live-view framing guides grey→blue; `ff00ff`@80a made them **magenta**, and
magenta appears nowhere in Sony's palette, so nothing but entry `0x400c` can
explain it.

### `style_cmn.uxc` — two interleaved record families

| | count | stride | marker | indices |
|---|---:|---:|---|---|
| base | 26 | 36 | `a0 07 26 08` | `00`–`0b`, `1f`, `23`, `24`, `27`, `31`–`3a` |
| extension | 34 | 24 | `a0 07 26 06` | `0c`–`22`, `25`, `26`, `28`–`30`, `3b` |

26 + 34 = **60 = the control low byte.** The extension indices fill exactly the
gaps in the base set. Class count is **278** under strict invariants (a looser
descriptor predicate gives 279 — a parsing-strictness difference, not a format
disagreement).

`style_cmn.uxc` contains **no `0x40xx` palette ids at all** — styles inline their
own RGBA. 186 aligned 4-byte quads across 301 files match a palette colour,
**9,212× above chance**, but the record is a variable-length TLV and unsolved.

### View files

| claim | result |
|---|---|
| section descriptor (high byte `0x7e`) | 214/214 files, 1,240 sections, **0 misses** |
| `offset[0] == 1 + 2N` | 1,240/1,240 valid |
| objects indexed | **10,640** |
| largest `N` (a u8) | 83 |
| property records walked | 49,287 |
| distinct signatures | 92 |

**No view file carries a colour.** 211,844 u16 windows examined; 279 land in
`0x4000..0x4022`; **113 expected by chance → 2.5×, not enriched.** The colour
reference is compiled into the rendering code. Geometry, layout, text,
visibility, z-order, state and event bindings remain fully editable.

### `global.xdb` — the view index

`uxa` container, 239 entries, magic in `viewUnified2.so`'s string table. Record:

```
09 00 <id:u16> | 01 20 00 00 | 00 00 00 00 | 80 "<filename>" NUL pad
```

id == entry index throughout; 236 of 239 carry a filename. `field@04` is a kind:
`0x00002001` on 225, `0x00004002` on 9, `0x00044022` on 2. `offset[0]` is 0, so
`data_start = 0x10 + 4*239 = 0x3cc`.

Names `color.uxb`, `lang.uxb`, `style.uxb` — **`color.uxb` and `color_cmn.uxc` are
the same file.**

**76 files on disk are not indexed:** 68 `string_<language>.uxc`, 8 `image_*.uxc`.

### `string_english_f.uxc` — the UI string table

349,020 bytes → **7,190 records**. Framing: 2-byte id, constant marker `1b 1e`,
NUL-terminated text with alignment padding; the low id byte increments.

```
81 ac 1b 1e "Memory"      82 ac 1b 1e "MENU"       a5 b2 1b 1e "JPEG"
50 a4 1b 1e "DRO"         0d b5 1b 1e "MAC Address"
```

7,190/7,190 markers found; 7,189/7,189 ascending id steps; ids `0xa000`..`0xbc19`;
**round-trip byte-exact, 349,020 = 349,020.**

`string_english.uxc` has **zero** `1b 1e` records — it is the help-text file in a
different format. **The `_f` suffix is the string table.**

### Other files in `/usr/share/app`

| file | bytes | |
|---|---:|---|
| `global.xdb` | 12,252 | the view index |
| `lang.uxb` | 2,896 | `uxb` |
| `style.uxb` | 540 | `uxb` |
| `area_check_data.dat` | 1,174,103 | magic `UXAC`, unexplored |
| `fontlist.dat` | 360 | `NAME<9>path`, e.g. `FONT_UNIVERS` |
| `Sony_DI_Icons.ttf` | 619,664 | `OS/2 VDMX cmap gasp glyf head hhea hmtx name post` |
| `*.ltt` × 3 | 611k–924k | Monotype font-linking bundles |

The engine is a family of seven: `viewUnified2.so` 14,284,732 (the one that
opens `global.xdb`), `4` 3,287,604, `3` 941,232, `5` 749,136, `6` 589,336
(15.4× enriched), `7` 579,944, `8` 283,208.

### The icon font

`Sony_DI_Icons.ttf`, registered as `FONT_ICONS`. 1,732 glyphs, no checksum table,
no key table, no unknown addressing scheme — the first target where that is true.

```
std     md5 1dffdb46352f91c7b484a4b75cf1905f  619,664 B
patched md5 b1e5d23e9d69b269b785b9155688f351  614,336 B
```

138 glyph outlines replaced; cmap 1,684 entries identical; advance widths moved 0;
1,594 non-target glyphs byte-identical.

## 11. Verified changes on the device

| file | before | after | note |
|---|---|---|---|
| `/usr/share/pmbp/DeviceInfo.xml` | `325881bdde84eb36d006ba13efb54eb5` 517 B | `9b2d8cc0f59d9b82c69e1f8e2478e545` 517 B | 12 bytes: `1.3.00.19200`→`9.9.99.99999`, `1.0.00`→`9.9.99` |
| `/usr/share/app/string_english_f.uxc` | `349711603d2e16c1fc620e4e8bf30be0` | `9853d47ad4197d3387f10babdc8728b9` | 24 bytes: `Playback`→`OPENCODE` at `0x041bb0`, `0x0476dc`, `0x04cbc0` |
| `/usr/lib/libtestcmd.so` | stock | `f370de888ae662e7f509f2274846eac6` restored | 66-byte code-exec proof, reverted |
| `/setting/Backup.bin` | `bdc524e5cdcf3b290aed1c9271ccf921` | — | staged on the card |

The first two are **md5-verified on the camera and never seen on screen** — the
application that would draw them is not deployed. An 8-byte slice at `0x041bb0`
md5s to `04fbbbde1afb0c4bafde6ba5ce069ac6` = md5 of `OPENCODE`, not `Playback`
(`8dc55bfc…`).

## 12. USB and the lens bus

| PID | mode |
|---|---|
| `0x0d95` | mass storage — the entry point |
| `0x0336` | service mode, after `senserShellCommand` |
| `0x994` | **updater mode** — drives `FirmUpReq` / `CASND LUPDT_*` over CAIF |
| `0x05dc` | PTP |

The raw host tunnel (`sony_cmd.py`) is a `USBC` CBW header plus a 68-byte
`cam_struct`: **command `code` at struct offset `0x0b`**, payload length at
**`0x1c`**, code `0x12` = a query.

```
PC --USB tunnel--> camera host bridge
        v
   LensFirmUpdate / Lens handler (av-cam.bin)
        v  CAIF   [CA->EN] / [EN->CA]
        v  LIF    low-level UART, 750k baud default
   [LC->LENS] / [LC<-LENS]   E-mount serial
```

`ldec.ko` and `ldec` are unrecoverable — statically allocated core, loaded from
the ramdisk, freed after boot.

`/lens/VX<id>_lensfile.bin`: `LF` magic, version, `lens_id` @+14, `ED` block of
int16 coefficient sections. 61 samples on the camera.

## 13. The updater door

`crypter.elf` (39,084 B) `.rodata`, in order:

```
le.cpp
/tmp_updater/updater
/tmp_updater/updater/bodyimg
/usr/bin/udtrbody.bin
/root/IAMUPDATER
/tmp_updater/updater/bodyfs
/tmp_updater/updater/bodyfs/bodylib/libupdaterbody.so
```

Body magic `0100UDTRFIRM`; the body is Compressed ROMFS (magic `453dcd28`).
`/usr/bin/udtrbody.bin` is 143,360 B, writable. Integrity check is
`CrcChecker` / `uc_crc32sum.elf` — **CRC, forgeable, not a signature.**

**No disassembly is needed to pick the symbol.** `crypter.elf` contains exactly
two plain unmangled C identifiers: `Dec_ScrambleInit` (`0x1d7f`) and `Fsys_Init`
(`0x1e12`, `0x67eb`). A replacement library can **export both** and whichever is
looked up resolves.

`/usr/tool/` is not empty: `LeakCheck` (689 B), `LeakTracer.so` (31,128 B,
exports `malloc` `free` `realloc` `lt_malloc` `lt_calloc` `new_slot` `del_slot`),
`libjemalloc_tsh.so.1` (115,504 B). `init` will `LD_PRELOAD`
`/usr/tool/libsonyefence.so` or `libduma.so` depending on its checks, and
`/usr/tool/` is on the persistent writable `/usr` — so which allocator the
application runs under is a **file-level decision**.

`change_mode.sh` supports `echo 3g > /setting/mode/dmode` (target gdb),
`3s` (gdbserver) and `3p` + `PRELOAD_FILE=/setting/mode/preload`
(LD_PRELOAD). All three are Sony's own debug entry points.

## 14. Network

```
26: p2p-p2p0-0   inet 192.168.122.1/16   scope global
udp  0.0.0.0:67  -> the DHCP server, the only listening socket
```

**Nothing on TCP at all.** `wlan0` and `p2p0` carry only IPv6 link-local. The
remote stack exists in code (`libInfraRemote.so` 8.7 MB, `ObjRemote`,
`ObjRemoteAsync`, `libcurl`, `libssh2`, strongswan, an `openssl` binary exporting
`app_http_tls_cb`) but **none of it is listening in service mode.**

The camera runs a **WiFi Direct group owner on `192.168.122.1`** and hands out
DHCP leases. Sony cameras expose an HTTP control API on that link. The cheapest
untried route; the PC is not associated with that radio.

## 15. Camera-side essentials

- BusyBox 1.34.1 ash, built **without** `base64`, `stty`, `md5sum`, `df`, `tr`,
  `head`, `which`. Use `busybox <applet>` — which does reach `md5sum`, `tail`,
  `dd`, `od`. `/tmp/busybox` looks like a busybox and is a **zero-byte file**.
- `xxd` / `tr` / `head` / `wc` are listed by `busybox --help` but **not linked**.
- `busybox xxd -r -p` is unusable: 132 hex chars → 30 bytes.
- Write binary with `printf '\200\265...'` (3-digit octal) and slice with
  `busybox tail -c +N` / `dd bs=1 count=N` (`dd skip=` produced a 0-byte file).
- `dd` has **no `conv=notrunc`** — any `dd of=<live file>` truncates. Use `cp`.
- Mount the card: `mkdir -p /tmp/sd; mount /dev/mmca1 /tmp/sd`. `/proc/partitions`
  calls it `mmca10p1`; `/dev/mmcca1` is a different controller and fails.
- Commands are bounded at **~1,022 characters**; a 4,000-char command is accepted
  and **silently discarded**. stdin is not length-limited — stream base64 there
  with `stty -echo` first.
- `remount /usr` rw persists across reboots.
- PowerShell eats `$` in camera commands: `echo RC=$?` arrives as `RC=\True`.
- The shell wrapper truncates the console at **25 lines**. Read
  `zve10_shell.log` in the repo root, not the console.

## 16. `sndcmd` / `rcvcmd` / `testcmd`

```
<options> [osal_id] [size]:[data] ...
  --ver --ifile --ibfile --obfile --ulogio --sync --sid
  size   b | w | d | digit
  data   decimal or hex(0x) or string
```

Default `--sid` `0x00dc0000`. `rcvcmd.elf` takes `--ifile`, `--tmo <ms>`,
`--sync`. Payload files are **`key:value` fields, hex-encoded**, read until the
requested byte count is satisfied. The header is 32-bit little-endian with the
total length at offset **`0x2c`**.

`libtestcmd.so` is version 1.7, built Mar 15 2025. GCC 4.5.1, glibc 2.4, Thumb.
It disassembles offline with full section headers — unlike `av-cam.bin`.

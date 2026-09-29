# What is actually on the camera, and how it links together

Produced by `research/firmware/elf_catalog.py` over 648 ELF files in the dumps.
Everything below comes from ELF headers and symbol tables — no disassembly. The
full 520-name export list is in `research/firmware/libobj_exports.txt`.

Where a claim here did need the code read rather than just the tables — the
`libIMDB.so` manifest, the `im.elf` control plane, the scenario message
layout — the method and its traps are in
[RE_METHOD.md](RE_METHOD.md).

## Why inventory before conclusions

Three load-bearing claims in this project were inherited rather than checked, and
all three were wrong: that `av-cam.bin` was encrypted, that `libupdatercommon.so`
was encrypted *and contained the UIPC endpoint*, and that `/usr/bin` was read-only
squashfs. Each was cheap to test and each would have cost hours if believed. So:
measure first.

The filesystem is entirely ARM — ELF32, little-endian, `e_machine=40`, 182 `DYN`,
103 `REL`, 41 `EXEC`. 153 files carry ELF magic but have a section table pointing
past EOF; they are containers, and the catalog records them rather than aborting.

## The spine: libosal_uipc.so

**`libosal_uipc.so` is needed by 166 of the catalogued binaries** — more than any
library except libc. It is linked into essentially every service-side executable
and into all 59 scenario plugins. Its exports are the send/receive API:
`u_osal_snd_sync_direct`, `osal_snd_sync_msg`, `u_osal_reg_sync_msg_queue_cb`,
`free_fblock`, `vpool_free`, `u_osal_wai_sem_tmo`.

That is the bus between the service Linux and the camera application, and
`libInfraBluetoothCore.so` sits on it too, exporting `UIPC_SendBuf` and
`uipc_avk_init`. This is the `sndcmd.elf` path that already returns RC=0.

Other hubs: `libbackup.so` (68), `dataflowInfraFramework.so` (46), `libosal_utm.so`
(41), `libMWF.so` (29), `libtestcmd.so` (20).

## The application: libObj.so

**`libObj.so`, 21,305,456 bytes, `DYN`, ARM, 1,953 exports, 1,939 imports.** It is
needed by nothing — it is the root, `dlopen`ed by the application — and it is the
single most informative file on the camera. Its 520 unmangled C exports fall into
five layers.

### 1. `Obj*` — the subsystem plugin contract (17 groups, ~6 functions each)

A uniform lifecycle, repeated for every subsystem:

```
ObjRenderer        ObjPlayer         ObjMedia          ObjDisplay
ObjEditor          ObjMetaRecorder   ObjStillRecorder  ObjMovieRecorder
ObjFaceRecorder    ObjConverter      ObjSalvage        ObjFtpClient
ObjDubbing         ObjSpeaker        ObjMic            ObjGenlock
ObjEffect          ObjAvAdjCtrl      ObjCntMgr         ObjRemote
ObjRemoteAsync     ObjCamera         ObjCameraAgent    ObjMixer
ObjMediaServer     ObjNetMediaServer ObjNetSetting     ObjStreamingUsb
ObjImporter        ObjHandover       ObjSystemSound
```

each with `_Create / _Init / _Destroy / _Exit / _RegisterCommand /
_UnregisterCommand`. Every subsystem registers its commands into this one
registry, so the export list *is* the camera's command surface.

### 2. `Model*ToInstance` — the screens (~150)

One entry point per UI view: `ModelMovieRecToInstance`, `ModelFocusToInstance`,
`ModelFormatToInstance`, `ModelCautionToInstance`, `ModelLiveViewTransfer…`,
`ModelDlnaServerToInstance`, `ModelUsbMtpToInstance`, `ModelFirmupExtDvd…`.
This is the layer `viewUnified2..8.so` supply, and the `global.xdb` view index
indexes it.

### 3. `Ts*` — the text and font layer

This is the one that matters for the icon-font problem:

```
TextRM_createText   TextRM_drawText   TextRM_getBounds   TextRM_unloadFont
FsLtt_init          FsLttComponent_init
TsLayoutText_init   TsSimpleText_init TsString_init
TsDrawGlyphParams_init
TsOtGlyphID_init  TsOtHhea_init  TsOtOS_2_init  TsOtClassDef_init
TsOtCoverage_init TsOtFeatureList_init TsOtLookupList_init
TsOtScriptList_init TsOtDeviceTable_init TsOtWordBlock_init TsOt_post_init
```

`TextRM` is the text renderer. It loads fonts through **`FsLtt`** — the `.ltt`
bundle system that `fontlist.dat` points at. The `TsOt*` family is an OpenType
table parser: the application reads `hhea`, `OS/2`, `cmap`, `classDef`, `coverage`,
`featureList`, `lookupList`, `scriptList` and `deviceTable` **itself**, rather than
through a library. That is why a plain TrueType file with no checksum table was a
reasonable thing to patch — and it is also where glyph selection actually happens.

### 4. `GRM` (17) and `MTX` (7) — graphics and packing

```
GRM_bitmapGetPhysicalAddress  GRM_screenGetOnBitmap
GRM_fbrmPrepareUpdateYUV      GRM_bitmapCreateComposite
MTX_TABLE_COMPRESS_Destroy    MTX_RA_TT_Create / MTX_RA_TT_Destroy
MTX_BITIO_Create              MTX_RA_DECOMP_Destroy
```

`GRM` is the framebuffer. `MTX_RA_TT_*` is a TrueType resource handler — `RA` for
resource archive, `TT` for TrueType. Worth noting next to the font work.

### 5. Entry points and the unified framework

```
Application_System_Init   getModelTree    getModelConfig   getConfig
initializeModelTree       initializeConfig  terminateModelTree  terminateConfig
pViewManager   timerManager   core_sync_set_event   g_pEvtMgr
uniobj_init  unimodel_init  unigi_init  uniinfra_init
SelRegister  SelDeregister  SelGetClientId  SelRegisterWithData
toInstance   toInstanceAC   stella_print_log   testmode_debugPrint
```

`Uni*` is the unified framework that `viewUnified*.so` plugs into. `Sel*` is a
registration layer with an optional data payload. `toInstance` / `toInstanceAC`
are the two generic view constructors.

## The plugin architecture

**313 of 391 shared objects are not `NEEDED` by anything in the dumps.** They are
not orphans; they are `dlopen`ed at runtime. `libOnDemandLoader.so`
(`OnDemandLoaderInitialize`, `odl_init`, `odl_res`, `odl_sus`) is the mechanism,
and the uniform `Obj*_RegisterCommand` / `_UnregisterCommand` pairs are how each
one attaches and detaches. So the library set is a plugin set, and a file being
unreferenced by any `DT_NEEDED` means nothing at all.

The 59 `*_SCN_*.so` plugins in `/usr/share/scenario` are the visible face of this,
each exporting exactly `scenario_run`, driven by `/usr/bin/scenario.elf`:

```
CAMERA_SCN_MOVIE_REC_START        CAMERA_SCN_SET_ZOOM_DRV
CAMERA_SCN_EXTERNAL_RAW_RECORD    CAMERA_SCN_VIDEOLIGHT_SW
CAMERA_SCN_FACE_REC_DATA          CAMERA_SCN_EE_SET_PRM
MPR_SCN_FORMAT                    MPR_SCN_SET_FACTORY_MODE
MPR_SCN_EXEC_FACTORY_MODE         MPR_SCN_EXEC_WIFI_TEST
MPR_SCN_GET_CONTENT_COUNT         MPR_SCN_GET_TOTAL_LOG
MPR_SCN_FLASH_BACKUP_INIT         AVBB_SCN_START/STOP_{AUDIO,VIDEO,MIC,HDMI,…}
```

Named, enumerable, and dispatched by name. `MPR_SCN_SET_FACTORY_MODE` and
`MPR_SCN_EXEC_FACTORY_MODE` are the pair worth understanding first.

## Other subsystems, by their own exports

- **USB device stack:** `libInfraMtpServer` (`mtpw_cmd_GetObjectInfo`,
  `mtpw_ssnmgr_OpenSession`), `libInfraMscServer` (`MassStorageServer_Create`),
  `libptp` (`ptpw_res_OpenSession`, `ptp_check_cmd_header_packet`),
  `libInfraPtpExtCmd` (`PtpExtCmd_Init`), `libusbcmd`
  (`UsbCmd_ExtCmdSvcWrap_Init`), `libInfraExtCmdSvc`, `libInfraStreamingUsb`
  (`StreamingGadget_init`). **The PTP/MTP/MSC stack the PC already speaks is
  userspace here, not in the main firmware.**
- **Remote / network:** `libInfraRemote.so` is 8.7 MB and exports
  `InfraRemote_Init` / `InfraRemote_Exit`; `ObjRemote` and `ObjRemoteAsync` are its
  application-side halves. Alongside it: `libcurl`, `libssh2`, strongswan/ipsec,
  `libInfraDlnaControl`, `libInfraNetConnectionManager*`, `libWlanResource`, and
  an `openssl` binary exporting **`app_http_tls_cb`** and `verify_callback` — an
  HTTP TLS callback, i.e. a server, not just a client.
- **Settings / NVRAM:** `libbackup` (`Backup_read`, `Backup_write_setting_attr`),
  `libIMDB` (`IMDB_find_entry`, `IMDB_get_entries`, `IMDB_find_target_bit`),
  `libBizFw`/`libBizFw2`.
- **Updater:** `crypter.elf` + `libupdatertalk.so` (`Dec_ScrambleInit`,
  `Dec_Scramble`) + `libupdatercommon.so` + `libupdaterufp` (`udtr_*`) +
  `libupdaterufunc` + `libupdatermedia`, and in the body
  `libupdaterbody.so` exporting exactly `GetBody` and `ReleaseBody`.
- **Media:** `libmpr.so` is 13 MB (`smf_AviEn_*`, `smf_AviEa_*`),
  `libmprctrl`, `libInfraMediaCommon` (`mcmn_*`), `libInfraMediaMount`,
  `libInfraMetaSupplier`, `InfraStillPool`.
- **Lens / sensor:** `libInfraLensCommunicator` (`LensCommunicator_Init`),
  `/usr/bin/sen.elf`, `libAK8975` (AKSC_* sensor maths).
- **Location:** `libcompassutil` (`compass_util_GetDirection`), `libgps_rsrc`,
  `PsmGetGenuineTime`.
- **Diagnostics:** `libEMG.so` (`emg_init`, `emg_shortly_reboot`),
  `libosal_ulogio`, `libInfraKikiLog*`, `libInfraAccessLog`, `libMWF`
  (`MWF_Init`, `MonTskInput`, `MonTskOutput`, `MonConPutStr`).
  `/usr/bin` also carries `iperf`, `tcpdump`, `openssl`, `wpa_supplicant`,
  `bsa_server` (Bluetooth), `ud_send_lsi.elf`, `ud_datcnv.elf`.

## What the map changes

1. The camera application is not unreachable. It is `libObj.so` plus
   `viewUnified2..8.so` plus `CautionConfig.so`, all present locally and all
   unstripped enough to read. `dumps/v203/camuser.elf` (21,305,528 B) is the
   matching application binary, though it is one of the files whose section table
   is unreadable, so it is a container rather than a plain ELF.
2. The service side is not the odd one out. `libosal_uipc` with 166 dependents is
   how the service tools and the application talk, and it is a documented-enough
   API surface to use rather than reverse.
3. The font is consumed by `TextRM` via `FsLtt`, with OpenType tables parsed
   in-process by `TsOt*`. That is the layer to read next if the font work
   continues, and it is in a file we have.
4. The scenario plugins are a named, enumerable command surface, which is a much
   better place to look for "reach another subsystem" than a forged library.

## Correction: the main firmware is on this kernel

An earlier note said the camera UI runs on a different CPU from the service
terminal, inferred from `ls -l /proc/*/exe` showing no application. That
inference was wrong, and the reason is a measurement bug: `ls -l /proc/*/exe`
silently skips anything it cannot read, so of 263 processes only 8 distinct
executables appeared. Reading `/proc/*/comm` instead, which is world-readable,
shows the real picture:

```
uipc_dumper      PID 93, stack size 8192  -> a kernel thread
RMCMND-UIPC   x2
ULOGIO_LOGREC x2
liro-kliro_91 .. liro-kliro_99, and 139 threads named liro-*
```

**139 `liro` threads.** LIRO is the RTOS that `av-cam.bin` implements, loaded by
the `liro.ko` module — so the "main firmware" is running on this same kernel as
kernel threads, not on a separate processor. It is reachable; it was simply not
visible through the one procfs field that was being filtered on permission.

## The live bus: /proc/osal/uipc

`osal_uipc.ko` (38,960 B) creates a procfs directory with three nodes:

```
-r--------  1 0 0  0  /proc/osal/minfo
-rw-------  1 0 0  0  /proc/osal/uipc
-rw-------  1 0 0  0  /proc/osal/ulogio
```

The module's strings name the handlers — `__k_uipc_proc_read`,
**`__k_uipc_proc_write`**, `__k_cmd_debug`, and the dump routines `msgq_dump`,
`fblock_dump`, `vpool_dump`, `bsem_dump`, plus `uipc_dumper` as the kernel
thread that services it. So the bus is both observable and configurable.

Read live:

```
OSAL Version 4.2
Compiled at Mar 15 2025 03:07:32
proxy threads=4
log async=1
log sync=0
mia=off

====Global Info====
[] Resource
msgqs   860
sems    198
msgs    16
cbs     1168
misc    377
- fblock        (83744) free=202688
- normal vblock (5568)  698e0000 128512
- realtime vblock
   139(8064)  69800020 8192      <- id(count) address size
   13A(35424) 69802020 81568
   E(896)     69816020 4096
   ...
SEM   A=8192 F=8192
BMSGQ A=4096 F=4096
MSGQ  A=4096 F=4096
[] GSEM   [] GMSGQ   [] LMSGQ   [] LSEM
- dynamic ids
====Process 149====   ====Process 157====
```

`LMSGQ` and `LSEM` — the live queue and semaphore tables — are **empty**, which
is consistent with the bus being idle in service mode. The `- realtime vblock`
entries carry non-zero counts for a handful of ids (0x139, 0x13A, 0xE, 0x3F,
0x414E, …), so something is allocated even though no queue is attached.

`log async` / `log sync` / `mia` are printed as settings and the node is
writable, which is the obvious next thing to try: enable sync logging, run a
scenario, and read back the actual message ids. **Not done yet** — it is a write
into a kernel interface whose command grammar is not known, and guessing at a
`__k_cmd_debug` parser is not a good use of the only shell we have.

## The scenario runner is a real, name-addressed interface

`/usr/bin/scenario.elf` is live and self-documenting:

```
Usage: /usr/bin/scenario.elf <options> [scenario_name] [size]:[data] ...
        scenario_name
                specified scenario name like below
                        /usr/scenario/xxxx.so
```

The plugin directory is `/usr/scenario/` (35 `.so` files) — **not**
`/usr/share/scenario/`, which is what the dump path suggested and which does not
exist on the camera.

It shares the `[size]:[data]` convention with `sndcmd.elf`, because both go
through `libtestcmd.so` (`cmdline_show_usage`, `testcmd_run_scenario`). Each
plugin is a thin shim whose only job is to send one message: for example
`MPR_SCN_EXEC_FACTORY_MODE.so` contains
`Mpr::If::ExecMprUtility(MPR::UtilityCmdId, void*)` and nothing else of substance.

Verified live:

| command | result |
|---|---|
| `scenario.elf MPR_SCN_GET_TOTAL_LOG 4:00000000` | exit 0 |
| `scenario.elf NOSUCH_SCENARIO` | non-zero exit |

The bogus name failing is the control that matters: the runner really does
resolve and load the named plugin, so `LOG_OK` is not merely "the binary
exited cleanly". It does **not** yet prove the message reached the application —
exit 0 is equally consistent with a message queued to an endpoint nobody is
listening on, which is what an empty `LMSGQ` predicts.


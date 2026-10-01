# 03 — Binaries: what is on the camera and how it links together

Produced by `research/firmware/elf_catalog.py` over 650 ELF files in the dumps.
Everything in the catalog sections comes from ELF headers and symbol tables — no
disassembly. The full 520-name export list is in
`research/firmware/libobj_exports.txt`.

Related: [01-hardware.md](01-hardware.md) · [02-service-shell.md](02-service-shell.md) ·
[04-messaging.md](04-messaging.md) · [05-formats.md](05-formats.md) ·
[06-method.md](06-method.md)

- [ELF catalog](#elf-catalog)
- [The spine: libosal_uipc.so](#the-spine-libosal_uipcso)
- [The application: libObj.so](#the-application-libobjso)
- [The plugin architecture](#the-plugin-architecture)
- [Other subsystems, by their own exports](#other-subsystems-by-their-own-exports)
- [av-cam.bin: the RTOS command engine](#av-cambin-the-rtos-command-engine)
- [VDF, the display subsystem](#vdf-the-display-subsystem)
- [The live bus: /proc/osal/uipc](#the-live-bus-procosaluipc)
- [Negative results](#negative-results)

## ELF catalog

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

**123 of the 165 readable shared objects are not `NEEDED` by anything.** They
are not orphans; they are `dlopen`ed at runtime. `libOnDemandLoader.so`
(`OnDemandLoaderInitialize`, `odl_init`, `odl_res`, `odl_sus`) is the mechanism,
and the uniform `Obj*_RegisterCommand` / `_UnregisterCommand` pairs are how each
one attaches and detaches. So the library set is a plugin set, and a file being
unreferenced by any `DT_NEEDED` means nothing at all. The 123 break down as 35
scenario plugins, 40 in the `libInfra*`/`viewUnified*` block that
`libOnDemandLoader` accounts for, and 48 that are distro runtime
(`libnl-*`, strongswan, curl, opus, zlib) or updater-side tools.

> **Corrected figure.** This used to read *"313 of 391 shared objects"*, and the
> 313 does not reproduce. The 591 catalog basenames partition into **231 carved
> fragments** — ELFs recovered from a raw image dump, not files the camera has —
> **134 degenerate entries** with no imports, no `DT_NEEDED` and no exports
> (`camuser.elf` among them), **165 readable shared objects**, and **61 readable
> executables**. Counting the first two classes as shared objects is what
> produced 313. Reproduce with `research/firmware/dep_graph.py`; pinned by
> `tests/test_dep_graph.py::test_orphan_count_is_123_not_313`.

One trap worth naming, because it is the same shape as the ones in
[06-method.md](06-method.md): `libObj.so` appears **twice** in the catalog with
opposite outcomes — an 81,920-byte truncated decoy that yields nothing, and the
real 21,305,456-byte file under `dumps/engine/` carrying 1,904 exports. A count
keyed on basename must treat a name as readable if *any* copy parsed, or the
real library is discarded along with the decoy.

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

## What the catalog establishes

1. The camera application is not unreachable. It is `libObj.so` plus
   `viewUnified2..8.so` plus `CautionConfig.so`, all present locally and all
   unstripped enough to read. `dumps/v203/camuser.elf` (21,305,528 B) is the
   matching application binary. (Its section table is unreadable by pyelftools —
   `expected 4, found 0` — which is why an earlier pass saw a container. A raw
   byte search shows an ordinary dynamically-linked ARM ELF.)
2. The service side is not the odd one out. `libosal_uipc` with 166 dependents is
   how the service tools and the application talk, and it is a documented-enough
   API surface to use rather than reverse.
3. The font is consumed by `TextRM` via `FsLtt`, with OpenType tables parsed
   in-process by `TsOt*`. That is the layer to read next if the font work
   continues, and it is in a file we have.
4. The scenario plugins are a named, enumerable command surface, which is a much
   better place to look for "reach another subsystem" than a forged library.

### Negative results

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

## av-cam.bin: the RTOS command engine

Extracted offline from `fw/av-cam.bin` (161,595 strings) with `cmd_surface.py`. No
camera needed.

**`CMD_ID_SDF_*` — the top-level command namespace (12):** `CMD_ID_SDF_ALL`,
`_CANCEL`, `_CLOSE`, **`_EXEC`**, `_INPUT`, `_OPEN`, `_OUTPUT`, `_PAUSE`,
`_RESTART`, `_START`, `_STOP`, `_UNKNOWN`.

**`SDF_*` — 57 subsystem codes**, and the error/state families show this is a real
execution engine rather than a naming artefact:

```
SDF_ERR_*        OK PARAM TIMEOUT MEMORY HW_TROUBLE NOT_SUPPORTED
                 REQ_OVERFLOW UNEXPECTED UNIQUEID SDS SET_PARAM CANCEL_*
SDF_INTRA_ERR_*  the same family plus JPEG_QVALUE ENCODE_SIZE_OVER
                 EXTENT SA PIN_CONNECT
SDF_RECMODE_*    STILL_REC OPAL_DUAL_REC HW_DUAL_REC
```

So SDF is a media / still / codec pipeline engine with an
`OPEN -> INPUT/OUTPUT -> EXEC -> START -> STOP/CANCEL/RESTART/CLOSE` lifecycle.
**`EXEC` feeds it data or commands to run** — the obvious target, and the open
question is what it accepts as its target/argument and whether that is validated.

**164 `Exec*` dispatch symbols**, in families:

```
ExecApi*   ExecApiExecBaseSetting, ExecApiExecIdtVerification, ExecApiNotify*,
           ExecApiStart*, ExecApiCancel*                    external API entry points
ExecSens*  ExecSensCmd, ExecSensComp, ExecSensMsg           sensor subsystem
ExecSdf*   ExecSdfMsg, ExecSdfMsgParallel, ExecPinSdfMsg     SDF pipeline messages
ExecJpeg*  ExecJpegOpen/Close/Ready/Encode/TanzEncode        JPEG pipeline
ExecMovie* ExecMovieCodecMsg, ExecMovieCodecResponse          movie codec
ExecRc*    ExecRcAcquire/Release/Resize/DistCorrection*      recomposition / zoom
ExecTanz*  ExecTanzaku, ExecTanzSrcDistCalc, ExecTanzRcDistCalc*
ExecVfx*   ExecVfxEffect*, ExecVfxStart/Open/Close          video effects
ExecPin*   ExecPinCmd/Get/MsgResponce/Send/YCPin*           pin and connection management
           ExecConnect/ExecDisconnect/ExecRequestConnect/ExecRequestDisconnect
           ExecCmd, ExecSendCommand, ExecReceive, ExecMain, Execute*, ExecTrigger
ExecGuard/ExecGard/ExecPathSequenceGard/ExecTimeTypeGard    GARD = guarded exec
```

Plus ~98 `*Handler` symbols (`ExecModeHandler`, `ExecRawDevHandler`,
`ExecReleaseHandler`) and several hundred `*Msg` symbols (`Proc*ProcMsg*`,
`*MsgSet*`, `*MsgChk*`) — the IPC message names.

> **Negative result.** **No numeric opcode table exists in the plaintext strings**
> — only symbolic names. The actual command ids live in code, so mapping
> `ID -> handler` requires reading the dispatch switch, which needs either the
> decrypted body or the plaintext loader stub that still references the handler
> table. The 4 KB LIRO header plus any plaintext init code is where to look.

`ExecGuard` / `ExecGard` suggest Sony added guarded-execution wrappers — probably
after an earlier bug — which implies exec validation was already a known soft
spot.

## VDF, the display subsystem

`VDF` = "Video Display Framework", a message-driven display subsystem inside
`/system/av-cam.bin`. 361 `N3VDF*` mangled RTTI names plus long
`virtual VDF::VDF_ERR VDF::Class::Method(...)` strings. Those second ones are
**log strings, not RTTI names** — and they are the useful ones, because they are
referenced pc-relative from real code and therefore resolve to genuine function
addresses by name.

**Load base `0x635C6000`**, solved from RTTI name pointers (375/400 validated)
and independently corroborated by the ORIL init table. Runtime address = file
offset + `0x635C6000`.

### The pc-relative string reference encoding

`av-cam.bin` is a **raw binary, not an ELF** (`0a 00 00 ea 4f 52 49 4c` — ARM code
then `ORIL`) and carries no relocations. A pointer to a string or table is built
in two instructions:

```
ldr  rX, [pc, #imm]      ; pool word is a FILE offset, not an address
add  rX, pc              ; rX = pool + pc  ->  the file offset
```

Two conventions, and getting either wrong silently yields zero matches:

1. **Do not apply the load base.** The pool word and `addr` are both file
   offsets; their sum is already the target. Subtracting `BASE` shifts every key
   by 6.4 MB.
2. **`pc` is the raw `addr + 4`, not `Align(PC,4)`.** ARM's architecture says
   `ADD (register)` reads `Align(PC,4)`, but this toolchain's encoded literal is
   `target - (addr+4)`. Using the aligned value lands 2 bytes low.

Both are implemented and regression-tested in `thumb.pcrel_strrefs`, against
three independently-anchored ground truths.

### Resolved methods

`research/firmware/vdf_methods.py` resolves 35 of 36 signature strings (the 36th is
a duplicate `SystemCmdNotfound::Execute` key, not a real miss):

| method | file offset | insn |
|---|---|---|
| `VdfDisplayCmdSetOsdAlpha::Execute` | `0x00150A9C` | 74 |
| `VdfDisplayCmdSetOsdAlpha::Activate` | `0x0015091E` | 1 (thin) |
| `VdfDisplayCmdSetPanelOsdLuminance::Execute` | `0x00151360` | 75 |
| `VdfDisplayCmdSetPanelOutPin::Execute` | `0x00151450` | 386 |
| `VdfDisplayCmdSetPanelReverse::Activate` | `0x00151CBA` | 52 |
| `VdfSrvcDrawOsdManager::Execute` | `0x00178892` | 86 |
| `VdfInputCmdUpdateYuv::Execute` | `0x001681A0` | 32 |
| `SystemCmdPinSend::Execute` | `0x00184938` | 468 |
| `SystemCmdSysv::Execute` | `0x00185534` | 331 |
| `SystemCmdDebug::Execute` | `0x001803AE` | 1447 |

`SetPanelBrightness` has no `Execute` signature string, but `0x00150BA8` (313
insn, 30 calls) is adjacent to the `SetOsdAlpha` pair and behaves identically in
shape. Treat that identification as **strong but not string-proven**.

### Why a panel command cannot simply be called

`SetOsdAlpha::Execute` (`0x00150A9C`) and `SetPanelBrightness::Execute`
(`0x00150BA8`) share a shape:

```
push {r4,r5,r6,r7,lr}
ldr  r3, [r3, #8]            ; arg3 (SubsystemAccessorIf*) -> vtable slot 2
blx  r3
ldrb r2, [r5, #1]            ; the value, a byte in the command object
...
ldr.w r3, [r3, #0x44c]       ; more subsystem vtable slots
ldr.w r3, [r3, #0x454]
ldr.w r3, [r3, #0x45c]
ldr.w r3, [r3, #0x6cc]
ldr.w r3, [r3, #0x858]
```

A display command needs **two live interface objects** — a `MsgAccessorIf*` and a
`SubsystemAccessorIf*` — and reaches the panel handle through a chain of virtual
calls at vtable offsets `0x44c / 0x454 / 0x45c / 0x4bc / 0x4d4 / 0x670 / 0x6cc /
0x858`. The vtable is therefore >`0x858` bytes and its methods must return valid
subsystem pointers. **Fabricating those from an injected stub is not a safe
experiment: a wrong pointer there is a hard hang, not a visible effect.**

The message-post helper is `0x0072F47C`:

```
push {r0,r1,r4,r5,r6,lr}
str  r3, [sp]
movs r0, #3
mov  r1, r6 / r2, r5 / r3, r4
bl   0x17B388                ; the msgpump
```

Callers pass `r0 = 0xEEEEEEEE` as a "no sender" sentinel, `r1 = value`, `r2 =
context pointer`, `r3 = command id` (e.g. `0x5D8`, `0x51`). This is the
legitimate path, but the command id and payload layout are per-subsystem and would
have to be reconstructed exactly.

### The brightness path is a table lookup, not a register write

In `SetPanelBrightness::Execute` (`0x00150BA8`):

```
0x00150BEA  ldr   r3, [pc, #0x378]     ; -> 0x0087D7E4
0x00150BEC  ldrb  r2, [r5, #1]         ; brightness value, an INDEX
0x00150BEE  add   r3, pc
0x00150BF0  ldr.w r3, [r3, r2, lsl #2] ; curve = table[brightness]
0x00150BF4  str   r3, [sp, #0x18]
0x00150BF6  strb  r3, [sp, #0x21]
```

The table at file `0x0087D7E4` is 16.16 fixed point, incrementing by `0x10000` per
entry in 16-entry rows — a colour/scale LUT, **not** a monotone brightness curve,
so editing it would not do the obvious thing.

**Writability is unproven.** The image is not an ELF, so there are no section
headers and which byte ranges are writable cannot be determined offline. It would
have to be established at runtime before any data patch — and a data patch to a
misidentified table is exactly the kind of unquantified side effect that bricks a
device.

> **Negative result: vtable slots do not identify methods.** The vtables at
> `0x00FBB0F8` etc. are real — they decode cleanly at `(stored & ~1) - BASE`
> (every entry carries the Thumb bit), slot `[-1]` matches the typeinfo address
> exactly, and they are spaced on 32-byte boundaries with a `0x00000000`
> terminator. But the per-class slots do **not** line up with the string-resolved
> method addresses: `SetPanelReverse` slot `[5]` is `0x0071E632` while its
> `Activate` is `0x00151CBA`. An earlier claim that "slot `[5]` == `Execute`" was
> a single coincidence with `SetOsdAlpha` and is wrong. **Slot index is
> unidentified.**

### Negative result: there is no CPU-visible framebuffer

The display is descriptor-driven (APL/AIC + XDMAC + HME) and the panel is fed by a
private `ldec` driver. Four independent lines of evidence, each checked against a
positive control:

- `0x6AA00000` is a hardware aperture that **wedges the CPU on a single-byte
  read** (reproduced 3x).
- `MemTotal` is 128 MB against a claimed 1 GB window.
- `/proc/iomem` shows no sensor/ISP or display framebuffer region.
- The decode-path hook we own, `0xA9F90`, is a **ring-buffer index refill**
  (`ldr r5,[r4,#4]` / `cmp` against a limit / `str r0,[r4,#4]`) — no decoded
  pixels pass through it.

`ldec` is **not** in any on-disk module. `/proc/modules` gives it 10,106 bytes
with flag `(P)` = statically allocated core, so its code is linked into the kernel
image. `dmm.ko` (85,588 B), `stream.ko` and `stream2.ko` were all pulled and
checked: no ldec symbols. `init` loads `ldec.ko` from `/kmod/ldec.ko`, which is on
the ramdisk and is **freed after boot**, so it cannot be dumped from a running
camera at all.

`stream.ko` / `stream2.ko` do export `stream_mmap`, and `stream2`'s walks a
5-entry table in `.data` at `0x8c` calling `remap_pfn_range` per entry. Not a
display surface — a scatter-gather buffer mapper. Noted, not pursued.

Reaching a visible display effect therefore requires a full VDF message
transaction with valid subsystem interface pointers, or a runtime-proven writable
data symbol. Neither is available offline, and guessing is a hang risk.

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

(`/usr/bin/scenario.elf` does not `dlopen` the plugin — the `dlopen` happens on
the far side of the message bus. That is in
[04-messaging.md](04-messaging.md). What follows is the runner's own live
behaviour.)

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

## Tools

```powershell
& ".venv\Scripts\python.exe" -B research\firmware\elf_catalog.py   # build the ELF inventory
& ".venv\Scripts\python.exe" -B research\firmware\dep_graph.py     # DT_NEEDED graph, orphans, entry classes
```

`dep_graph.py` reads only `research/firmware/elf_catalog.json`, which is tracked,
so it runs on a fresh checkout with **no camera binaries present**. It classifies
every basename as carved / degenerate / readable, shows that the classes
partition exactly, and splits the DT_NEEDED orphans into the three groups above.
Pinned by `tests/test_dep_graph.py`.


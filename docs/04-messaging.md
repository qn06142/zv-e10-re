# 04 — Messaging: the bus, the ids, and the command vocabulary

Everything known about how the camera's subsystems are addressed. This is the
consolidated agent-facing view; it supersedes the four separate documents it was
assembled from, which are in `90-session/_merge-*.md`.

Reproduce any table with the tools listed at the end.

## Two layers, and they are not the same thing

There are two ID spaces and conflating them is what made the earlier work
stall:

```
  0x00dc0000   bus endpoint  (liro / RTOS)     <- what sndcmd.elf addresses
      |
      +-- 0x2004, 0x0101, 0x0301 ...          <- command ids carried *inside*
          the message.  THIS document.
```

The one endpoint known to be accepted is `0x00dc0000`. It is an *address the
bus delivers to*, not a command. `0x00dc0000` appears nowhere in
`/proc/osal/uipc`, because the RTOS keeps its own queues — the 139 liro threads
have their own bus state that the Linux dump does not show.

`sndcmd.elf` posting to `0x00dc0000` returns RC=0. That establishes the
firmware *accepts* the message. It does **not** establish that the message does
anything.

## Node spaces on the live bus

From `/proc/osal/uipc` (`OSAL Version 4.2`, compiled Mar 15 2025):

| pid | process | msgqs | sems | cbs |
|---|---|---:|---:|---:|
| 157 | **`/usr/bin/im.elf`** | 417 | 134 | 310 |
| 149 | — | 0 | 0 | 0 |

Global totals: 860 msgqs, 198 sems.

Local queue indices are small (`4C`, `74`, `114`, `160`, `16F`); the global
table carries a node column, and the nodes fall into two disjoint families:

- `0x0094xxxx` — 89 occurrences. The Linux-process side.
- `0x00dcxxxx` — **0 occurrences.** The RTOS, tracked separately.

The RTOS side of the bus is unsolved: the message format `sndcmd` speaks is a
different problem from the MWF format below, and is the highest-value open
item.

## `libIMDB.so` is the application manifest

`libIMDB.so` (37,044 B) exports only `IMDB_find_entry`, `IMDB_get_entries`,
`IMDB_find_target_bit` and one data symbol, `imdb_raw`. It is not a settings
database — its string table is **the complete load manifest for the camera
application**: **174 libraries, 16 kernel modules, 22 paths**, in boot order,
each with its `init`/`exit`/`sus`/`res`/`inact`/`act` entry points.

`imdb_raw` is 132 bytes — 66 `u16`, of which nine are offsets into `.rodata`
naming the modes:

```
0x3512 -> "sim"      0x3516 -> "usbj"     0x351b -> "resub"
0x3521 -> "adjust"  0x3528 -> "test"     0x3532 -> "default"
0x353f -> "qemu"     0x3549 -> "nfs"      0x3552 -> "set"
```

(The tenth non-zero word, `0x0002`, is a count, not an offset — reading strings
there yields `LF`.) Decoding the table settles the mode-selection question with
no camera involved.

Head of the manifest:

```
libIMDB.so            the manifest itself
libosal_uipc.so       the message bus
libosal_utm.so
libosal_ulogio.so
libInfraInterchipDatatrans.so
libNVM.so             NVM_Initialize          <- the settings store
libbackup.so          libSaveLoadSettings.so  libbkdmn.so
libOnDemandLoader.so  odl_init                <- the plugin loader
... 160 more
```

Two application entry points appear: **`appFw.so` →
`Application_System_Init`** and **`gui.so` → `DPro_App_UI_init`**. The remote
stack is all initialised from the same list, including
`libInfraWebApi.so` → `InfraNetWebApi_init`, `libInfraRemoteCtrlCGI.so`,
`libInfraLiveViewClient.so`, four streaming backends, FTP and file transfer.

## The scenario runner is a client, not a loader

`scenario.elf` does **not** `dlopen` the plugins. `libtestcmd.so` imports no
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

Endpoints are `0x00dc0292` (register) and `0x00dc0293` (send). The descriptor
struct `testcmd_sndmsg`/`testcmd_rcvmsg` use is `u32 id` at `+0`, a flags byte
at `+0x0c` whose bit 0 selects the synchronous call, and a source id written
back at `+0x14`. Return codes are `0xfffffb01`–`0xfffffb06` and
`0xfffffc00`/`0xfffffc01`.

So the scenario name is a **UIPC message payload, and the `dlopen` happens on
the far side** — in a peer that is not loaded in service mode. That is why
`scenario.elf` is fire-and-forget and why the 35 plugins in `/usr/scenario/`
never ran. The name is truncated at 32 bytes by that `memcpy`, and validation
is only "no spaces", so a 32-character name containing `../` is accepted by the
sender.

## The plugin command vocabulary

`/usr/scenario/*.so` is 35 shared objects, 543 KB, each exporting one function
`scenario_run`. They are the only readable description of what the scenarios
do. Two RPC frameworks appear:

| framework | plugins | shape |
|---|---:|---|
| `DataflowInfra*` | 18 | raw OSAL messages; `SendASync(uint, DataflowInfraMsg*)` — one id |
| `MWF::*` | 8 | `ObjIf`, `ObjMsg`, events, pins; **two** ids, category + message |
| neither (thin) | 9 | dispatch, or straight to `libtestcmd`/`libIMDB` |

The ids are not in any table — they are `movw`/`movt` immediates in the code.
Sweeping them gives **96 distinct values** in a structured 16-bit namespace:

| group | uses | values |
|---|---:|---|
| `0x0___` | 139 | `0x101` `0x115`(6) `0x141`(4) `0x295`(4) `0x301`(16) `0x303`(8) `0x313`(12) `0x401`(12) … |
| `0x1___` | 54 | `0x1001`(10) `0x1002`(8) `0x1005`(4) `0x1102`(5) `0x1106`(6) `0x1317`(2) |
| `0x2___` | 93 | `0x2001`(17) `0x2004`(**76**) |
| `0x3___` | 10 | `0x3001`(2) `0x3003`(5) `0x3006` `0x3023` |
| `0x8___` | 55 | `0x8001`(7) `0x8102`(10) `0x8301`(7) `0x8313`(6) `0x8401`(6) |

**`0x2004` — 76 uses, the most common id in the entire vocabulary — is
`PIN_SOUND`**, the audio dataflow pin. Not derivable from the numbers.

### The MWF half is two-dimensional

The `MWF` plugins construct an `MWF::ObjMsg`, and its constructor takes two
ids: `MWF::ObjMsg::ObjMsg(unsigned int, unsigned int)`, read back with
`GetCategoryId()` and `GetMessageId()`. 14 construction sites:

| plugin | category | message |
|---|---:|---:|
| `MPR_FORMAT` | `0x0001` | `0x1` ×3 |
| `MPR_INSTALL_MAP_DEMOMOVIE` | `0x2000` | `0x1` ×4 |
| `MPR_FORMAT` | `0x3800` | `0x1` |
| `MPR_FORMAT` | `0x3700` | `0x1`, `0x1022` |
| `MPR_GET_CONTENT_COUNT` | `0x3700` | `0x102a` |
| `MPR_GET_CONTENT_COUNT` | `0x6000` | `0x1001`, `0x81000`, `0x81003` |

Five categories, four of them round — a subsystem allocation table, not a hash.

**The two frameworks cross-validate.** `0x1001`, `0x1022` and `0x102a` appear in
*both*, recovered by entirely separate means: one from a constructor's
arguments, one from a `movw` sweep. `0x1022` and `0x102a` were seen only in
`MPR_SCN_FORMAT` and `MPR_SCN_GET_CONTENT_COUNT` by both methods. That agreement
is the strongest evidence the vocabulary is read rather than pattern-matched.

## `libSysDef.so` names every id

3.2 MB, 18 exports, and three of them are the tables the command space is built
from. Each is an array of fixed-stride records with `u32` pointers into the
same object, so the tables name themselves.

| table | stride | shape |
|---|---:|---|
| `m_cateTbl` | 8 | `{u32 id, u32 name}` |
| `m_objTbl` | 12 | `{u32 id, u32 CATEID_*, u32 Obj*}` — **two names** |
| `m_pinTbl` | 16 | `{u32 id, u32 aux, u32 name, u32 name}` |

Strides differ and **guessing one produces plausible nonsense rather than an
error**: at stride 8 `m_pinTbl` yields `\x7fELF` (it followed a zero word to
vaddr 0), at 12 it interleaves id and name columns. And `m_objTbl` carries two
names per record — reading the second word as the name reports `ObjCntMgr` for
`0x3700` where the category is `CATEID_CNT_MGR`.

### Categories — 33

```
0x00000000 CATEID_UNKNOWN       0x00006000 CATEID_DATABASE
0x00000001 CATEID_NONE          0x00006010 CATEID_INFRA_CACHEMGR
0x00000002 CATEID_MWF           0x00006020 CATEID_INFRA_SALVAGESTATUS
0x0000ffff CATEID_ALL           0x00006100 CATEID_INFRA_SELECTOR
0x00001000 CATEID_APP           0x00006101 CATEID_HOTPLUG
0x00001100 CATEID_APP_FRAMEWORK 0x00006102 CATEID_USBHOSTSTORAGE
0x00001200 CATEID_APP_MODELS    0x00006103 CATEID_USBCONTROL
0x00001300 CATEID_APP_VIEWS     0x00006104 CATEID_MSCSERVER
0x00001400 CATEID_APP_WIDGETS   0x00006105 CATEID_MTPSERVER
0x00001500 CATEID_APP_INPUT     0x00006106 CATEID_INFRA_MEDIA_PWRMGR
0x00001600 CATEID_APP_WRAPPERS  0x00006107 CATEID_BUSPOWER
                                0x00006108 CATEID_INFRA_STILLPOOL
                                … 0x0000610c CATEID_INFRA_REMOTE
                                  0x0000610d CATEID_INFRA_PTPCTRL
                                  0x0000610e CATEID_INFRA_WEBAPI
                                  0x0000610f CATEID_INFRA_HIGHLIGHT
                                  0x00006110 CATEID_INFRA_MAKESCENARIO
                                  0x00006111 CATEID_INFRA_BGMMETA
                                  0x00006112 CATEID_INFRA_IPTC
```

`0x1000`–`0x1600` is the application layer, split the way `libObj.so`'s exports
are. `0x6100`–`0x6112` is infrastructure, and it is the remote stack from the
manifest. **`CATEID_INFRA_WEBAPI` at `0x610e` is the web API, as a first-class
category id.**

### Objects — 45, and which are implemented

Each record names both the object and its owning category. Joining against
`libObj.so`'s exports — exactly one `Obj*_RegisterCommand`/`_UnregisterCommand`
pair per implemented object — splits the table **exactly**:

**Implemented (25):** `ObjRenderer` 0x3200, `ObjMovieRecorder` 0x3300,
`ObjDisplay` 0x3400, `ObjAudioProcessor` 0x3420, `ObjMic` 0x3430,
`ObjSpeaker` 0x3450, `ObjStillRecorder` 0x3500, `ObjPlayer` 0x3600,
`ObjCntMgr` 0x3700, `ObjEditor` 0x3710, `ObjDubbing` 0x3720,
`ObjMedia` 0x3800, `ObjEffect` 0x3900, `ObjImporter` 0x3a40,
`ObjNetMediaServer` 0x3a46, `ObjSalvage` 0x3a42, `ObjConverter` 0x3a48,
`ObjRemote` 0x3a4a, `ObjMetaRecorder` 0x3a4f, `ObjAvAdjCtrl` 0x3a50,
`ObjRemoteAsync` 0x3a51, `ObjFtpClient` 0x3a52, `ObjGenlock` 0x3a53,
`ObjNetSetting` 0x3a54, `ObjStreamingUsb` 0x3a56

**Declared only (20):** `ObjCamera` 0x3100, `ObjSystemSound` 0x3410,
`ObjMixer` 0x3440, `ObjMap` 0x3950, `ObjMediaServer` 0x3a00, `ObjInbox` 0x3a10,
`ObjUploader` 0x3a20, `ObjCameraAgent` 0x3a30, `ObjFinalize` 0x3a41,
`ObjDvdWriterFirmup` 0x3a43, `ObjFaceRecorder` 0x3a44, `ObjNetUploader` 0x3a45,
`ObjNetBackupServer` 0x3a47, `ObjScalar` 0x3a49,
`ObjNetExternalStreaming` 0x3a4b, `ObjExternalInput` 0x3a4c,
`ObjHandover` 0x3a4d, `ObjRemoteClient` 0x3a4e, `ObjMediaServerResident` 0x3a55

**Zero orphans in either direction** — every `Obj*` in `libObj.so` is in the
table and every table entry with a `RegisterCommand` is in `libObj.so`. Two
independent symbol lists agreeing exactly is unlikely by accident.

The 20 unimplemented look pluggable or model-gated rather than missing;
`ObjCamera` is the interesting one, being presumably provided by a library
that is not `libObj.so`.

### Pins — 12

```
0x2001 PIN_YC             0x2007 PIN_MEDIA_STATUS
0x2002 PIN_PANEL          0x2008 PIN_STILL_DATA
0x2003 PIN_LINE           0x2009 PIN_EDIT_INFO
0x2004 PIN_SOUND          0x200a PIN_CAMERA_STATUS
0x2005 PIN_REC_CNT_INFO   0x200b PIN_IMPORT_CNT
0x2006 PIN_PB_CNT_INFO    0x200c PIN_EXPORT
```

These are what the AVBB plugins call `PinConnect_*` and `CheckPinUnConnect*`
on by name. `PIN_CAMERA_STATUS` is the camera→UI status channel.

## `0x2000` is `CATEID_PIN`

`MWF::ParamDump::ConvMessageId` (vaddr `0x24176`, 96 B, real export) routes on
the category:

```
00024190  cmp.w r6, #0x2000    ; category == 0x2000?
00024194  beq   #0x2419e       ; -> MwfTbl::PinMsg2Name(msgId)
00024196  cmp.w r6, #0x3000
0002419a  bne   #0x241b2
000241a0  blx   #0x1bdd0       ; -> MwfTbl::PinMsg2Name
```

Both call sites verified as real exports with the PLT resolving. The message
`MPR_SCN_INSTALL_MAP_DEMOMOVIE` sends is `(0x2000, 0x1)`, with parameters
`0x1000` pin type, `0x1001` pin number, `0x1002` direction, passed to
`ObjIf::GetPin`/`ConnectPin`/`DisconnectPin`.

> **Correction of record.** This was previously inferred as "plausibly a pin
> *group*" from the numbering (`0x2001`–`0x200c` are pins). It is a message
> category, established from the dispatch code. The inference happened to land
> near the truth for the wrong reason.

## Core framework message tables (`libMWF.so`)

`m_baseMsgTbl` (12 records) — lifecycle for `category == 0x3000`:
`0x1000` UNKNOWN, `0x1001` NONE, `0x1002` START_OBJ_CMD, `0x1003` STOP_OBJ_CMD,
`0x1004` KILL_OBJ_CMD, `0x1005` START_OBJ_CMP, `0x1006` STOP_OBJ_CMP,
`0x1008` RESUME_OBJ_CMD, `0x1009` SUSPEND_OBJ_CMD, `0x100a` RESUME_OBJ_CMP,
`0x100b` SUSPEND_OBJ_CMP, `0x100c` ALL.

`m_pinMsgTbl` (11 records): `0x1000` OPEN, `0x1001` CLOSE, `0x1002` DELIVER,
`0x1003` NOTIFY, `0x2000` REQ_OPEN, `0x2001` REQ_STOP, `0x2002` REQ_DELIVER,
`0x2003` REQ_NOTIFY, `0x3000` CONNECT, `0x3001` DISCONNECT, `0x3002`
DISCONNECTPIN_CMP.

`m_pinParamTbl`: `0x1000` PIN_TYPE, `0x1001` PIN_NUMBER, `0x1002`
PIN_DIRECTION, `0x1003` PIN_DATA. `m_pinDirTbl`: 0 IN, 1 OUT, 2 INOUT.

## Database category `0x6000`

48 client methods in `libNetContUtil.so` map to message ids. The main ones:

| msg | methods |
|---|---|
| `0x1001` | `destroyHandle` |
| `0x100e` | `copyHandle` |
| `0x2000`–`0x2009` | content-list management: create, destroy, add, delete, get entries, check num, get entry pos |
| `0x81000` | `createRootHandle` / `createChildHandle` |
| `0x81002` | `getObjectNum`, `getMediaId`, `getGroupCondOfHandle`, `getContentTypeCombiOfHandle` |
| `0x81003` | `getContentType`, `getItemDate`, `getDirectoryName`, `getItemAttribute`, `getItemBurstType` |
| `0x8101e`/`0x8101f` | `getDCFFileType`, `getDCFFileInfo` |
| `0x81022` | `getObjProperty` |
| `0x81023`/`0x81024` | `getExtentNum`, `getExtent` |
| `0x81036`/`0x81037` | `getContentFileType`, `getTotalCountList` |
| `0x8103c` | `getContentProfile`, `getBGMContentProfile` |
| `0x81050`/`0x81053`/`0x81054` | `getContentsListFromAVIndex`, `getExtentByUniqId`, `getFocusedContentPosition` |
| `0x82008` | `getHandleFromContentList`, `createRootHandleOfList` |

The underlying `APICD_*` table in `libObj.so` is at file offset `0x13ec720`,
`{u32 id, u32 name_vaddr, …}` at **stride 36**, **115 records**, contiguous
from `0x1000`. Selected:

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

> **Correction of record.** The stride was originally given as 72, which reads
> every *second* record. It still starts in the right place and every name
> pointer still resolves, so it looks like it works — it reports 58 records
> instead of 115 and pairs each id with the wrong name further along. The
> giveaway is contiguity: at stride 36 the ids run `0x1000, 0x1001, 0x1002` with
> no gaps. `tests/test_mwf_catalog.py::test_apicd_stride_is_36_not_72` now
> pins this, and asserts that stride 72 *does* miss the odd-indexed names, so it
> fails on the old code.

## Content manager `0x3700` (`ObjCntMgr`)

From `ObjCntMgr::ParseObjCommand`:

```
0x100a MSGID_GET_FORMAT_TIME_CMD      0x100b MSGID_GET_FORMAT_TIME_CMP
0x1022 MSGID_FORMAT_CMD               0x1023 MSGID_FORMAT_CMP
0x1024 MSGID_FORMAT_PROGRESS_EVT      0x1026 MSGID_UNLOAD_EVT
0x102a MSGID_SET_CONTENT_TARGET_CMD   0x103c MSGID_CREATE_APP_STRUCTURE_CMD
0x10000002 MSGID_LOAD_EVT             0x10000013 MSGID_MOUNT_EVT
0x10000014 MSGID_UNMOUNT_EVT          0x1000001e MSGID_FSYS_FORMAT_CMD
0x1000001f MSGID_FSYS_FORMAT_CMP      0x10000036 MSGID_MASS_STORAGE_START
0x10000037 MSGID_MASS_STORAGE_END
0x1000005a MSGID_TEMPERATURE_RANGE_NORMAL
0x1000005b MSGID_TEMPERATURE_RANGE_OVER
```

The high-bit ids (`0x1000xxxx`) are events rather than commands — a distinct
band, which is why they appear in a different range in every sweep.

## Playback `0x3600` (`ObjPlayer`)

69 commands from `DefObjPlayer`: `0x1000` PB_START_CMD, `0x1001` PB_START_CMP,
`0x1002` PB_STOP_CMD, `0x1003` PB_STOP_CMP, `0x1004` CHANGE_PB_SPEED_CMD,
`0x1006` CHANGE_CONTENTS_CMD, `0x1008` SET_PB_CONFIG_CMD, `0x100a`
MAKE_SCENARIO_CMD, `0x100c` SAVE_SCENARIO_CMD, `0x100e` LOAD_SCENARIO_CMD,
`0x1010` PB_START_BGM_CMD, `0x1016` REQ_CACHE_INSTANCE_CMD, `0x1020`
GET_RESUME_POINT_CMD, `0x1022` GET_PB_POSITION_CMD, `0x1026`
SET_CONV_CACHE_INSTANCE_CMD, `0x102a` CLEAR_CONV_CACHE_INSTANCE_CMD, `0x102c`
GET_HIGHLIGHT_INFO_CMD, plus events `0x2000` INTERNAL_PB_STOP_EVT, `0x2001`
CAM_INFO_EVT, `0x2002` GPS_INFO_EVT, `0x2005` PB_TIME_EVT, `0x2006`
PB_STATUS_EVT, `0x200b` CONTENT_TYPE_EVT.

## The `IMCFG` block in `libObj.so`

Found by searching for `0x1001`, which returned three hits exactly 20 bytes
apart — a table, not code. 16 `u32` ids followed by ASCII:

```
0x1000 0x1001 0x1006 0x1007 0x1200 0x1010 0x1002 0x1004
0x4000 0x2000 0x4200 0x3001 0x4400 0x1005 0x4100 0x4300
IMCFG   VER:109 CATEGORY:MAIN TYPE:COM CXD:COM
```

and **70 device names** after it:

| family | count | range |
|---|---:|---|
| `/dev/ms` | 3 | memory stick |
| `/dev/mmc` | 13 | SD / MMC |
| `/dev/sata` | 9 | SATA |
| **`/dev/nflasha`** | **32** | raw nand A |
| `/dev/sd` | 4 | SCSI disk |
| `/dev/sr` | 2 | SCSI CD |
| **`/nondev/`** | **7** | pseudo-devices, no kernel node |

All 32 `nflasha` nodes are listed, which accounts for the partitions that kept
appearing with nothing in the mount table referencing them. The `/nondev/`
entries — `dvdmenu`, `simulate`, `pcremote`, `air`, `streaming`, `iptc`,
`ipremote` — are **media sources with no block device behind them**, which is
why the manifest can list them alongside real mounts.

`VER:109` appears in all three `IMCFG` markers, so it is a constant in the
format string, not a version of that block.

The id array contains `0x1001` but **not** `0x1022`, `0x102a`, `0x81000` or
`0x81003` — a different space that overlaps, not the registry the plugins draw
from. It also holds a `0x4xxx` group (`0x4000`, `0x4100`, `0x4200`, `0x4300`,
`0x4400`) that nothing names.

## The `OM` monitor command table is not MWF

`ObjMedia_RegisterCommand` (`0xa3ea25`, Thumb; 12 bytes) is a **dead end for
MWF ids.** It is `push {r7,lr}` / `add r7,sp` / `bl 0xa3e8ec` / `movs r0,#0` /
`pop`, and `0xa3e8ec` is a *static* function — no `.dynsym` symbol covers it,
and the `blx` inside it targets `0x10af78`/`0x10c7e0`, also unexported. It has
to be read, not looked up.

Reading it confirms a debug command set: the function loads a string at
`0x10afcc1`, which is `<id>`, and the surrounding strings are

```
OM_InOutInsert   OM_InOutPullout   OM_ChangeTarget
"Object Media Command"   "Monitor Output"   "InOut Media"
AllInfo  MMgrMediaInfo  EventCheck  Eject  FileSystemMount
Unmount  Temperature  Drop  "Eye-Fi {iseyefi/init/fin}"
"PC Remote Event {start/stop/active/inact}"  SetMedia
```

registered through `MonLib::MonCmdAdd(char const*, bool(*)(int, char**), char
const*)` — a name, an `(argc, argv)` handler and a help string. **A text
command interpreter, not the message bus.**

## Open items in this area

1. **The RTOS-side message format** in `av-cam.bin` (17 MB, on disk). What
   `sndcmd.elf` speaks. Highest value, needs no hardware.
2. **The `0x4xxx` id family** — real, named by nothing.
3. **The per-object message vocabulary** is now covered for `ObjCntMgr`,
   `ObjPlayer` and the database; the other implemented objects are not.
4. **`ObjFaceRecorder`** — the four `MSGID_*FACE*` strings are at
   `0xf03a41`–`0xf03bcc` and the pointer table is near `0x13dc660`, but the
   record layout is **not established**. `0x13dc504` is a different table
   (its word 0 is `0x1000` and word 3 resolves to `MSGID_OPEN`).

## Tools

```powershell
& ".venv\Scripts\python.exe" -B research\firmware\sysdef_tables.py    # MWF tables -> names
& ".venv\Scripts\python.exe" -B research\firmware\scenario_vocab.py  # flat movw/movt sweep
& ".venv\Scripts\python.exe" -B research\firmware\mwf_ids.py         # category/message pairs
& ".venv\Scripts\python.exe" -B research\firmware\mwf_catalog.py     # core tables, APICD, ObjCntMgr, ObjPlayer
& ".venv\Scripts\python.exe" -B research\firmware\imcfg_block.py     # device table + id array
& ".venv\Scripts\python.exe" -B research\firmware\annotate.py <elf> <symbol>
```

Traps specific to this material — Thumb bit, PLT resolution, table strides,
`vaddr` vs file offset — are in [06-method.md](06-method.md).

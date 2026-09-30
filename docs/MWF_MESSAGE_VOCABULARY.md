# MWF Message Vocabulary & Object Command Dispatch

This document resolves **Open Item 1** (Plugin Message Vocabulary Naming) and
**Open Item 3** (Category `0x2000`) from [HANDOFF.md](file:///D:/02_Development_And_Projects/pmca-re/docs/HANDOFF.md).

All message IDs, names, and structures documented here were recovered directly
from the firmware binaries:
- [`libMWF.so`](file:///D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib/libMWF.so) (core tables)
- [`libNetContUtil.so`](file:///D:/02_Development_And_Projects/pmca-re/dumps/camera_2025/usr/usr/lib/libNetContUtil.so) (database client API)
- [`dumps/engine/libObj.so`](file:///D:/02_Development_And_Projects/pmca-re/dumps/engine/libObj.so) (21 MB object dispatch engine)

Tool: [`research/firmware/mwf_catalog.py`](file:///D:/02_Development_And_Projects/pmca-re/research/firmware/mwf_catalog.py) reproduces every table below.

---

## 1. Architecture: The Two-Dimensional Command Space

In Sony's MWF (Media WorkFlow) framework, IPC messages are two-dimensional:

$$\text{Command} = (\text{Category ID}, \text{Message ID})$$

Built via:
```cpp
MWF::ObjMsg::ObjMsg(unsigned int categoryId, unsigned int messageId);
MWF::ObjMsg::SetCateIdMsgId(unsigned int categoryId, unsigned int messageId);
```

While category IDs are exported in `libSysDef.so` ([`docs/MWF_TABLES.md`](file:///D:/02_Development_And_Projects/pmca-re/docs/MWF_TABLES.md)),
**message IDs were previously unnamed**. We have recovered the message registries
across all primary subsystems.

---

## 2. Core Framework Message Tables (`libMWF.so`)

Defined directly in `libMWF.so` at fixed addresses:

### 2.1 Base Object Lifecycle (`m_baseMsgTbl`, `0x428b8`, 12 records)
Common lifecycle commands handled by base objects (`category == 0x3000`):

| Message ID | Canonical Name | Description |
|---|---|---|
| `0x00001000` | `MSGID_UNKNOWN` | Sentinel unknown message |
| `0x00001001` | `MSGID_NONE` | No-op message |
| `0x00001002` | `MSGID_START_OBJ_CMD` | Start object lifecycle |
| `0x00001003` | `MSGID_STOP_OBJ_CMD` | Stop object lifecycle |
| `0x00001004` | `MSGID_KILL_OBJ_CMD` | Terminate object |
| `0x00001005` | `MSGID_START_OBJ_CMP` | Start completion reply |
| `0x00001006` | `MSGID_STOP_OBJ_CMP` | Stop completion reply |
| `0x00001008` | `MSGID_RESUME_OBJ_CMD` | Resume suspended object |
| `0x00001009` | `MSGID_SUSPEND_OBJ_CMD` | Suspend running object |
| `0x0000100a` | `MSGID_RESUME_OBJ_CMP` | Resume completion reply |
| `0x0000100b` | `MSGID_SUSPEND_OBJ_CMP` | Suspend completion reply |
| `0x0000100c` | `MSGID_ALL` | Broadcast to all handlers |

### 2.2 Pin IPC Messages (`m_pinMsgTbl`, `0x42918`, 11 records)
Controls pin connection and data delivery:

| Message ID | Canonical Name | Description |
|---|---|---|
| `0x00001000` | `MSGID_OPEN` | Open pin channel |
| `0x00001001` | `MSGID_CLOSE` | Close pin channel |
| `0x00001002` | `MSGID_DELIVER` | Deliver pin payload data |
| `0x00001003` | `MSGID_NOTIFY` | Pin notification event |
| `0x00002000` | `MSGID_REQ_OPEN` | Request open pin |
| `0x00002001` | `MSGID_REQ_STOP` | Request stop pin |
| `0x00002002` | `MSGID_REQ_DELIVER` | Request data delivery |
| `0x00002003` | `MSGID_REQ_NOTIFY` | Request notification |
| `0x00003000` | `MSGID_CONNECT` | Connect pin endpoint |
| `0x00003001` | `MSGID_DISCONNECT` | Disconnect pin endpoint |
| `0x00003002` | `MSGID_DISCONNECTPIN_CMP` | Disconnect completion reply |

### 2.3 Pin Parameters & Directions
- `m_pinParamTbl` (`0x42970`):
  - `0x1000`: `PARAMID_PIN_TYPE`
  - `0x1001`: `PARAMID_PIN_NUMBER`
  - `0x1002`: `PARAMID_PIN_DIRECTION`
  - `0x1003`: `PARAMID_PIN_DATA`
- `m_pinDirTbl` (`0x42990`):
  - `0`: `PIN_IN`
  - `1`: `PIN_OUT`
  - `2`: `PIN_INOUT`

---

## 3. Resolution of Category `0x2000` (Open Item 3)

In `MWF::ParamDump::ConvMessageId`:
```arm
00024190  cmp.w r6, #0x2000    ; Category == 0x2000?
00024194  beq   #0x2419e       ; -> MWF::MwfTbl::PinMsg2Name(msgId)
```

**Finding:**
`0x2000` is `CATEID_PIN` (the outer category for pin descriptor messages).
The call in `MPR_SCN_INSTALL_MAP_DEMOMOVIE.so`:
```arm
mov.w r1, #0x2000  ; Category = CATEID_PIN
movs  r2, #1       ; Message = 1
blx   MWF::ObjMsg::ObjMsg(uint, uint)
```
with parameters:
- `0x1000` (`PARAMID_PIN_TYPE`) = pin ID (`PIN_SOUND`, `PIN_YC`, etc.)
- `0x1001` (`PARAMID_PIN_NUMBER`) = channel index (e.g. `0`)
- `0x1002` (`PARAMID_PIN_DIRECTION`) = `2` (`PIN_INOUT`)

is passed directly to `MWF::ObjIf::GetPin`, `ConnectPin`, and `DisconnectPin`.

---

## 4. Database Category (`0x6000`, `CATEID_DATABASE`)

### 4.1 Client API (`NetContUtil::NetDbIf`)
The 48 client methods in `libNetContUtil.so` map to specific message IDs:

| Category | Message ID | C++ Method & Purpose |
|---|---|---|
| `0x6000` | `0x1001` | `destroyHandle(handle, bool)` — release handle |
| `0x6000` | `0x100e` | `copyHandle(handle, bool)` — duplicate handle |
| `0x6000` | `0x1055` | `registerNotifyTargetForUniqId(uniqId)` |
| `0x6000` | `0x1056` | `unregisterNotifyTargetForUniqId(uniqId)` |
| `0x6000` | `0x2000` | `createContentsList(type, bool)` |
| `0x6000` | `0x2001` | `destroyContentsList(bool)` |
| `0x6000` | `0x2002` | `addContentToList(msg, ...)` |
| `0x6000` | `0x2003` | `deleteContentFromList(msg, ...)` |
| `0x6000` | `0x2004` | `getContentsListEntries(handle, bool)` |
| `0x6000` | `0x2005` | `deleteAllContentsFromList(bool)` |
| `0x6000` | `0x2006` | `checkNumInContentsList(bool)` |
| `0x6000` | `0x2007` | `checkNumInContentsList(handle, ...)` |
| `0x6000` | `0x2009` | `getEntryPosInHandle(pos, handle, bool)` |
| `0x6000` | `0x81000` | `createRootHandle` / `createChildHandle` (Handle creation for media/types) |
| `0x6000` | `0x81002` | `getObjectNum`, `getMediaId`, `getGroupCondOfHandle`, `getContentTypeCombiOfHandle` |
| `0x6000` | `0x81003` | `getContentType`, `getItemDate`, `getDirectoryName`, `getItemAttribute`, `getItemBurstType` |
| `0x6000` | `0x8100b` | `convHndl2EntryId(handle, entryId, bool)` |
| `0x6000` | `0x8101e` | `getDCFFileType`, `getDcfType` |
| `0x6000` | `0x8101f` | `getDCFFileInfo` |
| `0x6000` | `0x81022` | `getObjProperty` |
| `0x6000` | `0x81023` | `getExtentNum` |
| `0x6000` | `0x81024` | `getExtent` |
| `0x6000` | `0x81036` | `getContentFileType` |
| `0x6000` | `0x81037` | `getTotalCountList` |
| `0x6000` | `0x8103c` | `getContentProfile`, `getBGMContentProfile` |
| `0x6000` | `0x81050` | `getContentsListFromAVIndex` |
| `0x6000` | `0x81053` | `getExtentByUniqId` |
| `0x6000` | `0x81054` | `getFocusedContentPosition` |
| `0x6000` | `0x82008` | `getHandleFromContentList`, `createRootHandleOfList` |

### 4.2 Underlying Database Command Table (`APICD_*` in `libObj.so`)
Located at offset `0x13ec720`, stride 72 bytes:

| Command ID | APICD Symbol Name |
|---|---|
| `0x00001000` | `APICD_CREATE_HNDL` |
| `0x00001002` | `APICD_GET_HNDL_ATTRIBUTE` |
| `0x00001004` | `APICD_SET_RESUME_POS` |
| `0x00001006` | `APICD_CLEAR_RESUME_POS` |
| `0x00001008` | `APICD_GET_CONTENT_POS` |
| `0x0000100a` | `APICD_GET_CREATED_HNDL_PARAM` |
| `0x0000101e` | `APICD_GET_DCF_FILE_TYPE` |
| `0x00001020` | `APICD_SYNC_CONV_ENTRYID2ITEMNO` |
| `0x00001022` | `APICD_GET_CONTENT_PROPERTY` |
| `0x00001024` | `APICD_GET_CONTENT_EXTENT` |
| `0x00001026` | `APICD_GET_EVENT_RANGE` |
| `0x0000102a` | `APICD_END_GET_LOCATION_ITEM_IN_RACTANGLE` |
| `0x00001036` | `APICD_GET_CONTENT_FILE_TYPE` |
| `0x0000103c` | `APICD_GET_CONTENT_PROFILE` |
| `0x00001046` | `APICD_CONV_HNDL2ENTRYID_LIST` |
| `0x00001048` | `APICD_CHECK_CONTENT_EXIST` |
| `0x00001054` | `APICD_GET_FOCUSED_CONTENT_POS` |
| `0x00002001` | `APICD_CONTENTLIST_DESTROY_ID` |
| `0x00002003` | `APICD_CONTENTLIST_DEL_ENTRYID` |
| `0x00002005` | `APICD_CONTENTLIST_DEL_ALL_ENTRYID` |
| `0x00002007` | `APICD_CONTENTLIST_IS_EXIST_ENTRY` |
| `0x00002009` | `APICD_CONTENTLIST_GET_ENTRY_POS` |
| `0x00003001` | `APICD_CREATE_CONTENT_POS_HNDL` |

---

## 5. Content Manager Subsystem (`0x3700`, `ObjCntMgr`)

Recovered from `ObjCntMgr::ParseObjCommand`:

| Message ID | Command / Event Name | Role |
|---|---|---|
| `0x0000100a` | `MSGID_GET_FORMAT_TIME_CMD` | Request estimated media format duration |
| `0x0000100b` | `MSGID_GET_FORMAT_TIME_CMP` | Format duration response |
| `0x00001022` | `MSGID_FORMAT_CMD` | **Primary Format Request** |
| `0x00001023` | `MSGID_FORMAT_CMP` | Format completion reply |
| `0x00001024` | `MSGID_FORMAT_PROGRESS_EVT` | Format progress percentage event |
| `0x00001026` | `MSGID_UNLOAD_EVT` | Media unloaded event |
| `0x0000102a` | `MSGID_SET_CONTENT_TARGET_CMD` | **Set Content Target** (configures active type) |
| `0x0000103c` | `MSGID_CREATE_APP_STRUCTURE_CMD` | Create camera directory structure |
| `0x10000002` | `MSGID_LOAD_EVT` | Media loaded event |
| `0x10000013` | `MSGID_MOUNT_EVT` | Filesystem mounted event |
| `0x10000014` | `MSGID_UNMOUNT_EVT` | Filesystem unmounted event |
| `0x1000001e` | `MSGID_FSYS_FORMAT_CMD` | Low-level filesystem format command |
| `0x1000001f` | `MSGID_FSYS_FORMAT_CMP` | Low-level filesystem format completion |
| `0x10000036` | `MSGID_MASS_STORAGE_START` | USB MSC started |
| `0x10000037` | `MSGID_MASS_STORAGE_END` | USB MSC ended |
| `0x1000005a` | `MSGID_TEMPERATURE_RANGE_NORMAL` | Thermal threshold OK |
| `0x1000005b` | `MSGID_TEMPERATURE_RANGE_OVER` | Thermal protection triggered |

---

## 6. Playback Engine (`0x3600`, `ObjPlayer`)

69 commands and events recovered from `DefObjPlayer` table at `0x1365b00`:

| Message ID | Command / Event Name |
|---|---|
| `0x00001000` | `MSGID_PB_START_CMD` |
| `0x00001001` | `MSGID_PB_START_CMP` |
| `0x00001002` | `MSGID_PB_STOP_CMD` |
| `0x00001003` | `MSGID_PB_STOP_CMP` |
| `0x00001004` | `MSGID_CHANGE_PB_SPEED_CMD` |
| `0x00001006` | `MSGID_CHANGE_CONTENTS_CMD` |
| `0x00001008` | `MSGID_SET_PB_CONFIG_CMD` |
| `0x0000100a` | `MSGID_MAKE_SCENARIO_CMD` |
| `0x0000100c` | `MSGID_SAVE_SCENARIO_CMD` |
| `0x0000100e` | `MSGID_LOAD_SCENARIO_CMD` |
| `0x00001010` | `MSGID_PB_START_BGM_CMD` |
| `0x00001016` | `MSGID_REQ_CACHE_INSTANCE_CMD` |
| `0x00001020` | `MSGID_GET_RESUME_POINT_CMD` |
| `0x00001022` | `MSGID_GET_PB_POSITION_CMD` |
| `0x00001026` | `MSGID_SET_CONV_CACHE_INSTANCE_CMD` |
| `0x0000102a` | `MSGID_CLEAR_CONV_CACHE_INSTANCE_CMD` |
| `0x0000102c` | `MSGID_GET_HIGHLIGHT_INFO_CMD` |
| `0x00002000` | `MSGID_INTERNAL_PB_STOP_EVT` |
| `0x00002001` | `MSGID_CAM_INFO_EVT` |
| `0x00002002` | `MSGID_GPS_INFO_EVT` |
| `0x00002005` | `MSGID_PB_TIME_EVT` |
| `0x00002006` | `MSGID_PB_STATUS_EVT` |
| `0x0000200b` | `MSGID_CONTENT_TYPE_EVT` |

---

## 7. Face Recorder (`0x3a44`, `ObjFaceRecorder`)

Dispatch table at `0x13dc504` in `libObj.so` (29 entries):

| Message ID | Command / Event Name | Reply ID |
|---|---|---|
| `0x00006500` | `MSGID_SYNC_REQ_RECORDED_FACE_NUM_CMD` | `0x6501` (`_CMP`) |
| `0x00008500` | `MSGID_NOTIFY_RECORDED_FACE_NUM_EVT` | — |
| `0x00007500` | `MSGID_SET_FACE_FRAME_CMD` | `0x7501` (`_CMP`) |
| `0x00008501` | `MSGID_NOTIFY_FACE_DETECTED_EVT` | — |
| `0x00007502` | `MSGID_FACE_RECORD_CMD` | `0x7503` (`_CMP`) |
| `0x00007504` | `MSGID_FACE_LIST_DISPLAY_START_CMD` | `0x7505` (`_CMP`) |
| `0x00007506` | `MSGID_FACE_LIST_DISPLAY_CANCEL_START_CMD` | `0x7507` (`_CMP`) |
| `0x00008502` | `MSGID_NOTIFY_FACE_LIST_DISPLAY_EVT` | — |
| `0x00008503` | `MSGID_NOTIFY_FACE_LIST_DISPLAY_END_EVT` | — |
| `0x00007508` | `MSGID_ALL_FACE_DELETE_CMD` | `0x7509` (`_CMP`) |
| `0x0000750a` | `MSGID_FACE_DELETE_CMD` | `0x750b` (`_CMP`) |
| `0x0000750c` | `MSGID_FACE_PRIORITY_CHANGE_CMD` | `0x750d` (`_CMP`) |

---

## 8. Summary of Solved Mysteries

| Scenario Immediate | Previous Status | Resolved Definition | Source |
|---|---|---|---|
| `cat=0x3700, msg=0x1022` | "Format request" | `MSGID_FORMAT_CMD` | `ObjCntMgr::ParseObjCommand` |
| `cat=0x3700, msg=0x102a` | "Content count" | `MSGID_SET_CONTENT_TARGET_CMD` | `ObjCntMgr::ParseObjCommand` |
| `cat=0x6000, msg=0x81000` | "Phase 1" | `NetDbIf::createRootHandle` / `createChildHandle` | `libNetContUtil.so` |
| `cat=0x6000, msg=0x81003` | "Phase 2" | `NetDbIf::getContentType` / `getItemAttribute` | `libNetContUtil.so` |
| `cat=0x6000, msg=0x1001` | "Retrieve count" | `NetDbIf::destroyHandle` | `libNetContUtil.so` |
| `cat=0x2000, msg=0x1` | "Unknown category" | `CATEID_PIN` pin descriptor to `GetPin`/`ConnectPin` | `libMWF.so` (`ConvMessageId`) |

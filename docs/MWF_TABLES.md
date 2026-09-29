# libSysDef.so: the tables that name every id in the vocabulary

`libSysDef.so` is 3.2 MB and exports 18 symbols. Three of them are the tables
the whole MWF command space is built from:

    MWF::MwfTbl::m_cateTbl    264 bytes    33 categories
    MWF::MwfTbl::m_pinTbl     192 bytes    12 pins
    MWF::MwfTbl::m_objTbl     540 bytes    45 objects

`SCENARIO_VOCAB.md` recovered ids like `0x3700`, `0x6000` and `0x81003` out of
the plugins' code but had no way to say *which subsystem* they name. That
answer is here, in a library, with the names in it.
`research/firmware/sysdef_tables.py` dumps all three.

## How the tables are laid out

Each is an array of fixed-stride records with a `u32` pointer into the same
object, so the tables are self-describing — read the words, follow the
pointer, and the name is there. **The stride differs per table and does not
change between entries:**

| table | stride | shape |
|---|---:|---|
| `m_cateTbl` | 8 | `{u32 id, u32 name}` |
| `m_objTbl` | 12 | `{u32 id, u32 name, u32 aux}` |
| `m_pinTbl` | 16 | `{u32 id, u32 aux, u32 name, u32 name}` |

Guessing the stride fails in a way that produces plausible nonsense rather
than an error, which is why it is worth stating:

- read at **8**, `m_pinTbl` yields `\x7fELF` — it has followed a zero word to
  vaddr 0, which is the ELF header, and printed its first four bytes as a
  "name"
- read at **12**, it interleaves the id column with the name column, so
  `PIN_PANEL` appears against the id `0x1987a`

Neither raises. Both look like data.

## The tables

### Categories — 33

```
0x00000000  CATEID_UNKNOWN              0x00006000  CATEID_DATABASE
0x00000001  CATEID_NONE                 0x00006010  CATEID_INFRA_CACHEMGR
0x00000002  CATEID_MWF                  0x00006020  CATEID_INFRA_SALVAGESTATUS
0x0000ffff  CATEID_ALL                  0x00006100  CATEID_INFRA_SELECTOR
0x00001000  CATEID_APP                  0x00006101  CATEID_HOTPLUG
0x00001100  CATEID_APP_FRAMEWORK        0x00006102  CATEID_USBHOSTSTORAGE
0x00001200  CATEID_APP_MODELS           0x00006103  CATEID_USBCONTROL
0x00001300  CATEID_APP_VIEWS            0x00006104  CATEID_MSCSERVER
0x00001400  CATEID_APP_WIDGETS          0x00006105  CATEID_MTPSERVER
0x00001500  CATEID_APP_INPUT            0x00006106  CATEID_INFRA_MEDIA_PWRMGR
0x00001600  CATEID_APP_WRAPPERS         0x00006107  CATEID_BUSPOWER
                                       0x00006108  CATEID_INFRA_STILLPOOL
                                       … 0x0000610c CATEID_INFRA_REMOTE
                                         0x0000610d CATEID_INFRA_PTPCTRL
                                         0x0000610e CATEID_INFRA_WEBAPI
                                         0x0000610f CATEID_INFRA_HIGHLIGHT
                                         0x00006110 CATEID_INFRA_MAKESCENARIO
                                         0x00006111 CATEID_INFRA_BGMMETA
                                         0x00006112 CATEID_INFRA_IPTC
```

`0x1000`–`0x1600` is the application layer, split the same way `libObj.so`'s
exports are (`Model*ToInstance` screens under `APP_VIEWS`, `Ts*` text under
`APP_FRAMEWORK`, and so on). `0x6100`–`0x6112` is the infrastructure layer,
and it is the remote stack from `libIMDB`'s manifest: `INFRA_REMOTE`,
`INFRA_PTPCTRL`, **`INFRA_WEBAPI`**, `HIGHLIGHT`, `MAKESCENARIO`, `IPTC`.
**`CATEID_INFRA_WEBAPI` is the web API, as a first-class category id** — the
thing `docs/ATTACK_SURFACE.md` could not place.

### Objects — 45

Named after the object they address, so this is a component map:

```
0x3100 ObjCamera          0x3a00 ObjMediaServer     0x3a49 ObjScalar
0x3300 ObjMovieRecorder   0x3a10 ObjInbox           0x3a4a ObjRemote
0x3410 ObjSystemSound     0x3a20 ObjUploader        0x3a4b ObjNetExternalStreaming
0x3430 ObjMic             0x3a30 ObjCameraAgent     0x3a4c ObjExternalInput
0x3450 ObjSpeaker         0x3a40 ObjImporter        0x3a4d ObjHandover
0x3500 ObjStillRecorder   0x3a41 ObjFinalize        0x3a4e ObjRemoteClient
0x3600 ObjPlayer          0x3a42 ObjSalvage         0x3a4f ObjMetaRecorder
0x3700 ObjCntMgr          0x3a43 ObjDvdWriterFirmup 0x3a50 ObjAvAdjCtrl
0x3710 ObjEditor          0x3a44 ObjFaceRecorder    0x3a51 ObjRemoteAsync
0x3720 ObjDubbing         0x3a45 ObjNetUploader     0x3a52 ObjFtpClient
0x3800 ObjMedia           0x3a46 ObjNetMediaServer  0x3a53 ObjGenlock
0x3900 ObjEffect          0x3a47 ObjNetBackupServer 0x3a54 ObjNetSetting
0x3950 ObjMap             0x3a48 ObjConverter       0x3a55 ObjMediaServerResident
                                                  0x3a56 ObjStreamingUsb
```

`ObjAvAdjCtrl` at `0x3a50` is the AV adjustment control — the same surface as
the `adjstctl.elf` tool already mapped from the service side, now with its
in-system name.

### Pins — 12

```
0x2001 PIN_YC             0x2007 PIN_MEDIA_STATUS
0x2002 PIN_PANEL          0x2008 PIN_STILL_DATA
0x2003 PIN_LINE           0x2009 PIN_EDIT_INFO
0x2004 PIN_SOUND          0x200a PIN_CAMERA_STATUS
0x2005 PIN_REC_CNT_INFO   0x200b PIN_IMPORT_CNT
0x2006 PIN_PB_CNT_INFO    0x200c PIN_EXPORT
```

These are the dataflow connections the AVBB plugins call `PinConnect_*` and
`CheckPinUnConnect*` on by name. `PIN_CAMERA_STATUS` is the camera→UI status
channel; `PIN_STILL_DATA` carries captured stills.

## Cross-check: the vocabulary resolves

Feeding the ids recovered from the plugins back through these tables resolves
**4 of 5**:

| plugin id | name |
|---|---|
| `0x0001` | `CATEID_NONE` |
| `0x2000` | *not in any table* |
| `0x3700` | `ObjCntMgr` — the content manager |
| `0x3800` | `ObjMedia` |
| `0x6000` | `CATEID_DATABASE` |

And the flat vocabulary, checked against the pin table:

    0x2001  PIN_YC       17 uses
    0x2004  PIN_SOUND    76 uses

**The single most common id in the entire 96-value vocabulary is `PIN_SOUND`,
used 76 times.** That is the audio dataflow pin, and the AVBB audio/HDMI
scenarios are largely routing signal along it. This is the kind of answer that
only falls out of having the table — `0x2004` means nothing without it.

The two tables are parallel, not nested: the object table carries ids in the
same ranges as the category table (`0x3700` is both a plausible category and
`ObjCntMgr`), so an id has to be looked up in the right one. `0x3700` and
`0x3800` are **objects**, not categories — which is why an earlier check
against the category table alone called them misses.

## What is still open

`0x2000` is used by `MPR_SCN_INSTALL_MAP_DEMOMOVIE` and is in none of these
three tables. It is category-shaped, so either there is a fourth table or it is
allocated elsewhere. The message ids `0x1001`, `0x1022`, `0x102a` and
`0x81000`/`0x81003` are the *message* half of the pair, not the category, and
no table here names them; the per-object message vocabulary is the next thing
to recover and it is not in this library.

Two much larger tables are also exported and untouched:
`DefInh::sm_refTbl` (3,158,400 bytes — 97% of the file) and
`DefRsrc::scm_refTbl` (98,778). `DefRsrc::GetRsrcMgrId` and
`GetRsrcMgrCount` take an `AcsrId_t`, so the resource table is indexed by
resource id rather than message id. Those two are the natural next target for
whatever the categories refer to.

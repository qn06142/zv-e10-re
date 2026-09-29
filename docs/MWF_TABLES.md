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

Each is an array of fixed-stride records with `u32` pointers into the same
object, so the tables are self-describing — read the words, follow the
pointers, and the names are there. **The stride differs per table and does not
change between entries:**

| table | stride | shape |
|---|---:|---|
| `m_cateTbl` | 8 | `{u32 id, u32 name}` |
| `m_objTbl` | 12 | `{u32 id, u32 CATEID_*, u32 Obj*}` — **two names** |
| `m_pinTbl` | 16 | `{u32 id, u32 aux, u32 name, u32 name}` |

Guessing the stride fails in a way that produces plausible nonsense rather
than an error, which is why it is worth stating:

- read at **8**, `m_pinTbl` yields `\x7fELF` — it has followed a zero word to
  vaddr 0, which is the ELF header, and printed its first four bytes as a
  "name"
- read at **12**, it interleaves the id column with the name column, so
  `PIN_PANEL` appears against the id `0x1987a`

Neither raises. Both look like data.

`m_objTbl` carries **two** names per record, and picking by position gets it
backwards: the second word is the `CATEID_` name and the third is the `Obj*`
name. An earlier positional read reported `ObjCntMgr` for `0x3700` — where the
category is really `CATEID_CNT_MGR`. Both names are printed below, because the
pairing is the interesting part: the object table is a map from object to the
category that owns it.

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

### Objects — 45, and which of them are implemented

Every record names both the object and the category that owns it. Joining that
against `libObj.so`'s exports — which carries exactly one
`Obj*_RegisterCommand` / `_UnregisterCommand` pair per implemented object —
splits the table cleanly:

**Implemented in `libObj.so` — 25:**

```
0x3100  (declared only)                     0x3a48  ObjConverter         CATEID_CONVERTER
0x3200  ObjRenderer        CATEID_RENDERER   0x3a4a  ObjRemote            CATEID_REMOTE
0x3300  ObjMovieRecorder   CATEID_MOVIE_RECORDER
                                         0x3a4f  ObjMetaRecorder      CATEID_META_RECORDER
0x3400  ObjDisplay         CATEID_DISPLAY    0x3a50  ObjAvAdjCtrl         CATEID_AVADJCTRL
0x3410  (declared only)                     0x3a51  ObjRemoteAsync       CATEID_REMOTE_ASYNC
0x3420  ObjAudioProcessor  CATEID_AUDIOPROCESSOR
                                         0x3a52  ObjFtpClient         CATEID_FTP_CLIENT
0x3430  ObjMic             CATEID_MIC        0x3a53  ObjGenlock           CATEID_GENLOCK
0x3440  (declared only)                     0x3a54  ObjNetSetting        CATEID_NET_SETTING
0x3450  ObjSpeaker         CATEID_SPEAKER    0x3a56  ObjStreamingUsb      CATEID_STREAMING_USB
0x3500  ObjStillRecorder   CATEID_STILL_RECORDER
0x3600  ObjPlayer          CATEID_PLAYER     0x3700  ObjCntMgr            CATEID_CNT_MGR
0x3710  ObjEditor          CATEID_EDITOR     0x3720  ObjDubbing           CATEID_DUBBING
0x3800  ObjMedia           CATEID_MEDIA      0x3900  ObjEffect            CATEID_EFFECT
0x3a40  ObjImporter        CATEID_IMPORTER   0x3a42  ObjSalvage           CATEID_SALVAGE
0x3a46  ObjNetMediaServer  CATEID_NET_MEDIA_SERVER
```

**Declared in the table but with no `RegisterCommand` in `libObj.so` — 20:**

```
0x3100 ObjCamera        0x3440 ObjMixer              0x3a41 ObjFinalize
0x3410 ObjSystemSound   0x3950 ObjMap                0x3a43 ObjDvdWriterFirmup
0x3a00 ObjMediaServer   0x3a10 ObjInbox              0x3a44 ObjFaceRecorder
0x3a20 ObjUploader      0x3a30 ObjCameraAgent        0x3a45 ObjNetUploader
0x3a47 ObjNetBackupServer  0x3a49 ObjScalar           0x3a4b ObjNetExternalStreaming
0x3a4c ObjExternalInput 0x3a4d ObjHandover           0x3a4e ObjRemoteClient
0x3a55 ObjMediaServerResident
```

**The join is exact: 25 implemented, 20 declared-only, and zero orphans in
either direction.** Every `Obj*` in `libObj.so` appears in the table, and
every table entry with a `RegisterCommand` in `libObj.so` is in the table.
That is a strong consistency check on both sides — it is very unlikely two
independent symbol lists agree exactly by accident.

The 20 unimplemented ones are not missing so much as *pluggable*: `ObjMap`,
`ObjFaceRecorder`, `ObjNetBackupServer`, `ObjStreamingUsb` and the rest are
features gated by model or region, and the table reserves the id whether or not
the build fills it in. `ObjCamera` (`0x3100`) being declared-only is the
interesting one — the camera object is presumably provided by a library that is
not `libObj.so`.

`ObjAvAdjCtrl` at `0x3a50` is the AV adjustment control — the same surface as
the `adjstctl.elf` tool already mapped from the service side, now with its
in-system name and category.

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
| `0x3700` | `ObjCntMgr` / `CATEID_CNT_MGR` — the content manager |
| `0x3800` | `ObjMedia` / `CATEID_MEDIA` |
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
three tables. It is category-shaped (`0x2001`–`0x200c` are the pins, so
`0x2000` is plausibly a pin *group*), but that is an inference and is recorded
as one.

The message ids `0x1001`, `0x1022`, `0x102a` and `0x81000`/`0x81003` are the
*message* half of the pair, not the category, and no table here names them.
A second id array in `libObj.so` does contain `0x1001` — but not the other
four, so it is a different space that overlaps rather than the registry the
plugins draw from. That array also contains a `0x4xxx` group
(`0x4000`, `0x4100`, `0x4200`, `0x4300`, `0x4400`) that **nothing in these
tables names**. The per-object message vocabulary remains the open item; it is
not in `libSysDef.so` and not in the `IMCFG` block.

Two much larger tables are also exported and untouched:
`DefInh::sm_refTbl` (3,158,400 bytes — 96.7% of the file) and
`DefRsrc::scm_refTbl` (98,778). `DefRsrc::GetRsrcMgrId` and
`GetRsrcMgrCount` take an `AcsrId_t`, so the resource table is indexed by
resource id rather than message id. Those two are the natural next target for
whatever the categories refer to.

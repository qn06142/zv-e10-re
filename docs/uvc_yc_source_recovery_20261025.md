See [26 October native640x480 continuation](uvc_yc_live_source_20261026.md) for new execution evidence and scope corrections to the historical geometry/alignment claims below.

# Live YC source recovery — 25 October 2026

Scope is offline reverse engineering toward real camera frames through the working 2.4p YUY2 transport. Loader diagnostics are set aside at the user's instruction. No camera access, hardware test or firmware/RAM change occurred during this work. The previous revision3 RAM installation is historical; current camera state is unknown and old addresses must not be replayed.

## Verified metadata, with executable evidence

Executed Sony libObj.so Thumb printer at0x2c3678 and genuine dataflowInfraFramework.so GetData_All at0x246d6 against a tagged60-byte input; only printf/memory imports were stubbed. This recovers field offsets and widths from Sony's actual loads and field labels, not the team's earlier mock IPC structures. The following fields are verified; their numeric enum meanings, byte strides and plane layout are NOT established by this experiment.

| Field | Offset | Bytes |
|---|---:|---:|
| imageAttach | `0x00` | 1 |
| unitType | `0x04` | 4 |
| unitHandle | `0x08` | 2 |
| unitDataOffset | `0x0c` | 4 |
| recordSizeX | `0x14` | 2 |
| recordSizeY | `0x16` | 2 |
| canvasSizeX | `0x18` | 2 |
| canvasSizeY | `0x1a` | 2 |
| validOffsetX | `0x1c` | 2 |
| validOffsetY | `0x1e` | 2 |
| validSizeX | `0x20` | 2 |
| validSizeY | `0x22` | 2 |
| targetOffsetX | `0x24` | 2 |
| targetOffsetY | `0x26` | 2 |
| targetSizeX | `0x28` | 2 |
| targetSizeY | `0x2a` | 2 |
| dataSite | `0x2c` | 1 |
| iibNumber | `0x2d` | 1 |
| aspect | `0x2e` | 1 |
| ycCompress | `0x2f` | 1 |
| dataTransfer | `0x30` | 1 |
| dataPlacement | `0x31` | 1 |
| dataContent | `0x32` | 1 |
| dataScan | `0x33` | 1 |
| stripWidth | `0x34` | 2 |

## Genuine memory path

libBizFw.so `DmmCh::freeSdsAndYc`,0x364a0..0x3662c, opens the SDS handle at0x364d8 and maps its returned address/capacity through AvbbcPhycMem. It builds StdData_YC at0x36536, extracts ImageSizeInfo at0x36546/0x3655e, and reads the pixel memory handle at metadata+0x08 (`ldrh` at0x36574). That handle goes to DmmCh::free at0x3657a. The SDS unit is separately closed and freed at0x365b0/0x365dc. This proves metadata and pixel storage can have separate handles. This cleanup function MUST NOT be invoked for a borrowed source frame. It does not prove that opening a DMM unit freezes live pixels.

libObj.so renderer consumer0x2bbad4..0x2bbd08 opens the incoming handle at0x2bbb6c, stores the returned address/capacity at input record+0x0c/+0x10, and sends a real ObjMsg request via an existing object interface at0x2bbbfc. The numeric0x39 there belongs to that local object interface; it is NOT a recovered RTOS acquisition opcode. The renderer extracts `PARAMID_YC_DATA_MEM_HANDLE`0x1719 from the reply at0x2bbc3a..0x2bbc46.

The actual `ExecCommandGetYcDataParam` implementation is0x2c2154..0x2c29b8: it reads an address/capacity pair from MWF Struct param0xe001, maps the SDS allocation with AvbbcPhycMem, parses StdData_YC at0x2c2364, extracts the unit handle at0x2c262c, adds it as parameter0x1719, and copies geometry/aspect/color fields into a28-byte MWF Struct reply at0x2c2840..0x2c28ca. It resets StdData_Base's address binding before destruction at0x2c28d8. This is a real delivered-frame consumer path; whether this exact sequence handles active preview during USB Streaming is still unproven.

## New source component

`sony_yc_metadata.h/.c` decodes only the25 verified fields and resolves a bounded byte span from one DMM address/capacity pair plus unitDataOffset. It does not classify YUY2/NV16/NV12, fabricate planes, subscribe, acquire or release. No modification of the transport or default synthetic output is made. Existing guessed Sony backend remains fail-closed.

The compiled Cortex-A5 ARM decoder matches all25 field values emitted by the real Sony printer/getter experiment, including unaligned input. All60 truncated input lengths are rejected without changing output. Invalid extents, offsets and32-bit physical wrap are rejected; the final addressable physical byte is handled. These tests validate metadata decoding/bounds, not source ownership or webcam delivery.

## Reproducible investigation artifacts

Session `outputs/yc-source-re-20261025/`: `image-size-layout-verified.json`, `metadata-decoder-verification.json`, `libObj.yc-raw-xrefs.json`, `libObj.selected-consumers.json/.txt`, `renderer-get-yc-param.txt`, and `libBizFw.so.yc-callers.json/.txt`. Raw scan found190 candidate YC-related callsites in libObj; unwind boundaries from61886 ARM exidx records narrowed consumers and recovered embedded source labels. Raw callsite hits still require function/context validation; do not assume all190 are live-frame paths.

Saved baseline application log decodes114050 records /3166203 bytes with zero corruption/slack. It contains viewfinder state transactions but provides no verified source metadata or frame ownership token. Logs were already archived and cleared on camera in the prior session. User standing procedure remains archive/hash-verify/clear diagnostic captures around each hardware test, with bounded fresh logging.

## Remaining work required for a live webcam patch

Trace renderer input delivery/acknowledgment and the producer that supplies it, distinguishing preview from playback/still paths. Prove when the YC unit can be safely read and how to return its frame reference. Recover dataPlacement/dataTransfer/ycCompress numeric meanings and pixel stride/plane offsets from actual consumers. Only then bind a bounded source to `raw_live_ops` and the existing converter. A working live webcam patch is not yet established; guessing source units or repurposing cleanup/free calls would invalidate the ownership contract.

## Native pin and RTOS producer recovery — handoff checkpoint

Work stopped at the user's request on25 October2026. No camera access or new installation. This checkpoint adds source components and genuine execution evidence; it does not establish a working live-camera webcam patch. Permanent2.4p bars/counters remains the last hardware-verified output. Metadata decoder still normalizes25 fields; six additional field offsets were just recovered but are not yet integrated into that decoder.

### Native delivery protocol and new source files

The actual SDK SEND constructor0x219ae emits52 bytes with little-endian header(category0x1000, opcode0x0102, size0x34, version1). COMPLETE constructor0x219e4 emits44 bytes, header(0x1000,0x8102,0x2c,1). SEND+8 is the producer/output PIN_PROPERTY; +0x18 is the consumer/input property. Each property is four u32: data_type, direction, index, queue. SEND+0x28 is an opaque tag, +0x2c a u16 SDS metadata unit, +0x2e reserved, +0x30 opaque auxiliary word. COMPLETE retains the SAME logical output/input property order and contains signed completion status at+0x28. It contains no unit/tag; preserve completion ordering per pin. SEND_WITH_DATA is a distinct64-byte variant, unsupported by the new52-byte decoder. A native ACK alone does not prove an immutable pixel lease.

`research/firmware/raw_frame_source/verified_yc/sony_yc_pin_wire.h/.c` implements byte-wise bounded SEND decoding and exact COMPLETE encoding, including alias-safe encoding. Verification executes original SDK SendComp0x21fc4 and original constructors; C output matches the Sony acknowledgement bytes, including negative status. All52 truncated SEND lengths and four invalid header fields reject. Message wrappers and OSAL sender were intercepted; no OSAL IPC ran.

`sony_yc_sds.h/.c` is a bounded container reader that avoids Sony C++ construction in the future source path. Actual Sony YC constructor/CreateHeader and SetEntryData produced SSYC containers with32-byte header, version1 at+8, count at+0xc, first-entry offset+0x10. ETRY nodes have category+4, data offset+0xc, data size+0x10, next-entry offset+0x14; nodes occupy32 bytes. All offsets are container-relative. Image category is0. Native SDK padded the60-byte image entry to64 bytes. The reader accepts supported version1, caps traversal at64 entries, checks mapped extents and normalizes the existing25 fields. It performs no mapping, subscription, pin acknowledgement or pixel-format classification. Tests execute original Sony insertion, lookup and GetData_All: single-entry data and a two-entry chain agree;128 truncations, eight malformed headers/extents and missing/cyclic/invalid links pass. The three C components compile together for Cortex-A5 with Wall/Wextra/Werror and no undefined symbols.

### RTOS identity, pin registrations and source path

Flat RTOS image is `dumps/firmware/av-cam.bin`, MD5 cdcae9d4fdbf66a33704a4c7564e346d, runtime base0x635c6000. Input hashes are preserved in evidence/input-binary-hashes.json. Most string references are PIC LDR-literal plus ADD-PC, so absolute string scans miss consumers. Raw branch hits require context validation; embedded literal pools can disassemble as instructions.

The Linux pin constructor matches RTOS0x63ac1a48; object size0x38, peer property+8, self property+0x18, state+0x28. Native Pin::Send is0x63ac1b8c; SendComp0x63ac1ce4. Direction1 is input,2 output; direction3 exists but its meaning is not established.

VDF initializer0x63744f30 copies12 registrations from0x63e4423c. Table row order is(index,data_type,direction,queue), reordered into PIN_PROPERTY. Native VDF queue is0x0059000e. Registration rows2/3/4/5 are type0 outputs with source indices0/1/2/3. The wrapper0x6374580c takes a REGISTRATION ARRAY INDEX and indexes pin objects at stride0x38. Do not confuse this index with the source property's index. Tail thunk0x63cf57a0 is vtable0x64583160 slot+0xb4. VEF initializer0x6376278c has15 rows from0x63e5ff7c and queue0x005a0048. Old guessed queue0x01670464/pin0x00550101 is not this verified ABI. Do not revive the fake0x400 acquisition backend.

`VDF::SystemCmdSysv::Execute` contains inlined `out_pin0_send`, identified by source label at0x6374c55a (NOT a standalone function entry). It extracts native YUVInfo from message parameter0x11 using0x63ce259a, then invokes the real metadata builder0x6374ae88 at0x6374c58c/0x6374c5b6 with slot1. It sends SDS through registration index2 at0x6374c5e6. Slot2 builder call0x6374c8c6 precedes registration index3 send0x6374c922.

The builder copies unitType from nativeYUVInfo+0x24+slot*0x40 and unitHandle from+0x28+slot*0x40, but unitDataOffset always from common+0x2c. Exposure bytes are copied from input+1..4, aspect from+a, transfer/placement/content/scan from+c..f, stripWidth from+0x10. Geometry comes from12-byte records at0x63e4433c. Executing the original builder with all four slots and no external stubs proves this mapping. Initial image records are3840x2160/ycCompress1,3840x2160/1,1920x1080/1,1280x720/0. These are OFFLINE INITIAL DATA, not active camera geometry. Transfer/placement/type/handle values in that experiment are synthetic input tags. Slot3 is a possible lead, not a verified linear preview source; no direct slot3 builder call was found.

Immediately before pin0 SEND,0x6374c5d0 dispatches through the ownership object's first virtual method. Executing real object constructors resolves vtables0x645852c8 (first method0x63748bec) and logging wrapper0x64585300 (first method0x63748da0). Method0x63748bec passes type/handle to0x6371f60c, which emits DMM command2, with embedded debug labels vdf:mm-sha-s/e: this is a real share operation. The temporary metadata mappings are closed via0x6371f4a0 after SEND, using command6. Share/open establishes allocation references; producer completion and write-stability rules still need tracing. Do not replace them with freeSdsAndYc or borrow cleanup methods.

### Additional verified fields and unresolved source layout

`verify_individual_getters.py` executed all31 named scalar ImageSizeInfo getters against a byte-tagged fixture. The six fields previously omitted by the debug printer are ExposureTime+0x10/u8, ExposePicDelay+0x11/u8, ScenarioEnd+0x12/u8, Mirror+0x13/u8, YcBitDepth+0x36/u8 and CamFreqCharH+0x38/u16. All 31 fields are now fully integrated into `sony_yc_metadata.h/.c` and verified in Unicorn via `verify_metadata_decoder.py` against both compiled Cortex-A5 code and Sony's actual SDK getter execution.

Additionally, two other entry categories in the SSYC container have been completely recovered and verified:
1. **Category 1: `C_DataflowInfra_Entry_YcStateInfo`** (6 wire bytes):
   - Offsets: `y_range` (+0x00, u8), `colorimetry` (+0x01, u8), `chroma_phase` (+0x02, u8), `scanline` (+0x03, u8), `copy_protection` (+0x04, u8), `author` (+0x05, u8).
   - Implemented in `sony_yc_state_decode` and supported in `sony_yc_sds_decode_state`.
2. **Category 0x11: `C_DataflowInfra_Entry_MultipleSegmentImageInfo`** (288 wire bytes = 0x120 bytes):
   - Layout: 32-byte header followed by up to 4 segment descriptors of 64 bytes each (`0x20 + i * 0x40`).
   - Header contains global geometry and camera timing: `image_attach` (+0x00), `exposure_time` (+0x01), `expose_pic_delay` (+0x02), `scenario_end` (+0x03), `mirror` (+0x04), `record_size_x, y` (+0x06, +0x08), `aspect` (+0x0a), `yc_compress` (+0x0b), `data_transfer` (+0x0c), `data_placement` (+0x0d), `data_content` (+0x0e), `data_scan` (+0x0f), `strip_width` (+0x10), and `total_segment_num` (+0x1f).
   - Each segment slice carries separate DMM unit parameters (`unit_type` +0x04, `unit_handle` +0x08, `unit_data_offset` +0x0c) and slice geometry (`canvas_size_x, y` +0x10, +0x12, `valid_offset_x, y` +0x14, +0x16, `valid_size_x, y` +0x18, +0x1a, `target_offset_x, y` +0x1c, +0x1e, `target_size_x, y` +0x20, +0x22, `data_site` +0x24, `iib_number` +0x25).
   - In QFHD (4K) split-transfer mode, it carries 2 active segments representing left and right halves.
   - Genuine RTOS converters from `av-cam.bin` were reverse engineered and verified byte-for-byte in Unicorn against our Cortex-A5 compiled C implementation (`verify_multi_segment.py`):
     - `0x63cebf24`: extracts an individual slice (`slot` 0 or 1) into a standard 60-byte `ImageSizeInfo`.
     - `0x63cebfbe`: splits a single `ImageSizeInfo` into a 2-segment dual-strip container.
     - `0x63cec0d8`: merges dual horizontal slices back into a full-width `ImageSizeInfo` by summing slice widths (`canvas_size_x`, `valid_size_x`, `target_size_x`).

### VDF DMM IPC commands, ownership manager vtable and release handler

The complete VDF DMM IPC wrapper family in `av-cam.bin` (`0x6371f4a0..0x6371f8f8`) has been disassembled and documented:
- `0x6371f6cc`: **DMM Command 1 (Alloc unit)**. Issues IPC request, writes returned unit handle to `[obj+4]` and physical address to `[obj+0x0c]`.
- `0x6371f60c`: **DMM Command 2 (Share unit)**. Takes source handle and destination queue (`dst_queue`), returns cross-context shared handle. Used exclusively before pin0 SEND.
- `0x6371f7ac`: **DMM Command 4 (Immediate Free)** when `sync == -1` / **Command 13 (Delayed Sync Free)** when timed synchronization arguments are supplied. Zeros stored handle and mapping.
- `0x6371f540`: **DMM Command 5 (Open handle mapping)**. Maps shared handle, writes physical address to `[obj+0x0c]`.
- `0x6371f4a0`: **DMM Command 6 (Close handle mapping)**. Closes temporary mapping opened by Command 5 without freeing underlying unit.

The VDF Ownership Manager (`0x637489d4` -> vtable `0x645852c8` / logging decorator `0x64585300`) implements 10 virtual methods across 18 call sites:
- `+0x00` (`0x63748bec` / `0x63748da0`): `share_yc_mem` -> calls DMM Command 2 (Share). Used by `out_pin0_send` at `0x6374c5ba` and `0x6374c8f6`.
- `+0x04` (`0x63748bd0` / `0x63cfb054`): `free_handle` -> calls DMM Command 4 (Immediate Free).
- `+0x08` (`0x63748c0c` / `0x63cfb060`): `release_sds_and_yc_units` -> opens SSYC, looks up categories 0 and 0x0d, opens & frees non-zero YC handles via Command 5 + Command 4, then frees the SSYC handle.
- `+0x10` (`0x63748b2c` / `0x63748ca8`): `release_slot_yc_mem` -> frees primary and secondary DMM objects for `slot` via Command 4 or Command 13.
- `+0x14` (`0x63cfb020` / `0x63748ce0`): immediate free of slot YC memory (`sync = -1`).
- `+0x18` (`0x63748a94` / `0x63748d10`): frees stored SSYC pin unit handle for slot.
- `+0x1c` (`0x63748a4c` / `0x63748d6c`): frees primary DMM object and stores incoming `DrvCallDmm::CtrlData`.

The matching release and completion handler is `VDF::VdfInputReleasePinAndMem::Execute` (`0x63728000..0x6372889c`, `VdfInputCmdReleasePinandMem.cpp`). It receives incoming pin completions and uses ownership manager methods `+0x04`, `+0x08`, `+0x10`, and `+0x18` to retire previous frame references. `VDF::VdfInputCmdUpdateYuv::UpdateYuvThrough` (`0x6372d250..0x6372d62c`) and `UpdateYuvResize` (`0x6372d660..0x6372de70`) also rotate DMM handles via this manager at `0x6372d4a6` and `0x6372ddb2`.

### Hardware DMA alignment and geometry table constraints

- **SDF Plane/Stride Alignment**: Function `0x63a2e47c` in `av-cam.bin` inspects plane tables (`0x63dbcd70` / `0x63dbcdb8`) and enforces that every plane physical address and byte length must be 128-byte aligned (`tst.w reg, #0x7f == 0`), with total frame size capped at `0x4e00000` (81,788,928 bytes). Any unaligned plane triggers error logging at `0x63c5fe48`.
- **Builder Slot 3 Calling Status**: An exhaustive scan across all `BL` instructions in `av-cam.bin` proved that `0x6374ae88` has only 3 call sites: `0x6374c58c` (slot 1), `0x6374c5b6` (slot 1), and `0x6374c8c6` (slot 2). Slot 0 and Slot 3 (1280×720) are never invoked in `av-cam.bin`. Instead, preview downscaling is performed downstream via `UpdateYuvResize` using the 18-entry geometry table at `0x63e43e9c` (where entry 0 is 1080p and entry 1 is 640×480).

Movie consumer0x63691dec opens SDS;0x63691ebc opens its separate pixel unit;0x63691f94 shares the image;0x63692218 closes it. McAvcYcData image address getter0x63c6124a reads object+0x3c. Its setters consume DMM reply addresses. RTOS mapping helper0x63c48e0c dispatches via OSAL memory mapping functions; RTOS address to Linux physical translation is still unproven.0x63c618fc computes a frame ID/timestamp, not a pixel address. Previously suspected0x63b41d98 belongs to fc_api_face_record.cpp; actual fc_api_monitoring.cpp code starts around0x63b42800.

The VDF RGBA8888-to-YUV422 class executes hardware VFX configuration, not a CPU conversion loop. Its name does not prove that YC metadata placement values map to standard YUY2 or NV16. SDF compression mapper0x63cc3c3e and SetYcCompress0x636eb63c are further leads, not a recovered CPU pixel unpacker. Actual live routing, immutable lease/return, byte stride, plane offsets and pixel packing remain unresolved. Generic2.5 pipeline currently requires source640x480; higher dimensions also need an explicit, validated scale/crop step.

### Continue from here

Trace the native YUVInfo parameter0x11 producer, VDF type0 output index3 and the matching SEND completion handler. Distinguish per-frame reference ownership from allocation lifetime and determine whether a bounded CPU copy can precede acknowledgement. The VdfToAdfYcDataSenderImpl execute0x63748f44 builds a0x74-byte category0x2004/subcommand0x127 message at0x63cfb0b4; this is a metadata/control path, not itself a direct pixel getter. Preserve the verified ABI and keep the guessed backend fail-closed. Integrate only proven metadata additions, recover packing from actual consumers, and bind raw_live_ops only when a stable completed frame source and release semantics are established.

Evidence and scripts are preserved alongside the source under verified_yc/evidence and verified_yc. Full local investigation remains in `C:/Users/qn061/Documents/Codex/2026-10-22/chec/work/yc-source-re/` and `outputs/yc-source-re-20261025/`. Published verification scripts use the repo's existing verify_support loader, GCC at C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe, and Python from the repo .venv. Run from the workspace above, where the outputs directory exists. Emulation tests validate recovered code paths; they are not hardware webcam tests.

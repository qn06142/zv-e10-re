# Property semantics: the first property named from code, and a located rect

Date: 2026-09-28. Engine: `viewUnified2.so` (.text 7,647,084 B).
Scripts: `trace_bool2.py`, `find_setter_callers.py`, `arity_verify.py`, `find_rect_key.py`.

## 1. `c34c39a70111` is the caution flag

The first property whose meaning has been established from the code rather than
from its value distribution.

The chain, each step read directly:

```
0x002334f8  push {r4, r5, r7, lr}
0x002334fe  movs r0, #0x10
0x00233500  blx  0x18e5f8
0x00233504  bl   0x231054        ; property lookup
0x00233508  cbz  r0, ->false     ; absent -> return 0
0x0023350a  ldrb r1, [r0, #0x11] ; the payload byte
0x0023350c  cmp  r1, #1
0x0023350e  bne  ->false         ; != 1 -> return 0
0x00233516  b.w  0x23342a        ; tail call on true
```

A strict `== 1` test with a false path returning zero: a boolean, confirmed from
code. The predicate sits inside the exported symbol **`ViewCautionToInstance`**
(0x00231a12 .. 0x00236b0a). The setter at 0x0023342a is the same function's
local: it branches on the argument, passes 1 or 0 to 0x190a50, and writes the
value to a 2-byte slot at `[r4, #0x31]` mirrored to a byte at `[r4, #0x16c]`.

So the property is the **caution** flag: whether a caution overlay is shown.
This lands on a third option that the value distribution never offered — the
188 classes with the byte uniformly 1, the 18 uniformly 0 and the 32 mixed are
all consistent with a flag that most caution widgets set and a few do not.

## 2. The four "deserialisers" are constructors

This corrects an earlier note. 0x640850, 0x640878, 0x6408a0 and 0x648150 were
recorded as deserialisers. Read in full they are one identical function:

```
blx  0x1872c8          ; base-class constructor
ldr  r3, [r4, r3]      ; the class vtable
adds r3, #8
str  r3, [r5]          ; install vtable+8
movs r3, #0
str  r3, [r5, #0x14]   ; zero the payload
```

**Not one instruction reads the input stream.** They build, install a vtable and
zero. The consequence is the useful part: **the number of payload fields a
constructor zeroes is the property's arity**, and arity can be counted instead of
guessed at from a byte pattern.

`0x6408a0` is excluded and is not a property constructor at all. Its `r4`/`r5` are
reused for a PC-relative base, so its stores land in `.rodata`:

```
add  r5, pc            ; r5 is a rodata address, no longer 'this'
mov  r4, r5
str  r3, [r4], #0x14   ; patching a global table
```

## 3. Arity census, with the detector calibrated first

`arity_census.py` reported "exactly one arity-4 class" while its own
calibration was failing. That number was a property of the filter, not of the
binary, and was discarded. `arity_verify.py` replaces the displacement-reading
with a small abstract interpreter (r0 seeded as `this`; post-increment forms
tracked) and refuses to print a census unless it reproduces ground truth.

Calibration, and it passes:

| address | key | expected | got |
|---|---|---|---|
| 0x640850 | `ed188f1a018d` | 1 word @ 0x14 | 1 word @ 0x14 |
| 0x640878 | `c34c39a70111` | 1 byte @ 0x11 | 1 byte @ 0x11 |
| 0x648150 | `1f0280550208` | 2 words @ 0x14,0x18 | 2 words @ 0x14,0x18 |

Census of the 0x1872c8 family:

| arity | classes | distinct keys |
|---:|---:|---:|
| 1 | 84 | 112 |
| 2 | 7 | 51 |
| **4** | **1** | **1** |

**The arity-4 class: constructor 0x677010, fields 0x14/0x18/0x1c/0x20, and
exactly one key — `38f85c32..` (engine constant 0x325cf838).** Four consecutive
word fields. A rect.

Scope, stated rather than glossed: the census only sees classes calling the
shared base constructor 0x1872c8, so every count is a **lower bound**. The
result is "one found", not "one exists".

## 4. The key is in the view files, but the payload is constant

Across 299 view files (79,656,916 B):

| key | 4-byte prefix hits | full 6-byte hits |
|---|---:|---:|
| `c34c39a70111` | 8,311 | 8,304 |
| `1f0280550208` | 11,531 | 11,530 |
| `ed188f1a018d` | 2,283 | 2,283 |
| `1b572204010e` | 13,035 | 13,035 |
| **`38f85c32..`** | **37** | (bytes 5-6 unknown) |

The engine carries only the **first four** key bytes as a constant — verified on
all three known keys (`c3 4c 39 a7 | 01 11` → `0xa7394cc3`). So the target had to
be searched as a 4-byte prefix; searching all six would have returned nothing
and looked like a refutation.

37 hits against an expected 0.0185 random, in 4 files (`master_camera`,
`viewBeautyEffect`, `viewIroiroCon`, and one more). **But 35 of the 37 have a
byte-identical 20-byte tail.** That is a constant, not a payload. A constant
means the occurrence is a *declaration*, not an instance — the same trap as the
23 constant payload bytes found earlier.

**So the file-side read is still open.** The values for this key are not
adjacent to it, and locating them needs the index mechanism, not a scan.

## 4b. There is no four-field reader in viewUnified2.so, and the dispatch table is not in the file

Two results, both negative, both with a reason rather than a shrug.

**No four-field reader.** A census of every function in the library for a
contiguous four-word payload run — not restricted to the 0x1872c8 family this
time, and with the byte-field case included so the boolean is detected — finds
the shape **231 functions** in total across all arities:

| arity | functions | call the base ctor |
|---:|---:|---:|
| 1 | 213 | 87 |
| 2 | 12 | 7 |
| 3 | 2 | 0 |
| **4** | **1** | **1** |
| 5 | 1 | 0 |
| 7 | 1 | 0 |
| 11 | 1 | 0 |

The single four-field function is the constructor at 0x677010. So the reader is
not in this library in a form this detector can see. The candidates are: it is in
another library (`viewUnified6.so`, `libObj.so`, `libSysDef.so`); or the four
fields are filled by four separate callers; or it writes them by block copy,
`stmia`, or a vector store, none of which produce four individual `str`
instructions.

**The class dispatch table cannot be read from the file.** Every constructor
installs its class entry the same way:

```
ldr  r5, [pc, #p]     ; a pc-relative offset
add  r5, pc
ldr  r3, [pc, #q]     ; a slot index
ldr  r3, [r5, r3]     ; r3 = table[base + index]
adds r3, #8           ; skip two header slots, the usual address-point fixup
str  r3, [r4]         ; store at the object head
```

Hand-computing this for the four classes puts all four on the same base,
`0xC1A3AE`, and the section table says where that is:

| section | addr | size |
|---|---|---|
| `.data.rel.ro` | 0x00b82698 | 0x00097c20 |
| `.dynamic` | 0x00c1a2b8 | 0x000000f8 |
| **`.got`** | **0x00c1a3b0** | **0x0000d758** |

`0xC1A3AE` is two bytes below `.got`, and all four slots (`0xC2625E`,
`0xC2068A`, `0xC1F216`, `0xC21EF2`) are inside `.got`. Two of them read as zero
on disk, which is what an unrelocated GOT looks like.

The obvious escape is `.rel.dyn`, and it is present: 1,283,752 bytes, divisible
by 8 and not by 12, so `SHT_REL` with 160,373 entries, and `.dynsym` has 4,181
symbols — enough to resolve a `GLOB_DAT` statically. **But not one of those
160,373 relocations targets any of the four slots.** They are almost entirely
for `.data.rel.ro`. So the class dispatch entries are written at load time by a
mechanism the file does not record.

Consequence: the reader cannot be reached from the static binary by following
the class entry. Two routes remain, and both are outside what the file supports:

- a **runtime dump** of `.got` from the live process, which the existing
  `arm_probe.py` / `pagewalk.py` / `pagemap_probe.py` work is aimed at;
- the other engines, `viewUnified6.so` and `libObj.so`, where the reader may
  live outright.

Note for whoever picks this up: `.data.rel.ro` is 621 KB of ~155,000 fully
relocated pointers and is readable as it stands. If any vtable in this binary is
statically visible, it is in there, not in the GOT.

## 4c. The widget system is named and enumerated

This is the most useful thing found in the stretch, and it is not about geometry.

`.data.rel.ro` is 621,088 bytes and fully relocated, so unlike the GOT it is
readable as it stands. Scanning it for maximal runs of consecutive `.text`
pointers — that is, for vtables — gives:

| section | runs of >= 6 consecutive .text pointers |
|---|---:|
| `.data.rel.ro` | **1,943** |
| `.rodata` | 35 |

`.rodata` cannot contain a vtable, so its 35 runs are the rate at which adjacent
words merely look like code addresses. The ratio is 55x, so the 1,943 are real
structures. The most common run length is 11 (799 runs), then 8 (464) and 12
(373) — the shape of a C++ vtable with a shared prefix.

What they point at is the payoff for identification. The runs are full of named
UI code:

```
PAS_BtnBase::cast
PAS_MenuListTab::openLevel2Popup
PAS_ExtFlashReceiverSetItem::setInformation
LayoutableWidgetBaseCustom::setDispLevel
WrapperFocusArea
CmnSettingNodeUtil::invalidatWidgets
CmnFnWrapper::GetShutterspeedValue
ViewRootRemoteToInstance
```

**Every widget class in the camera is identified by name**, and its vtable is
readable. Combined with the 2,385 exported symbols and the named geometry
methods below, a UI element can be tied to a class without guessing.

Named geometry methods that exist, exported:

```
PAS_IconLevelBarAndSetting::setbarPosSize
PAS_IconLevelBarAndSetting::setPlusPosSize
PAS_IconLevelBarAndSetting::setMinusPosSize
PAS_IconLevelBarAndSetting::setChannelPosSize
PAS_IconLevelBarAndSetting::setVolValuePosSize
PAS_ZoneArea_C::setIconPosition
PAS_ZoneArea_C::setIconSize
PAS_Index::convContentIDToPosID
ACT_IconExternalFlashCompensationAll::setCordinatesOnExternalFlashLayout(int)
```

`convContentIDToPosID` is the PosID converter referred to in earlier notes.
Note the shape of the `PAS_*` methods: each widget class hard-codes its own
positions rather than consulting a general layout API, so there is no single
`setRect` to find. Positions arrive as data and each widget applies them.

## 4d. The layout names exist, but only in the symbol table

162 exported symbols carry layout identifiers — `CMN_M_REC_EVF_FOCUSCONTROL_LR`,
`CMN_M_PLAY_MOVIE_WITH_FOOTER`, `CMN_DIALOG_BACKGROUND`,
`LAYOUT_ID_43_5W_SET_COMMON_EDITBOX` and 130 more, across `LG_master_camera`,
`LG_master_network`, `LG_master_browser` and `LG_master_other`. If those names
were in the resource files, every screen would have a name and the "which .uxc
is which" problem would be solved outright.

They are not. Checked directly, with a control:

| | in `viewUnified2.so` | in the 299 view files |
|---|---:|---:|
| each of 133 extracted tokens | **exactly 1** | **0** |

One occurrence in the binary is the symbol table entry itself, so the finder
works; zero in 79,656,916 bytes of view files means the names are compile-time
identifiers only. **The resource files are anonymous.** This is the load-bearing
negative for the whole GUI-reshaping goal, and it is worth stating plainly: any
approach that relies on the files naming their own screens cannot work.

## 4e. There is no keyed four-field reader anywhere, and the rect is withdrawn

The arity-4 class at 0x677010 has one key. If it were a rect deserialised from a
stream, a keyed function filling `0x14/0x18/0x1c/0x20` would exist. Searching
all thirteen engine libraries — 45 MB of `.text`, 157,528 recovered functions —
finds **12** keyed four-field functions:

| library | address | fields | keys |
|---|---|---|---|
| libObj.so | 0x00860a20 | 0x14,0x18,0x1c,0x20 | `1259d900..` |
| libObj.so | 0x00d9f504 | 0x14,0x18,0x1c,0x20 | `9a6b6300..` |
| libObj.so | 0x00197430 | 0x18,0x1c,0x20,0x24 | `bb81c800..` |
| libObj.so | 0x001f4518 | 0x58,0x5c,0x60,0x64 | `7eab2301..` |
| libObj.so | 0x0020b170 | 0x4c,0x50,0x54,0x58 | 5 keys |
| libObj.so | 0x0039e160 | 0x18,0x1c,0x20,0x24 | `72046901..` |
| libObj.so | 0x00d72e74 | 0x28,0x2c,0x30,0x34 | `9a766300..` |
| libmpr.so | 0x0063f9c8 | 0x14,0x18,0x1c,0x20 | `60a6aa00..` |
| libmpr.so | 0x00655cec | 0x24,0x28,0x2c,0x30 | `d0a3ac00..` |
| libmpr.so | 0x006b9bcc | 0x28,0x2c,0x30,0x34 | `49b9aa00..` |
| libmpr.so | 0x00874d98 | 0x1c,0x20,0x24,0x28 | 2 keys |
| viewUnified2.so | 0x00677010 | 0x14,0x18,0x1c,0x20 | `38f85c32..` |

Both tests are calibrated. The shape detector reproduces viewUnified2.so's known
arity-4 class at 0x677010, and the key-reachability test finds its known key
`38f85c32..` — the first version of that test scanned each candidate's own body
for a call to itself and so reported "none" for everything, including the pair
that was already established. A control that can only print "none" is not a
control.

**All 12 are constructors.** Disassembled, each zeroes the four fields and then
initialises sub-objects:

```
libObj.so 0x00860a20
  str  r6, [r0, #0x14] / [r0,#0x18] / [r0,#0x1c] / [r0,#0x20]
  add.w r0, r0, #0x24
  bl    #0x85f6bc          ; sub-object init
  bl    #0x86b98c
```

The initial classifier called them non-constructors because they do not call
`0x1872c8` — that is a *viewUnified2-specific* base constructor, so its absence
means nothing about the other libraries. Reading the code corrected it.

**So the "four-field property = rect" identification is withdrawn.** A class
with four word fields and one key is a keyed four-word value type. There is no
evidence it is a rectangle, and no evidence of how a rect would be encoded,
because no code in any engine library reads four values from a stream into a
keyed object. The four fields are filled by direct stores from whatever builds
the object, and that builder is not identified.

This is the honest end of the geometry thread by static means. The engine does
not describe how geometry is decoded, because in the binary it does not decode
it — it is either done at run time or done by a caller this pass has not found.

## 5. Two claims withdrawn

Recorded because both were nearly mistaken for confirmations.

- **"92 property classes matches the 92 view signatures."** No. The census
  returned 92 and the file format has 92 signatures, but the coincidence came
  from one lossy filter being lossy in the same way twice. The two numbers come
  from unrelated data, which makes a coincidence *more* likely to look
  meaningful, not less. The engine certainly has far more than 92 property
  classes — 12,008 distinct keys were seen in one pass.
- **Vtable slot offsets as type tags.** A census found 133 offsets and
  `0x19c`/`0x44`/`0x1b0` do behave as type tags in composite readers. But the
  calibration required the four known classes to show one virtual read each and
  they showed **zero**: the scalar properties are constructors, not readers, so
  the census was measuring a different layer. Void.

## 6. Instrument bugs found and fixed, kept for the record

- **Capstone desynchronised** when decoding all of `.text` with `skipdata=True`,
  reinterpreting literal pools as opcodes (`ldrtmi`, `ldrvs`, `ldrdeq` — not ARM
  mnemonics). Symptom: a search returned 0 hits for the field offset *and* for
  both controls. Fixed by decoding only inside recovered function bodies:
  impossible `ldr<cond>` fell from tens of thousands to 0.11%.
- **Hand-rolled Thumb `bl` decoding** was wrong twice (J1/J2 are in the second
  halfword; the mask is `0xC000`, not `0xD000`). Caught by a self-test against a
  known call. Its output, "0 call sites for the setter", was fiction. Replaced
  with capstone's branch rendering.
- **The abstract interpreter** initially resolved `mov r5, r0` to nothing because
  `r0` was not seeded as `this`, so all four ground-truth classes came back
  empty. The calibration caught it.
- **A regex** expected `movs r3, #0x0` where capstone prints `movs r3, #0`,
  which made a detector match nothing while passing silently.

Each was found by a control returning a value it should not have. None would
have been caught by inspection.

## 7. State of the machine

- Camera is still patched to **magenta** guides (`0x400c` → `ff00ff`@80α).
  Restore file: `color_cmn.restore.uxc`, md5 `f468bd3e72ca4e5b948a1c9f1f35c0a1`.
- `/usr` is still mounted **rw**.
- The vtable-census and key-walk tables (`prop_table.tsv`) are **not** used; the
  key walk failed its own consistency invariant at 18.6%.

## 8. Next step

Find where the values for key `38f85c32..` live. The key's 37 occurrences are
declarations, so the values are reached by index — the same shape as the
container index rule already solved (`index_count = control & 0xff`, control at
0x0c) and the view object table (`offset[0] == 1 + 2N`). The rect class at
0x677010 gives the expected shape to look for: four words, in order, at the
slot the index points to.

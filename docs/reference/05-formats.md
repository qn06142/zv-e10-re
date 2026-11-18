# 05 — Formats: the UXC container, view files, and the palette

The file formats under `/usr/share/app/`. The layouts here are derived from the
files rather than assumed, and the container arithmetic is verified across all
302 `.uxc` files. This consolidates six documents now in `90-session/`.

**One caveat up front, because it is the kind that hides:** the palette's
byte-exact round trip does **not** prove its field boundaries are right. See
[Negative results](#negative-results) below.

All sizes below are the real files in `dumps/camera/app/`.

## The UXC container header

Three magics share one header shape. The version word is the discriminator.

| magic | version word | what |
|---|---:|---|
| `uxc` | 8 | every screen (`view*.uxc`) and shared resource |
| `uxb` | 9 | `lang.uxb`, `style.uxb` — u32 offset tables |
| `uxa` | 9 | `global.xdb` — the view index |

`color_cmn.uxc` header, byte-exact:

```
0x00  3 bytes  magic 'uxc'
0x03  u8       format version (7)
0x04  3 bytes  zero
0x07  u8       zero
0x08  u16      stream version: 8 for .uxc, 9 for .uxb/.uxa
0x0A  u16      0x004a  (file-specific, not a checksum)
0x0C  u16      0x4023  = one past the highest id (high-water mark)
0x0E  u16[]    sparse id->slot index, 0xffff = absent
0x58            body: 28 records of exactly 8 bytes
```

**`0x0a` is `resource_id`; the index count is `control & 0xff` at `0x0c`.**
Reading `control` at `0x0a` makes the data-start rule below appear to fail
everywhere, which is how it was first "refuted".

### The data-start rule

```
index_count = control & 0xff
data_start  = align4(0x10 + 2*index_count)
```

The index is a list of `u16` offsets **relative to `data_start`**, `0xffff`
meaning absent. The rule generates the body start for all 302 `.uxc` files, and
is confirmed on content, not just arithmetic:

| | |
|---|---:|
| files where predicted `data_start` is inside the file | 302 / 302 |
| non-absent index entries | 12,082 |
| …that land inside the file | 12,082 (100.0%) |
| absent (`0xffff`) entries | 727 |

Worst case 100%. The base is right, so an editor can follow an index entry to
the thing it names.

`uxa`/`uxb` use a **four**-byte index instead of two. In `global.xdb`,
`offset[0]` is 0, so `data_start` is the first byte of entry 0, visibly at
`0x3cc` — and `0x10 + 4*239 = 0x3cc` exactly, with `offset[1] - offset[0] =
0x2c` landing the next record's tag on the byte.

> The structural checks (every offset inside the file; offsets non-decreasing)
> **both pass on the wrong `data_start`**. They constrain the offset array, not
> where the array ends. The check that discriminates is content: record 0 must
> begin with a sane tag and yield a filename that exists on disk.

### Navigation hierarchy

```
file header
  -> u16 index (n = control & 0xff, offsets from data_start, 0xffff absent)
    -> 4-byte-aligned body
      -> section descriptor (60 bytes)
        -> object offset table (offset[0] == 1 + 2N)
          -> 14-byte object header
            -> property_count top-level properties
              -> fixed or variable payload
                -> optional nested children
```

The container is navigable, not merely parseable.

### Section descriptor: `w10 == w9`

1,240 descriptors, **0 exceptions**. Two of the three "ref/raw fields" that
were recorded independently are one field written twice.

### Record families interleave

`style_cmn.uxc` has **two** record families, which is why a single-marker
histogram leaves gaps:

| | count | stride | marker | indices |
|---|---:|---:|---|---|
| base | 26 | 36 | `a0 07 26 08` | `00`–`0b`, `1f`, `23`, `24`, `27`, `31`–`3a` |
| extension | 34 | 24 | `a0 07 26 06` | `0c`–`22`, `25`, `26`, `28`–`30`, `3b` |

26 + 34 = **60 = the control low byte.** The extension indices fill exactly the
gaps in the base set, so the two families interleave into one `0x00`–`0x3b`
index space. The extension index steps up by one on 88% of consecutive pairs.

Class count is **278**, under the strict descriptor invariants. (A looser
predicate admits a few extra offsets and gives 279; that is a
parsing-strictness difference, not a format disagreement.)

## `color_cmn.uxc` — the palette

312 bytes, 28 records of exactly 8 bytes at `0x58..0x137` (the whole file).

```
+0  u16  id       sequential 0x4000 .. 0x4022
+2  u16  const    0x3a09 in every record
+4  u8   r
+5  u8   g
+6  u8   b
+7  u8   a
```

| id | rgba | reads as | | id | rgba | reads as |
|----|------|----------|-|----|------|----------|
|4000| `ffffff` | white | |400f| `33333380` | dark grey 50% a |
|4001| `dddddd` | light grey | |4010| `dd5500` | orange |
|4002| `00000099` | black 60% | |4011| `dd5500` | orange |
|4003| `00000088` | black 53% | |4012| `dddddd` | light grey |
|4004| `dddddd` | light grey | |4013| `dd6600` | yellow |
|4005| `dddddd` | light grey | |4015| `dddddd` | light grey |
|4006| `dddddd` | light grey | |4017| `00000099` | black 60% |
|4007| `dd0000` | **red** | |4018| `00000044` | black 27% |
|4008| `00dd00` | **green** | |401b| `000000cc` | black 80% |
|4009| `0000dd` | **blue** | |401f| `dddddd` | light grey |
|400a| `cccccc80` | mid grey 50% a | |4020| `dddddd` | light grey |
|400b| `cccccc80` | mid grey 50% a | |4021| `ffffff` | white |
|400c| `33333380` | dark grey 50% a | |4022| `0000004c` | black 30% |

- **There is no checksum.** Nothing in the file validates its own payload, so a
  single-quad edit cannot be rejected on integrity grounds. The only risk is
  semantic: an out-of-range or garbage quad.
- **The ids are consecutive, `0x4000`–`0x4022`.** What look like gaps are the
  `0xffff` holes in the *index* at `0x0e`, a sparse id→slot map — not the
  colour list. The round-trip test is what catches confusing the two.
- `uxc_color.py` parses, re-emits, and asserts byte equality before it will
  produce a patched variant. Verified: 312 bytes re-emitted, byte-exact match.
  **But see [Negative results](#negative-results) — that test cannot fail, so it
  is not evidence for the layout.**
- A single-quad patch changes 2 bytes at offsets `0x94, 0x96` (id `0x4007`,
  red → `ff00ff`). One offset is a colour channel, the other is the *next*
  record's id field, which is how a mis-sized edit corrupts a neighbour rather
  than failing.

`color_cmn.uxc` has 28 non-absent index entries pointing into a 28-record body
— a 1:1 map. The header index **is** the id→record mapping.

### The palette is authoritative — hardware-verified

Three palette states, three observed framing-guide colours:

| palette `0x400c` | observed guide lines |
|------------------|----------------------|
| `333333` @ 80a (stock) | grey |
| `0000dd` @ 80a | blue |
| `ff00ff` @ 80a | **magenta** |

The magenta test is the control that carries the argument: `ff00ff` appears
nowhere in Sony's palette, so magenta guides cannot be resolving through
anything except palette entry `0x400c`. The blue result was consistent with both
readings; the magenta result is consistent with only one.

That matters because `style_cmn.uxc` contains **no `0x40xx` palette ids at
all** — styles inline their own RGBA. The blue result alone could not exclude
"the guide style had its own inline `333333` and the palette edit was
coincidental".

### There are two colour levers, not one

| | mechanism | file | reach |
|---|-----------|------|-------|
| 1 | palette lookup by id | `color_cmn.uxc` (312 B) | every screen that references an id |
| 2 | inline RGBA per style/widget | `style_cmn.uxc`, `view*.uxc` | per-widget overrides |

Lever 1 is decoded, verified, and controllable. Lever 2 is confirmed to exist —
**186 aligned 4-byte quads across 301 files match a palette colour, 9,212x above
chance** — but its record layout is a variable-length TLV and is not solved.

Because the rendering code holds the ids (below), lever 2 may also be bypassed
for anything the code colours directly.

## The view files: no colour field exists

This is a **negative result with a computed null model**, and it is
conclusive:

```
211,844 u16 windows examined   (every u16 at every offset of every property
                                payload, all 214 view files)
    279 land in 0x4000..0x4022
    113 expected by chance
    2.5x  -- not enriched
```

**The view files cannot be recoloured.** Not "hard to" — there is no colour
field in them. Effort spent on view colour is wasted.

A second candidate mechanism (a property carrying a style index) reported "100%
supported" for 30 signatures, and was a false positive produced by its own
output: `1b572204010e` occurs 10,500 times with **1 distinct value**,
`1f0280550208` 9,507 times with **1 distinct value**. A property with a single
constant value is a type tag. The 100% hit rate came from small integers
`0..0x3a` being common enum values, with `0x3a` = 58 sitting inside
`style_cmn`'s sparse index set. The test had no null model.

**Surviving explanation: the colour reference is compiled into the rendering
code.** The guides follow palette `0x400c`; no view file references it; the
palettes are consulted by code that holds the ids, not by resources that name
them. The small-enum signatures are plainly not colour ids:

```
0fcbce250190   1970 occ   9 vals  00 01 02 03 04 05 06 07 08
1f0b9b400190   3693 occ  12 vals  00..08 0b 10 11
7fb68c7f0190   1100 occ  13 vals  00..0a 0d 0f
0d4d93430190    673 occ  14 vals  00..0c 0e
```

Consecutive-from-zero, sparse beyond the obvious range: widget types, z-orders,
visibility, alignment, states.

### The parser, verified

Object boundaries are **derived**, not searched. That is the whole difference,
and it is why a marker-gap approach could never get here — it infers structure
from repetition, which is the wrong inference.

| claim | result |
|---|---|
| section descriptor (high byte `0x7e`, then fixed words) | **214/214** view files, 1,240 sections, **0 misses** |
| object index table invariant `offset[0] == 1 + 2N` | **1,240/1,240 valid, 0 invalid** |
| objects indexed | **10,640** |
| largest `N` (a u8) | 83 |
| property records walked | 49,287 |
| distinct signatures | 92 |

### The `0x400c` byte-pair trap

`0c 40` inside `viewContPbGroup.uxc` is part of the section discriminator
`0x400c0000` at `0x0e20`, not a colour reference. Verified: that is the
enclosing u32.

A prior claim of "**14,721 references** across the `image_*` atlases" was
retracted. It was a raw byte-pair count with no structural validation:
**14,720 raw hits, zero of them in a structural word**, spread across a 27 MB
bitmap atlas where a two-byte pattern is meaningless.

**View files remain fully editable** for geometry, layout, text, visibility,
z-order, state, and event bindings — 10,640 objects with derived boundaries and
known property signatures. That is a much larger surface than colour.

## `global.xdb` — the view index

`viewUnified2.so` contains the literal `global.xdb`, so the engine loads it by
name. Container, magic `uxa`, **239 entries**, `control & 0xff` at `0x0c` =
239. Each record:

```
09 00 <id:u16> | 01 20 00 00 | 00 00 00 00 | 80 "<filename>" NUL pad
```

The id equals the entry index throughout. 236 of 239 carry a filename. The
named non-view resources are:

```
\x80color.uxb     <- the real name of the palette file, a.k.a. color_cmn.uxc
\x80lang.uxb
\x80style.uxb
LayoutMaster_Other.uxc
viewUUG_Update.uxc
```

**`color.uxb` and `color_cmn.uxc` are the same file.** Worth recording so the
next pass does not treat them as two things.

`field@04` is a kind: `0x00002001` on 225 entries, `0x00004002` on 9,
`0x00044022` on 2.

**76 files on disk are not in the index:** 68 `string_<language>.uxc` and 8
`image_*.uxc`. So `global.xdb` indexes views, and localisation and images load
by some other path.

## The UI string table

`string_english_f.uxc` is 349,020 bytes and parses into **7,190 records**:

```
81 ac 1b 1e "Memory"      82 ac 1b 1e "MENU"       a5 b2 1b 1e "JPEG"
50 a4 1b 1e "DRO"         0d b5 1b 1e "MAC Address"
```

A 2-byte id, the constant marker `1b 1e`, then NUL-terminated text with
alignment padding. The low id byte increments.

| check | result |
|---|---|
| records found / `1b 1e` markers in file | 7,190 / 7,190 |
| ascending id steps | 7,189 of 7,189 (100%) |
| distinct ids | 7,190, range `0xa000`..`0xbc19` |
| **round-trip identity** | **byte-exact, 349,020 = 349,020** |

The round trip is what makes this a parse rather than a pattern. Content
includes the on-screen labels (`Playback`, `Aperture`, `Aspect`, `AF/MF`,
`Focus Mode`, `Exposure Comp.`, `Shutter Speed`, `ND Filter`) and the help text
("You can adjust the shutter speed and aperture as you like in the [M] mode").

`string_english.uxc` has **zero** `1b 1e` records — it is the help-text file in a
different format. **The `_f` suffix is the string table.** A first pass that read
the wrong file found nothing, which would have looked like a failed parse rather
than a wrong target.

Entries are not wholly anonymous: `string_japanese.uxc` contains
`_CANNOT_MOVIE_RECORD_WITHOUT_CONNECTING_COMPATIBLE_RAW_DEVICE`, a resource key
name. Some entries are identifiers, not just text.

## The other files in `/usr/share/app/`

`usr_share.tgz` holds 465 entries; 299 are `.uxc` view files, plus nine
non-view files:

| file | bytes | what it is |
|---|---:|---|
| `global.xdb` | 12,252 | container, magic `uxa` — the view index |
| `lang.uxb` | 2,896 | container, magic `uxb` |
| `style.uxb` | 540 | container, magic `uxb` |
| `area_check_data.dat` | 1,174,103 | magic `UXAC`, unexplored |
| `fontlist.dat` | 360 | text: `FONT_UNIVERS` / `/usr/share/...` |
| `Sony_DI_Icons.ttf` | 619,664 | real TrueType: `OS/2 VDMX cmap gasp glyf head hhea hmtx name post` |
| `*.ltt` x 3 | 611k–924k | Monotype **font-linking** bundles, each embedding TTFs (`embeddedoffset`, `embeddedsize`, `targetdirectory`) |

`fontlist.dat` is tab-separated `NAME<9>path`, e.g.
`FONT_UNIVERS -> /usr/share/app/UniversOTS-SJ_wIcon.ltt`.

## The view-index / ELF-symbol join is a substring match

The 133 layout identifiers that exist only in the symbol table
(`CMN_M_REC_EVF_FOCUSCONTROL_LR`, `CMN_DIALOG_BACKGROUND`, …) return **zero**
exact filename matches. The tokens inside them do:

| token | filename |
|---|---|
| `FOCUSCONTROL` | `viewFocusControl.uxc` |
| `QUICKNAVI` | `viewQuickNavi.uxc` |
| `EVF` | `viewEvfAdjustment_D.uxc`, `viewEvfBrightness.uxc` |

The two vocabularies are separate — short view names versus long layout names —
but a substring join is usable. `CMN_M_REC_EVF_FOCUSCONTROL_LR` almost certainly
means `viewFocusControl.uxc`. **This is a heuristic and is labelled as one.**

## Negative results

**The palette round trip cannot fail, and therefore proves nothing about the
layout.** `uxc_color.py` printed *"BYTE-EXACT MATCH — container decoded"*. The
test parses into records, re-packs the same fields, and re-concatenates the
untouched prefix — the exact inverse of the parse. **It returns the input for
*any* stride that divides the body evenly.**

So it proves the codec loses nothing. It does not prove the field boundaries are
right. A stride of 4, 2, or 1 would pass just as cleanly.

What actually supports the 8-byte stride is circumstantial but mutually
reinforcing, and it is the thing to check if anyone revisits this:

- the `u16` at `+0` steps `0x4000`…`0x4022` at exactly stride 8;
- `0x4023` (the `control` high-water mark at `0x0c`) sits exactly one past the
  last id, which only happens if the record count and stride are both right;
- the bytes at `+4..+7` are the only plausible UI colours in the file — and the
  magenta control later proved they *are* the colours.

The load-bearing evidence is the third item: the hardware result, not the round
trip.

**A negative from a sample too small to be informative.** An early palette scan
covered five tiny boot screens, found no palette ids, and nearly ruled out the
whole approach. Against the full 291-screen set, **197 files reference the
`0x4000`-range ids, 2,245 clean hits**. The negative was a sampling artefact.

**Do not re-derive either of these.** Both cost a full pass each.

## Open

1. **Semantic names for the raw class ids and property keys.** The blocker is
   named precisely: `libJiritsuUIView.so` is not in the archive, and it was not
   in the `/usr` tree either — the engine family is `viewUnified2..8.so` plus
   `libSysDef.so` and `libObj.so`.

   > **This lead is closed as far as the catalog can close it.** There *is* a
   > Jiritsu library on the camera — `/usr/lib/libJiritsu.so`, 114,688 B — so the
   > premise "if one exists under a different name" is answered. But its catalog
   > entry is **degenerate**: no imports, no `DT_NEEDED`, no exports, and no
   > `stripped` flag, which is the signature of a file whose ELF structure the
   > parser could not walk. The same class as `camuser.elf`. Nothing can be read
   > out of it without the binary itself, so **this needs the device**, not more
   > offline analysis. Pinned by
   > `tests/test_dep_graph.py::test_jiritsu_lead_is_closed_offline`.
2. **The style TLV** (lever 2): layout solved, record length not.
3. **`area_check_data.dat`** (1.2 MB, magic `UXAC`) is untouched.
4. The engine is a **family of seven**, one per screen class, and
   `viewUnified2.so` (14,284,732 B, `.text` 7,647,084 B) is the one that opens
   `global.xdb`:

   | binary | bytes |
   |---|---:|
   | **`viewUnified2.so`** | **14,284,732** |
   | `viewUnified4.so` | 3,287,604 |
   | `viewUnified3.so` | 941,232 |
   | `viewUnified5.so` | 749,136 |
   | `viewUnified6.so` | 589,336 (15.4x enriched over controls) |
   | `viewUnified7.so` | 579,944 |
   | `viewUnified8.so` | 283,208 |

## Tools

```powershell
& ".venv\Scripts\python.exe" -B research\firmware\uxc_color.py     # palette parse/re-emit/patch
& ".venv\Scripts\python.exe" -B research\firmware\uxc_view_full.py  # full container walk
& ".venv\Scripts\python.exe" -B research\firmware\verify_view_parser.py
```

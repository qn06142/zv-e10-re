# Looking wider in the filesystem: the view index, and the UI text

Date: 2026-09-28. Everything below came from archives already on the card
(`F:\RE_DUMP\TREES`), no device access needed.

## 1. The app directory has nine non-view files

`usr_share.tgz` holds 465 entries; 299 are `.uxc` view files, and nine more sit
in the same directory:

| file | bytes | what it is |
|---|---:|---|
| `global.xdb` | 12,252 | container, magic `uxa` — **the view index** |
| `lang.uxb` | 2,896 | container, magic `uxb` |
| `style.uxb` | 540 | container, magic `uxb` |
| `area_check_data.dat` | 1,174,103 | magic `UXAC`, unexplored |
| `fontlist.dat` | 360 | text: `FONT_UNIVERS` / `/usr/share/...` |
| `Sony_DI_Icons.ttf` | 619,664 | real TrueType, tables `OS/2 VDMX cmap gasp glyf head hhea hmtx name post` |
| `*.ltt` × 3 | 611k–924k | Monotype **font-linking** bundles, each embedding TTFs (`embeddedoffset`, `embeddedsize`, `targetdirectory`) |

`global.xdb` matters because `viewUnified2.so` contains that exact literal, so
the engine loads it by name. It had never been opened.

## 2. `global.xdb` is the view index

Container, 239 entries, `control & 0xff` at 0x0c = 239. Each record:

```
09 00 <id:u16> | 01 20 00 00 | 00 00 00 00 | 80 "<filename>" NUL pad
```

with the id equal to the entry index throughout. 236 of the 239 carry a
filename. It names views, and also three non-view resources:

```
\x80color.uxb     <- the real name of the palette file we already patched
\x80lang.uxb
\x80style.uxb
LayoutMaster_Other.uxc
viewUUG_Update.uxc
```

**`color.uxb` is the palette file** whose 28 RGBA records we edited and verified
on hardware as `color_cmn.uxc`. Same file, different name — worth recording so
the next pass does not treat them as two things.

`field@04` is a kind: `0x00002001` on 225 entries, `0x00004002` on 9,
`0x00044022` on 2.

### The data-start rule was wrong in the earlier note

`UXC_FORMAT_COMPLETE.md` records `data_start = align4(0x10 + 2n)`. Here
`offset[0]` is 0, so `data_start` is the first byte of entry 0, which is
visibly at **0x3cc** — and `0x10 + 4*239 = 0x3cc` exactly, with
`offset[1] - offset[0] = 0x2c` landing the next record's `09 00 01 00` on the
byte. The index is **four** bytes per entry, not two.

Worth recording how that was caught: the checks already in the script — every
offset inside the file, offsets non-decreasing — **both passed on the wrong
data_start**. They constrain the offset array, not where the array ends. The
check that discriminates is content: record 0 must begin with a sane tag and
yield a filename that exists on disk. That is now part of verification.

### 76 files on disk are not in the index

| group | count |
|---|---:|
| `string_<language>.uxc` | 68 |
| `image_*.uxc` | 8 |

So `global.xdb` indexes views, and localisation and images are loaded by some
other path.

## 3. The join to the ELF layout names is a substring match, not a table

The 133 layout identifiers that exist only in the symbol table
(`CMN_M_REC_EVF_FOCUSCONTROL_LR`, `CMN_DIALOG_BACKGROUND`, …) return **zero**
exact filename matches. But the tokens inside them do:

| token | filename |
|---|---|
| `FOCUSCONTROL` | `viewFocusControl.uxc` |
| `QUICKNAVI` | `viewQuickNavi.uxc` |
| `EVF` | `viewEvfAdjustment_D.uxc`, `viewEvfBrightness.uxc` |

The two vocabularies are separate — short view names versus long layout names —
but a substring join is usable. `CMN_M_REC_EVF_FOCUSCONTROL_LR` almost
certainly means `viewFocusControl.uxc`. That is a heuristic, and is labelled as
one.

## 4. The UI text is in plain ASCII, and the table is solved

This is the find that changes what is possible.

`string_english_f.uxc` is 349,020 bytes and parses into **7,190 records** with
the framing

```
81 ac 1b 1e "Memory"      82 ac 1b 1e "MENU"       a5 b2 1b 1e "JPEG"
50 a4 1b 1e "DRO"         0d b5 1b 1e "MAC Address"
```

a 2-byte id, the constant marker `1b 1e`, then NUL-terminated text with
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
different format. The `_f` suffix is the string table.

And the files are not wholly anonymous after all: `string_japanese.uxc` contains
`_CANNOT_MOVIE_RECORD_WITHOUT_CONNECTING_COMPATIBLE_RAW_DEVICE`, a resource key
name. Some entries are identifiers, not just text.

## 5. A verified, reversible patch — built, not applied

Same-length in-place substitution, for the same reason the palette edit was safe:
replacing N bytes with N bytes cannot move an offset, change an entry count, or
touch the container index.

`'Playback'` → `'OPENCODE'`, both 8 bytes, 3 occurrences:

```
@0x041bac rec / 0x041bb0 text  id 0xb547
@0x0476d8 rec / 0x0476dc text  id 0xb740
@0x04cbbc rec / 0x04cbc0 text  id 0xb976
```

| verification | result |
|---|---|
| bytes differing | 24, exactly as expected |
| all inside a target string | yes |
| differences landing on a `1b 1e` marker | 0 |
| container header and index | untouched |
| file length | 349,020 → 349,020 |
| record count | 7,190 → 7,190 |
| every other record text | unchanged, 7,187 checked |
| edited records read back | `['OPENCODE', 'OPENCODE', 'OPENCODE']` |

Artifacts, written locally only:

- patched `string_english_f.uxc.opencode`, md5 `9853d47ad4197d3387f10babdc8728b9`
- restore `string_english_f.uxc.restore`, md5 `349711603d2e16c1fc620e4e8bf30be0`

### Unquantified side effects, stated not hidden

- Only takes effect if the camera is set to **English**.
- `'Playback'` occurs 3 times, so all three labels change, not one.
- The other 67 language files are untouched, so switching language shows the
  original.
- It is **unknown whether the engine measures text width before drawing**. Equal
  length in a proportional font can still occupy a different pixel width. That
  is a rendering difference, not a structural one, but it could affect a
  right-aligned or centred label's position. The palette edit had no such
  question because it changed colour, not content.

## 6. Bugs caught by controls this pass

- **`data_start` off by a factor of two**, and the two structural checks passed
  on it. Added the content check that actually discriminates.
- **Name off by one byte** in the record walk, and a `bytes`/`str` sort crash —
  both caught by asking whether the extracted name exists on disk.
- **V3 failed on bookkeeping, not the edit**: the guard stored the text offset
  and compared it against record offsets, so its exclusion set never matched. A
  guard that cannot identify what it is guarding is worse than none.
- A first pass at the string table read `string_english.uxc` and found no
  records. That was correct — the table is in the `_f` file — but it would have
  looked like a failed parse rather than a wrong target.

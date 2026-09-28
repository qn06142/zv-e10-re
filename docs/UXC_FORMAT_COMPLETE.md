# The UXC container is now fully solved, and the index rule was the missing piece

Integrating `UXC_FORMAT_FULL.md` + `uxc_view_full.py`, with independent
verification of every claim that changes what we know.

## The rule I never found

```
index_count = control & 0xff              control is at 0x0c, NOT 0x0a
data_start  = align4(0x10 + 2*index_count)
```

One line. It generates every body offset I had measured by hand across three
separate files and never noticed the pattern in:

| file | control | n | predicted | measured earlier |
|---|---|---:|---|---|
| `color_cmn.uxc` | `0x4023` | 35 | `0x58` | `0x58` |
| `style_cmn.uxc` | `0xc03c` | 60 | `0x88` | `0x88` |
| `lang_cmn.uxc` | `0x002f` | 47 | `0x70` | `0x70` |
| `viewBaseMenu.uxc` | `0x2001` | 1 | `0x14` | `0x14` |

302 of 302 files: the predicted `data_start` is inside the file.

**And it is confirmed on content, not just arithmetic.** The entries are
relative offsets from `data_start`, `0xffff` meaning absent:

```
non-absent index entries  12082
land inside the file     12082  (100.0%)
absent (0xffff)            727
```

Every one, in every file, worst case 100%. That is a much stronger result than
"the arithmetic works out" — the base is right, so an editor can follow an index
entry to the thing it names.

My first test of this rule "failed" and I was wrong to take that at face value:
I read `control` at `0x0a`, which is `resource_id`. With `0x0c` the rule holds
everywhere.

## `style_cmn.uxc` has a second record family

This corrects my analysis directly. I found 26 base records of 36 bytes with
marker `a0 07 26 08`, and declared the remaining bytes unexplained. There is a
second family:

| | count | stride | marker | indices |
|---|---:|---:|---|---|
| base | 26 | 36 | `a0 07 26 08` | `00`–`0b`, `1f`, `23`, `24`, `27`, `31`–`3a` |
| extension | 34 | 24 | `a0 07 26 06` | `0c`–`22`, `25`, `26`, `28`–`30`, `3b` |

26 + 34 = **60 = the control low byte**. The extension indices fill exactly the
gaps in the base set, so the two families interleave into one 0x00–`0x3b`
index space. The extension index steps up by one on 88% of consecutive pairs.

My "unexplained gaps" in the marker histogram (492, 108, 84, 252) were the
boundary between families and the tail. I was searching for one marker and so
could not see the other.

## Section descriptor: `w10 == w9`

1240 descriptors, **0 exceptions**. Two of the three "ref/raw fields" I recorded
independently are one field written twice. Minor, but it is a real structural
fact and it was listed as three unknowns.

## Class count: 278, not my 279

My 279 came from a looser descriptor predicate that admitted a few extra
offsets. 278 under the strict invariants is the defensible figure. A
parsing-strictness difference, not a format disagreement.

## What this changes about editing

The container is now navigable, not merely parseable. The hierarchy is:

```
file header
  -> u16 index (n = control & 0xff, offsets from data_start, 0xffff absent)
    -> 4-byte-aligned body
      -> 60-byte section descriptor
        -> object offset table (offset[0] == 1 + 2N)
          -> 14-byte object header
            -> property_count top-level properties
              -> fixed or variable payload
                -> optional nested children
```

An editor can now: find the object index for a class, walk the header index to
a named subfield, and know which bytes to change. Before this, the palette was
the only editable thing and only because its layout happened to be regular.

Practical consequence for the two palette files specifically: `color_cmn.uxc`
has 28 non-absent index entries pointing into a 28-record body — a 1:1 map. So
the header index is not decorative; it is the id→record mapping I had guessed
at. And `style_cmn.uxc`'s 60 index entries against 26+34 records confirms the
two families are addressed by the same table.

## Still open

Unchanged and honestly so: semantic names for the raw class ids and property
keys. The document identifies the blocker precisely — `libJiritsuUIView.so` is
not in the archive. It was not in the `/usr` tree either; the engine family is
`viewUnified2..8.so` plus `libSysDef.so` and `libObj.so`. If a Jiritsu library
exists under a different name, finding it is the fastest route to real member
names, and the `.dynsym` of a stripped-but-exported library often retains them.

The colour path is also still open in the same place as before: no view
property carries a palette id (2.5× chance over 211,844 windows), `viewUnified2.so`
opens `global.xdb`, and `libSysDef.so` is 45.7× enriched in palette ids. Those
three facts now have a structure to hang on.

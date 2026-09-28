# View file format: solved, and the colour path is now settled too

Integrating the second agent's `uxc_view_parse.py` with independent
verification, plus the colour-path question that was left open.

## The incoming parser is sound — verified, not assumed

`verify_view_parser.py` re-derived its central claims from the corpus:

| claim | result |
|---|---|
| section descriptor (high byte `0x7e`, then fixed words) | **214/214** view files, 1,240 sections, **0 misses** |
| object index table invariant `offset[0] == 1 + 2N` | **1,240/1,240 valid, 0 invalid** |
| objects indexed | **10,640** |
| largest `N` (a u8) | 83 |
| property records walked | 49,287 |
| signatures | 92 |

Object boundaries are now **derived**, not searched. That is the whole
difference, and it is why the marker-gap approach could never get here: it was
inferring structure from repetition, which is exactly the wrong inference.

### The `0x400c` trap, confirmed — against my own number

The incoming doc claimed the `0c 40` in `viewContPbGroup.uxc` is inside the
section discriminator `0x400c0000` at `0x0e20`, not a colour reference.
Verified: yes, that is the enclosing u32.

That also retracts my most recent commit. I had corrected an earlier "appears
once" claim to "**14,721 references** across the `image_*` atlases". That was a
raw byte-pair count with no structural validation: **14,720 raw hits, zero of
them in a structural word**, spread across a 27 MB bitmap atlas where a two-byte
pattern is meaningless. I applied no structural test to my own number while
demanding one of the format. The count is retracted for good.

## The colour path: no view property carries a colour

With the parse working, this is now answerable, and the answer is clean.

**M1 — a property whose value is a palette id: ruled out.**
Every u16 at *every* offset of every property payload, all 214 view files:

```
211,844 u16 windows examined
    279 land in 0x4000..0x4022
    113 expected by chance
    2.5x  -- not enriched
```

The null model is what makes this conclusive. 2.5× on 279 hits is noise.

**M2 — a property carrying a style index: ruled out, and it was a false
positive in my own previous script.** That run reported "M2 supported" for 30
signatures at 100%. The tell was in the same output: `1b572204010e` occurs
10,500 times with **1 distinct value**, `1f0280550208` 9,507 times with **1
distinct value**. A property with a single constant value is a type tag. The
100% hit rate came from small integers `0..0x3a` being common enum values and
`0x3a` = 58 sitting inside `style_cmn`'s sparse index set. The test had no null
model, so it could not tell a signal from a coincidence.

**M3 — the colour reference is compiled into the rendering code: supported.**

The surviving explanation, and it fits the hardware result. The guides follow
palette `0x400c`; no view file references it; the palettes are consulted by code
that holds the ids, not by resources that name them.

Supporting evidence from the value distributions — the small-enum signatures
are plainly not colour ids:

```
0fcbce250190   1970 occ   9 vals  00 01 02 03 04 05 06 07 08
1f0b9b400190   3693 occ  12 vals  00..08 0b 10 11
7fb68c7f0190   1100 occ  13 vals  00..0a 0d 0f
0d4d93430190    673 occ  14 vals  00..0c 0e
```

Consecutive-from-zero, sparse beyond the obvious range: widget types, z-orders,
visibility, alignment, states.

## What this means for editing

- **The view files cannot be recoloured.** Not "hard to" — there is no colour
  field in them. Effort spent on view colour is wasted.
- **The only colour levers are the two palette tables**: `color_cmn.uxc`
  (hardware-confirmed) and `style_cmn.uxc` (layout solved).
- But if the code holds the ids, `style_cmn.uxc` may also be bypassed for
  anything the code colours directly. The palette still works — that is the
  magenta control — so at minimum `color_cmn.uxc` is definitely on the path.
- Geometry, layout, text, visibility, z-order, state, and event bindings in the
  view files remain **completely editable**, and the parser gives exact offsets
  for every one. That is a much larger surface than colour, and it is real.

So the highest-value remaining target is not colour at all. It is **layout**:
moving a widget, changing its size, hiding it. 10,640 objects with derived
boundaries and known property signatures.

## The lesson from this session, recorded three times over

Three conclusions in this project were wrong in the same way — a search that
could not fail was treated as a result:

1. the byte-exact round-trip in `uxc_color.py` (self-inverse parse/re-emit)
2. the ext superblock `RO_COMPAT` (format capability, not mount behaviour)
3. the `0x400c` byte-pair counts (no structural context, 2.5× chance)

Each time the method was fine and the *null model* was missing. The correction
is procedural: any claim about a byte pattern needs a computed chance rate, and
any claim about a "constant" needs a cardinality check to prove it isn't a tag.

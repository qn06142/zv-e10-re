# Confirmed: the palette is authoritative, and the mechanism is settled

**2026-09-28. Three palette states, three observed guide-line colours.**

| palette `0x400c` | observed guide lines |
|------------------|----------------------|
| `333333` @ 80α (stock) | grey |
| `0000dd` @ 80α | blue |
| `ff00ff` @ 80α | **magenta** |

The magenta test was the control that mattered. It was designed to be
unambiguous: `ff00ff` appears nowhere in Sony's palette, so if the guides
showed magenta they cannot be resolving through anything except palette entry
`0x400c`.

**They did.** The mechanism is settled.

## What had been in doubt

After the first (blue) success I noticed that `style_cmn.uxc` contains no
`0x40xx` palette ids at all — styles inline their own RGBA. That opened the
possibility that the framing guides were *not* resolving through `0x400c`, and
that our first patch had worked by coincidence: the guide style might have had
its own inline `333333` @ 80α, and recolouring the palette entry to `0000dd`
would then have had no bearing on them at all.

The blue result was consistent with both readings. The magenta result is
consistent with only one.

It matters beyond curiosity. If the palette is authoritative, then:

- `color_cmn.uxc` is the single control point for every colour the UI resolves
  by id, across all ~290 screens
- the style files' inline colours are the *other* mechanism, for widgets that
  do not go through the palette — so there are two real levers, not one
- a full recolour of the UI is a matter of rewriting ~20 quads in one
  312-byte file, with byte-exact rollback

## The two levers, established

| | mechanism | file | reach |
|---|-----------|------|-------|
| 1 | palette lookup by id | `color_cmn.uxc` (312 B) | every screen that references an id |
| 2 | inline RGBA per style/widget | `style_cmn.uxc`, `view*.uxc` | per-widget overrides |

Lever 1 is decoded, verified, and controllable. Lever 2 is confirmed to exist —
186 aligned 4-byte quads across 301 files match a palette colour, **9,212× above
chance** — but its record layout is a variable-length TLV and is not yet solved.

## Transfer note

The second transfer attempt nearly wrote a corrupted file: a hand-typed base64
character error (`/` for `N`) decoded to `0000` at offsets `0xa5`/`0xa6`, which
are the **id field of the next record**, not a colour. The pre-write md5
comparison caught it. The file was never written in that state.

The lesson is now enforced: base64 chunks are generated programmatically and
the staged file is hashed **on the camera before** being written, not after.

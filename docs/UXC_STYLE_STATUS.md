# Status: palette works; `style_cmn.uxc` is NOT decoded

Recording this because two failed attempts are on record in the repo and a
third would be worse than useless. The difference matters: the palette result is
**verified on hardware**, and this is not.

## What works, verified

`color_cmn.uxc` — 5 bytes, framing guides changed grey→blue on a real boot.
Container decoded, ids 0x4000–0x4022, 8-byte records, RGBA at +4. Solid.

## What does not: style_cmn.uxc

**Status: partially understood, layout not solved, do not patch.**

Two attempts, both wrong in instructive ways.

### Attempt 1: assumed stride 36, RGBA at +12

`uxc_style_rec.py`. The stride divided 1800 evenly, which made it look
plausible. Its own output refuted it:

- index at +0 was **not** increasing
- the +1..+4 "marker" was **not** constant — 6 distinct values
- 40 of 50 records decoded as `?? a0 07 26` with "alpha 38", which is the
  marker being misread as a colour

Lesson: a stride that divides the length evenly is not evidence of anything.
Record tables routinely have padding, headers, or variable-length entries.

### Attempt 2: derive the stride from the marker's own gaps

`uxc_style_derive.py`. Better method — let the file nominate its boundary by
searching for the `a0 07 26 08` signature and measuring the gaps:

```
26 occurrences, gaps: 36 x21, then 492, 108, 84, 252
dominant gap 36, but only 84% of gaps
1756 / 36 = 48.78  -- does not divide evenly
```

**The records are variable length.** The four large gaps are the real signal:
they mark where the layout changes between groups. This is a TLV structure, the
same shape seen in the `view*.uxc` widget records
(`1b 57 22 04 01 0e 08`, `1f 02 80 55 02 08 00`), not a fixed-stride table.

RGBA relative to the marker: `marker-5` gives a palette colour in 18 of 26
records (69%), which is suggestive but nowhere near the confidence needed to
patch. At `marker-5` the values are mostly `00 00 00 ff` (black) with a few
degenerate reads like `02 00 00 00` and `a7 01 b0 01`, which is what a wrong
offset looks like.

### What is actually established

One solid finding, from `uxc_inline.py`:

> Across 301 uxc/uxb files, 186 aligned 4-byte quads match a palette colour
> exactly. Chance expectation: 0.0. **Observed 9,212× chance.**

So inline RGBA in style and view files is **real, not coincidence**. That
finding is independent of the record layout and stands on the null model alone.

Concentrated in 10 files:

| file | quads | size |
|------|-------|------|
| `style_cmn.uxc` | 63 | 1,888 |
| `lang_cmn.uxc` | 42 | 1,048 |
| `viewmovierecpatch.uxc` | 20 | 48,436 |
| `viewStlrec.uxc` | 13 | 34,512 |
| `master_camera.uxc` | 10 | 101,804 |
| `master_network.uxc` | 5 | 35,584 |
| `viewIroiroCon.uxc` | 2 | 25,596 |
| `master_browser.uxc` | 1 | 27,328 |
| `viewPanoramaStl.uxc` | 1 | 46,632 |
| `viewRemoteCameraControl.uxc` | 1 | 13,300 |

By palette entry: `0x4000` black ×100, `0x4021` white ×51, `0x4020` grey ×3,
`0x4003` ×2, `0x4013` yellow ×1, `0x4007` red ×1.

`style_cmn.uxc` is the densest single source of UI colour, which makes it the
best next target — once its layout is actually solved.

## An important reframing of the win

`style_cmn.uxc` contains **no 0x40xx palette ids at all**. Styles inline their
own RGBA rather than referencing the palette.

So when the framing guides went blue, they were **not** resolving through palette
entry `0x400c`. Two readings, and the boot result favours neither strongly
enough to claim:

- the guides' style *inherits* or copies the palette default at load time, or
- `0x400c` (`333333` @ 80α) happens to be the value the guide style already used

The second is a real possibility and would mean our palette edit worked partly
by coincidence. It does not diminish the result — the guides changed, the write
is verified, the effect is ours — but the *mechanism* is less settled than the
first write-up implied. Worth testing directly: change `0x400c` to something
absurd, like `ff 00 ff` magenta, and see whether the guides follow. If they do,
the palette is genuinely authoritative. If they don't, the guides were matching
by value and the real control is in the style files.

**That test is cheap and would settle it. It should be the next camera
session.**

## Why not just brute-force it

It is tempting to flip every palette-matching quad in `style_cmn.uxc` to a
garish colour and see what happens. Against that:

- 63 quads at unverified offsets, in a layout not understood, in a file the
  engine parses at boot. A wrong offset is a wrong *other* field, and we would
  not know which.
- The palette gave us a 5-byte change with a verified layout and an exact
  rollback. That discipline is the asset here; spending it on a blind edit
  trades a known-good result for an unknown one.
- The 9,212× null model proves the quads are real colours. It does not prove
  *which byte* is which channel, or that alpha is where it appears.

## Sensible next steps, in order

1. **The mechanism test** (one session, 2 bytes changed): set palette `0x400c`
   to `ff 00 ff` and see whether the guides follow. Settles how the UI resolves
   colour, and tells us whether the palette or the style file is the real lever.
2. **Decode the TLV properly.** The `view*.uxc` marker
   `1b 57 22 04 01 0e 08` and the style marker `a0 07 26 08` look like
   type+length+payload records. Parsing the type field properly would resolve
   the layout without guessing offsets. This is real work, not a tweak.
3. **`logo.bin`** (8,532 B, plain JFIF JPEG) — needs no format knowledge at
   all, and it is the startup logo on the LCD. The cheapest visible change left.
4. **`global.xdb`** — resource directory with absolute paths and `_43`/`_169`
   model pairings. `image_cmn_169.uxc` is referenced but absent on-device, which
   is worth understanding: it may be model-gated, or it may point somewhere we
   have not looked.

Option 1 first. It is one small edit and it tells us which of the other three
are worth doing.

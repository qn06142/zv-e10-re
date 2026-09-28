"""Confirm the widget record that carries palette colour ids.

uxc_xref_full.py showed 197 of 291 screens reference the 0x4000-range palette
ids, 2,245 clean hits, and that the hits in master_camera.uxc and
viewPanoramaStl.uxc sit inside a repeating byte pattern:

    1b 57 22 04 01 0e 08 00 00 40 00 08 00 00 30 00
                          ^ id 0x4000

That marker also appears in every small view file, including ones too tiny to
contain any colour use at all (viewBaseMenu.uxc is 84 bytes).  So before
treating the id field as meaningful, the record itself has to be pinned down:
what is its stride, which offset holds the colour id, and is that offset
really a colour reference or just a field that happens to hold a small number.

Method -- find the marker by raw search, then measure the period between
successive hits rather than assuming it.  Then check: within one period, is
there a slot whose value is always in the palette id range, and does that slot
move with a consistent offset across several different files?

The noise caveat from the xref run is handled explicitly: the string_*.uxc
files are ascending u16 offset tables and produce coincidental hits, so they
are excluded here and only structural files are considered.
"""
import re
import struct
import tarfile
from collections import Counter
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')
MARKER = bytes([0x1b, 0x57, 0x22, 0x04, 0x01, 0x0e, 0x08])


def load_all():
    t = tarfile.open(TGZ)
    return {m.name: t.extractfile(m).read()
            for m in t.getmembers() if m.isfile()}


def palette_ids(b):
    hw = struct.unpack_from('<H', b, 12)[0]
    base = hw - 0x23
    return {v for v in range(base, hw)}


def find_all(buf, pat):
    out = []
    s = 0
    while True:
        i = buf.find(pat, s)
        if i < 0:
            break
        out.append(i)
        s = i + 1
    return out


def main():
    d = load_all()
    ids = palette_ids(d['share/app/color_cmn.uxc'])
    print('=== %d palette ids, 0x%04x..0x%04x ==='
          % (len(ids), min(ids), max(ids)))

    struct_files = {k: v for k, v in d.items()
                    if v[:3] == b'uxc'
                    and not k.split('/')[-1].startswith(('string_', 'image_'))}
    print('=== %d structural uxc files (excludes string_/image_) ==='
          % len(struct_files))

    # 1. how often does the marker appear, and at what period?
    print()
    print('=== marker 1b 57 22 04 01 0e 08 : occurrence and period ===')
    per_file = {}
    for name, b in sorted(struct_files.items()):
        hits = find_all(b, MARKER)
        if not hits:
            continue
        gaps = [hits[i + 1] - hits[i] for i in range(len(hits) - 1)]
        c = Counter(gaps)
        per_file[name] = (hits, gaps)
    print('  %d of %d files contain the marker'
          % (len(per_file), len(struct_files)))
    allgaps = Counter()
    for _n, (h, g) in per_file.items():
        allgaps.update(g)
    print('  gap histogram across all files: %s'
          % ', '.join('%d x%d' % (k, v) for k, v in allgaps.most_common(10)))

    # 2. take the dominant period and check the id slot
    if not allgaps:
        print('  no marker -- aborting')
        return 1
    period = allgaps.most_common(1)[0][0]
    print('  dominant period: %d' % period)

    print()
    print('=== within one period, where do palette ids sit? ===')
    slot_hits = Counter()
    slot_seen = Counter()
    for name, (hits, _g) in sorted(per_file.items()):
        b = d[name]
        for h in hits:
            for k in range(period):
                o = h + k
                if o + 1 >= len(b):
                    continue
                v = struct.unpack_from('<H', b, o)[0]
                slot_seen[k] += 1
                if v in ids:
                    slot_hits[k] += 1
    for k in sorted(slot_hits):
        print('  offset +%2d : %5d palette hits / %5d samples  (%.0f%%)'
              % (k, slot_hits[k], slot_seen[k],
                 100.0 * slot_hits[k] / max(1, slot_seen[k])))
    print('  (offset +7 is past the marker, i.e. the first field after it)')

    best = max(slot_hits, key=lambda k: slot_hits[k]) if slot_hits else None
    if best is None:
        print()
        print('  NEGATIVE: no offset within a period is a colour id slot.')
        return 1
    print()
    print('  strongest colour slot: +%d' % best)

    # 3. show a few records, and the distribution of values in that slot
    print()
    print('=== value distribution in slot +%d ===' % best)
    vals = Counter()
    for name, (hits, _g) in sorted(per_file.items()):
        b = d[name]
        for h in hits:
            o = h + best
            if o + 1 < len(b):
                vals[struct.unpack_from('<H', b, o)[0]] += 1
    for v, c in vals.most_common(40):
        tag = '  <-- palette id' if v in ids else ''
        nm = v - min(ids) if v in ids else None
        print('   0x%04x  %6d%s%s' % (v, c, tag,
                                     '' if nm is None else
                                     '  (offset %d)' % nm))
    print()
    print('  %d distinct values, %d of %d samples are palette ids (%.0f%%)'
          % (len(vals), sum(c for v, c in vals.items() if v in ids),
             sum(vals.values()),
             100.0 * sum(c for v, c in vals.items() if v in ids)
             / max(1, sum(vals.values()))))

    # 4. dump a couple of full records for the record
    print()
    print('=== example records (24 bytes either side of the marker) ===')
    shown = 0
    for name, (hits, _g) in sorted(per_file.items()):
        if shown >= 4:
            break
        b = d[name]
        for h in hits[:1]:
            lo = max(0, h - 16)
            hi = min(len(b), h + period + 8)
            ch = b[lo:hi]
            print('  %-30s @0x%04x' % (name.split('/')[-1], h))
            print('    %s' % ' '.join('%02x' % c for c in ch))
            caret = 4 + (h - lo) * 3
            print('    %s^ marker   %s^ colour slot +%d'
                  % (' ' * caret, ' ' * (caret + best * 3), best))
            shown += 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

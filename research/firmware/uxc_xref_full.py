"""The decisive cross-reference: do real screens reference the palette ids?

The 2025 dump has all 299 .uxc screens, not the 8 I pulled by hand.  The
hand-pulled sample gave a negative, but it was tiny -- 5 view files, none of
them a real menu with many widgets.  viewSettingMenu.uxc is 19,476 bytes and
viewGlobalMenu.uxc is 3,316.  If any of them names a 0x4000-range colour id,
the palette is live and the approach is sound.

This is the positive control that was missing.  Method:

  1. Re-derive the palette id set from color_cmn.uxc itself, not from a
     hardcoded list, so the search range cannot drift from the file.
  2. For every .uxc in the tar, count u16 words inside that id set, at both
     even and odd alignment (records may not be 2-aligned).
  3. Rank by hit count, so the screens that use colour the most float up.
  4. Require a real hit to be structurally plausible: the offset should sit in
     the file's body, not in a string table, and the neighbours should look
     like other small integers rather than text bytes.

The structural check matters.  A u16 that lands inside an ASCII string will
also decode to some number, so raw counts overstate.  Screening hits to
body-only, and requiring the byte pair to not be two printable ASCII chars,
removes almost all of them.

Everything runs on the 41 MB local tar.  No camera needed.
"""
import re
import struct
import tarfile
from collections import Counter
from pathlib import Path

TGZ = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share_app.tgz')


def load_all():
    t = tarfile.open(TGZ)
    out = {}
    for m in t.getmembers():
        if not m.isfile():
            continue
        out[m.name] = t.extractfile(m).read()
    return out


def palette_ids(b):
    """Re-derive ids from the file, using the 0x4023 high-water in the header."""
    hw = struct.unpack_from('<H', b, 12)[0]
    base = hw - 0x23          # 0x4023 - 0x23 = 0x4000
    ids = set()
    for o in range(0x58, len(b) - 1, 8):
        v = struct.unpack_from('<H', b, o)[0]
        if base <= v < hw:
            ids.add(v)
    return base, hw, ids


def body_start(b):
    """Where the record body begins. 0x58 for these files, but verify."""
    for cand in (0x58, 0x0c, 0x10, 0x14, 0x18, 0x20):
        if cand <= len(b):
            return cand
    return 0


def is_texty(b, o):
    if o + 1 >= len(b):
        return True
    a, c = b[o], b[o + 1]
    return 32 <= a < 127 and 32 <= c < 127


def main():
    d = load_all()
    print('=== %d files from usr_share_app.tgz ===' % len(d))

    cb = d['share/app/color_cmn.uxc']
    base, hw, ids = palette_ids(cb)
    print('=== palette ids re-derived from color_cmn.uxc ===')
    print('  high-water 0x%04x, base 0x%04x, %d ids: %s'
          % (hw, base, len(ids),
             ' '.join('0x%04x' % v for v in sorted(ids))))

    pal_ids = {v - base for v in ids}
    print('  as offsets from base: %s' % sorted(pal_ids))

    uxc = {k: v for k, v in d.items() if v[:3] == b'uxc'}
    print()
    print('=== scanning %d uxc files for palette ids ===' % len(uxc))

    ranked = []
    for name, b in sorted(uxc.items()):
        if name.endswith('color_cmn.uxc'):
            continue
        bs = body_start(b)
        raw = 0
        clean = 0
        offs = []
        for o in range(0, len(b) - 1):
            v = struct.unpack_from('<H', b, o)[0]
            if v in ids:
                raw += 1
                if o >= bs and not is_texty(b, o):
                    clean += 1
                    if len(offs) < 8:
                        offs.append(o)
        ranked.append((clean, raw, name, offs, len(b)))
    ranked.sort(key=lambda r: (-r[0], -r[1]))

    total_clean = sum(r[0] for r in ranked)
    total_raw = sum(r[1] for r in ranked)
    nz = [r for r in ranked if r[0]]
    print('  %d files with >=1 clean hit, %d total clean hits, %d raw'
          % (len(nz), total_clean, total_raw))
    print()
    print('  --- top 30 by clean hits ---')
    for clean, raw, name, offs, sz in ranked[:30]:
        print('   %4d clean %5d raw  %7d B  %-44s %s'
              % (clean, raw, sz, name.split('/')[-1],
                 ' '.join('0x%04x' % o for o in offs[:5])))

    if not nz:
        print()
        print('  NEGATIVE across all 299 screens.')
        print('  The 0x4000-range ids in color_cmn.uxc are NOT referenced by')
        print('  any screen file.  Recolouring the palette would then change')
        print('  nothing, and the approach is dead.')
        return 1

    # what do the clean hits look like in context?
    print()
    print('=== context of clean hits in the top 5 files ===')
    for clean, raw, name, offs, sz in [r for r in ranked if r[0]][:5]:
        b = d[name]
        print()
        print('  %s (%d B, %d clean)' % (name.split('/')[-1], sz, clean))
        for o in offs[:4]:
            lo = max(0, (o - 8) & ~0xF)
            hi = min(len(b), o + 16)
            ch = b[lo:hi]
            print('    %04x  %s' % (lo, ' '.join('%02x' % c for c in ch)))
            mark = ' ' * 4 + ' ' * ((o - lo) * 3) + '^ 0x%04x = id 0x%04x' % (o, struct.unpack_from('<H', b, o)[0])
            print('    %s' % mark)

    # do the clean hits cluster at 8-byte stride?  that would confirm records
    print()
    print('=== are clean hits at a consistent stride (i.e. real records)? ===')
    for clean, raw, name, offs, sz in [r for r in ranked if r[0]][:8]:
        all_o = []
        b = d[name]
        for o in range(0, len(b) - 1):
            v = struct.unpack_from('<H', b, o)[0]
            if v in ids and o >= body_start(b) and not is_texty(b, o):
                all_o.append(o)
        st = Counter(all_o[i + 1] - all_o[i] for i in range(len(all_o) - 1))
        print('   %-42s %s' % (name.split('/')[-1],
                              ', '.join('%d x%d' % (k, v)
                                        for k, v in st.most_common(4))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

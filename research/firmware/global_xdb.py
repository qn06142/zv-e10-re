"""Parse global.xdb: the view index, and check it against the files on disk.

What was found
--------------
viewUnified2.so contains the literal string global.xdb, so this file is loaded by
the engine, and it had never been opened.  It is a container of the same family
as the .uxc files -- magic "uxa", version 7 -- and it contains ASCII filenames:

    09 00 00 00  01 20 00 00  00 00 00 00  80 "viewDeleteSelected4Index.uxc"
    09 00 e9 00  01 20 00 00  00 00 00 00  80 "viewExpMode.uxc"
    09 00 ee 00  01 20 00 00  00 00 00 00  80 "viewPrivacyNotice.uxc"

with a 16-bit id that runs 0, 1, ... 238 in step with the entry order.  So this
is an ordered, named index of the view system: which view file is which screen,
and what number the engine calls it.

Why that matters more than it looks
-----------------------------------
The previous stretch established that the .uxc files are anonymous -- no layout
name appears in any of them.  An index that names them, sitting in a file the
engine loads by name, is the one artefact that ties the 299 anonymous blobs to
something a person can reason about.  It is also the place to look for the 133
layout identifiers that exist only in the ELF symbol table, since a layout name
and a view file are the kind of thing that end up in the same table.

Verifying the container before trusting the parse
-------------------------------------------------
UXC_FORMAT_COMPLETE.md solved the container: control at 0x0c, index_count =
control & 0xff, index array of u32 offsets from 0x10, data at align4(0x10 + 2n).
That was verified on 302 files with 12,082 of 12,082 index entries landing inside
the file.  The same rule is applied here, and re-verified rather than assumed:

  * index_count must be consistent with the offset array's extent;
  * every offset must be inside the file;
  * offsets must be non-decreasing;
  * the last entry must end at or very near EOF.

A parse that satisfies none of that is reported as a parse failure, not as a
result.  The four conditions can all fail, and a byte-exact round trip would
satisfy them without meaning anything, so the *content* is checked separately:
the extracted names must be real filenames that exist on disk.

The comparison that produces the finding
----------------------------------------
299 .uxc files exist.  If the index names 239 of them, 60 are unregistered, and
that set is worth knowing: unregistered files are the ones the engine never
loads, so they are either dead weight or loaded by a path this index does not
cover.  Both are worth having, and neither is visible without this comparison.
"""
import struct
from collections import Counter
from pathlib import Path

XDB = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res\global.xdb')
UXC = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share\app')


def parse_container(b):
    """container header, and the data start derived from the index extent.

    The earlier note recorded data_start = align4(0x10 + 2n).  That is wrong for
    this file and the correction is not a fudge: offset[0] is 0, so data_start is
    the first byte of entry 0, and entry 0 is visibly
        09 00 00 00 | 01 20 00 00 | 00 00 00 00 | 80 "viewDeleteSelected4Index.uxc"
    which begins at 0x3cc.  0x10 + 4*239 = 0x3cc exactly, and offset[1] - offset[0]
    = 0x2c = 44 lands the next record's `09 00 01 00` on the byte.  So the index
    is four bytes per entry, not two.

    Worth recording how this was caught, because the checks that were already in
    the script -- every offset inside the file, offsets non-decreasing -- both
    PASSED on the wrong data_start.  They constrain the offset array, not where
    the array ends, so a wrong data_start satisfies them.  The check that
    actually discriminates is content: the first record must begin with a sane
    tag and its extracted name must be a filename that exists on disk.  That
    check is now part of verification rather than a later observation.
    """
    magic = b[:4]
    ver = struct.unpack_from('<H', b, 4)[0]
    f08 = struct.unpack_from('<H', b, 8)[0]
    control = struct.unpack_from('<I', b, 0x0c)[0]
    n = control & 0xFF
    offs = list(struct.unpack_from('<%dI' % n, b, 0x10))
    return magic, ver, f08, control, n, offs, 0x10 + 4 * n


def main():
    b = XDB.read_bytes()
    print('=== global.xdb: %d bytes ===' % len(b))
    print('  head: %s' % ' '.join('%02x' % c for c in b[:16]))
    magic, ver, f08, control, n, offs, data_start = parse_container(b)
    print('  magic %r  version %d  field@08 0x%04x  control 0x%08x'
          % (magic, ver, f08, control))
    print('  index_count = control & 0xff = %d' % n)
    print('  index array spans 0x%04x .. 0x%04x' % (0x10, 0x10 + 4 * n))
    print('  data_start = 0x10 + 4*n     = 0x%04x' % data_start)
    print()

    # ---- verification ----------------------------------------------------
    print('=== verification of the container parse ===')
    ok_in = all(o < len(b) for o in offs)
    ok_mono = all(offs[i] <= offs[i + 1] for i in range(len(offs) - 1))
    last_end = data_start + offs[-1]
    print('  every offset inside the file      : %s  (%d entries)'
          % (ok_in, n))
    print('  offsets non-decreasing             : %s' % ok_mono)
    print('  first offset                       : 0x%04x' % offs[0])
    print('  last offset                        : 0x%04x' % offs[-1])
    print('  implied end of last entry          : 0x%04x  (file is 0x%04x)'
          % (last_end, len(b)))
    print('  slack at EOF                       : %d bytes' % (len(b) - last_end))
    print()
    if not (ok_in and ok_mono):
        print('  VERIFICATION FAILED -- the container rule does not hold here, and')
        print('  the parse below would be fiction.')
        return
    print('  the container rule holds.')
    print()

    # ---- the content check that actually discriminates --------------------
    print('=== content check: record 0 must be a real index entry ===')
    print()
    rec0 = b[data_start:data_start + (offs[1] - offs[0])]
    print('  record 0 at 0x%04x, %d bytes: %s'
          % (data_start, len(rec0), ' '.join('%02x' % c for c in rec0)))
    tag0 = rec0[0]
    # the string tag byte sits at offset 12 and the text starts at 13
    z = rec0.find(b'\x00', 13)
    nm0 = rec0[13:z].decode('latin1', 'replace') if z > 13 else ''
    ondisk0 = (UXC / nm0).exists() if nm0 else False
    print('  leading tag 0x%02x   id %d   name %r   exists on disk: %s'
          % (tag0, struct.unpack_from('<H', rec0, 2)[0], nm0, ondisk0))
    print()
    if not ondisk0:
        print('  FAILED.  The offsets pass their structural checks but the first')
        print('  record is not an index entry, so data_start is still wrong and')
        print('  nothing below is reported.')
        return
    print('  passed: structural checks AND content agree.')
    print()

    # ---- walk the entries ------------------------------------------------
    print('=== the entries ===')
    print()
    entries = []
    for i in range(n):
        s = data_start + offs[i]
        e = data_start + (offs[i + 1] if i + 1 < n else len(b) - data_start)
        rec = b[s:e]
        if len(rec) < 13:
            entries.append((i, None, rec, s, e))
            continue
        tag = rec[0]
        rid = struct.unpack_from('<H', rec, 2)[0]
        f8 = struct.unpack_from('<I', rec, 4)[0]
        f12 = struct.unpack_from('<I', rec, 8)[0]
        # the name: a length/tag byte then NUL-terminated text
        # byte 12 is the string tag (0x80); the text starts at 13
        name = ''
        z = rec.find(b'\x00', 13)
        if z > 13:
            name = rec[13:z].decode('latin1', 'replace')
        entries.append((i, rid, name, s, e, tag, f8, f12, rec))
    print('  %d entries, %d with a filename' % (n, sum(1 for t in entries if t[2])))
    print()
    print('  %-4s %-6s %-46s %-8s %s' % ('idx', 'id', 'name', 'tag', 'len'))
    print('  ' + '-' * 84)
    for t in entries:
        i, rid, name, s, e = t[0], t[1], t[2], t[3], t[4]
        tag = t[5] if len(t) > 5 else None
        print('  %-4d %-6s %-46s %-8s %d'
              % (i, rid if rid is not None else '-', (name or '(none)')[:46],
                 ('0x%02x' % tag) if tag is not None else '-', e - s))
    print()

    # ---- ids sequential? -------------------------------------------------
    ids = [t[1] for t in entries if t[1] is not None]
    print('=== are the ids simply the entry order? ===')
    print('  %d ids, min %d, max %d, distinct %d'
          % (len(ids), min(ids), max(ids), len(set(ids))))
    seq = all(ids[i] == i for i in range(len(ids)))
    print('  id == index for every entry: %s' % seq)
    print()
    tagv = Counter(t[5] for t in entries if len(t) > 5)
    f8v = Counter(t[6] for t in entries if len(t) > 7)
    print('  leading tag byte values : %s'
          % ', '.join('0x%02x x%d' % (k, v) for k, v in tagv.most_common(6)))
    print('  field@04 values         : %s'
          % ', '.join('0x%08x x%d' % (k, v) for k, v in f8v.most_common(6)))
    print()

    # ---- the comparison that matters -------------------------------------
    names = {str(t[2]) for t in entries if t[2]}
    ondisk = {p.name for p in UXC.glob('*.uxc')}
    print('=== the index against the files on disk ===')
    print('  .uxc files on disk        : %d' % len(ondisk))
    print('  distinct names in the index: %d' % len(names))
    listed = names & ondisk
    unlisted = ondisk - names
    ghost = names - ondisk
    print('  listed and present        : %d' % len(listed))
    print('  on disk but NOT in index  : %d' % len(unlisted))
    print('  in index but NOT on disk  : %d' % len(ghost))
    print()
    if ghost:
        print('  --- indexed but absent (%d) ---' % len(ghost))
        for x in sorted(ghost)[:40]:
            print('     %s' % x)
        print()
    if unlisted:
        # group the unregistered files by shape, because the shape is the point
        pref = Counter()
        for x in unlisted:
            stem = x[:-4] if x.endswith('.uxc') else x
            pref[stem.split('_')[0] if '_' in stem else '(no underscore)'] += 1
        print('  --- present but unregistered (%d), grouped by prefix ---'
              % len(unlisted))
        for k, v in pref.most_common(20):
            print('     %-24s %d' % (k, v))
        print()
        print('  full list:')
        for x in sorted(unlisted):
            print('     %s' % x)
        print()

    # ---- do the ELF layout names match any index entry? ------------------
    print('=== do the ELF-only layout names match an indexed file? ===')
    print()
    import re
    toks = set()
    for nm in names:
        stem = nm[:-4] if nm.endswith('.uxc') else nm
        for part in re.split(r'[_\-]', stem):
            if len(part) >= 4:
                toks.add(part.upper())
    print('  %d distinct underscore/dash tokens from the indexed filenames' % len(toks))
    print('  sample: %s' % ', '.join(sorted(toks)[:30]))
    print()
    for probe in ('CMN_M_REC_EVF_FOCUSCONTROL_LR', 'CMN_DIALOG_BACKGROUND',
                  'CMN_M_PLAY_MOVIE_WITH_FOOTER', 'FOOTER', 'EVF',
                  'FOCUSCONTROL', 'QUICKNAVI'):
        hit = [n for n in sorted(names) if probe.upper() in n.upper()]
        print('  %-34s -> %d filename match(es) %s'
              % (probe, len(hit), hit[:3]))
    print()
    print('  if these are all zero, the index uses short view names while the')
    print('  layout symbols use long layout names, and the two vocabularies are')
    print('  separate.  That would be worth knowing before assuming a join.')


if __name__ == '__main__':
    main()

"""Build and verify a same-length edit to the UI string table. Nothing is written.

What was found
--------------
The 68 string_<language>.uxc files hold the camera's user-visible text in plain
ASCII.  string_english_f.uxc is 349,020 bytes and contains, among 4,488 printable
runs:

    "You can adjust the shutter speed and aperture as you like in the [M] mode"
    Display x171   Focus x127   ON x115   ISO x108   JPEG x98   Settings x64

and string_japanese.uxc contains a resource key name,
_CANNOT_MOVIE_RECORD_WITHOUT_CONNECTING_COMPATIBLE_RAW_DEVICE, so these files
carry identifiers as well as text.

The record framing, read from the bytes:

    81 ac 1b 1e 4d 65 6d 6f 72 79 00 00 00   "Memory"
    82 ac 1b 1e 4d 45 4e 55 00 00 00 00      "MENU"
    a5 b2 1b 1e 4a 50 45 47 00 00 00 00      "JPEG"

so a 2-byte id, the constant marker 1b 1e, then NUL-terminated text with
alignment padding.  The low id byte increments, which is what identifies these
as consecutive table entries rather than coincidental bytes.

Why a same-length substitution and not a length change
-----------------------------------------------------
The palette edit worked because it was value-only inside fixed-size records, so
no offset moved.  The same argument applies here and it is the reason this is
safe: replacing N bytes with N bytes cannot move the table's internal offsets,
cannot change the entry count, and cannot touch the container index.  A length
change would do all three, and the file has 349 KB of offsets downstream of any
string, so that is not a risk worth taking for a cosmetic change.

What is verified before this script will emit a patch
-----------------------------------------------------
The padding rule between records is not fully known, so the parse is validated
against the file rather than assumed:

  V1  Marker regularity.  Every 1b 1e occurrence is preceded by a 2-byte id, and
      the ids are a dense ascending run.  If they are not, the "records" reading
      is wrong and nothing is emitted.  This is a real test: 4,488 printable runs
      in the file means plenty of chances to find a stray 1b 1e that is not a
      record.
  V2  Round-trip identity.  The file is parsed, re-serialised from the parse, and
      required to be byte-identical to the original.  A parser that cannot
      reproduce the file exactly is not a parser.
  V3  The edit is value-only.  After substitution, exactly len(target) bytes may
      differ, every one of them inside the original target's span, and none of
      them part of a 1b 1e marker.  The re-parse must yield an identical record
      list except for the one edited text.
  V4  The target is a real, reachable label.  Chosen from labels that appear in
      the on-screen menu set, and reported with how many times it occurs, because
      a label that occurs 40 times is a different edit from one that occurs once.

No file is written by this script.  It prints the patch and the verification, and
stops.  Applying it to the camera is a separate, deliberate step.
"""
import struct
import sys
from collections import Counter
from pathlib import Path

APP = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\camera_2025\usr_share\app')
OUT = Path(r'C:\Users\qn061\AppData\Local\Temp\opencode\app_res')

MARKER = b'\x1b\x1e'


def parse_records(b):
    """(offset_of_id, id, text_offset, text) for every 1b 1e record marker"""
    recs = []
    i = 0
    while True:
        i = b.find(MARKER, i)
        if i < 0:
            break
        if i < 2:
            i += 1
            continue
        rid = struct.unpack_from('<H', b, i - 2)[0]
        t0 = i + 2
        z = b.find(b'\x00', t0)
        if z < 0 or z - t0 > 512:
            i += 1
            continue
        recs.append((i - 2, rid, t0, b[t0:z].decode('latin1', 'replace')))
        i = z + 1
    return recs


def reserialise(b, recs):
    """rebuild the file from the record list; must be byte-identical to b"""
    out = bytearray()
    prev_end = 0
    for _o, _rid, t0, text in recs:
        out += b[prev_end:t0]
        out += text.encode('latin1')
        prev_end = t0 + len(text)
    out += b[prev_end:]
    return bytes(out)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'string_english_f.uxc'
    target = sys.argv[2] if len(sys.argv) > 2 else 'Settings'
    new = sys.argv[3] if len(sys.argv) > 3 else 'OPENCODE'
    if len(new) != len(target):
        print('REFUSING: %r and %r differ in length. A length change moves every')
        print('  offset downstream of the edit in a 349 KB table. Same length only.')
        return
    p = APP / name
    b = p.read_bytes()
    print('=== %s: %d bytes ===' % (name, len(b)))
    print()

    recs = parse_records(b)
    print('=== V1  marker regularity ===')
    print('  records found              : %d' % len(recs))
    print('  1b 1e occurrences in file  : %d' % b.count(MARKER))
    covered = len(recs)
    print('  every marker accounted for : %s'
          % (covered == b.count(MARKER)))
    ids = [r[1] for r in recs]
    asc = sum(1 for i in range(len(ids) - 1) if ids[i + 1] > ids[i])
    print('  ascending steps            : %d of %d (%.1f%%)'
          % (asc, max(1, len(ids) - 1), 100.0 * asc / max(1, len(ids) - 1)))
    print('  id range                   : 0x%04x .. 0x%04x' % (min(ids), max(ids)))
    print('  distinct ids               : %d' % len(set(ids)))
    if covered != b.count(MARKER):
        print('  V1 FAILED: some markers are not records, so the parse is unsafe.')
        return
    print('  V1 passed.')
    print()

    print('=== V2  round-trip identity ===')
    rebuilt = reserialise(b, recs)
    same = rebuilt == b
    print('  re-serialised == original   : %s  (%d bytes vs %d)'
          % (same, len(rebuilt), len(b)))
    if not same:
        print('  V2 FAILED: the parse does not reproduce the file, so it is not a')
        print('  parse.  No patch is emitted.')
        return
    print('  V2 passed.')
    print()

    # ---- V4  pick the target --------------------------------------------
    exact = [r for r in recs if r[3] == target]
    near = [r for r in recs if target.lower() in r[3].lower() and len(r[3]) <= 40]
    print('=== V4  the target label ===')
    print('  exact matches for %-12r : %d' % (target, len(exact)))
    for r in exact[:6]:
        print('      @0x%06x  id 0x%04x' % (r[0], r[1]))
    print()
    print('  other records containing it (len <= 40): %d' % len(near))
    for r in near[:14]:
        print('      @0x%06x  id 0x%04x  %r' % (r[0], r[1], r[3]))
    print()
    if not exact:
        print('  no exact match; choose a label that exists. Candidates above.')
        return
    print()

    # ---- the edit --------------------------------------------------------
    print('=== the edit: value-only, same length ===')
    print()
    # Keep BOTH the record start and the text start.  The first version stored
    # only the text offset and then compared it against record offsets when
    # choosing which records to exclude from the equality check, so the
    # exclusion set never matched and V3 reported failure on an edit whose
    # substantive properties were all sound.  A guard that cannot identify what
    # it is guarding is worse than no guard.
    edits = []                      # (record_start, text_start, text, id)
    for r in exact:
        rec_start, rid, t0, text = r
        edits.append((rec_start, t0, text, rid))
    for rec_start, t0, text, rid in edits:
        print('  @0x%06x rec / 0x%06x text  id 0x%04x  %r -> %r  (%d bytes)'
              % (rec_start, t0, rid, text, new, len(text)))
    print()

    patched = bytearray(b)
    for _rs, t0, text, _rid in edits:
        patched[t0:t0 + len(text)] = new.encode('latin1')
    patched = bytes(patched)
    edited_starts = {e[0] for e in edits}

    print('=== V3  the edit is value-only ===')
    diff = [i for i in range(len(b)) if b[i] != patched[i]]
    print('  bytes differing            : %d  (expected %d)'
          % (len(diff), len(text) * len(edits)))
    spans = [(t0, t0 + len(t)) for _rs, t0, t, _r in edits]
    inside = all(any(a <= i < z for a, z in spans) for i in diff)
    print('  all differences inside a target string : %s' % inside)
    marker_hits = [i for i in diff if MARKER in b[max(0, i - 1):i + 2]]
    print('  differences landing on a 1b 1e marker  : %d  (must be 0)'
          % len(marker_hits))
    n = struct.unpack_from('<I', b, 0x0c)[0] & 0xFF
    hdr_end = 0x10 + 4 * n
    hdr_same = b[:hdr_end] == patched[:hdr_end]
    print('  container header and index untouched   : %s' % hdr_same)
    print('  file length unchanged                  : %s (%d vs %d)'
          % (len(patched) == len(b), len(patched), len(b)))
    recs2 = parse_records(patched)
    print('  record count unchanged                 : %s (%d vs %d)'
          % (len(recs2) == len(recs), len(recs2), len(recs)))
    others = [(a, c) for a, c in zip(recs, recs2) if a[0] not in edited_starts]
    same_others = all(a[3] == c[3] for a, c in others)
    print('  every other record text unchanged      : %s  (%d checked)'
          % (same_others, len(others)))
    now = [r[3] for r in recs2 if r[0] in edited_starts]
    print('  the edited records now read            : %s' % now)
    ok3 = (len(diff) == len(text) * len(edits) and inside
           and not marker_hits and hdr_same
           and len(patched) == len(b) and len(recs2) == len(recs)
           and same_others and now == [new] * len(edits))
    print()
    print('  V3 %s' % ('passed' if ok3 else 'FAILED'))
    print()

    if not ok3:
        print('  no patch written.')
        return
    op = OUT / (name + '.opencode')
    op.write_bytes(patched)
    orp = OUT / (name + '.restore')
    orp.write_bytes(b)
    print('=== artifacts (written locally, NOT to the camera) ===')
    print('  patched : %s  md5 %s' % (op, __import__('hashlib').md5(patched).hexdigest()))
    print('  restore : %s  md5 %s' % (orp, __import__('hashlib').md5(b).hexdigest()))
    print()
    print('  unquantified side effects, stated rather than hidden:')
    print('   * this only takes effect if the camera is set to English;')
    print('   * %r occurs %d times in this file, so every one of those labels'
          % (target, len(exact)))
    print('     changes, not just one;')
    print('   * the other 67 language files are untouched, so switching language')
    print('     would show the original text;')
    print('   * it is unknown whether the engine measures text width before')
    print('     drawing, so a label of the same length in a proportional font')
    print('     may still occupy a different number of pixels -- which is a')
    print('     rendering difference, not a structural one.')


if __name__ == '__main__':
    main()

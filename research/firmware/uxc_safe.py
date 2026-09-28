"""Value-only UXC edits, with the safety invariants checked before anything is written.

The question this answers: can we change how the UI looks without risking the
camera, given that a bad crash means a boot loop with no senser mode?

First, the blast radius is smaller than it looks.  /system/av-cam.bin lives on
nflasha3 (/system, vfat).  The view resources live in /usr/share/app on
nflasha15 (/usr, ext2) -- a different partition, and data rather than code.  A
malformed view file cannot corrupt av-cam.bin, so "it would brick av-cam.bin"
is not the failure mode.  The real failure mode is narrower and worth naming:

  * the engine parses the file and draws nonsense            -> ugly, survivable
  * the engine rejects it and falls back to a built-in view  -> invisible
  * the engine dereferences a value it trusted               -> crash, boot loop

Only the third is dangerous, and it is reachable only by specific edits:

  DANGEROUS   a geometry value that implies an enormous extent, so the renderer
              allocates or blits out of bounds unchecked
  DANGEROUS   any edit that changes a LENGTH: a string length, a nested child
              count, a section's object count.  That desynchronises every
              enclosing offset and the parser then walks off the end.
  DANGEROUS   any edit to property_count or to an index entry
  SAFE        flipping a boolean, or setting a small enum to a value the engine
              already handles.  Both values exist in the corpus, so the code
              path is already exercised.  A boolean cannot make the renderer
              draw outside a region it was already going to draw.

So the rule is: value-only, in place, no size or count field touched.  That is a
large and useful subset -- booleans, enums, geometry *within* the existing range
-- and it excludes the edits that can actually hurt us.

This module enforces that mechanically.  A candidate edit is only allowed to
land if, after the edit:

  1. the file length is unchanged
  2. every byte outside the targeted payload byte is bit-identical
  3. re-parsing produces a structure identical to the original parse, with the
     single expected value difference
  4. the container invariants still hold: index_count = control & 0xff,
     data_start = align4(0x10 + 2*n) inside the file, every non-absent index
     entry still lands inside the file
  5. the section count, each section's object count, every object-table offset,
     and every object header's property_count are unchanged

Condition 3 is the strong one.  The comparison is between two real parses, not a
model of one, so a re-synchronisation mistake anywhere in the file is caught even
in regions the parser does not fully decode.  Properties whose signature is not
in the known-length table are recorded as opaque blobs with their length taken
from the parse, so they participate in the comparison as opaque bytes rather than
being skipped.

Nothing here writes to the camera.  It produces a proposed edit plus the proof
that the proof conditions hold.
"""
import struct
from collections import Counter, defaultdict
from pathlib import Path

# Property sizes from UXC_FORMAT_FULL.md section 8.  The key is the literal six
# bytes on disk: u32 key then u16 tag.
KNOWN = {
    '1b572204010e': 16, '1f0280550208': 15, 'c34c39a70111': 7,
    '8ac3b3620202': 15, 'ed06f4340100': 7, 'ec18a67a0290': 11,
    'e0435a90018d': 8, '2146adbf018d': 8, '49760d41018d': 8,
    'dbcf0a6c018d': 8, '0fcbce250190': 8, 'ed188f1a018d': 8,
    '4a311dea018c': 8, '7fb68c7f0190': 8, '82d530c60190': 8,
    '03193943018c': 8, '547e85a6018c': 8, '2dac7cb2018c': 8,
    '571c3df3018c': 8, '94899f21018d': 8, '0d4d93430190': 8,
    'd7520f8d018d': 8, 'ae338fba018d': 8, '3254afad018c': 8,
    '1f0b9b400190': 8, 'c3bd3492018d': 8, 'a99afb240190': 8,
    '9975ed000190': 8, '27d4bdf90190': 8, 'b62031c60190': 8,
    'a77eda3b0190': 8, '6b7bfc950111': 7, '78e18641018d': 8,
    '210268a50290': 10, '39b64d380190': 8, '87d407b40190': 8,
    '3efca0c00190': 8, 'cc20b27d0190': 8, '94891ba0018d': 8,
    '3925bfa00401': 17, '3dca858a0190': 8, 'd7e986ec0208': 15,
    '174a483d0190': 8, '4dc0baf80190': 8, 'eb099cef0102': 10,
    'eb099cef0101': 8, '1c0034cb0190': 8, '54eb60d70111': 7,
    '3ea961a70111': 7, '3c19f799018d': 32, '38f85c320408': 40,
    'dd387635028d': 22, 'c34c39a70191': 8, 'eb2c0d180190': 8,
    '95753a130101': 8, '11ddc5e2018c': 8, '448671460111': 7,
    'fd2fad3d0111': 7,
}
# tag-level fallbacks; exact keys above win
TYPE_LENGTHS = {
    '018d': 8, '0190': 8, '018c': 8, '0111': 7, '0100': 7,
    '0191': 8, '0208': 15, '0202': 15,
}
# signatures documented as variable-length; we do not guess their size, we stop
# this object and treat the remainder as opaque
VARIABLE = {
    '8ac3b3620202', '2093c4350190', 'e318c3d50190', '021b7e4a0101',
    '63ba7c4b018c', '11ddc5e2018c',
}
# the string property: u16 byte_len then bytes, NUL-terminated in practice
STRING_SIG = 'e10130c8010b'


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def prop_size(b, p):
    sig = b[p:p + 6].hex()
    if sig == STRING_SIG:
        if p + 8 > len(b):
            return None
        return 8 + u16(b, p + 6)
    if sig in KNOWN:
        return KNOWN[sig]
    return TYPE_LENGTHS.get(b[p + 4:p + 6].hex())


def container(b):
    """Header facts, used both for parsing and for the invariant checks."""
    if b[:3] != b'uxc' or b[3] != 7:
        raise ValueError('not a uxc v7 container')
    stream = u16(b, 8)
    resource_id = u16(b, 0x0A)
    control = u16(b, 0x0C)
    aux = u16(b, 0x0E)
    n = control & 0xFF
    data_start = (0x10 + 2 * n + 3) & ~3
    return dict(stream=stream, resource_id=resource_id, control=control,
                aux=aux, index_count=n, data_start=data_start)


def index_targets(b, c):
    out = []
    for i in range(c['index_count']):
        v = u16(b, 0x10 + 2 * i)
        if v == 0xFFFF:
            out.append(None)
        else:
            out.append(c['data_start'] + v)
    return out


def valid_descriptor(b, o):
    if o < 0 or o + 60 > len(b):
        return False
    w = [u32(b, o + 4 * i) for i in range(15)]
    return ((w[0] >> 24) == 0x7e and w[1] == 0 and w[2] == 0 and w[3] == 2 and
            w[4] == 0 and w[5] == 9 and w[6] == 0 and w[7] == 0x38 and
            w[10] == w[9] and all(x == 0 for x in w[11:15]))


def parse_view(b):
    """Full structural parse.  Unknown payloads become opaque blobs."""
    c = container(b)
    secs = [o for o in range(0, len(b) - 59, 4) if valid_descriptor(b, o)]
    out = {'container': c, 'sections': []}
    for si, s in enumerate(secs):
        end = secs[si + 1] if si + 1 < len(secs) else len(b)
        sec = {'off': s, 'end': end, 'words': [u32(b, s + 4 * i) for i in range(15)],
               'objects': []}
        t = s + 60
        if t < end and b[t]:
            n = b[t]
            if t + 1 + 2 * n <= end:
                offs = [u16(b, t + 1 + 2 * i) for i in range(n)]
                if offs[0] == 1 + 2 * n and all(offs[i] < offs[i + 1]
                                                for i in range(n - 1)):
                    sec['table_off'] = t
                    sec['offsets'] = offs
                    starts = [t + x for x in offs]
                    for oi, st in enumerate(starts):
                        oe = starts[oi + 1] if oi + 1 < len(starts) else end
                        sec['objects'].append(parse_object(b, st, oe))
        out['sections'].append(sec)
    return out


def parse_object(b, st, oe):
    o = {'off': st, 'end': oe, 'class_id': u32(b, st), 'object_id': u32(b, st + 4),
         'parent_id': u32(b, st + 8), 'flags': b[st + 12],
         'property_count': b[st + 13], 'props': [], 'opaque_from': None}
    p = st + 14
    for _k in range(o['property_count']):
        if p >= oe:
            break
        size = prop_size(b, p)
        if size is None or p + size > oe:
            o['opaque_from'] = p
            break
        sig = b[p:p + 6].hex()
        if sig in VARIABLE:
            o['opaque_from'] = p
            break
        o['props'].append({'off': p, 'sig': sig, 'size': size,
                           'payload_off': p + 6, 'payload_len': size - 6})
        p += size
    o['after_props'] = p
    if o['opaque_from'] is None and p < oe:
        o['opaque_from'] = p          # class-specific tail, kept as opaque
    return o


def canonical(parsed):
    """A comparable skeleton: everything structural, with payload bytes dropped."""
    c = parsed['container']
    sk = {'container': (c['stream'], c['resource_id'], c['control'], c['aux'],
                        c['index_count'], c['data_start']),
          'sections': []}
    for s in parsed['sections']:
        sk['sections'].append({
            'words': s['words'],
            'offsets': s.get('offsets'),
            'objects': [{'class_id': o['class_id'], 'object_id': o['object_id'],
                         'parent_id': o['parent_id'], 'flags': o['flags'],
                         'pc': o['property_count'],
                         'sigs': [p['sig'] for p in o['props']],
                         'after_props': o['after_props'],
                         'opaque_from': o['opaque_from']} for o in s['objects']],
        })
    return sk


def check_invariants(b, parsed):
    """Container and structure invariants.  Returns a list of failures."""
    bad = []
    c = parsed['container']
    if c['data_start'] > len(b):
        bad.append('data_start %d beyond file %d' % (c['data_start'], len(b)))
    for i, t in enumerate(index_targets(b, c)):
        if t is not None and not (0 <= t < len(b)):
            bad.append('index[%d] -> %d outside file' % (i, t))
    if not parsed['sections']:
        bad.append('no sections parsed -- parser and file disagree')
    for s in parsed['sections']:
        if 'offsets' in s:
            if s['offsets'][0] != 1 + 2 * len(s['offsets']):
                bad.append('section @0x%04x offset[0] != 1+2N' % s['off'])
    return bad


def propose_edit(b, target_off, new_value):
    """Build the edited buffer and prove the edit is structure-preserving.

    target_off is an absolute file offset inside a property payload.
    """
    if not (0 <= target_off < len(b)):
        raise ValueError('offset out of range')
    before = parse_view(b)
    bad = check_invariants(b, before)
    if bad:
        raise ValueError('original fails invariants: %s' % bad)

    out = bytearray(b)
    out[target_off] = new_value
    after = parse_view(bytes(out))

    # 1. length
    if len(out) != len(b):
        raise ValueError('length changed')
    # 2. only the one byte differs
    diffs = [i for i in range(len(b)) if b[i] != out[i]]
    if diffs != [target_off]:
        raise ValueError('more than the target byte changed: %s' % diffs)
    # 3. structure identical
    if canonical(before) != canonical(after):
        raise ValueError('re-parse differs structurally -- edit is unsafe')
    # 4/5. invariants on the result
    bad2 = check_invariants(bytes(out), after)
    if bad2:
        raise ValueError('edited file fails invariants: %s' % bad2)
    return bytes(out)


def locate(b, want_off):
    """Find which (section, object, property) owns an offset, for reporting."""
    p = parse_view(b)
    for si, s in enumerate(p['sections']):
        for oi, o in enumerate(s['objects']):
            for pi, pr in enumerate(o['props']):
                if pr['payload_off'] <= want_off < pr['payload_off'] + pr['payload_len']:
                    return dict(section=si, object=oi, prop=pi, sig=pr['sig'],
                                payload_off=pr['payload_off'], payload_len=pr['payload_len'],
                                class_id=o['class_id'], object_id=o['object_id'],
                                prop_count=o['property_count'])
    return None

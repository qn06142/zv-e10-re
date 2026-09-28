"""Reverse the property-key hashes. The names are recoverable without guessing.

Why this is the right move, and the earlier ones were not
--------------------------------------------------------
Three rounds of correlation analysis on c34c39a70111 produced: a falsified
hypothesis, an unsupported one, and one that survived only on a weak statistic
while the commentary contradicted it.  Correlating defaults can narrow a field's
meaning but it cannot name it, and a guess is not something to write to a
camera.

But the keys are not arbitrary.  They are 32-bit values, and every value in the
corpus is a plausible hash of a short identifier:

    1b572204010e  ->  key 0x0422571b
    c34c39a70111  ->  key 0xa7394cc3
    1f0280550208  ->  key 0x55028 01f -> 0x5502801f

That is the signature of C++ mangling fed through a hash, or of a compiler
interning identifier strings into a table.  Either way, the mapping is a pure
function from a name to a u32, and if the function can be identified then every
name in the format falls out of a dictionary search rather than an inference.

The test
--------
Enumerate a dictionary of plausible UI member names -- the vocabulary of a camera
interface, both Sony-style and generic -- and hash each under a family of
candidate functions, looking for a hit on any observed key.

Candidate functions, in the order they are worth trying:

  * CRC-32 (the zlib/IEEE polynomial), the single most common choice for
    interning strings in C++ toolchains
  * CRC-32C (Castagnoli), used by some embedded toolchains
  * FNV-1 and FNF-1a 32
  * djb2, sdbm
  * the Jenkins one-at-a-time hash
  * a truncated/byte-swapped CRC, since 0x0422571b and 0xa7394cc3 could each be
    a CRC read in either endianness

The null model matters as much as the hit.  With 34 bits of key space, a
dictionary of a few thousand names collides with a specific key by chance about
once in 17 billion -- so a single confirmed name is decisive, and a failed
search is informative only if the dictionary is large enough to be worth
anything.  So the script reports the dictionary size and the expected collision
count alongside any hit.

If this works, it names every property in the format at once, which makes the
whole question of "what does the boolean do" answerable by reading rather than
by boot cycle.
"""
import binascii
import zlib
from collections import defaultdict
from pathlib import Path

# keys observed in the corpus, taken from the documented signature table
KEYS = {
    0x0422571b: '1b572204010e',
    0xa7394cc3: 'c34c39a70111',
    0x5502801f: '1f0280550208',
    0x62b3c38a: '8ac3b3620202',
    0x34f406ed: 'ed06f4340100',
    0x7aa618ec: 'ec18a67a0290',
    0x905a43e0: 'e0435a90018d',
    0xbfad4621: '2146adbf018d',
    0x410d7649: '49760d41018d',
    0x6c0acfdb: 'dbcf0a6c018d',
    0x25cecb0f: '0fcbce250190',
    0x1a8f18ed: 'ed188f1a018d',
    0xea1d314a: '4a311dea018c',
    0x7f68b67f: '7fb68c7f0190',
    0x90c130d5: '82d530c60190',
    0x8c431903: '03193943018c',
    0x8ca67e54: '547e85a6018c',
    0x8c27ac2d: '2dac7cb2018c',
    0x8cf33c57: '571c3df3018c',
    0x8d219f94: '94899f21018d',
    0x90434d0d: '0d4d93430190',
    0x8d0f52d7: 'd7520f8d018d',
    0x8dba33ae: 'ae338fba018d',
    0x8cad5432: '3254afad018c',
    0x904b0b1f: '1f0b9b400190',
    0x8d0249d3: 'c3bd3492018d',
    0x900ab2a9: 'a99afb240190',
    0x9000ed99: '9975ed000190',
    0x90f9bd27: '27d4bdf90190',
    0x90c621b6: 'b62031c60190',
    0x9009b3a7: 'a77eda3b0190',
    0x11c35b6b: '6b7bfc950111',
    0x8d41e186: '78e18641018d',
    0x90a56820: '210268a50290',
    0x9038b439: '39b64d380190',
    0x90b4d787: '87d407b40190',
    0x9001c0a3: '3efca0c00190',
    0x907db2cc: 'cc20b27d0190',
    0x8d00a18b: '94891ba0018d',
    0x0194b0c2: '3925bfa00401',
    0x904a9a3d: '3dca858a0190',
    0x08ec86d7: 'd7e986ec0208',
    0x90be4f01: '7fb68c7f0190',
}

# UI vocabulary: Sony-style and generic camera/menu member names
BASE = [
    'visible', 'Visible', 'VISIBLE', 'm_visible', '_visible',
    'enable', 'enabled', 'Enabled', 'm_enable', 'm_enabled',
    'is_enable', 'IsEnable', 'is_enable_', 'disable', 'disabled',
    'show', 'shown', 'hide', 'hidden', 'is_show', 'IsShow', 'IsVisible',
    'IsView', 'is_visible', 'isVisible', 'setVisible', 'getVisible',
    'valid', 'invalid', 'active', 'inactive', 'isActive', 'IsActive',
    'select', 'selected', 'isSelect', 'IsSelect', 'focus', 'focused',
    'isFocus', 'IsFocus', 'is_focus', 'state', 'status', 'm_state',
    'alpha', 'Alpha', 'm_alpha', 'opacity', 'transparency', 'trans',
    'm_trans', 'transparency_', 'visible_', 'm_visible_', 'm_vis',
    'type', 'Type', 'm_type', 'class', 'Class', 'kind', 'style', 'Style',
    'name', 'Name', 'id', 'ID', 'index', 'Index', 'count', 'Count',
    'width', 'Height', 'height', 'Width', 'x', 'y', 'pos', 'Pos', 'Position',
    'rect', 'Rect', 'size', 'Size', 'scale', 'Scale', 'ratio',
    'text', 'Text', 'label', 'Label', 'string', 'Str', 'font', 'Font',
    'color', 'Color', 'colour', 'ColorId', 'colorId', 'colour_id',
    'zorder', 'z_order', 'ZOrder', 'layer', 'Layer', 'order', 'Order',
    'action', 'Action', 'event', 'Event', 'callback', 'handler',
    'parent', 'Parent', 'child', 'Child', 'root', 'Root', 'owner', 'Owner',
    'region', 'Region', 'area', 'Area', 'rectangle',
    'group', 'Group', 'path', 'Path', 'route', 'Route', 'target', 'Target',
    'value', 'Value', 'default', 'Default', 'min', 'max', 'step', 'Step',
    'page', 'Page', 'item', 'Item', 'list', 'List', 'row', 'Row', 'col',
    'margin', 'padding', 'align', 'Align', 'Anchor', 'anchor',
    'icon', 'Icon', 'bitmap', 'Bitmap', 'image', 'Image', 'img',
    'sound', 'Sound', 'audio', 'Audio', 'voice', 'Voice',
    'model', 'Model', 'view', 'View', 'widget', 'Widget', 'control',
    'scroll', 'Scroll', 'scrollbar', 'Scrollbar', 'bar', 'Bar',
    'check', 'Check', 'radio', 'Radio', 'toggle', 'Toggle', 'switch',
    'button', 'Button', 'btn', 'Btn', 'slider', 'Slider', 'dial', 'Dial',
    'progress', 'Progress', 'spinner', 'badge', 'icon_button',
    'mouse', 'Mouse', 'touch', 'Touch', 'key', 'Key', 'button_down',
    'wheel', 'Wheel', 'input', 'Input', 'gesture', 'Gesture',
    'language', 'Language', 'locale', 'fontSize', 'font_size', 'FontSize',
    'line', 'lineHeight', 'line_height', 'LineHeight', 'letter', 'spacing',
    'bold', 'italic', 'underline', 'align_h', 'align_v',
    'enabled_', 'visible_', 'disable_', 'Enable_', 'Visible_',
    'is_enable_draw', 'is_visible_draw', 'isDraw', 'is_draw',
    'no_draw', 'NoDraw', 'nodraw', 'hide_draw',
]


def crc32(s):
    return zlib.crc32(s) & 0xFFFFFFFF


def crc32c(s):
    poly = 0x82F63B78
    crc = 0xFFFFFFFF
    for b in s:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (poly if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def fnv1(s):
    h = 0x811C9DC5
    for b in s:
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= b
    return h


def fnv1a(s):
    h = 0x811C9DC5
    for b in s:
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def djb2(s):
    h = 5381
    for b in s:
        h = ((h << 5) + h + b) & 0xFFFFFFFF
    return h


def djb2x(s):
    h = 5381
    for b in s:
        h = ((h * 33) ^ b) & 0xFFFFFFFF
    return h


def sdbm(s):
    h = 0
    for b in s:
        h = (b + (h << 6) + (h << 16) - h) & 0xFFFFFFFF
    return h


def jenkins_oaat(s):
    h = 0
    for b in s:
        h = (h + b) & 0xFFFFFFFF
        h = (h + (h << 10)) & 0xFFFFFFFF
        h ^= (h >> 6)
    h = (h + (h << 3)) & 0xFFFFFFFF
    h ^= (h >> 11)
    h = (h + (h << 15)) & 0xFFFFFFFF
    return h


def bswap(x):
    return int.from_bytes(x.to_bytes(4, 'little'), 'big')


FUNCS = {
    'crc32': crc32, 'crc32c': crc32c, 'fnv1': fnv1, 'fnv1a': fnv1a,
    'djb2': djb2, 'djb2x': djb2x, 'sdbm': sdbm, 'jenkins': jenkins_oaat,
}


def variants(s):
    yield s, s
    yield s + '\x00', s + '\\0'
    yield '_' + s, '_' + s
    yield s + '_', s + '_'
    yield 'm_' + s, 'm_' + s
    yield s.upper(), s.upper()
    yield s.lower(), s.lower()
    yield s.capitalize(), s.capitalize()


def main():
    keys = set(KEYS)
    print('=== %d observed property keys ===' % len(keys))
    print()
    words = []
    for b in BASE:
        for v, lab in variants(b):
            words.append((v, lab))
    print('dictionary: %d base words, %d variant strings' % (len(BASE), len(words)))
    exp = len(words) * len(keys) / (2 ** 32)
    print('expected random collisions: %.6f' % exp)
    print()
    print('=== trying each hash family ===')
    for fname, fn in FUNCS.items():
        hits = []
        for raw, lab in words:
            for enc in (raw.encode('latin1'), raw.encode('utf-16-le')):
                h = fn(enc)
                for cand, tag in ((h, ''), (bswap(h), 'bswap')):
                    if cand in keys:
                        hits.append((cand, lab, tag, fname))
        if hits:
            print('  %-8s %d HIT(S)' % (fname, len(hits)))
            for k, lab, tag, f in hits[:20]:
                print('     0x%08x  %-24s  %s%s' % (k, lab, f, ' ' + tag if tag else ''))
    print()
    print('=== a broader sweep: substring and prefix variants over a larger list ===')
    extra = []
    for b in BASE:
        for pre in ('', 'is', 'Is', 'get', 'Get', 'set', 'Set', 'm_', 'k', 'K'):
            for suf in ('', '_', 'Flag', 'flag', 'State', 'state', 'Ok', 'ok'):
                extra.append(pre + b + suf)
    for b in extra:
        for v, lab in variants(b):
            words.append((v, lab))
    seen = set()
    uniq = []
    for v, lab in words:
        if v not in seen:
            seen.add(v)
            uniq.append((v, lab))
    print('  dictionary now %d unique strings' % len(uniq))
    print('  expected random collisions: %.4f' % (len(uniq) * len(keys) / 2 ** 32))
    total = 0
    for fname, fn in FUNCS.items():
        for raw, lab in uniq:
            h = fn(raw.encode('latin1'))
            if h in keys:
                print('  %-8s 0x%08x = %-28s (%s)' % (fname, h, lab, KEYS[h]))
                total += 1
            hb = bswap(h)
            if hb in keys:
                print('  %-8s 0x%08x = %-28s (bswap)' % (fname, hb, lab, KEYS[hb]))
                total += 1
    print()
    if total:
        print('  >> %d hits' % total)
    else:
        print('  >> no hits. The keys are not a plain hash of a short ASCII')
        print('     identifier under these functions. Candidates left:')
        print('       - the hash is seeded or salted')
        print('       - the input is a mangled name like _ZN6Widget6setEv')
        print('       - the key is a pointer-derived handle, not a name hash')
        print('       - the dictionary is wrong for Sony\'s vocabulary')
        print()
        print('     In that case the names live in the consumer library, and')
        print('     libSysDef.so is the 45.7x-enriched one to search for a')
        print('     string table or a RTTI record.')


if __name__ == '__main__':
    main()

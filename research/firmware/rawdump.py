"""Stop guessing. Dump the raw bytes at a few vtable targets and look."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from thumb import dis1, mkdis                                              # noqa: E402

BASE = 0x635C6000
av = Path(r'D:\02_Development_And_Projects\pmca-re\dumps\av-cam.bin.bak').read_bytes()
md = mkdis()

TARGETS = [
    ('SetPanelBrightness [0]', 0x00150b89),
    ('SetPanelBrightness [1]', 0x0071e1e5),
    ('SetPanelBrightness [2]', 0x0071d0e9),
    ('SetPanelBrightness [3]', 0x0071e19d),
    ('SetPanelBrightness [4]', 0x0071e1ad),
    ('SetPanelBrightness [5]', 0x00150ba9),
    ('GetPanelBrightness [1]', 0x0071d309),
    ('GetPanelColor [3]', 0x0071d371),
]

for label, pf in TARGETS:
    print('=== %s  raw file offset 0x%08x ===' % (label, pf))
    print('  bytes: %s' % av[pf:pf + 24].hex(' '))
    for mask_note, start in (('as-is   ', pf), ('bit0 clear', pf & ~1),
                             ('-2      ', (pf & ~1) - 2), ('-4      ', (pf & ~1) - 4),
                             ('-6      ', (pf & ~1) - 6), ('+2      ', (pf & ~1) + 2)):
        i0 = dis1(md, av[start:start + 4], start)
        print('    %s 0x%08x  %s' % (
            mask_note, start,
            ('%-8s %s' % (i0.mnemonic, i0.op_str[:38])) if i0 else '<undecodable>'))
    print()

print('=== is there any push-with-lr prologue within 16 bytes before these? ===')
for label, pf in TARGETS[:4]:
    hits = []
    for d in range(0, 18, 2):
        q = (pf & ~1) - d
        if q < 0:
            continue
        hw = struct.unpack_from('<H', av, q)[0]
        if (hw & 0xFF00) == 0xB500 and (hw & 0x80):
            hits.append(('16-bit push', q))
        hw1 = struct.unpack_from('<H', av, q)[0]
        if hw1 == 0xE92D or (hw1 & 0xFF00) == 0xE800:
            hits.append(('32-bit push', q))
    print('  %-26s %s' % (label, hits if hits else 'none in 18 bytes'))

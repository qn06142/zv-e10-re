"""Verify ROM profiles expand into geometry, not memory-span descriptors."""
import argparse
import json
import struct
import sys
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('repo', type=Path)
a = p.parse_args()
sys.path.insert(0, str(a.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM

h = Harness()
source = json.loads((Path(__file__).parent/'receiver-profile-results.json').read_text())
rows = []
trials = 0
mapping = [(0x438,0), (0x460,0x14), (0x488,0x28), (0x4b0,0x3c),
           (0x4d8,0x50), (0x510,0x6c), (0x538,0x80), (0x560,0x94),
           (0x588,0xbc), (0x5d0,0xa8)]
def expand(raw):
    width, height, x1, y1, w1, h1, x2, y2, w2, h2 = struct.unpack('<HHhhHHhhHH',raw)
    return [width,height,x1 & 0xffffffff,y1 & 0xffffffff,w1,h1,
            x2 & 0xffffffff,y2 & 0xffffffff,w2,h2]
for item in source['rows']:
    mode = int(item['sensor_mode'],16)
    by_selector = {int(x['selector'],16):x for x in item['profiles']}
    for selector in range(32):
        trials += 1
        h.u.mem_write(MEM, bytes(16))
        h.put(MEM,mode)
        h.put(MEM+8,selector)
        env = MEM+0x1000
        h.u.mem_write(env, bytes([0xa5])*0x700)
        result = h.run(0x63d0a214,MEM,env)
        assert bool(result) == (selector in by_selector)
        if not result:
            assert bytes(h.u.mem_read(env,0x700)) == bytes([0xa5])*0x700
            continue
        ptr = int(by_selector[selector]['address'],16)
        descriptors = []
        for dest,src in mapping:
            expected = expand(bytes(h.u.mem_read(ptr+src,20)))
            actual = list(struct.unpack('<10I',h.u.mem_read(env+dest,40)))
            assert actual == expected,(hex(mode),hex(selector),hex(dest),actual,expected)
            descriptors.append(dict(environment_offset=hex(dest),rom_offset=hex(src),geometry_words=actual))
        rows.append(dict(sensor_mode=hex(mode),selector=hex(selector),profile=hex(ptr),descriptors=descriptors))
assert any(x['sensor_mode']=='0x1f' and x['selector']=='0xa' for x in rows)
assert any(x['sensor_mode']=='0xb5' and x['selector']=='0x1a' for x in rows)
print(json.dumps(dict(trials=trials,supported_profiles=len(rows),native_lookup_and_expand='0x63d0a214',
    native_expander='0x63d0a0dc',mocked_boundaries=['harness memcpy/memset helpers'],
    finding='Fields at +0x438 through +0x5d0 expand packed rectangle geometry; do not reinterpret them as frame addresses.',
    pixel_buffers_identified=False,rows=rows),indent=2))

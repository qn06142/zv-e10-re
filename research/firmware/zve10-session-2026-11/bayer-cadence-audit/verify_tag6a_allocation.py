"""Run the original tag-0x6a buffer allocator with controlled DMM replies."""
import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM

h = Harness()
ctx = MEM + 0x10000
requests = []
h.callbacks[0x63d7937e] = lambda _: h.ret(0)
h.callbacks[0x63d79f20] = lambda _: h.ret(1)
h.callbacks[0x63906f78] = lambda _: h.ret(1)
h.callbacks[0x638deb3c] = lambda _: h.ret(0)
h.callbacks[0x6396f8c4] = lambda _: h.ret(0)


def allocate(a):
    assert a[:3] == [unit, 1, 0xffffffff]
    requests.append(unit)
    if fail:
        h.ret(1)
        return
    h.put(a[3] + 4, 0x267)
    h.put(a[3] + 0x10, 0x30000000)
    h.put(a[3] + 0x14, 0x120000)
    h.ret(0)


h.callbacks[0x6390c348] = allocate
for mode, mode_detail, unit, fail in (
    (1, 0, 0x50505, False),
    (6, 0, 0x14c, False),
    (6, 2, 0x236, False),
    (0x1b, 0, 0x23e, False),
    (6, 2, 0x236, True),
):
    requests.clear()
    h.put(ctx + 0x67b2, 0xffff)
    h.put(ctx + 0x208, mode)
    h.put(ctx + 0x9e8, mode_detail)
    h.put(ctx + 0x683c, 0)
    h.put(ctx + 0x6b4c, 0)
    h.put(ctx + 0x6b50, 0)
    assert h.run(0x638da14c, ctx, 0) == (0xffff if fail else 0x267)
    assert requests == [unit]
    assert h.word(ctx + 0x6b4c) == (0 if fail else 0x30000000)
    assert h.word(ctx + 0x6b50) == (0 if fail else 0x120000)
    if not fail:
        assert h.word(ctx + 0x6b48) == unit
        requests.clear()
        assert h.run(0x638da14c, ctx, 0) == 0x267 and requests == []
    print(f'mode {mode:#x}/{mode_detail}: unit {unit:#x}, failure={fail}')
print('Stock allocation records the reply handle, address and span and reuses a populated slot')

# The DFE transfer path calls a different allocator with a fixed unit.
unit = 0x50505
for fail in (True, False):
    requests.clear()
    h.put(ctx + 0x67b2, 0xffff)
    h.put(ctx + 0x6b4c, 0)
    h.put(ctx + 0x6b50, 0)
    assert h.run(0x638d9a94, ctx) == (0xffff if fail else 0x267)
    assert requests == [unit]
    assert h.word(ctx + 0x6b4c) == (0 if fail else 0x30000000)
    assert h.word(ctx + 0x6b50) == (0 if fail else 0x120000)
    if not fail:
        assert h.word(ctx + 0x6b48) == unit
print('DFE fixed-unit allocator selects 0x50505 on success and failure')

# The allocator named AllocMem_Raw_BolLv owns a separate handle.
for mode, unit in ((2, 0x50505), (3, 0x3fb), (4, 0x50505)):
    fail = False
    requests.clear()
    h.put(ctx + 0x681e, 0xffff)
    h.put(ctx + 0x6844, mode)
    h.put(ctx + 0x67b2, 0x269)
    assert h.run(0x638d9a30, ctx) == 0x267
    assert requests == [unit]
    assert h.word(ctx + 0x681e) & 0xffff == 0x267
    assert h.word(ctx + 0x67b2) & 0xffff == 0x269
    assert h.word(ctx + 0x6b6c) == 0x30000000
    assert h.word(ctx + 0x6b70) == 0x120000
    print(f'AllocMem_Raw_BolLv mode {mode}: unit {unit:#x}, separate context +0x681e handle')

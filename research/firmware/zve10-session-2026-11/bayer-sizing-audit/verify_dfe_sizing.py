"""Execute the original DFE encType size switch and its alignment helper."""
import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness

h = Harness()
errors = []
def log_invalid(regs):
    errors.append(regs[1])
    h.ret(0)
h.callbacks[0x6396f8c4] = log_invalid
for enc in range(10):
    for count in (0, 1, 15, 16, 17, 31, 32, 33, 6000, 24_000_000):
        if enc == 0:
            expected = count * 2
        elif enc in (1, 4, 5, 6):
            expected = (count + 1) // 2
        elif enc == 3:
            expected = ((count + 15) & ~15) * 3 // 2
        else:
            expected = count
        assert h.run(0x6379e274, enc, count) == expected, (enc, count, expected)
    assert (enc in errors) == (enc == 8)
    print(f'encType {enc}: counts 16/17/6000 -> {[h.run(0x6379e274, enc, n) for n in (16,17,6000)]}')
print('100 native sizing cases passed')

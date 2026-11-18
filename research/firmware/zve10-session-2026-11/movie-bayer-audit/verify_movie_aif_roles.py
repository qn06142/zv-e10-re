"""Verify how native DFE diagnostics classify the two movie AIF channels."""
import argparse
import json
import sys
from pathlib import Path

from unicorn.arm_const import UC_ARM_REG_SP

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos import cstr
from rtos_harness import Harness

harness = Harness()
harness.u.mem_map(0xfc000000, 0x400000)
for function in (0x63ae1ba4, 0x635df208, 0x635df224, 0x6396f8c4):
    harness.callbacks[function] = lambda _: harness.ret(0)
harness.run(0x6379d44c)

channels = []
for logical, obj, role in ((7, 0x6426adb0, 'R0'), (8, 0x6426ae18, 'R1'),
                           (5, 0x6426aea0, 'W0'), (6, 0x6426af00, 'W1')):
    dma = harness.word(obj + 0xc)
    assert harness.u.mem_read(obj + 8, 1)[0] == logical
    bank = harness.word(dma + 4)
    port = harness.u.mem_read(dma + 8, 1)[0]
    register = bank + 0x210 + port * 0x80
    marker = 0x12345600 + logical
    harness.put(register, marker)
    channels.append(dict(logical=logical, role=role, dma=hex(dma), bank=hex(bank),
                         port=port, register=hex(register), marker=marker))

diagnostics = {}
def observe_log(args):
    sp = harness.u.reg_read(UC_ARM_REG_SP)
    diagnostics[cstr(args[0])] = args[1:] + [harness.word(sp + 4*i) for i in range(5)]
    harness.ret(0)

harness.callbacks[0x6396f8c4] = observe_log
harness.run(0x6379b694)
format_string = 'IMG:CurAddr: R0%x R1%x R2%x R3%x R4%x R5%x W0%x W1%x'
values = diagnostics[format_string]
for channel in channels:
    role = channel['role']
    index = int(role[1]) + (6 if role.startswith('W') else 0)
    assert values[index] == channel['marker'], (role, values)

print(json.dumps(dict(native_diagnostic='0x6379b694', format=format_string,
                      channels=channels, arguments=[hex(value) for value in values],
                      register_values_are_fixtures=True, pixels_emulated=False), indent=2))

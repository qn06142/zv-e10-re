"""Execute the native tag-0x6f BolLv RAW export path through open, dump, and release."""
import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM, STACK, STOP
from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_SP, UC_ARM_REG_PC

h = Harness()
ctx = MEM + 0x10000
h.put(ctx + 0x681e, 0x267)
h.put(ctx + 0x6844, 2)
h.put(ctx + 0x7206, 1)
h.put(ctx + 0x7218, 1)
h.put(ctx + 0x7279, 0x12)
h.put(ctx + 0x290, 1920)
h.put(ctx + 0x294, 1080)
calls = []

def open_frame(a):
    assert a[:3] == [0x267, 0, 0xffffffff]
    calls.append('open')
    h.put(a[3] + 0x10, 0x30000000)
    h.put(a[3] + 0x14, 0x1800000)
    h.ret(0)

def send_frame(a):
    assert a == [0x6f, 0x30000000, 1920 * 1080 * 2, 0x12], a
    calls.append('send')
    h.ret(0)

def release_frame(a):
    assert a[:2] == [0x267, 2]
    calls.append('release')
    h.ret(0)

h.callbacks.update({0x63d893f4: lambda _: h.ret(1), 0x6390878c: lambda a: h.ret(int(a[0] == 0x6f)),
                    0x63d8a42a: open_frame, 0x63908820: send_frame,
                    0x63d8a3fc: release_frame, 0x638f4c80: lambda _: h.u.emu_stop()})
h.u.reg_write(UC_ARM_REG_R4, ctx)
h.u.reg_write(UC_ARM_REG_SP, STACK)
h.u.emu_start(0x638f4c3f, STOP, count=250)
assert h.u.reg_read(UC_ARM_REG_PC) == 0x638f4c80
assert calls == ['open', 'send', 'release']
assert h.word(ctx + 0x681e) & 0xffff == 0xffff
print('Native tag 0x6f opens BolLv handle, exports canvas width * height * 2, releases and clears handle')

# Verify the native allocator gate with the actual selection byte and counters.
from unicorn.arm_const import UC_ARM_REG_R6
got, config = MEM + 0x20000, MEM + 0x30000
h.put(got + 0x4b04, config)
h.put(ctx + 0x848, 8)
gates = []
h.callbacks[0x63d89408] = lambda a: h.ret(int(a[0] == 0x6f))
h.callbacks[0x638d9a30] = lambda a: (gates.append(a[0]), h.ret(0x267))
h.callbacks[0x638f720a] = lambda _: h.u.emu_stop()
for setting, state, frame, expected in (
    (0x13, 1, 1, False), (0x13, 1, 2, True), (0x13, 1, 3, False),
    (0x10, 1, 6, False), (0x10, 1, 7, True),
    (0x00, 0, 2, True), (0x00, 1, 2, False),
    (0x20, 1, 2, False),
):
    gates.clear()
    h.u.mem_write(config + 0x35, bytes([setting]))
    h.u.mem_write(ctx + 0x841, bytes([state]))
    h.put(ctx + 0x844, frame)
    h.u.reg_write(UC_ARM_REG_R4, ctx)
    h.u.reg_write(UC_ARM_REG_R6, got)
    h.u.reg_write(UC_ARM_REG_SP, STACK)
    h.u.emu_start(0x638f71b1, STOP, count=100)
    assert h.u.reg_read(UC_ARM_REG_PC) == 0x638f720a
    assert h.u.mem_read(ctx + 0x7218, 1)[0] == expected
    assert gates == ([ctx] if expected else [])
print('Eight native allocation-gate cases passed, including a chosen frame and the final-frame default')

"""Check the original encoder open_pin_data path with controlled DMM replies."""
import argparse
import struct
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness, MEM

h = Harness()
ctx, msg, out, owner, endpoint = [MEM + 0x1000 * i for i in range(1, 6)]
h.put(ctx, owner)
h.put(owner, endpoint)
h.put(msg + 0x28, 0x12345678)
h.put(msg + 0x30, 0xabcdef)
handle = 0x263
h.u.mem_write(msg + 0x2c, struct.pack('<H', handle))
address = 0x22220002
mapped = 0x40200000
calls = []


def query(a):
    assert a[0] == endpoint
    h.ret(0x42)


def dmm(a):
    data = bytes(h.u.mem_read(a[0], 0x20))
    assert struct.unpack_from('<HH', data) == (5, handle)
    assert struct.unpack_from('<H', data, 0x14)[0] == 0x1111
    assert a[2] == 0x42
    calls.append('open')
    h.put(a[1] + 8, 1)
    h.put(a[1] + 0x10, address)
    h.put(a[1] + 0x14, span)
    h.ret(0)


def mapping(a):
    assert a[:3] == [address, 0x10, 2]
    calls.append('map')
    h.ret(mapped)


def attach(a):
    assert a[0] == mapped + 0xabcdef
    record = bytes(h.u.mem_read(out + 0x28, 20))
    assert struct.unpack('<IHHIII', record) == (0x12345678, handle, 0, mapped, 0xabcdef, span)
    assert a[1] == span
    calls.append('attach')
    h.ret(0)


h.callbacks.update({0x63c609ec: lambda a: h.ret(0), 0x63c609c2: query,
                    0x6364dac0: dmm, 0x63c48e0c: mapping, 0x63ddf882: attach})
for span in (0x1000, 0x3f4800, 0x7e9000):
    calls.clear()
    assert h.run(0x63691dec, ctx, msg, out) == 0
    assert calls == ['open', 'map', 'attach']
    print(f'Open -> map -> attach, reply span {span:#x} forwarded unchanged')

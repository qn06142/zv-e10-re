"""Trace original RDC format methods and their shared register accesses."""
import argparse
import json
import struct
import sys
from pathlib import Path

from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_READ
from unicorn.arm_const import UC_ARM_REG_PC

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
object_base = 0x6426a000
object_words = list(struct.iter_unpack('<I', harness.u.mem_read(object_base, 0x2000)))
registers = (0xfc0a0500, 0xfc0a0504, 0xfc0a0560, 0xfc0a0564)
accesses = []


def observe(cpu, access, address, size, value, data):
    if address in registers:
        accesses.append((access, address, size, value, cpu.reg_read(UC_ARM_REG_PC)))


harness.u.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, observe,
                   begin=registers[0], end=registers[-1]+3)
rows = []
for role, vtable in (('R2', 0x64588ac0), ('R3', 0x64588af8),
                     ('W0', 0x64588b30), ('W1', 0x64588ba0)):
    index = object_words.index((vtable,))
    obj = object_base + index*4
    rtti = cstr(harness.word(harness.word(vtable-4)+4))
    assert rtti == f'N6Camera7DFECore5Rdc{role}E'
    method = harness.word(vtable + 0x2c) & ~1
    for encoding in range(10):
        traces = []
        for seed in (0, 0xa55ac33c):
            harness.u.mem_write(0xfc0a8000, bytes(0x1000))
            for address in registers:
                harness.put(address, seed)
            accesses.clear()
            harness.run(method, obj, encoding)
            assert all(access != UC_MEM_READ for access, *_ in accesses)
            traces.append(list(accesses))
        assert traces[0] == traces[1], (role, encoding, traces)
        owned_mask = {'R2': 0x3, 'R3': 0x18, 'W0': 0x1c0, 'W1': 0xe00}[role]
        commands = [(address, value) for _, address, _, value, _ in traces[0]]
        assert len(commands) in (2, 4)
        clear_mask = commands[0][1]
        assert commands[:2] == [(0xfc0a0504, clear_mask), (0xfc0a0564, clear_mask)]
        set_mask = 0
        if len(commands) == 4:
            set_mask = commands[2][1]
            assert commands[2:] == [(0xfc0a0560, set_mask), (0xfc0a0500, set_mask)]
        assert (clear_mask | set_mask) == owned_mask and (clear_mask & set_mask) == 0
        writes = [[hex(pc), hex(address), size, hex(value)] for _, address, size, value, pc in traces[0]]
        rows.append(dict(role=role, object=hex(obj), method=hex(method), encoding=encoding,
                         shared_writes=writes, owned_mask=hex(owned_mask)))

print(json.dumps(dict(cases=len(rows), seeds=2, rows=rows,
                      shared_register_reads=0, mmio_is_ram=True), indent=2))

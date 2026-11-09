"""Compare native fast-mode setup with and without a hypothetical W0 tap."""
import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_PC

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repo', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.repo / 'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos import cstr, word
from rtos_harness import Harness, MEM

native_params = {
    row['sensor_mode']: bytes.fromhex(row['drv_param_hex'])
    for row in json.loads(Path(__file__).with_name('movie-native-param-results.json').read_text())['rows']
}


def setup(sensor, drive, width, encoding, enable_w0, include_w0_in_default_flags=False):
    harness = Harness()
    harness.u.mem_map(0xfc000000, 0x400000)
    harness.u.reg_write(UC_ARM_REG_C1_C0_2, 0xf00000)
    harness.u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    for function in (0x63ae1ba4, 0x635df208, 0x635df224, 0x6396f8c4):
        harness.callbacks[function] = lambda _: harness.ret(0)
    for constructor in (0x6379d44c, 0x6379bf60, 0x637a6d90):
        harness.run(constructor)
    table = word(0x64638120 + 0x4490)
    resource = harness.run(0x637a6d78, drive, MEM)
    assert resource == 0x39
    operation = next(obj for i in range(27) if (obj := harness.word(table+4*i))
                     and harness.word(obj+4) == resource)
    harness.callbacks[0x6379be60] = lambda _: harness.ret(operation)
    harness.run(0x63d26a42, word(0x64638120+0x49e4), 72, 0, 0, 1)
    owner = harness.run(0x637a6e88, 0, drive, 0)
    runtime = harness.run(0x637a6c84, drive, 0)
    assert harness.word(owner + 0x5c) == 0
    if enable_w0:
        harness.put(operation + 0x28, harness.word(operation + 0x28) | (1 << 21))
        if include_w0_in_default_flags:
            harness.put(operation + 0x20, harness.word(operation + 0x20) | (1 << 21))
        harness.put(owner + 0x5c, MEM+0x3000)
        harness.u.mem_write(MEM+0x3000, struct.pack('<6H', 2016, 0, 0, width, 1122, 0))
    acquire_result = harness.run(0x6379aee4, operation, MEM+0x3500)
    assert acquire_result == 0
    token = harness.word(MEM+0x3500)

    writes, logs, w0_calls = [], [], []

    def record_write(cpu, access, address, size, value, data):
        writes.append((cpu.reg_read(UC_ARM_REG_PC), address, size, value))

    def observe_w0(registers):
        obj, request, params = registers[:3]
        assert obj == 0x6426aea0 and harness.word(request+4) == owner
        w0_calls.append(harness.word(params+0xc))

    harness.u.hook_add(UC_HOOK_MEM_WRITE, record_write, begin=0xfc000000, end=0xfc3fffff)
    harness.callbacks[0x6379e2b8] = observe_w0
    harness.callbacks[0x6396f8c4] = lambda registers: (logs.append(cstr(registers[0])), harness.ret(0))
    harness.u.mem_write(MEM, struct.pack('<4I', drive, owner, runtime, 0))
    assert harness.run(0x6379a510, operation, token, MEM) == 0
    harness.u.mem_write(MEM+0x1000, native_params[sensor])
    request = MEM+0x2000
    for offset, value in ((4, drive), (8, 0x20000000), (0x10, encoding),
                          (0x14, 1), (0x18, 0x1000000)):
        harness.put(request + offset, value)
    assert harness.run(0x6379cb68, token, MEM+0x1000, request, 1, 0) == 0
    assert w0_calls == ([encoding] if enable_w0 else []), w0_calls
    setup_writes = list(writes)
    writes.clear()
    start_calls = []
    irq_selectors = []
    harness.callbacks[0x63d23398] = lambda registers: start_calls.append(hex(registers[0]))
    harness.callbacks[0x6379eb38] = lambda registers: irq_selectors.append(registers[0])
    assert harness.run(0x6379ab48, operation, token, MEM+0x3800) == 0
    assert start_calls == (['0x6426aea0'] if enable_w0 else []), start_calls
    assert len(irq_selectors) == 1
    control = harness.word(0xfc0a9200)
    assert bool(control & 1) == enable_w0, hex(control)
    start = dict(w0_start_objects=start_calls, irq_selector=irq_selectors[0],
                 w0_control=hex(control), writes=encode_writes(writes))
    if enable_w0:
        # Hold W0 busy while supplying only the registered stock IRQ bits.
        callbacks = []
        callback = MEM+0x3800
        harness.callbacks[callback] = lambda _: (callbacks.append(harness.word(0xfc0a9204)), harness.ret(0))
        harness.put(0xfc0a9204, 0x80000000)
        harness.put(0xfc0a0014, 0x80000)
        harness.put(0xfc0a002c, 0x1000)
        harness.run(0x6379ef08)
        assert callbacks == [0x80000000], callbacks
        start['injected_irq_callback_while_w0_busy'] = True
        contender = next(obj for i in range(27) if (obj := harness.word(table+4*i))
                         and harness.word(obj+4) == 0x2f)
        assert harness.run(0x6379aee4, contender, MEM+0x3504) == 2
        release_result = harness.run(0x6379ad4c, operation)
        busy_after_release = bool(harness.word(0xfc0a9204) & 0x80000000)
        assert release_result == 0 and busy_after_release
        assert harness.word(operation) == 0x00ffffff
        active_mask = harness.word(word(0x64638120+0x9000))
        assert active_mask == (0 if include_w0_in_default_flags else 1 << 21), hex(active_mask)
        contender_result = harness.run(0x6379aee4, contender, MEM+0x3504)
        assert contender_result == (0 if include_w0_in_default_flags else 2)
        start['teardown'] = dict(release_result=release_result,
                                 w0_busy_after_release=busy_after_release,
                                 conflicting_resource='0x2f',
                                 contender_rejected_before_release=True,
                                 active_mask_after_release=hex(active_mask),
                                 contender_acquired_after_release=contender_result == 0)
    return setup_writes, logs, [harness.word(0xfc0a9220 + i*4) for i in range(4)], start


def encode_writes(writes):
    return [[hex(pc), hex(address), size, hex(value)] for pc, address, size, value in writes]


rows = []
for sensor, drive in (('0x5', 0x17), ('0x7', 0x18)):
    for width, encoding in ((1996, 0), (1996, 3), (2000, 3)):
        baseline, baseline_logs, _, baseline_start = setup(sensor, drive, width, encoding, False)
        enabled, enabled_logs, descriptor, enabled_start = setup(sensor, drive, width, encoding, True)
        assert baseline_start['irq_selector'] == enabled_start['irq_selector']
        added = list((Counter(enabled)-Counter(baseline)).elements())
        removed = list((Counter(baseline)-Counter(enabled)).elements())
        expected_line = width*2 if encoding == 0 else 24*((width+15)//16)
        assert descriptor[:2] == [0x20000000, expected_line], descriptor
        assert not removed, encode_writes(removed)
        shared = {0xfc0a0500, 0xfc0a0504, 0xfc0a0560, 0xfc0a0564}
        def touches_w0_or_shared(write):
            address = write[1]
            return 0xfc0a8000 <= address < 0xfc0aa000 or address in shared
        assert all(map(touches_w0_or_shared, added)), encode_writes(added)
        assert [write for write in baseline if not touches_w0_or_shared(write)] == [
            write for write in enabled if not touches_w0_or_shared(write)
        ]
        rows.append(dict(sensor=sensor, drive=hex(drive), width_fixture=width, encoding=encoding,
                         descriptor=[hex(value) for value in descriptor],
                         added_writes=encode_writes(added), removed_writes=encode_writes(removed),
                         baseline_logs=baseline_logs, enabled_logs=enabled_logs,
                         baseline_start=baseline_start, enabled_start=enabled_start))

_, _, _, default_flags_case = setup('0x5', 0x17, 1996, 0, True, True)
print(json.dumps(dict(paired_cases=len(rows), rows=rows, mmio_is_ram=True,
                      w0_in_default_flags_teardown=default_flags_case['teardown'],
                      dma_executed=False, w0_geometry_is_fixture=True), indent=2))

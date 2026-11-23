"""Trace the active shooting IRQs in the identified ZV-E10 firmware, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_SP

IMAGE_BASE = 0x635c6000
BODY_SHA256 = "98f05bebd113cb5b4911d71384e5ae7cec21dd4494b0f0569bb2f1b2b3231c6b"
IRQ83_STATUS = 0xf3950610
IRQ84_BASE = 0xf3c30000
SCRATCH = 0x20000000
RETURN = SCRATCH + 0x800
IRQ84_SLOTS_PA = 0x04263d24


def read_slot_table(path):
    """Read eight subscriber records from the recorder's BusyBox hexdump."""
    buffer = bytearray()
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) == 1:
            if len(buffer) != 256 or int(fields[0], 16) != IRQ84_SLOTS_PA + 256:
                raise ValueError("Incomplete IRQ 84 table hexdump")
            continue
        if (len(fields) != 9 or int(fields[0], 16) != IRQ84_SLOTS_PA + len(buffer)
                or any(len(field) != 4 for field in fields[1:])):
            raise ValueError("Unexpected IRQ 84 table hexdump row")
        buffer.extend(struct.pack("<8H", *(int(value, 16) for value in fields[1:])))
    if len(buffer) != 256:
        raise ValueError("Expected eight complete IRQ 84 records")
    return bytes(buffer)


def decode_slots(path):
    result = []
    for index, row in enumerate(struct.iter_unpack("<8I", read_slot_table(path))):
        slot, source, selector, callback, adjustment, context = row[:6]
        if slot != index:
            raise ValueError(f"IRQ 84 slot {index} has unexpected index {slot}")
        if source != 0xff:
            result.append({"slot": index, "source": hex(source), "selector": hex(selector),
                           "callback_word": hex(callback), "adjustment": hex(adjustment),
                           "virtual_callback": bool(adjustment & 1), "context_word": hex(context)})
    return result


def audit(path, captures=()):
    image = path.read_bytes()
    if hashlib.sha256(image).hexdigest() != BODY_SHA256:
        raise ValueError("Unexpected body firmware identity")
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(IMAGE_BASE, (len(image) + 4095) & ~4095)
    cpu.mem_write(IMAGE_BASE, image)
    for page in (SCRATCH, IRQ83_STATUS & ~4095, IRQ84_BASE):
        cpu.mem_map(page, 4096)

    def put(address, *values):
        cpu.mem_write(address, struct.pack(f"<{len(values)}I", *values))

    def word(address):
        return struct.unpack("<I", cpu.mem_read(address, 4))[0]

    def run(entry):
        cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0xff0)
        cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
        cpu.emu_start(entry | 1, RETURN, count=2000)
        assert cpu.reg_read(UC_ARM_REG_PC) == RETURN

    writes, callbacks = [], []
    cpu.hook_add(UC_HOOK_MEM_WRITE, lambda _u, _k, a, s, v, _c: writes.append((a, s, v)),
                 begin=0xf0000000, end=0xffffffff)
    assert word(0x64592740) == 0x6376dbed and word(0x64592748) == 83
    assert word(0x64592750) == 0x6377fd41 and word(0x64592758) == 84
    slots = 0x6377fd5e + word(0x6377fd6c)
    assert 0x64000000 <= slots < 0x64600000
    for index in range(8):
        callback = SCRATCH + index * 4
        cpu.mem_write(callback, b"\x70\x47")  # bx lr
        cpu.hook_add(UC_HOOK_CODE, lambda _u, address, _s, _c: callbacks.append((address - SCRATCH) // 4),
                     begin=callback, end=callback)
        put(slots + index * 32, index, 0, 0, callback | 1, 0, 1)

    for pending in (0, 1, 0x80, 0xa5, 0xff, 0x101):
        writes.clear()
        callbacks.clear()
        put(IRQ84_BASE + 4, pending)
        for index in range(8):
            put(IRQ84_BASE + 0x20 + index * 4, 0x12345600 + index)
        run(0x6377fd40)
        assert writes == [(IRQ84_BASE + 8, 4, pending)]
        assert callbacks == [i for i in range(8) if pending & (1 << i)]

    # Observe the real callbacks using two direct fixture consumers.
    trace_flag = 0x6376dbfa + word(0x6376dc4c)
    cpu.mem_write(trace_flag, b"\0")
    irq83_flags = []
    for index, (pc, literal) in enumerate(((0x6376dc30, 0x6376dc58), (0x6376dc44, 0x6376dc5c))):
        callback = SCRATCH + 0x40 + index * 4
        cpu.mem_write(callback, b"\x70\x47")
        cpu.hook_add(UC_HOOK_CODE, lambda uc, _a, _s, _c: irq83_flags.append(uc.reg_read(UC_ARM_REG_R0)),
                     begin=callback, end=callback)
        put(pc + word(literal) + 4, callback | 1)
    for status in (0, 1, 0x0f000000, 0x80000001):
        writes.clear()
        irq83_flags.clear()
        put(IRQ83_STATUS, status)
        run(0x6376dbec)
        assert writes == [(IRQ83_STATUS, 4, status)]
        assert irq83_flags == [int(bool(status & 0x0f000000))] * 2
    print("Verified IRQ 83 status writeback and IRQ 84 eight-slot dispatch on the captured firmware")

    captured_calls = []
    entry_points = (0x6394ed6c, 0x63950d78, 0x6395151c, 0x638d0e80)

    def record_leaf(uc, address, _size, _context):
        captured_calls.append((address, uc.reg_read(UC_ARM_REG_R0)))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    if captures:
        for entry in entry_points:
            cpu.hook_add(UC_HOOK_CODE, record_leaf, begin=entry, end=entry)
    for capture in captures:
        records = decode_slots(capture)
        identity = [(r["slot"], r["source"], r["selector"], r["callback_word"],
                     r["adjustment"], r["context_word"]) for r in records]
        assert identity == [(slot, hex(source), "0x1", "0x63d63829", "0x0", hex(entry | 1))
                            for slot, source, entry in zip(range(4, 8), (0x17, 0x1e, 0x1d, 0x1c), entry_points)]
        cpu.mem_write(slots, read_slot_table(capture))
        for pending in (0x10, 0x20, 0x40, 0x80, 0xf0):
            captured_calls.clear()
            writes.clear()
            put(IRQ84_BASE + 4, pending)
            run(0x6377fd40)
            assert captured_calls == [(entry, 0x12345600 + slot) for slot, entry in zip(range(4, 8), entry_points)
                                      if pending & (1 << slot)]
            assert writes == [(IRQ84_BASE + 8, 4, pending)]
        print(json.dumps({"capture": capture.name, "subscribers": records, "dispatch_cases_passed": 5}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("--slots", type=Path, nargs="+")
    args = parser.parse_args()
    audit(args.firmware, args.slots or [])

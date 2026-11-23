"""Verify IMX284 mode and readout dispatch, register writes and nearby IRQ handlers."""
import argparse
import hashlib
from pathlib import Path
import struct

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MODE_THUMB, Uc
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1,
    UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
    UC_ARM_REG_R7, UC_ARM_REG_SP,
)

IMAGE_BASE = 0x635C6000
IMAGE_SHA256 = "bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa"
VTABLE = 0x64588E88
OBJECT = 0x20000000
PARAMS = 0x20001000
RETURN = 0x20002000
STACK = 0x20003FF0
MMIO_BASE = 0xFC020000
MMIO_SIZE = 0xE0000


def audit(path):
    image = path.read_bytes()
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError("Unexpected av-cam.bin identity")
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(IMAGE_BASE, (len(image) + 0xFFF) & ~0xFFF)
    cpu.mem_write(IMAGE_BASE, image)
    cpu.mem_map(OBJECT, 0x4000)
    cpu.mem_map(MMIO_BASE, MMIO_SIZE)

    def word(address):
        return struct.unpack("<I", cpu.mem_read(address, 4))[0]

    def put_word(address, value):
        cpu.mem_write(address, struct.pack("<I", value))

    def run(entry, arg0, arg1=0, end=RETURN, *, stack=STACK):
        cpu.reg_write(UC_ARM_REG_SP, stack)
        cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
        cpu.reg_write(UC_ARM_REG_R0, arg0)
        cpu.reg_write(UC_ARM_REG_R1, arg1)
        cpu.emu_start(entry | 1, end, count=500)
        assert cpu.reg_read(UC_ARM_REG_PC) == end

    assert word(0x6464263C) + 8 == VTABLE
    assert word(VTABLE - 4) == 0x645BC9F8
    assert word(0x645BC9FC) == 0x63F6D036
    type_name = b"N6Camera6Imager6IMX28419C_ImagerCtrl_IMX284E\0"
    assert cpu.mem_read(0x63F6D036, len(type_name)) == type_name
    assert word(VTABLE + 0x28) == 0x637ACD99
    assert word(VTABLE + 0x44) == 0x637AD06D
    assert word(VTABLE + 0x48) == 0x637AB589
    assert word(VTABLE + 0x74) == 0x637AB559

    put_word(0x6426B7B8, OBJECT)
    put_word(OBJECT, VTABLE)
    put_word(PARAMS, 0x11)
    run(0x6390B8FC, PARAMS, end=0x637ACD98)
    assert cpu.reg_read(UC_ARM_REG_R0) == OBJECT
    assert cpu.reg_read(UC_ARM_REG_R1) == PARAMS
    for selector, handler in ((1, 0x637AD06C), (0, 0x637AB588)):
        run(0x63D2A758, 0x6426B7B8, selector, end=handler)
        assert cpu.reg_read(UC_ARM_REG_R0) == OBJECT

    writes = []

    def record(_cpu, _access, address, size, value, _context):
        assert size == 4
        writes.append((address, value))

    cpu.hook_add(UC_HOOK_MEM_WRITE, record, begin=MMIO_BASE, end=MMIO_BASE + MMIO_SIZE - 1)

    for fill in (0, 0xA5A5A5A5, 0xFFFFFFFF):
        cpu.mem_write(MMIO_BASE, struct.pack("<I", fill) * (MMIO_SIZE // 4))
        writes.clear()
        run(0x63D2B6EE, OBJECT)
        assert writes == [
            (0xFC02A01C, fill | 0xFFF),
            (0xFC0F0050, 0),
            (0xFC0F0150, 0),
            (0xFC0F0000, fill & 0xFFFFFF00),
            (0xFC0F0000, fill & 0xFFFF0000),
            (0xFC0F0000, fill & 0xFFF00000),
            (0xFC0F0000, fill & 0xFCF00000),
            (0xFC0F0004, 0),
            (0xFC02A04C, fill & ~0xF),
            (0xFC02A048, fill & ~1),
            (0xFC02A05C, fill & ~0xF),
            (0xFC02A058, fill & ~1),
            (0xFC02A040, fill | 1),
        ]
    print("Verified IMX284 mode/readout dispatch and 13 ordered MMIO writes across three modeled initial states.")

    # The camera prefix runs unchanged. Supply predictable sequence and trace
    # helpers in place of native scheduler and tracing services.
    for address, code in (
        (0x63D90074, b"\x01\x20\x70\x47"),  # movs r0, #1; bx lr
        (0x63D31D5E, b"\x2a\x20\x70\x47"),  # movs r0, #42; bx lr
        (0x639D6D2C, b"\x70\x47"),
        (0x635DF9F0, b"\x70\x47"),
    ):
        cpu.mem_write(address, code)

    context = 0x643D85EC  # Index 0 returned by the native context selector.
    config = OBJECT + 0x1800
    imager = OBJECT + 0x2200
    put_word(0x6426B7B8, imager)
    put_word(imager, VTABLE)
    put_word(0x6463DF70, config)
    put_word(0x6463CC24, config)
    put_word(0x645CC364, 5)
    put_word(context + 0x2C, PARAMS)
    put_word(context + 0x38, PARAMS + 0x60)
    cpu.mem_write(PARAMS + 0x14, struct.pack("<6H", 91, 92, 93, 94, 95, 96))
    cpu.mem_write(PARAMS + 0x70, struct.pack("<4IH", 17, 18, 19, 20, 21))

    markers = []

    def trace(uc, _address, _size, _data):
        markers.append(uc.reg_read(UC_ARM_REG_R0))

    cpu.hook_add(UC_HOOK_CODE, trace, begin=0x635DF9F0, end=0x635DF9F0)
    for override in (False, True):
        cpu.mem_write(config + 0x23, b"\x08")
        cpu.mem_write(config + 0x1D, bytes([2 if override else 0]))
        run(0x6392FB08, OBJECT, end=0x637ACA24)
        assert markers.pop() == 0x63F8A159  # SetImgRd
        assert cpu.reg_read(UC_ARM_REG_R0) == imager
        assert cpu.reg_read(UC_ARM_REG_R2) == cpu.reg_read(UC_ARM_REG_R3) == 1
        descriptor = cpu.reg_read(UC_ARM_REG_R1)
        assert struct.unpack("<6H", cpu.mem_read(descriptor, 12)) == (
            42, 0xF00 if override else 92, 0 if override else 93, 94, 95, 96,
        )
        assert cpu.mem_read(descriptor + 0xC, 2) == b"\x15\0"
        assert struct.unpack("<4I", cpu.mem_read(descriptor + 0x10, 16)) == (17, 18, 20, 19)
    print("Verified SetImgRd marker precedes dispatch and both descriptor variants reach IMX284 slot +0x3c.")

    # Replay the still exposure result stores, the builder's copy, and the
    # capture-context copy. The calculator result on the stack is a fixture.
    exposure_state = word(0x6463A988)
    assert exposure_state == 0x6448139C
    shot_stack = OBJECT + 0x2800
    cpu.mem_write(exposure_state + 0x184, bytes(0x12))
    calculated = struct.pack("<4H2B2H", 0x0123, 0x0456, 0x0789, 0x0ABC,
                             0x11, 0x22, 0x0345, 0x0678)
    cpu.mem_write(shot_stack + 0xD0, calculated)
    cpu.reg_write(UC_ARM_REG_R6, exposure_state)
    run(0x63C04AB4, 0, end=0x63C04AF8, stack=shot_stack)
    expected = bytes.fromhex("000023015604110078062200")
    assert cpu.mem_read(exposure_state + 0x184, len(expected)) == expected
    assert cpu.mem_read(exposure_state + 0x190, 6) == struct.pack("<3H", 0x0ABC, 0x0789, 0x0345)

    shot_record = shot_stack + 0x198
    cpu.reg_write(UC_ARM_REG_R7, shot_record)
    cpu.reg_write(UC_ARM_REG_R5, exposure_state)
    run(0x63C04C62, 0, end=0x63C04C70)
    assert cpu.mem_read(shot_record + 0x0C, len(expected)) == expected
    cpu.reg_write(UC_ARM_REG_R4, OBJECT)
    run(0x638FF75E, 0, end=0x638FF76A, stack=shot_stack)
    assert cpu.mem_read(OBJECT + 0x750, len(expected)) == expected
    print("Verified the still exposure result stores and both native copies into SetImgRd's descriptor.")

    # The still task calls this virtual method after sensor readout and setup.
    # Supply event-wait success but execute both native wait paths.
    waits = []

    def capture_wait(uc, _address, _size, _context):
        args = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)
        waits.append(tuple(uc.reg_read(reg) for reg in args) + (word(uc.reg_read(UC_ARM_REG_SP)),))
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hook = cpu.hook_add(UC_HOOK_CODE, capture_wait, begin=0x635DF1CC, end=0x635DF1CC)
    sequence_state = word(0x6426B7B8) + 0x28C
    put_word(sequence_state, 0x20)
    put_word(sequence_state + 4, 0x40)
    for mode in (0, 2):
        put_word(sequence_state + 0x11C, mode)
        waits.clear()
        run(0x63D2A77A, 0x6426B7B8)
        expected_waits = ([(0x18, 0x60, 0, 2)] if mode == 2 else []) + [(0x18, 0x100, 1, 10)]
        assert waits == expected_waits, (mode, waits)
    cpu.hook_del(hook)
    print("Verified the still task's post-readout virtual dispatch and native event-wait arguments.")

    assert struct.unpack("<8I", cpu.mem_read(0x64592720, 32)) == (
        0x637968B1, 2, 74, 0, 0x6376DB79, 2, 75, 0,
    )
    callbacks = []

    def callback(uc, address, _size, _data):
        callbacks.append((address, uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))

    first = OBJECT + 0x3800
    second = first + 4
    for address in (first, second):
        cpu.mem_write(address, b"\x70\x47")
        cpu.hook_add(UC_HOOK_CODE, callback, begin=address, end=address)

    for base in (0xF3040000, 0xF3850000):
        cpu.mem_map(base, 0x1000)
        cpu.hook_add(UC_HOOK_MEM_WRITE, record, begin=base, end=base + 0xFFF)

    put_word(0x6426A3EC, first | 1)
    for status, mode_flag, events in ((2, 0, [2]), (2, 1, [4]), (4, 0, [4]), (6, 0, [2, 4])):
        callbacks.clear()
        writes.clear()
        put_word(0xF3040004, 0xABCD0000 | status)
        cpu.mem_write(0x6426A3E4, bytes([mode_flag]))
        run(0x637968B0, 0)
        assert writes == [(0xF3040004, status)]
        assert [(address, value) for address, value, _ in callbacks] == [(first, event) for event in events]

    put_word(0x6425BD64, first | 1)
    put_word(0x6425BD6C, second | 1)
    cpu.mem_write(0x6376DB86 + 0xD2CC20, b"\0")
    for status, flag in ((0, 0), (0x80000001, 0), (0x05000001, 1)):
        callbacks.clear()
        writes.clear()
        put_word(0xF3850610, status)
        run(0x6376DB78, 0)
        assert writes == [(0xF3850610, status)]
        assert callbacks[0] == (first, flag, 0)
        assert callbacks[1][:2] == (second, flag)
        assert len(callbacks) == 2
    print("Verified IRQ 74/75 table entries, acknowledge writes and callback arguments in seven modeled cases.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    audit(parser.parse_args().image)

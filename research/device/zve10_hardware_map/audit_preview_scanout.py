"""Verify the native preview address handoff, VPH staging, and video AIF arm paths."""
import argparse
import hashlib
from pathlib import Path
import struct

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MODE_THUMB, Uc
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4,
    UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R9, UC_ARM_REG_R11,
    UC_ARM_REG_SP,
)

from audit_imager_control import IMAGE_BASE, IMAGE_SHA256

SCRATCH = 0x20000000
STACK = SCRATCH + 0x1000
RETURN = SCRATCH + 0x1600
SHADOW = 0x64418D6C
AIF_BANKS = (0xF3441200, 0xF3441280, 0xF3441500, 0xF3441580)


def audit(path):
    image = path.read_bytes()
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError("Unexpected av-cam.bin identity")
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(IMAGE_BASE, (len(image) + 0xFFF) & ~0xFFF)
    cpu.mem_write(IMAGE_BASE, image)
    cpu.mem_map(SCRATCH, 0x2000)
    cpu.mem_map(0xF3441000, 0x1000)

    def put_word(address, value):
        cpu.mem_write(address, struct.pack("<I", value))

    def run(entry, stop=RETURN):
        cpu.reg_write(UC_ARM_REG_SP, STACK)
        cpu.reg_write(UC_ARM_REG_LR, RETURN | 1)
        cpu.emu_start(entry | 1, stop, count=1000)
        assert cpu.reg_read(UC_ARM_REG_PC) == stop

    vtable, = struct.unpack("<I", cpu.mem_read(0x64638BF0, 4))
    assert vtable + 8 == 0x645817F0
    assert cpu.mem_read(vtable + 8, 4) == struct.pack("<I", 0x63CE694F)

    # Leave the actual descriptor lines intact. Only supply responses for the
    # external memory manager and the sibling matching/diagnostic helpers.
    open_address = 0x6371F540
    close_address = 0x6371F4A0
    for address in (open_address, close_address, 0x63733864, 0x63CF547C):
        cpu.mem_write(address, b"\x00\x20\x70\x47")  # movs r0,#0; bx lr

    pixel = (0x295, 0x1234)
    opened = []
    fail_open = False

    def open_handle(uc, _address, _size, _context):
        request = uc.reg_read(UC_ARM_REG_R0)
        assert uc.mem_read(request, 6) == struct.pack("<IH", *pixel)
        opened.append("open")
        put_word(request + 0xC, 0x23456000)
        uc.reg_write(UC_ARM_REG_R0, int(fail_open))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def close_handle(uc, _address, _size, _context):
        request = uc.reg_read(UC_ARM_REG_R0)
        assert uc.mem_read(request, 6) == struct.pack("<IH", *pixel)
        opened.append("close")

    cpu.hook_add(UC_HOOK_CODE, open_handle, begin=open_address, end=open_address)
    cpu.hook_add(UC_HOOK_CODE, close_handle, begin=close_address, end=close_address)
    category, command = SCRATCH + 0x100, SCRATCH + 0x200
    cpu.mem_write(category + 4, struct.pack("<IH", *pixel))
    for fail_open in (False, True):
        opened.clear()
        put_word(command, 0)
        for reg, value in ((UC_ARM_REG_R4, 0), (UC_ARM_REG_R5, category),
                           (UC_ARM_REG_R6, command), (UC_ARM_REG_R7, SCRATCH)):
            cpu.reg_write(reg, value)
        run(0x63733E3E, 0x63733E50 if fail_open else 0x63733E94)
        assert opened == (["open"] if fail_open else ["open", "close"])
        assert cpu.mem_read(command, 4) == struct.pack("<I", 0 if fail_open else 0x23456000)

    for address in (0x63A76798, 0x63A66824, 0x63A62624):
        cpu.mem_write(address, b"\x00\x20\x70\x47")
    descriptor = struct.pack("<I", 0x23456000) + bytes(range(0x8C))
    cpu.mem_write(command, descriptor)
    cpu.reg_write(UC_ARM_REG_R0, command)
    run(0x63A5C2E4)
    assert cpu.mem_read(SHADOW + 4, 1) == b"\x01"
    assert cpu.mem_read(SHADOW + 8, 0x90) == descriptor

    envelope = 0x6441AE40
    destinations = SCRATCH + 0x300
    for pending in (0, 1):
        for selector in range(4):
            packet = bytearray(0xE4)
            packet[4] = pending
            packet[8:0x98] = descriptor
            struct.pack_into("<I", packet, 0x54, selector)
            cpu.mem_write(envelope, bytes(packet))
            cpu.mem_write(destinations, bytes(0xC00))
            cpu.reg_write(UC_ARM_REG_R0, destinations)
            run(0x63A5EC40)
            for route, flag, data in ((0, 0x180, 0x184), (1, 0xEC, 0xF0)):
                routed = pending and selector in (route, 2)
                assert cpu.mem_read(destinations + flag, 1) == bytes([int(routed)])
                assert cpu.mem_read(destinations + data, 0x90) == (
                    packet[8:0x98] if routed else bytes(0x90)
                )

    writes = []

    def write(_cpu, _access, address, size, value, _context):
        assert size == 4
        writes.append((address, value))

    cpu.hook_add(UC_HOOK_MEM_WRITE, write, begin=0xF3441000, end=0xF3441FFF)
    cpu.mem_map(0xF3440000, 0x1000)
    result = SCRATCH + 0x280
    for pixel_mode, row_offset, column_offset, row_stride, multiplier in (
        (1, 0, 0, 640, 1), (1, 3, 79, 672, 1),
        (2, 0, 63, 640, 2), (2, 9, 137, 704, 2),
    ):
        base = 0x23456000
        span, rows = 300, 480
        source = struct.pack("<II6HB3xI", pixel_mode, base, row_stride, 0,
                             column_offset, row_offset, span, rows, 1, 1)
        cpu.mem_write(command, source)
        cpu.reg_write(UC_ARM_REG_R0, command)
        cpu.reg_write(UC_ARM_REG_R1, result)
        run(0x63DCB590)
        linear = column_offset + row_offset * row_stride
        leading = linear % 64
        adjusted = base + (linear - leading) * multiplier
        fetch_samples = (leading + span + 63) & ~63
        fetch_bytes = fetch_samples * multiplier
        line_gap = (row_stride - fetch_samples) * multiplier
        assert cpu.mem_read(result, 8) == struct.pack("<II", leading, leading * multiplier)
        assert cpu.mem_read(result + 0x10, 4) == struct.pack("<I", adjusted)
        geometry = struct.unpack("<4I", cpu.mem_read(result + 0x14, 16))
        assert geometry == (fetch_samples, fetch_bytes, line_gap, rows), geometry

        for channel, bank in zip((0x39, 0x3A, 0x3E, 0x3F), AIF_BANKS):
            for enabled in (False, True):
                put_word(bank, int(enabled))
                put_word(bank + 0x1C, 0)
                writes.clear()
                cpu.reg_write(UC_ARM_REG_R0, result)
                cpu.reg_write(UC_ARM_REG_R1, channel)
                run(0x63DCB3C8)
                assert [(addr, value) for addr, value in writes if addr in (bank + 0x20, bank + 0x24)] == (
                    [] if enabled else [(bank + 0x24, fetch_bytes), (bank + 0x20, adjusted)]
                )
            writes.clear()
            cpu.reg_write(UC_ARM_REG_R0, result)
            cpu.reg_write(UC_ARM_REG_R1, channel)
            run(0x63DCB3F4)
            assert [(addr, value) for addr, value in writes if addr in (bank + 0x28, bank + 0x2C)] == [
                (bank + 0x28, line_gap), (bank + 0x2C, rows - 1),
            ]

    # Start at the two native secondary-descriptor builders after layout selection.
    primary_source = SCRATCH + 0x500
    secondary_source = SCRATCH + 0x540
    secondary_result = SCRATCH + 0x580
    for entry, stop, overlap, width_shift in (
        (0x635D3EE0, 0x635D3F12, 10, 1),
        (0x635D40C0, 0x635D40EA, 14, 1),
    ):
        for command_x, command_width in ((24, 640), (86, 721)):
            base, row_offset, row_stride = 0x23800000, 3, 1024
            half_width = command_width >> width_shift
            cpu.mem_write(command + 8, struct.pack("<3H", command_x, row_offset, command_width))
            source = struct.pack("<II6HB3xII", 2, base, row_stride, 0,
                                 command_x, row_offset, half_width + overlap, 480, 1, 1, 0)
            cpu.mem_write(primary_source, source)
            cpu.mem_write(secondary_source, bytes(0x20))
            put_word(STACK + 0x78, secondary_result)
            for reg, value in (
                (UC_ARM_REG_R4, command), (UC_ARM_REG_R5, primary_source), (UC_ARM_REG_R6, 0),
                (UC_ARM_REG_R7, primary_source), (UC_ARM_REG_R9, width_shift),
                (UC_ARM_REG_R11, secondary_source),
            ):
                cpu.reg_write(reg, value)
            run(entry, stop)
            secondary_x = command_x + half_width - overlap
            assert cpu.mem_read(secondary_source + 4, 4) == struct.pack("<I", base)
            assert cpu.mem_read(secondary_source + 0xC, 2) == struct.pack("<H", secondary_x)
            adjusted = base + ((secondary_x + row_offset * row_stride) & ~63) * 2
            assert cpu.mem_read(secondary_result + 0x10, 4) == struct.pack("<I", adjusted)

    cpu.mem_write(0x63DC97F0, b"\x00\x20\x70\x47")
    for path_start, path_end, plane0, plane1, enabled in (
        (0x63A7F292, 0x63A7F2D4, 0xF3441280, 0xF3441580, (1, 2)),
        (0x63A7FAE0, 0x63A7FB1A, 0xF3441200, 0xF3441500, (1,)),
    ):
        for layout in (0, 1, 2, 3):
            for address in AIF_BANKS:
                put_word(address, 2)
            writes.clear()
            cpu.mem_write(STACK + 0x204, bytes([layout]))
            run(path_start, path_end)
            assert writes == ([(plane0, 3), (plane1, 3)] if layout in enabled else [(plane0, 3)])
    print("Verified DMM lookup, VPH staging and route fan-out, split-region geometry, and AIF configuration and arm cases.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    audit(parser.parse_args().image)

"""Verify the stock movie APL address-programming block with simulated MMIO."""
import argparse
import hashlib
from pathlib import Path
import struct

from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_WRITE, UC_MODE_THUMB, Uc
from unicorn.arm_const import (
    UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4, UC_ARM_REG_R5,
    UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_SP,
)

from audit_imager_control import IMAGE_BASE, IMAGE_SHA256

APL_BUFFERS = 0x6425BFD4
SCRATCH = 0x20000000
FRAME_CONFIG = SCRATCH + 0x100
RECEIPT = SCRATCH + 0x200
STACK = SCRATCH + 0xFF0


def audit(path):
    image = path.read_bytes()
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError("Unexpected av-cam.bin identity")
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(IMAGE_BASE, (len(image) + 0xFFF) & ~0xFFF)
    cpu.mem_write(IMAGE_BASE, image)
    cpu.mem_map(SCRATCH, 0x1000)

    writes = []

    def record(_cpu, _access, address, size, value, _context):
        assert size == 4
        writes.append((address, value))

    for core, base in enumerate((0xF3850000, 0xF3950000)):
        cpu.mem_map(base, 0x1000)
        cpu.hook_add(UC_HOOK_MEM_WRITE, record, begin=base, end=base + 0xFFF)
        buffer_words = [0x12000000 + core * 0x10000000 + index * 0x1000 for index in range(14)]
        cpu.mem_write(APL_BUFFERS + core * 0x38, struct.pack("<14I", *buffer_words))
        cpu.mem_write(FRAME_CONFIG + 0x14, struct.pack("<H", 0xABCD))
        cpu.reg_write(UC_ARM_REG_SP, STACK)
        cpu.reg_write(UC_ARM_REG_R4, core)
        cpu.reg_write(UC_ARM_REG_R5, RECEIPT)
        cpu.reg_write(UC_ARM_REG_R6, FRAME_CONFIG)
        cpu.reg_write(UC_ARM_REG_R7, APL_BUFFERS)
        cpu.reg_write(UC_ARM_REG_R8, 1)
        writes.clear()
        cpu.emu_start(0x6376EA63, 0x6376EB2E, count=1000)
        assert cpu.reg_read(UC_ARM_REG_PC) == 0x6376EB2E
        assert cpu.mem_read(RECEIPT + 2, 2) == b"\xCD\xAB"
        assert writes == [(base + offset, value) for offset, value in (
            (0x4E0, 1), (0x4E4, 0), (0x4F0, 0),
            (0x400, buffer_words[0]),  # TAR__IN__ADDR
            (0x410, 0), (0x414, 0x29C00),
            (0x418, buffer_words[3]), (0x41C, buffer_words[4]),
            (0x420, buffer_words[5]),  # ME___OUT_ADDR
            (0x424, 0), (0x428, buffer_words[7]), (0x42C, buffer_words[8]),
            (0x430, 0),
            (0x434, buffer_words[9]),  # MV___OUT_ADDR
            (0x438, 0), (0x440, 0), (0x444, 0), (0x448, 0),
            (0x450, buffer_words[10]),  # REF0_OUT_ADDR
            (0x454, buffer_words[11]),  # REF1_OUT_ADDR
            (0x4A0, 0),
            (0x4A4, buffer_words[12]),  # MBL__OUT_ADDR
            (0x4D0, buffer_words[13]),
        )]

    # Check the stock movie caller's optional callback argument before the
    # native kick. The caller has already built the output scratch area here.
    context = SCRATCH + 0x100
    cookie = 0x12345678
    cpu.mem_write(context + 0xD6C, struct.pack("<I", cookie))
    cpu.reg_write(UC_ARM_REG_R4, context)
    cpu.reg_write(UC_ARM_REG_SP, SCRATCH)
    cpu.emu_start(0x63959B69, 0x63959B76, count=30)
    assert cpu.reg_read(UC_ARM_REG_PC) == 0x63959B76
    assert cpu.reg_read(UC_ARM_REG_R0) == cookie
    assert cpu.reg_read(UC_ARM_REG_R1) == 0
    print("Verified 23 ordered APL register writes on each core and the movie kick's null callback argument.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    audit(parser.parse_args().image)

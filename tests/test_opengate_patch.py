"""
Unit & Integration Test for Open Gate Unlock Patch (ZV-E10)
Validates binary signatures against real firmware dumps and tests compiled hook binary.
"""

import os
import struct
import pytest
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

LIBOBJ_PATH = "dumps/camera_2025/usr/usr/lib/libObj.so"
OPENGATE_SO_PATH = "out/opengate.so"

# Expected signatures
SIG_10B = bytes.fromhex("2c 23 a3 80 01 23 63 81 60 80")
DEFAULT_OFFSET = 0x2D2298


def test_firmware_libobj_signature_exists():
    """Verify that libObj.so contains the exact aspect ratio dispatch signature."""
    assert os.path.exists(LIBOBJ_PATH), f"Firmware dump not found: {LIBOBJ_PATH}"
    with open(LIBOBJ_PATH, "rb") as f:
        data = f.read()

    idx = data.find(SIG_10B)
    assert idx != -1, "Open Gate aspect signature not found in libObj.so!"
    assert idx == DEFAULT_OFFSET, f"Signature shifted: expected 0x{DEFAULT_OFFSET:x}, got 0x{idx:x}"


def test_firmware_target_instruction():
    """Verify that the target instruction is indeed 'movs r3, #1' (16:9 stock)."""
    with open(LIBOBJ_PATH, "rb") as f:
        f.seek(DEFAULT_OFFSET + 4)
        target_bytes = f.read(2)

    opcode = struct.unpack("<H", target_bytes)[0]
    assert opcode == 0x2301, f"Expected 0x2301 (movs r3, #1), got 0x{opcode:04x}"

    # Disassemble to confirm
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    ins = list(md.disasm(target_bytes, DEFAULT_OFFSET + 4))
    assert len(ins) == 1
    assert ins[0].mnemonic == "movs"
    assert "r3, #1" in ins[0].op_str


def test_simulated_patch_transformation():
    """Simulate applying the patch and verify that Thumb assembly disassembles to MOVIE_ASPECT_3_2."""
    with open(LIBOBJ_PATH, "rb") as f:
        f.seek(DEFAULT_OFFSET)
        chunk = bytearray(f.read(16))

    # Apply Open Gate patch (+4: movs r3, #2)
    chunk[4] = 0x02
    chunk[5] = 0x23

    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    disasm = list(md.disasm(bytes(chunk), DEFAULT_OFFSET))

    # Instructions expected:
    # 0: movs r3, #0x2c
    # 2: strh r3, [r4, #4]
    # 4: movs r3, #2        <-- 3:2 Open Gate
    # 6: strh r3, [r4, #0xa]
    assert any(ins.address == DEFAULT_OFFSET + 4 and ins.mnemonic == "movs" and "r3, #2" in ins.op_str for ins in disasm)
    assert any(ins.address == DEFAULT_OFFSET + 6 and ins.mnemonic == "strh" and "[r4, #0xa]" in ins.op_str for ins in disasm)


def test_compiled_hook_binary():
    """Verify that the compiled out/opengate.so is a valid ARMv7 ELF shared library."""
    assert os.path.exists(OPENGATE_SO_PATH), f"Compiled binary missing: {OPENGATE_SO_PATH}"
    with open(OPENGATE_SO_PATH, "rb") as f:
        hdr = f.read(52)

    magic = hdr[:4]
    assert magic == b"\x7fELF", "Invalid ELF magic"

    elf_class = hdr[4]
    assert elf_class == 1, "Expected 32-bit ELF (ELFCLASS32)"

    endian = hdr[5]
    assert endian == 1, "Expected Little Endian (ELFDATA2LSB)"

    e_type, e_machine = struct.unpack("<HH", hdr[16:20])
    assert e_type == 3, "Expected ET_DYN (Shared object)"
    assert e_machine == 0x28, "Expected EM_ARM (ARM architecture)"

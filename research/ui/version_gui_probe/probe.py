"""Build and emulate a marker-only Version-screen probe; never contacts a camera."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
    UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP)

INPUT_SHA256 = "e6459c22859d8978195baa1ef2e93ad6d5f4fcb3dd89c2c2f02c325b46616090"
PATCHES = ((0x41868, bytes.fromhex("1ab2"), bytes.fromhex("5822")),
           (0x4186e, bytes.fromhex("1b14"), bytes.fromhex("5823")))
BASE, STACK, OBJECT, WIDGET, STOP = 0x1000000, 0x2000000, 0x3000000, 0x4000000, 0x5000000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(data):
    if digest(data) != INPUT_SHA256:
        raise ValueError("Unsupported input viewUnified6.so SHA-256")
    result = bytearray(data)
    for offset, before, after in PATCHES:
        if data[offset:offset + len(before)] != before:
            raise ValueError("Instruction guard failed")
        result[offset:offset + len(before)] = after
    return bytes(result)


def emulate(image, current=0x00020003, offered=0x00020003, screen_state=1,
            boot_element=1):
    """Run the original Version vtable +0x130 callback, mocking external GUI APIs.

    The controlled widget records assigned strings; this is not physical scanout.
    """
    cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    cpu.mem_map(BASE, 0x100000)
    # This ELF has nonidentity file offsets after .ARM.exidx.
    import io
    elf = ELFFile(io.BytesIO(image))
    for segment in elf.iter_segments():
        if segment["p_type"] == "PT_LOAD":
            cpu.mem_write(BASE + segment["p_vaddr"], segment.data())
    for address in (STACK, OBJECT, WIDGET, STOP):
        cpu.mem_map(address, 0x10000)
    def put(address, value):
        cpu.mem_write(address, struct.pack("<I", value))
    def get(address):
        return struct.unpack("<I", cpu.mem_read(address, 4))[0]
    def string(address):
        return bytes(cpu.mem_read(address, 128)).split(b"\0", 1)[0].decode("ascii")
    put(OBJECT + 4, screen_state)
    put(OBJECT + 0x154, current)
    put(OBJECT + 0x158, offered)
    put(OBJECT + 0x174, boot_element)
    cpu.mem_write(OBJECT + 0x160, b"ZV-E10\0")
    put(WIDGET, WIDGET + 0x1000)
    put(WIDGET + 0x1000 + 0x1b4, WIDGET + 0x2001)
    put(WIDGET + 0x1000 + 0x1cc, WIDGET + 0x2011)
    registers = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                 UC_ARM_REG_R7, UC_ARM_REG_R8)
    expected_registers = [0x11110000 + n for n in range(len(registers))]
    for register, value in zip(registers, expected_registers):
        cpu.reg_write(register, value)
    initial_sp = STACK + 0xf000
    cpu.reg_write(UC_ARM_REG_SP, initial_sp)
    cpu.reg_write(UC_ARM_REG_R0, OBJECT)
    cpu.reg_write(UC_ARM_REG_R1, 3)
    cpu.reg_write(UC_ARM_REG_LR, STOP | 1)
    seen = {"formatted": [], "assigned": [], "widget_ids": []}
    pending = [None]
    def ret(value=0):
        cpu.reg_write(UC_ARM_REG_R0, value)
        cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))
    def hook(cpu, address, size, _):
        if address == STOP:
            cpu.emu_stop()
            return
        if address == WIDGET + 0x2000:
            ret()
            return
        if address == WIDGET + 0x2010:
            seen["assigned"].append(pending[0])
            ret()
            return
        if address == BASE + 0x221b8:
            ret(cpu.reg_read(UC_ARM_REG_R0))
            return
        if not BASE + 0x16cd0 <= address < BASE + 0x17b70:
            return
        relative = address - BASE
        r0, r1, r2, r3 = (cpu.reg_read(r) for r in
            (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        if relative == 0x17054:  # memset
            cpu.mem_write(r0, bytes([r1 & 255]) * r2)
            ret(r0)
        elif relative == 0x17960:  # ViewBase::getWidget
            seen["widget_ids"].append(r1)
            ret(WIDGET)
        elif relative == 0x17620:  # Check_PAS_LabelCustom
            ret(r0)
        elif relative == 0x17a0c:  # snprintf
            fmt = string(r2)
            minor = get(cpu.reg_read(UC_ARM_REG_SP))
            text = fmt % ((r3, minor) if fmt.count("%") == 2 else r3)
            cpu.mem_write(r0, text.encode()[:r1-1] + b"\0")
            seen["formatted"].append(text)
            ret(len(text))
        elif relative == 0x1799c:  # VariantInfoArray::addVarStr
            pending[0] = string(r2)
            ret()
        elif relative in (0x175fc, 0x17078, 0x17088):
            ret()
        else:
            raise AssertionError("Unexpected external call: " + hex(relative))
    cpu.hook_add(UC_HOOK_CODE, hook)
    cpu.emu_start(BASE + 0x41a0d, STOP, count=10000)
    assert cpu.reg_read(UC_ARM_REG_PC) == STOP, "Original callback failed to return"
    assert cpu.reg_read(UC_ARM_REG_SP) == initial_sp
    assert [cpu.reg_read(r) for r in registers] == expected_registers
    assert bytes(cpu.mem_read(OBJECT + 0x154, 8)) == struct.pack("<II", current, offered)
    return seen


def verify(original, candidate):
    # These controls use the original instruction paths, not a Python reimplementation.
    rows = []
    for current, offered in [(0x20003, 0x20003), (0x20003, 0x20004),
                              (0x10000, 0x10000), (0x30009, 0x30008)]:
        stock = emulate(original, current, offered)
        patched = emulate(candidate, current, offered)
        expected = "%2d.%02d" % (current >> 16, current & 0xffff)
        assert stock["formatted"][0] == expected
        assert patched["formatted"][0] == "88.88"
        assert "88.88" in patched["assigned"], "Marker did not reach widget setter"
        assert stock["widget_ids"] == patched["widget_ids"]
        assert stock["formatted"][1:] == patched["formatted"][1:]
        rows.append({"current": hex(current), "offered": hex(offered),
                     "stock": stock, "candidate": patched})
    for state in (0, 3):
        assert emulate(original, screen_state=state) == emulate(candidate, screen_state=state)
    # Boot element 2 uses a separate layout path and stays unchanged.
    assert emulate(original, boot_element=2) == emulate(candidate, boot_element=2)
    try:
        build(candidate)
    except ValueError:
        pass
    else:
        raise AssertionError("Already patched input was accepted")
    assert len(original) == len(candidate)
    assert [i for i, (a, b) in enumerate(zip(original, candidate)) if a != b] == [
        0x41868, 0x41869, 0x4186e, 0x4186f]
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    original = args.input.read_bytes()
    candidate = build(original)
    rows = verify(original, candidate)
    args.out.mkdir(parents=True, exist_ok=True)
    output = args.out / "viewUnified6.gui-probe.so"
    output.write_bytes(candidate)
    report = {"status": "offline-original-instruction-verified", "hardware_tested": False,
        "input_sha256": digest(original), "output_sha256": digest(candidate),
        "input_md5": hashlib.md5(original).hexdigest(),
        "output_md5": hashlib.md5(candidate).hexdigest(), "bytes": len(candidate),
        "factory": "ViewVersionNumberToInstance", "factory_thumb_va": "0x41235",
        "constructor_thumb_va": "0x4108d", "vtable_address_point_va": "0x8c7c0",
        "layout_callback_slot": "0x130", "layout_callback_thumb_va": "0x41a0d",
        "marker_render_thumb_va": "0x417e1",
        "patches": [{"file_offset": hex(o), "before": b.hex(), "after": a.hex()}
                     for o,b,a in PATCHES],
        "cases": rows,
        "limits": ["External GUI/widget APIs are mocked; no physical display tested",
                   "No button-sequence handler or OS handoff implemented",
                   "No storage writes or camera communication by this recipe"]}
    (args.out / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ["status", "hardware_tested", "output_sha256", "bytes"]}))


if __name__ == "__main__":
    main()

"""Compare bare-metal imager sequencer accessors with original ARM instructions.

All MMIO is modeled RAM. No camera access or physical completion is assumed.
"""
import argparse
import hashlib
from pathlib import Path
import random
import struct

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_MODE_THUMB, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_CPSR

from audit_imager_control import IMAGE_BASE, IMAGE_SHA256

SCRATCH, STOP, PORT, RUN, IRQ = 0x20000000, 0x20008000, 0xfc088300, 0xfc088e00, 0xfc088f00


class Machine:
    def __init__(self, thumb):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB if thumb else UC_MODE_ARM)
        self.thumb = thumb
        self.cpu.mem_map(SCRATCH, 0x10000)
        self.cpu.mem_map(0xfc088000, 0x1000)
        self.cpu.mem_map(0xfc01f000, 0x1000)
        self.writes = []
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.record, begin=0xfc088000, end=0xfc088fff)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.record, begin=0xfc01f000, end=0xfc01ffff)

    def record(self, _uc, _access, addr, size, value, _ctx):
        self.writes.append((addr, size, value))

    def put(self, addr, *values):
        self.cpu.mem_write(addr, struct.pack("<" + "I" * len(values), *values))

    def word(self, addr):
        return struct.unpack("<I", self.cpu.mem_read(addr, 4))[0]

    def call(self, address, *args):
        self.cpu.reg_write(UC_ARM_REG_CPSR, 0xf3 if self.thumb else 0xd3)
        self.cpu.reg_write(UC_ARM_REG_SP, SCRATCH + 0xfff0)
        self.cpu.reg_write(UC_ARM_REG_LR, STOP | int(self.thumb))
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), args):
            self.cpu.reg_write(register, value)
        self.cpu.emu_start(address | int(self.thumb), STOP, count=20000)
        assert self.cpu.reg_read(UC_ARM_REG_PC) == STOP
        return self.cpu.reg_read(UC_ARM_REG_R0)


def audit(image_path, elf_path):
    image = image_path.read_bytes()
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError("Unexpected av-cam.bin identity")
    native, port = Machine(True), Machine(False)
    native.cpu.mem_map(IMAGE_BASE, (len(image) + 4095) & ~4095)
    native.cpu.mem_write(IMAGE_BASE, image)
    with elf_path.open("rb") as stream:
        elf = ELFFile(stream)
        port.cpu.mem_map(0x81000000, 0x200000)
        for section in elf.iter_sections():
            if section["sh_flags"] & 2 and section["sh_type"] != "SHT_NOBITS":
                port.cpu.mem_write(section["sh_addr"], section.data())
        symbols = {s.name: s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()}

    rng = random.Random(0x284)
    cases = 0
    for _ in range(12):
        initial = rng.randbytes(0x1000)
        cfg0, cfg1 = rng.getrandbits(32), rng.getrandbits(32)
        for machine in (native, port):
            machine.cpu.mem_write(0xfc088000, initial)
            machine.writes.clear()
        native.put(SCRATCH, cfg0, cfg1)
        native.call(0x637a8c28, SCRATCH, 1)
        port.call(symbols["imager_seq_configure"], cfg0, cfg1)
        assert native.writes == port.writes
        cases += 1

        for length in (0, 1, 2, 255, 256, 257):
            data = rng.randbytes(257)
            for machine in (native, port):
                machine.cpu.mem_write(SCRATCH + 0x100, data)
                machine.writes.clear()
            if length <= 256:
                native.call(0x637a8c80, 0, 1)
            ok = native.call(0x637a8c98, SCRATCH + 0x100, length, 1)
            result = port.call(symbols["imager_seq_upload"], SCRATCH + 0x100, length)
            assert bool(ok) == (result == 0)
            assert native.writes == port.writes
            cases += 1

        for mode in (0, 1, 2):
            native.writes.clear()
            port.writes.clear()
            native.call(0x637a8ccc, mode, 1)
            assert port.call(symbols["imager_seq_run"], mode) == 0
            assert native.writes == port.writes
            cases += 1

        for helper, symbol in ((0x637a8c50, "imager_seq_stop"),
                               (0x637a8d38, "imager_seq_ack")):
            native.writes.clear()
            port.writes.clear()
            native.call(helper, 1)
            port.call(symbols[symbol])
            assert native.writes == port.writes
            cases += 1

        for enabled, helper in ((0, 0x637a8cf0), (1, 0x637a8d14)):
            native.writes.clear()
            port.writes.clear()
            native.call(helper, 1)
            port.call(symbols["imager_seq_irq_enable"], enabled)
            assert native.writes == port.writes
            cases += 1

    for symbol, args in (("imager_seq_run", (3,)), ("imager_seq_run", (0xffffffff,)),
                         ("imager_seq_upload", (0, 1)), ("imager_seq_upload", (SCRATCH, 257))):
        port.writes.clear()
        assert port.call(symbols[symbol], *args) == 0xffffffff
        assert port.writes == []
        cases += 1

    # Bind the actual event-0 callback and its sequencer object, then run the
    # complete original IRQ-132 dispatcher. Only its OS event notification is
    # intercepted; acknowledgements and engine parking execute unchanged.
    event_table = 0x6379d21e + native.word(0x6379d364)
    registry_slot = 0x637a89a0 + native.word(0x637a89ac) + native.word(0x637a89b0)
    registry = native.word(registry_slot)
    native.put(event_table, 0x637a8999)
    native.put(registry + 4, SCRATCH)
    native.put(SCRATCH, 16, 32, 1)
    events = []

    def notify(uc, _address, _size, _ctx):
        events.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1)))
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    native.cpu.hook_add(UC_HOOK_CODE, notify, begin=0x635df194, end=0x635df194)
    assert native.word(0x645928b0) == 0x6379d1f5
    assert native.word(0x645928b8) == 132
    for fill in (0, 0xa5a5a5a5, 0xffffffff):
        events.clear()
        for machine in (native, port):
            machine.put(IRQ + 4, fill)
            machine.put(0xfc01ff00, 0)
            machine.writes.clear()
        native.call(0x6379d1f4, 132)
        assert port.call(symbols["imager_seq_handle_irq"]) == 0
        assert events == [(24, 16)]
        assert native.writes == port.writes
        assert [a for a, _, _ in port.writes] == [IRQ + 4, RUN, 0xfc01ff00]
        cases += 1
    for event in (1, 2, 15, 16, 0xffffffff):
        port.put(0xfc01ff00, event)
        port.writes.clear()
        assert port.call(symbols["imager_seq_handle_irq"]) == 0xffffffff
        assert port.writes == []
        cases += 1
    print(f"Verified {cases} imager-sequencer cases against original instructions; hardware completion remains untested.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    audit(args.firmware, args.elf)

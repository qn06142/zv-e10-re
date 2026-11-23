"""Execute live-view diagnostics ARM code with modeled input/display services."""
import argparse
from pathlib import Path
import struct
import zlib

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_SP, UC_ARM_REG_CPSR

from build_rtos import HEADER, MAGIC, VERSION

BASES = (0xf3002380, 0xf3102380, 0xf3020200, 0xf3020280, 0xf3020300,
         0xfc0a9200, 0xf3441280, 0xf3441580, 0xf3441200, 0xf3441500)


def verify(directory):
    package = (directory / "rtos.bin").read_bytes()
    magic, version, size, count, entry, crc, flags, reserved = HEADER.unpack_from(package)
    code = package[size:]
    assert (magic, version, size, count, flags, reserved) == (MAGIC, VERSION, 32, len(code), 1, 0)
    assert entry < count and zlib.crc32(code) == crc
    with (directory / "rtos.elf").open("rb") as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s["st_value"] for s in elf.get_section_by_name(".symtab").iter_symbols()}
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for start, length in ((0x81000000, 0x200000), (0x82000000, 0x10000),
                          (0x85000000, 0x200000), (0x83000000, 0x1000)):
        cpu.mem_map(start, length)
    for page in sorted({base & ~0xfff for base in BASES}):
        cpu.mem_map(page, 0x1000)
    cpu.mem_write(0x81000000, code)

    def put(address, *values):
        cpu.mem_write(address, struct.pack("<" + "I" * len(values), *values))

    def words(address, count):
        return struct.unpack("<" + "I" * count, cpu.mem_read(address, count * 4))

    reads, writes = [], []
    cpu.hook_add(UC_HOOK_MEM_WRITE, lambda _c, _a, addr, size, _v, _u: writes.append((addr, size)))
    cpu.hook_add(UC_HOOK_MEM_READ, lambda _c, _a, addr, size, _v, _u: reads.append((addr, size)))

    def call(name, r0=0, r1=0):
        cpu.reg_write(UC_ARM_REG_CPSR, 0xd3)
        cpu.reg_write(UC_ARM_REG_SP, 0x8200fff0)
        cpu.reg_write(UC_ARM_REG_LR, 0x83000000)
        cpu.reg_write(UC_ARM_REG_R0, r0)
        cpu.reg_write(UC_ARM_REG_R1, r1)
        cpu.emu_start(symbols[name], 0x83000000, count=5000000)
        assert cpu.reg_read(UC_ARM_REG_PC) == 0x83000000

    samples = symbols["live_view_samples"]
    polls = symbols["live_view_polls"]
    call("live_view_sample")
    call("live_view_sample")
    assert words(polls, 1) == (2,)
    assert words(samples, 50) == (0,) * 50
    put(BASES[3], 3, 0x80000000)
    put(BASES[3] + 0x10, 0x23456000)
    call("live_view_sample")
    assert words(samples + 3 * 20, 5) == (3, 0x80000000, 0x23456000, 1, 1)
    put(BASES[3] + 4, 0)
    call("live_view_sample")
    assert words(samples + 3 * 20 + 12, 2) == (2, 1)
    put(samples + 3 * 20 + 12, 0xffffffff, 0xffffffff)
    put(polls, 0xffffffff)
    put(BASES[3] + 0x10, 0x23457000)
    call("live_view_sample")
    assert words(samples + 3 * 20 + 12, 2) == (0xffffffff,) * 2
    assert words(polls, 1) == (0xffffffff,)

    # Execute actual drawing and the payload loop. Model only established runtime
    # services, leaving ARM sampling/rendering and buffer selection intact.
    put(polls, 0)
    cpu.mem_write(samples, bytes(200))
    state = {"polls": 0, "flips": [], "retry": False, "retry_writes": 0}
    targets = {symbols[n]: n for n in ("zvrt_display_init", "zvrt_input_init", "zvrt_poll_keys", "zvrt_display_flip")}

    def service(uc, address, _size, _ctx):
        name = targets[address]
        arg = uc.reg_read(UC_ARM_REG_R0)
        result = 0
        if name == "zvrt_display_init":
            assert arg == 0x25000000
            assert words(polls, 1) == (1,)
            assert words(symbols["live_view_initial"] + 3 * 12, 3) == (3, 0, 0x23457000)
        elif name == "zvrt_poll_keys":
            state["polls"] += 1
            key = 16 if state["polls"] in (2, 4) else 0
            put(arg, key, key, 0)
        elif name == "zvrt_display_flip":
            if not state["retry"]:
                state["retry"] = True
                state["retry_writes"] = len(writes)
                state["retry_arg"] = arg
                result = 0xffffffff
            else:
                assert arg == state["retry_arg"]
                assert len(writes) == state["retry_writes"], "Pending frame repainted on timeout"
                state["retry"] = False
                state["flips"].append(arg)
                assert words(polls, 1)[0] == (2, 2, 2, 3, 4)[len(state["flips"]) - 1]
                if len(state["flips"]) == 5:
                    uc.emu_stop()
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    for address in targets:
        cpu.hook_add(UC_HOOK_CODE, service, begin=address, end=address)
    cpu.reg_write(UC_ARM_REG_SP, 0x8200fff0)
    cpu.reg_write(UC_ARM_REG_R0, 0x83000100)
    cpu.emu_start(symbols["rtos_main"], 0x83000000, count=30000000)
    assert state["flips"] == [0x25096000, 0x25000000, 0x25096000, 0x25000000, 0x25096000]
    assert words(0x83000100 + 28, 1) == (0x4f4b5254,)
    assert all(addr < 0xf0000000 for addr, _ in writes), "Sensor MMIO write"
    mmio_reads = {addr for addr, _ in reads if addr >= 0xf0000000}
    assert mmio_reads == {b + off for b in BASES for off in (0, 4, 0x10)}
    assert all(any(lo <= addr and addr + size <= hi for lo, hi in
                   ((0x81000000, 0x81200000), (0x82000000, 0x82010000),
                    (0x83000000, 0x83001000), (0x85000000, 0x8512c000)))
               for addr, size in writes), "Write outside image/stack/handoff/two framebuffers"
    print("Verified ARM live-view diagnostics: 10 banks, counters, saturation, freeze/resume, five flips, timeout retry; no sensor writes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    verify(parser.parse_args().directory)

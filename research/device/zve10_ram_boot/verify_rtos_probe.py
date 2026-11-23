"""Exercise the independent RTOS arena probe at relocated ARM addresses."""
import argparse
import struct
import zlib
from pathlib import Path

from unicorn import UC_ARCH_ARM, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
from unicorn.arm_const import UC_ARM_REG_CPSR, UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_SP

from build_rtos import HEADER, MAGIC, VERSION, package_image

HANDOFF_MAGIC = int.from_bytes(b"ZVRH", "little")
PROBE_OK = 0x4F4B5254
ARENA_BYTES = 0x4000


def verify_probe(code, entry, base, mutate=None):
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    context, stack, arena, stop = 0x2000000, 0x2100000, 0x2200000, 0x2300000
    for start, size in (
        (base, 0x1000), (context, 0x1000), (stack, 0x2000),
        (arena, ARENA_BYTES), (stop, 0x1000),
    ):
        cpu.mem_map(start, size)
    cpu.mem_write(base, code)
    handoff = [HANDOFF_MAGIC, VERSION, 32, 1, arena, 0x5000000, ARENA_BYTES, 0]
    if mutate:
        index, value = mutate
        handoff[index] = value
    cpu.mem_write(context, HEADER.pack(*handoff))
    cpu.reg_write(UC_ARM_REG_CPSR, 0xD3)
    cpu.reg_write(UC_ARM_REG_R0, context)
    cpu.reg_write(UC_ARM_REG_SP, stack + 0x2000)
    cpu.reg_write(UC_ARM_REG_LR, stop)
    writes = []

    def on_write(_cpu, _access, address, size, value, _data):
        if stack <= address < stack + 0x2000:
            return
        writes.append((address, size, value))

    cpu.hook_add(UC_HOOK_MEM_WRITE, on_write)
    cpu.emu_start(base + entry, stop, count=400)
    if mutate:
        assert cpu.reg_read(UC_ARM_REG_R0) == 1
        assert not writes
    else:
        assert cpu.reg_read(UC_ARM_REG_R0) == 0
        assert writes == [
            (arena, 4, PROBE_OK), (arena + ARENA_BYTES - 4, 4, PROBE_OK),
            (context + 28, 4, PROBE_OK),
        ]
    assert cpu.reg_read(UC_ARM_REG_SP) == stack + 0x2000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    magic, version, header_bytes, code_bytes, entry, checksum, flags, reserved =         HEADER.unpack_from(image)
    code = image[header_bytes:]
    assert (magic, version, header_bytes, flags, reserved) == (MAGIC, VERSION, 32, 0, 0)
    assert code_bytes == len(code) and zlib.crc32(code) == checksum
    assert package_image(code, entry) == image
    for length, bad_entry in ((0, 0), (5, 0), (4100, 0), (16, -4), (16, 2), (16, 16)):
        try:
            package_image(bytes(length), bad_entry)
        except ValueError:
            pass
        else:
            raise AssertionError((length, bad_entry))
    for base in (0x100000, 0x510000):
        verify_probe(code, entry, base)
        for invalid in ((0, 0), (1, 2), (2, 16), (3, 3), (4, 0),
                        (4, 0x2200001), (4, 0xFFFFFFF0), (6, 32), (6, 0x4001)):
            verify_probe(code, entry, base, invalid)
    print("Verified packaged image, 2 relocated arena probes and 18 rejected handoffs.")


if __name__ == "__main__":
    main()

"""Execute the stock speed-set dispatch and the createGadget error exits offline."""
from pathlib import Path
from struct import pack
import argparse

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_FP, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R4, UC_ARM_REG_R6, UC_ARM_REG_SP)


def put_word(cpu, address, value):
    cpu.mem_write(address, pack('<I', value))


def check_create_gadget(path):
    with path.open('rb') as stream:
        segments = [(s['p_vaddr'], s.data()) for s in ELFFile(stream).iter_segments()
                    if s['p_type'] == 'PT_LOAD']
    speed_ioctl, initialize = 0x4001e30c, 0xe305
    expected = [(speed_ioctl, 5), (initialize, None), (speed_ioctl, 5)]
    for failure, (result, state) in enumerate(((1, 5), (14, 7), (1, 5)), 1):
        cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        cpu.mem_map(0, 0x50000)
        for address, data in segments:
            cpu.mem_write(address, data)
        obj, msg, stop = 0x30000, 0x31000, 0x32000
        put_word(cpu, msg, obj)
        put_word(cpu, obj + 0x8c, 7)
        put_word(cpu, obj + 0x10, 0)
        cpu.reg_write(UC_ARM_REG_R0, msg)
        cpu.reg_write(UC_ARM_REG_SP, 0x4f000)
        cpu.reg_write(UC_ARM_REG_LR, stop | 1)
        calls = []

        def intercept(machine, pc, size, _):
            if pc == 0xcd68:
                ret = 0
            elif pc in (0xcd90, 0xcda2, 0xcdb6):
                cmd = machine.reg_read(UC_ARM_REG_R1)
                arg = machine.reg_read(UC_ARM_REG_R2)
                calls.append((cmd, machine.mem_read(arg, 1)[0] if cmd == speed_ioctl else None))
                ret = -1 if len(calls) == failure else 0
            else:
                return
            machine.reg_write(UC_ARM_REG_R0, ret & 0xffffffff)
            machine.reg_write(UC_ARM_REG_PC, (pc + size) | 1)

        cpu.hook_add(UC_HOOK_CODE, intercept)
        cpu.emu_start(0xcd55, stop, count=200)
        assert cpu.reg_read(UC_ARM_REG_PC) == stop
        assert cpu.reg_read(UC_ARM_REG_R0) == result
        assert cpu.mem_read(obj + 0x98, 1)[0] == state
        assert calls == expected[:failure]
        print(f'createGadget fault {failure}: return={result}, state={state}, calls={calls}')


def check_kernel_dispatch(path):
    base = 0x60108000
    kernel = path.read_bytes()
    for request, operation in ((3, 2), (5, 4)):
        for reject in (False, True):
            cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
            cpu.mem_map(0x602bc000, 0x1000)
            cpu.mem_write(0x602bc000, kernel[0x602bc000-base:0x602bd000-base])
            cpu.mem_map(0x10000, 0x4000)
            ctx, driver, vtable, fp = 0x10000, 0x11000, 0x12000, 0x13800
            put_word(cpu, ctx, driver)
            put_word(cpu, driver, vtable)
            put_word(cpu, vtable + 0x44, 0x10100)
            cpu.mem_write(fp - 0x28, bytes([request]))
            cpu.mem_write(ctx + 0x2d, b'\x02')
            cpu.reg_write(UC_ARM_REG_R4, ctx)
            cpu.reg_write(UC_ARM_REG_FP, fp)
            seen = []

            def intercept(machine, pc, size, _):
                if pc == 0x10100:
                    assert machine.reg_read(UC_ARM_REG_R0) == driver
                    seen.append(machine.reg_read(UC_ARM_REG_R1))
                    machine.reg_write(UC_ARM_REG_R0, 0xfffffff0 if reject else 0)
                    machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
                elif pc in (0x602bc604, 0x602bc5f0):
                    machine.emu_stop()

            cpu.hook_add(UC_HOOK_CODE, intercept)
            cpu.emu_start(0x602bc150, 0x602bc610, count=60)
            assert seen == [operation]
            assert cpu.reg_read(UC_ARM_REG_PC) == (0x602bc5f0 if reject else 0x602bc604)
            saved = cpu.mem_read(ctx + 0x2d, 1)[0]
            assert saved == (2 if reject else request)
            print(f'kernel request {request}: operation={operation}, rejected={reject}, saved={saved}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    args = parser.parse_args()
    check_create_gadget(args.repo / 'dumps/camera_2025/usr/usr/lib/libInfraUsbCmn.so')
    check_kernel_dispatch(args.repo / 'dumps/firmware/vmlinux.bin')

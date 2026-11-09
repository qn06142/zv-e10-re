"""Reproduce the v44 registration overwrite and check the containment kernel's call targets."""
import sys
from pathlib import Path
from struct import pack, unpack
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR

def targets(elf):
    sym = elf.get_section_by_name('.symtab')
    return {r['r_offset']: sym.get_symbol(r['r_info_sym']).name
            for r in elf.get_section_by_name('.rel.text').iter_relocations()}

old, clean = map(Path, sys.argv[1:])
with clean.open('rb') as f:
    t = targets(ELFFile(f))
    assert t[0x1fe4] == 'usb_gadgetcore_register_driver'
    assert t[0x2064] == 'usb_gadgetcore_unregister_driver'
with old.open('rb') as f:
    elf = ELFFile(f)
    assert targets(elf)[0x1fe4] == '__yc48_register_drivers'
    sym = elf.get_section_by_name('.symtab')
    entry = sym.get_symbol_by_name('__yc48_register_drivers')[0]
    sec = elf.get_section(entry['st_shndx'])
    code, start = sec.data(), entry['st_value']
    calls = {r['r_offset']: sym.get_symbol(r['r_info_sym']).name
             for r in elf.get_section_by_name('.rel.text.yc42_chunk').iter_relocations()}

for ss_rc in (0, -16):
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    base, dev, stop = 0x10000, 0x20000, 0x30000
    u.mem_map(base, 0x1000)
    u.mem_map(dev, 0x2000)
    u.mem_map(stop, 0x1000)
    u.mem_write(base, code)
    u.mem_write(dev + 0x70, pack('<I', 0x11223344))
    u.mem_write(dev + 0xac, pack('<I', 0xdecafbad))
    u.reg_write(UC_ARM_REG_R0, dev + 0x38)
    u.reg_write(UC_ARM_REG_SP, dev + 0x1800)
    u.reg_write(UC_ARM_REG_LR, stop)
    trace = []

    def service(machine, pc, size, _):
        name = calls.get(pc - base)
        if name is None:
            return
        trace.append((name, machine.reg_read(UC_ARM_REG_R0) - dev))
        rc = ss_rc if len(trace) == 2 else 0
        machine.reg_write(UC_ARM_REG_R0, rc & 0xffffffff)
        machine.reg_write(UC_ARM_REG_PC, pc + size)

    u.hook_add(UC_HOOK_CODE, service)
    u.emu_start(base + start, stop, count=100)
    assert u.reg_read(UC_ARM_REG_PC) == stop
    assert [offset for _, offset in trace] == ([0x38, 0x74, 0x38] if ss_rc else [0x38, 0x74])
    assert unpack('<I', u.mem_read(dev + 0xac, 4))[0] == 0x11223344
    print(f'Old hook overwrote teardown pointer with SuperSpeed return {ss_rc}')
print('Containment kernel restores both stock registration call targets')

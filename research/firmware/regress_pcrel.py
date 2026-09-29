"""Regression test for the PC-relative reference detector.

Known-good case, resolved by hand earlier:
  0xaa172  ldr r3, [pc, #0x24]
  0xaa178  add r3, pc
  -> literal at 0xaa198 = 0x008af3a5
  -> target = 0xaa178 + 4 + 0x008af3a5 = 0x959521 = 'dec/sfmc_dec_input_i.cpp'

If the detector cannot reproduce that, the bug is in the detection logic,
not in the sweep coverage.
"""
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm import ARM_OP_REG, ARM_OP_IMM, ARM_OP_MEM

BASE = Path(r'D:\02_Development_And_Projects\pmca-re')
av = (BASE / 'dumps' / 'av-cam.bin.bak').read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = True

print('=== what capstone says for the two known instructions ===')
for addr in (0xAA172, 0xAA178, 0xAA182, 0xAA184):
    for ins in md.disasm(av[addr:addr + 4] + b'\x00' * 8, addr):
        print('  0x%08x  %-12s %-24s  size=%d' % (addr, ins.bytes.hex(' '),
                                                   ins.mnemonic + ' ' + ins.op_str, ins.size))
        for n, op in enumerate(ins.operands):
            if op.type == ARM_OP_REG:
                print('        op%d REG   id=%-4d name=%s' % (n, op.reg, ins.reg_name(op.reg)))
            elif op.type == ARM_OP_IMM:
                print('        op%d IMM   %d (0x%x)' % (n, op.imm, op.imm))
            elif op.type == ARM_OP_MEM:
                print('        op%d MEM   base=%-4d(%s) index=%-4d disp=%d' % (
                    n, op.mem.base, ins.reg_name(op.mem.base), op.mem.index, op.mem.disp))
        break

print()
print('=== is the PC register id what I assumed (13)? ===')
for i in range(md.reg_name.__code__.co_argcount, 0, -1):
    pass
for cand in range(0, 300):
    try:
        nm = md.reg_name(cand)
    except Exception:
        continue
    if nm and nm.lower() in ('pc', 'ip', 'r13', 'sp'):
        print('  reg id %-4d -> %r' % (cand, nm))
print()

print('=== the known-good resolution, by hand ===')
la = ((0xAA172 + 4) & ~3) + 0x24
val = struct.unpack_from('<I', av, la)[0]
print('  literal pool at 0x%08x = 0x%08x' % (la, val))
print('  add r3,pc at 0xaa178 -> 0x%08x' % (0xAA178 + 4 + val))
end = av.find(b'\x00', 0xAA178 + 4 + val)
print('  string: %r' % av[0xAA178 + 4 + val:end].decode('ascii', 'replace'))
print()

print('=== walk the function at 0xaa14c with the detector logic ===')


def dis1(buf, addr):
    for extra in (b'', b'\x00' * 4, b'\x00' * 8, b'\x00' * 16):
        for i in md.disasm(bytes(buf) + extra, addr):
            return i
    return None


pending = {}
addr = 0xAA14C
found = []
while addr < 0xAA14C + 0x80:
    ins = dis1(av[addr:addr + 4], addr)
    if ins is None:
        print('  0x%08x  <disasm failed>' % addr)
        break
    ops = ins.operands
    m = ins.mnemonic
    note = ''
    if m.startswith('ldr') and len(ops) == 2 and ops[1].type == ARM_OP_MEM:
        mem = ops[1].mem
        is_pc = ins.reg_name(mem.base).lower() == 'pc'
        note = '  [mem.base name=%r is_pc=%s]' % (ins.reg_name(mem.base), is_pc)
        if is_pc:
            la = ((addr + 4) & ~3) + mem.disp
            val = struct.unpack_from('<I', av, la)[0]
            if ops[0].type == ARM_OP_REG:
                pending[ops[0].reg] = val
            note += '  -> pool 0x%06x = 0x%08x' % (la, val)
    if m in ('add', 'addw', 'adr') and len(ops) >= 2 and ops[1].type == ARM_OP_REG:
        if ops[0].type == ARM_OP_REG and ops[0].reg in pending:
            tgt = pending.pop(ops[0].reg) + (addr + 4)
            found.append(tgt)
            note += '  -> RESOLVED 0x%08x' % tgt
    print('  0x%08x  %-12s %-22s%s' % (addr, ins.bytes.hex(' '), m + ' ' + ins.op_str, note))
    addr += ins.size

print()
print('resolved targets: %s' % ['0x%08x' % t for t in found])
print('expected at least 0x00959521 (dec/sfmc_dec_input_i.cpp)')

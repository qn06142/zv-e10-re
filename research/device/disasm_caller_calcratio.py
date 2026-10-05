import struct
from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

def read_str(addr):
    if addr < 0 or addr >= len(data): return None
    end = data.find(b'\x00', addr)
    if end != -1 and end > addr:
        chunk = data[addr:end]
        if all(32 <= b < 127 for b in chunk): return chunk.decode('ascii')
    return None

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

start_addr = 0x261700
end_addr = 0x261980
f_bytes = data[start_addr:end_addr]
insns = list(cs.disasm(f_bytes, start_addr))

regs = {}
for insn in insns:
    if insn.mnemonic == 'ldr' and '[pc' in insn.op_str:
        op = insn.operands[1]
        if op.type == capstone.arm.ARM_OP_MEM and op.value.mem.base == capstone.arm.ARM_REG_PC:
            target = (insn.address & ~3) + 4 + op.value.mem.disp
            if target + 4 <= len(data):
                val = struct.unpack_from('<I', data, target)[0]
                rt = insn.reg_name(insn.operands[0].value.reg)
                regs[rt] = val
    elif insn.mnemonic == 'add' and 'pc' in insn.op_str:
        op0 = insn.reg_name(insn.operands[0].value.reg)
        if op0 in regs:
            val = regs[op0]
            resolved = (insn.address + 4) + val
            s = read_str(resolved)
            if s and len(s) > 3:
                print(f"0x{insn.address:06x}: {insn.mnemonic:6s} {insn.op_str:20s} ; \"{s}\"")
                continue
    print(f"0x{insn.address:06x}: {insn.mnemonic:6s} {insn.op_str}")

import struct
from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

# Search for 0x01369220 (or relative offset to it) in the .text section
# .text is from 0x0010fee0 to 0x0010fee0 + 0x00d3b028 = 0x00e4af08
target_addr = 0x01369220
target_bytes = struct.pack("<I", target_addr)

pos = 0
found_pool = []
while True:
    idx = data.find(target_bytes, pos)
    if idx == -1: break
    found_pool.append(idx)
    pos = idx + 1

print(f"Direct literal pool references to 0x{target_addr:08x}:")
for addr in found_pool:
    print(f"  at 0x{addr:08x}")
    # Now find LDR insns referencing this pool entry
    # Scan backwards 4KB
    scan_start = max(0x10fee0, addr - 4096)
    code_chunk = data[scan_start:addr]
    for insn in cs.disasm(code_chunk, scan_start):
        if insn.mnemonic == 'ldr' and '[pc' in insn.op_str:
            op = insn.operands[1]
            if op.type == capstone.arm.ARM_OP_MEM and op.value.mem.base == capstone.arm.ARM_REG_PC:
                tgt = (insn.address & ~3) + 4 + op.value.mem.disp
                if tgt == addr:
                    print(f"    referenced by 0x{insn.address:06x}: {insn.mnemonic} {insn.op_str}")

# Also check GOT references or offset-based references
# In Thumb PIC, it might load an offset to GOT, then GOT entry

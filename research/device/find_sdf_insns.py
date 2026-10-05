from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
avcam_path = HERE / "dumps" / "av-cam.bin"
AVCAM_BASE = 0x635c6000

data = avcam_path.read_bytes()
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

target_off = 0x00975133
target_va = AVCAM_BASE + target_off

# Check 0x973000 to 0x975133
start_off = 0x00970000
code = data[start_off:target_off]

for insn in cs.disasm(code, AVCAM_BASE + start_off):
    # Check if adr or add rx, pc, #imm targets target_va
    if insn.mnemonic in ['adr', 'add', 'sub']:
        for op in insn.operands:
            if op.type == capstone.arm.ARM_OP_MEM and op.value.mem.base == capstone.arm.ARM_REG_PC:
                dest = (insn.address & ~3) + 4 + op.value.mem.disp
                if abs(dest - target_va) < 0x200:
                    print(f"0x{insn.address:08x}: {insn.mnemonic} {insn.op_str} -> targets 0x{dest:08x}")
    elif insn.mnemonic == 'ldr' and '[pc' in insn.op_str:
        op = insn.operands[1]
        if op.type == capstone.arm.ARM_OP_MEM and op.value.mem.base == capstone.arm.ARM_REG_PC:
            tgt = (insn.address & ~3) + 4 + op.value.mem.disp
            if tgt - AVCAM_BASE + 4 <= len(data):
                val = int.from_bytes(data[tgt-AVCAM_BASE:tgt-AVCAM_BASE+4], 'little')
                if abs(val - target_va) < 0x200:
                    print(f"0x{insn.address:08x}: ldr {insn.op_str} -> pool at 0x{tgt:08x} = 0x{val:08x}")

with open('dumps/av-cam.bin', 'rb') as f:
    av = f.read()
import struct

AVCAM_BASE = 0x635c6000

# 0x636ce964:
# 0x636ce964: ldr r3, [pc, #0x38] -> (0x636ce964 & ~3) + 4 + 0x38 = 0x636ce9a0
got_off = struct.unpack_from('<I', av, 0x636ce9a0 - AVCAM_BASE)[0]
got_base = 0x636ce968 + 4 + got_off
print(f"GOT base at 0x{got_base:08x}")

# tbb [pc, r0] at 0x636ce96e
# PC is 0x636ce96e + 4 = 0x636ce972
table_start = 0x636ce972
offsets = []
for i in range(11):
    b = av[table_start - AVCAM_BASE + i]
    dest = table_start + (b * 2)
    offsets.append(dest)
    print(f"Case {i+1} (idx {i}): byte {b} -> 0x{dest:08x}")

# For each destination, disassemble 2-3 insns
import capstone
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

for i, dest in enumerate(offsets):
    code = av[dest - AVCAM_BASE:dest - AVCAM_BASE + 16]
    insns = list(cs.disasm(code, dest))
    # trace ldr r2, [pc, #imm]
    r2_val = None
    for ins in insns:
        if ins.mnemonic == 'ldr' and 'r2' in ins.op_str and '[pc' in ins.op_str:
            imm = int(ins.op_str.split('#')[-1].rstrip(']'), 16)
            pool = ((ins.address & ~3) + 4) + imm
            r2_val = struct.unpack_from('<I', av, pool - AVCAM_BASE)[0]
            break
    if r2_val is not None:
        got_entry = got_base + r2_val
        val = struct.unpack_from('<I', av, got_entry - AVCAM_BASE)[0] if 0 <= got_entry - AVCAM_BASE < len(av) - 4 else 0
        print(f"  Case {i+1}: dest 0x{dest:08x}, r2_val=0x{r2_val:x} -> got_entry=0x{got_entry:08x} -> val=0x{val:08x}")
    else:
        print(f"  Case {i+1}: dest 0x{dest:08x} (no r2)")

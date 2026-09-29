import os
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

BOOT = (ROOT_REPO / 'dumps/bootrom').as_posix()
br = open(BOOT, "rb").read()
ks = br.find(b"KEY f:%x r:%x")
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)

# The string is at 0x1344. Code references it via an LDR rx, =0x1344 (literal pool).
# Find any LDR rx,[pc,...] whose literal value == 0x1344, then disassemble the function around that insn.
target = 0x1344
hits = []
for i in range(0, len(br)-8, 4):
    w = int.from_bytes(br[i:i+4], "little")
    # LDR rx, [pc, #imm]  encoding: 0x59 or 0x51 (imm12) -> 0x59F?0000 pattern
    if (w & 0x0F7F0000) == 0x059F0000:
        imm = w & 0xFFF
        # pc in ARM disasm is insn_addr + 8
        pool_addr = (i + 8 + imm) & ~3
        if pool_addr == target:
            hits.append(i)
print("LDR referencing KEY string at insn offs:", [hex(h) for h in hits])
for h in hits:
    print("\n===== function around 0x%x =====" % h)
    start = max(0, h-0x180)
    for ins in md.disasm(br[start:start+0x300], start):
        mark = " >>>" if ins.address == h else ""
        print("  0x%04x: %-10s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))
        if ins.address > h + 0x1c0: break

# Also dump the literal pool around 0x1344 to see neighbouring strings/values
print("\n=== bytes around KEY string (0x1330..0x1380) ===")
print(br[0x1330:0x1380].hex())

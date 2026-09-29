import os, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

import pathlib
ROOT_REPO = pathlib.Path(__file__).resolve().parents[2]

BOOT = (ROOT_REPO / 'dumps/bootrom').as_posix()
br = open(BOOT, "rb").read()
print("bootrom size =", len(br))

ks = br.find(b"KEY f:%x r:%x")
print("KEY string at off=0x%x (%d)" % (ks, ks))

md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
md.detail = False

def disasm_region(data, base, n=40):
    print("\n--- disasm @ 0x%x (%d insns) ---" % (base, n))
    for ins in md.disasm(data, base):
        print("  0x%04x: %-10s %s" % (ins.address, ins.mnemonic, ins.op_str))
        n -= 1
        if n <= 0: break

# reset vector target
disasm_region(br[0x28:0x28+0x200], 0x28, 36)
# around the KEY string
for trybase in (max(0, ks-0x200), ks-0x80):
    if trybase < len(br):
        disasm_region(br[trybase:trybase+0x200], trybase, 22)

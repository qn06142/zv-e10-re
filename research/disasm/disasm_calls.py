import os
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

BOOT = r"C:\Users\Minhsnguhoa\pmca-re\dumps\bootrom"
br = open(BOOT, "rb").read()
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)

# 1) Find the print function: a function that takes a format string (r0) and varargs.
#    heuristic: scan all code for 'blx rN' / 'bl <imm>' and 'str r0..r3' setup.
#    Simpler: the KEY string lives in a region of strings; the code that uses it
#    is nearby. Disassemble the whole code area (exclude known string table at 0x1300+)
#    and print every 'bl'/'blx' plus any 'str' to a 0xE... base.

BANNED_START = 0x1300  # string/magic table region
print("=== scan bootrom code for calls + crypto-base stores ===")
base_pat = lambda v: (0xE0000000 <= v <= 0xFFFFFFFF) and (v & 0xFFF) == 0
crypto_writes = []
calls = []
for ins in md.disasm(br[:0x1300], 0):
    a = ins.address
    if ins.mnemonic == "bl" or ins.mnemonic == "blx":
        calls.append(a)
    # str rX, [rY, #imm]  where rY holds a 0xE.. base (loaded just before)
    if ins.mnemonic.startswith("str") and ins.op_str:
        # capture stores; we'll correlate with preceding base loads below
        crypto_writes.append((a, ins.mnemonic, ins.op_str))

print("  total calls (bl/blx) in code region: %d" % len(calls))
for c in calls[:30]:
    print("    call @0x%x" % c)

# 2) Find loads of 0xE.../0xF... MMIO bases and the stores to them
print("\n=== MMIO base loads (0xE..-0xF..) and following stores ===")
for ins in md.disasm(br[:0x1300], 0):
    a = ins.address
    if ins.mnemonic == "ldr" and "0x" in ins.op_str:
        # crude: extract an immediate after '=' or in [...,#imm]
        import re
        vals = re.findall(r"0x[0-9a-fA-F]+", ins.op_str)
        for v in vals:
            iv = int(v,16)
            if base_pat(iv):
                print("  0x%04x: %s %s   <- base %s" % (a, ins.mnemonic, ins.op_str, v))

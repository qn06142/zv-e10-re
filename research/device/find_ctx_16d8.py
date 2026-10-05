import capstone
from pathlib import Path

p = Path(__file__).resolve().parent.parent.parent / "dumps/camera_2025/usr/usr/lib/libmpr.so"
raw = p.read_bytes()
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.skipdata = True
ins = list(cs.disasm(raw[:0xb00000], 0))
print(len(ins), "insns")
for k, i in enumerate(ins):
    if i.mnemonic.startswith("add") and any(x in i.op_str for x in ("#0x16d8","#0x16d0","#0x16d4","#0x16dc")):
        nxt = ins[k + 1: k + 4]
        print(f"0x{i.address:08x}: {i.mnemonic} {i.op_str}  |  " + " ; ".join(f"{n.mnemonic} {n.op_str}" for n in nxt))


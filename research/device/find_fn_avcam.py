from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
avcam_path = HERE / "dumps" / "av-cam.bin"
AVCAM_BASE = 0x635c6000

with open(avcam_path, "rb") as f:
    data = f.read()

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

# Scan backwards from 0x63cb3df0 to find push {..., lr}
target = 0x63cb3df0
off = target - AVCAM_BASE
for back in range(0, 500, 2):
    p = off - back
    hw = int.from_bytes(data[p:p+2], 'little')
    # push {..., lr} is 0xb5xx or 0xe92d (32-bit push)
    if (hw & 0xff00) == 0xb500:
        fn_start = AVCAM_BASE + p
        print(f"Candidate fn start at VA 0x{fn_start:08x}")
        # Disassemble from fn_start to target + 100
        code = data[p:off+100]
        for insn in cs.disasm(code, fn_start):
            print(f"  0x{insn.address:06x}: {insn.mnemonic:8s} {insn.op_str}")
        break

from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
avcam_path = HERE / "dumps" / "av-cam.bin"

with open(avcam_path, "rb") as f:
    data = f.read()

# Base address of av-cam.bin
# av-cam.bin loaded at 0x63400000 or similar? Let's check offset for 0x63cb3d62
# If VA is 0x63cb3d62, what is file offset?
# Let's search for the bytes or find base address.
# Let's search for 4, 3, 16, 9 constants or function.
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

# Let's find base address of av-cam.bin
# In previous notes: 0x63cb3d62
# Let's check if 0x63400000 is base:
# offset = 0x63cb3d62 - 0x63400000 = 0x8b3d62
for base in [0x63400000, 0x63000000, 0x60000000]:
    off = 0x63cb3d62 - base
    if 0 <= off < len(data) - 100:
        print(f"Trying base 0x{base:08x}, offset 0x{off:08x}:")
        code = data[off:off+60]
        for insn in cs.disasm(code, 0x63cb3d62):
            print(f"  0x{insn.address:06x}: {insn.mnemonic:8s} {insn.op_str}")
        break

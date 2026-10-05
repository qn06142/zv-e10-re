from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
avcam_path = HERE / "dumps" / "av-cam.bin"
AVCAM_BASE = 0x635c6000

with open(avcam_path, "rb") as f:
    data = f.read()

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

def disasm_range(va_start, length):
    off = va_start - AVCAM_BASE
    print(f"=== Disasm at VA 0x{va_start:08x} (file offset 0x{off:08x}, length {length}) ===")
    code = data[off:off+length]
    for insn in cs.disasm(code, va_start):
        print(f"  0x{insn.address:06x}: {insn.mnemonic:8s} {insn.op_str}")

if __name__ == "__main__":
    disasm_range(0x636db590, 80)
    print()
    disasm_range(0x63cb3df0, 80)

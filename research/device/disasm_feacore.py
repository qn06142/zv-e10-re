from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_mpr_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libmpr.so"

with open(lib_mpr_path, "rb") as f:
    f.seek(0x542264)
    code = f.read(144)

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
print("=== FeaCore::SetRecAspect (0x542264) ===")
for insn in cs.disasm(code, 0x542264):
    print(f"  0x{insn.address:06x}: {insn.mnemonic:8s} {insn.op_str}")

with open(lib_mpr_path, "rb") as f:
    f.seek(0x5427b4)
    code2 = f.read(140)

print("\n=== FeaCore::SetRecTvScanMode (0x5427b4) ===")
for insn in cs.disasm(code2, 0x5427b4):
    print(f"  0x{insn.address:06x}: {insn.mnemonic:8s} {insn.op_str}")

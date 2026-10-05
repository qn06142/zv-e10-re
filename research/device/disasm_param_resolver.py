from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    f.seek(0x000469b0)
    code = f.read(0x100)

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
for insn in cs.disasm(code, 0x000469b0):
    print(f"0x{insn.address:06x}: {insn.mnemonic:8s} {insn.op_str}")

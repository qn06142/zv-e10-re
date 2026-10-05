from pathlib import Path
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

with open(lib_path, "rb") as f:
    # Let's inspect 0x2cca00 to 0x2ccf00
    start = 0x2cca00
    length = 0x2ccef0 - start
    f.seek(start)
    code = f.read(length)
    for insn in cs.disasm(code, start):
        # Look for function prologues (push {..., lr})
        note = ""
        if insn.mnemonic == "push" and "lr" in insn.op_str:
            note = "<--- PROLOGUE?"
        elif insn.mnemonic in ["pop", "bx", "b.w", "b"] and ("pc" in insn.op_str or "lr" in insn.op_str):
            note = "<--- EPILOGUE?"
        print(f"0x{insn.address:06x}:  {insn.mnemonic:10s} {insn.op_str:30s} {note}")

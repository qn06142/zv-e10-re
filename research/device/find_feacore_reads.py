from pathlib import Path
import struct
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_mpr_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libmpr.so"

with open(lib_mpr_path, "rb") as f:
    data = f.read()

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

print("=== Searching for reads of 0x16d8 in libmpr.so ===")
# 0x16d8 or nearby in [rX, #0x16d8] or [rX + 0x16c0]
for p in range(0x540000, 0x560000, 2):
    hw1 = struct.unpack_from("<H", data, p)[0]
    # Check for LDR with offset 0x16d8 or add with 0x16c0
    if p + 4 <= len(data):
        hw2 = struct.unpack_from("<H", data, p + 2)[0]
        # ADD.W rX, rY, #0x16c0 -> e28y x6c0 or similar
        # Let's just disassemble with capstone
        insns = list(cs.disasm(data[p:p+4], p))
        if insns:
            ins = insns[0]
            if "16c0" in ins.op_str or "16d8" in ins.op_str:
                print(f"0x{ins.address:06x}: {ins.mnemonic:8s} {ins.op_str}")

from pathlib import Path
import struct
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_mprctrl_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libmprctrl.so"

with open(lib_mprctrl_path, "rb") as f:
    data = f.read()

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
for insn in cs.disasm(data[0x24a1c:0x24a54], 0x24a1c):
    print(f"0x{insn.address:06x}: {insn.mnemonic:8s} {insn.op_str}")

# Check table for CnvStillAspect
rel_off = struct.unpack_from("<I", data, 0x24a34)[0]
table_addr = 0x24a26 + 4 + rel_off
print(f"rel_off = 0x{rel_off:x}, table_addr = 0x{table_addr:06x}")
for i in range(5):
    entry = struct.unpack_from("<I", data, table_addr + i*4)[0]
    print(f"  [{i}] -> {entry}")

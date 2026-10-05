import capstone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
libobj = (HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so").read_bytes()
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

for ins in cs.disasm(libobj[0x52fcd8:0x52fd80], 0x52fcd8):
    print(f"0x{ins.address:06x}: {ins.mnemonic:10s} {ins.op_str}")

import capstone
from pathlib import Path
from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent.parent.parent
libobj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

with open(libobj_path, "rb") as f:
    elf = ELFFile(f)
    # Read function at 0x2ccdc0
    f.seek(0x2ccdc0)
    code = f.read(0x300)
    print("=== Disassembly of InfraMovieEncoderSeqEncStart2Astra (0x2ccdc0) ===")
    for insn in cs.disasm(code, 0x2ccdc0):
        print(f"  0x{insn.address:06x}: {insn.mnemonic:10s} {insn.op_str}")
        if insn.mnemonic == 'pop' and 'pc' in insn.op_str:
            break

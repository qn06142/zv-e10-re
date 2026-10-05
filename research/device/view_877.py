import capstone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
av = (HERE / "dumps" / "av-cam.bin").read_bytes()
base = 0x635c6000
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

start = 0x00877380
end = 0x00877420

for insn in cs.disasm(av[start:end], start):
    print(f"0x{insn.address:08x} (VA 0x{base+insn.address:08x}): {insn.mnemonic:10s} {insn.op_str}")

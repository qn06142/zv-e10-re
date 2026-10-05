with open('dumps/av-cam.bin', 'rb') as f:
    av = f.read()
import capstone

AVCAM_BASE = 0x635c6000
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

slots = [
    (0, 0x63645f60),
    (4, 0x63646a94),
    (6, 0x63646db4),
    (7, 0x63646e40),
    (10, 0x63646eec),
    (12, 0x63647130),
    (13, 0x636471d0),
]

for slot, addr in slots:
    print(f"=== Slot {slot} at 0x{addr:08x} ===")
    code = av[addr - AVCAM_BASE:addr - AVCAM_BASE + 60]
    for ins in cs.disasm(code, addr):
        print(f"  0x{ins.address:08x}: {ins.mnemonic:8s} {ins.op_str}")

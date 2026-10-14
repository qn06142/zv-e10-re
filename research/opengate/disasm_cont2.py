import capstone

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
with open('dumps/camera_2025/usr/usr/lib/libObj.so', 'rb') as f:
    f.seek(0x2ccc6e)
    data = f.read(0x200)

for i in cs.disasm(data, 0x2ccc6e):
    print(f"0x{i.address:06x}: {i.mnemonic:10s} {i.op_str}")

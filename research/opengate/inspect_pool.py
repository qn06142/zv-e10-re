with open('dumps/camera_2025/usr/usr/lib/libObj.so', 'rb') as f:
    f.seek(0x2ccc40)
    data = f.read(80)
    for off in range(0, len(data), 4):
        addr = 0x2ccc40 + off
        val = int.from_bytes(data[off:off+4], 'little')
        # relative offset from pc
        pc = (addr + 4) & ~1
        target = pc + val
        s_val = ''
        if 0 < target < 0x800000:
            pos = f.tell()
            f.seek(target)
            s_val = f.read(64).split(b'\x00')[0].decode('ascii', errors='ignore')
            f.seek(pos)
        print(f"0x{addr:08x}: rel 0x{val:08x} -> 0x{target:08x}: '{s_val}'")

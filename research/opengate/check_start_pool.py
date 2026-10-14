with open('dumps/camera_2025/usr/usr/lib/libObj.so', 'rb') as f:
    f.seek(0x2cd520)
    data = f.read(128)
    for off in range(0, len(data), 4):
        addr = 0x2cd520 + off
        val = int.from_bytes(data[off:off+4], 'little', signed=True)
        target = addr + 4 + val
        s = ''
        if 0 < target < 0x2000000:
            pos = f.tell()
            try:
                f.seek(target)
                raw = f.read(64).split(b'\x00')[0]
                s = raw.decode('latin1', errors='ignore')
            except:
                pass
            f.seek(pos)
        print(f"0x{addr:06x}: val=0x{val & 0xffffffff:08x} target=0x{target:06x} '{s}'")

from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

offsets = [
    0x10ea86b, 0x10ea8b4, 0x10ea901, 0x10f116d, 0x10f1238, 0x10f1313,
    0x1124e55, 0x1151e67, 0x1151ebc, 0x1152341, 0x115239c, 0x118dc70
]

for off in offsets:
    s = data[off:off+60].split(b'\x00')[0].decode('ascii')
    print(f"0x{off:07x}: \"{s}\"")
    # Find pointers to off in data
    tb = struct.pack('<I', off)
    ptrs = []
    pos = 0
    while True:
        idx = data.find(tb, pos)
        if idx == -1: break
        ptrs.append(idx)
        pos = idx + 1
    print(f"  Pointers to 0x{off:07x}: {len(ptrs)} found: {list(map(hex, ptrs))}")

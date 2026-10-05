from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

target = 0x260a70
callers = []

for off in range(0, len(data) - 4, 2):
    hw1 = struct.unpack('<H', data[off:off+2])[0]
    if (hw1 & 0xf800) == 0xf000:
        hw2 = struct.unpack('<H', data[off+2:off+4])[0]
        if (hw2 & 0xd000) == 0xd000:
            s = (hw1 >> 10) & 1
            imm10 = hw1 & 0x3ff
            j1 = (hw2 >> 13) & 1
            j2 = (hw2 >> 11) & 1
            imm11 = hw2 & 0x7ff
            i1 = ~(j1 ^ s) & 1
            i2 = ~(j2 ^ s) & 1
            offset = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
            if s: offset -= (1 << 25)
            curr_pc = off + 4
            dest = curr_pc + offset
            if dest == target:
                callers.append(off)

print(f"Found {len(callers)} BL callers to ObjRenderer::CalcRatio (0x{target:06x}):")
for c in callers:
    print(f"  Caller at 0x{c:06x}")

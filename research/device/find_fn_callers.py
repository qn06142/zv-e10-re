from pathlib import Path
import struct
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

# Scan backwards from 0x261700 to find push {..., lr}
target = None
for p in range(0x261700, 0x261400, -2):
    hw = struct.unpack_from("<H", data, p)[0]
    if (hw & 0xff00) == 0xb500 or hw == 0xe92d: # PUSH {..., lr}
        print(f"Function starts at 0x{p:06x}")
        target = p
        break

# Find callers of target
callers = []
for off in range(0, len(data) - 4, 2):
    hw1 = struct.unpack_from('<H', data[off:off+2])[0]
    if (hw1 & 0xf800) == 0xf000:
        hw2 = struct.unpack_from('<H', data[off+2:off+4])[0]
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

print(f"Found {len(callers)} callers to 0x{target:06x}:")
for c in callers:
    print(f"  0x{c:06x}")

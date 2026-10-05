from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent.parent.parent
avcam_path = HERE / "dumps" / "av-cam.bin"
AVCAM_BASE = 0x635c6000

with open(avcam_path, "rb") as f:
    avcam = f.read()

target = 0x63cb3dca
callers = []

for off in range(0, len(avcam) - 4, 2):
    hw1 = struct.unpack('<H', avcam[off:off+2])[0]
    if (hw1 & 0xf800) == 0xf000:
        hw2 = struct.unpack('<H', avcam[off+2:off+4])[0]
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
            curr_pc = AVCAM_BASE + off + 4
            dest = curr_pc + offset
            if dest == target:
                callers.append(AVCAM_BASE + off)

print(f"Found {len(callers)} BL callers to 0x63cb3dca:")
for c in callers:
    print(f"  Caller VA 0x{c:08x}")

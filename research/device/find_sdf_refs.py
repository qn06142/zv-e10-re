from pathlib import Path
import struct
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
avcam_path = HERE / "dumps" / "av-cam.bin"
AVCAM_BASE = 0x635c6000

data = avcam_path.read_bytes()

target_va = 0x63f3b133
target_off = target_va - AVCAM_BASE
target_bytes = struct.pack("<I", target_va)

# Search for direct literal pool pointer or PC-relative offset
pos = 0
found_pool = []
while True:
    idx = data.find(target_bytes, pos)
    if idx == -1: break
    found_pool.append(idx)
    pos = idx + 1

print(f"Direct references to 0x{target_va:08x}:")
for off in found_pool:
    va = AVCAM_BASE + off
    print(f"  Pool at file 0x{off:08x} (VA 0x{va:08x})")

# Also search for relative offset
for p in range(0, len(data) - 4, 4):
    val = struct.unpack_from("<I", data, p)[0]
    # Check if p + val + 4 == target_va
    if (AVCAM_BASE + p + 4 + val) == target_va:
        print(f"  PC-relative at file 0x{p:08x} (VA 0x{AVCAM_BASE+p:08x})")

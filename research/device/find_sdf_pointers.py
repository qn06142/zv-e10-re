from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent.parent.parent
avcam_path = HERE / "dumps" / "av-cam.bin"
AVCAM_BASE = 0x635c6000

data = avcam_path.read_bytes()

# Search for any 32-bit word pointing into 0x63f3b000 - 0x63f3b300
low_va = 0x63f3b000
high_va = 0x63f3b400

print(f"Scanning for pointers in range 0x{low_va:08x} - 0x{high_va:08x}...")
for p in range(0, len(data) - 4, 4):
    w = struct.unpack_from("<I", data, p)[0]
    if low_va <= w <= high_va:
        va = AVCAM_BASE + p
        print(f"  Word at file 0x{p:08x} (VA 0x{va:08x}) -> 0x{w:08x}")

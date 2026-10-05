with open('dumps/av-cam.bin', 'rb') as f:
    av = f.read()
import struct
import capstone

AVCAM_BASE = 0x635c6000
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

# Target string file offset: 0x0094ef1a
# Let's search for relative PC references or literal loads around 0x940000 - 0x950000
target_va = AVCAM_BASE + 0x0094ef1a
print(f"Target VA for scanMode log: 0x{target_va:08x}")

# Scan for any literal word containing target_va or close to it
for off in range(0, len(av) - 4, 4):
    w = struct.unpack_from('<I', av, off)[0]
    if abs(w - target_va) < 0x200:
        va = AVCAM_BASE + off
        print(f"Direct pool at file 0x{off:08x} (VA 0x{va:08x}) -> 0x{w:08x}")

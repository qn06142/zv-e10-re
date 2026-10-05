with open('dumps/av-cam.bin', 'rb') as f:
    av = f.read()
import struct

AVCAM_BASE = 0x635c6000
str_va = 0x63f40fec # 25ModuleCalcAspectImageArea

# Find 32-bit pointer to str_va in av-cam.bin
matches = []
target_bytes = struct.pack('<I', str_va)
pos = 0
while True:
    idx = av.find(target_bytes, pos)
    if idx == -1: break
    va = AVCAM_BASE + idx
    matches.append(va)
    pos = idx + 1

print(f"Pointers to '25ModuleCalcAspectImageArea' (0x{str_va:08x}):")
for m in matches:
    print(f"  at 0x{m:08x}")
    # In std::type_info, the pointer to name is at offset +4.
    # So typeinfo struct begins at m - 4!
    ti_va = m - 4
    print(f"    typeinfo at 0x{ti_va:08x}")
    # Now find pointers to ti_va! (which are vtable[-1])
    ti_bytes = struct.pack('<I', ti_va)
    pos2 = 0
    vtables = []
    while True:
        idx2 = av.find(ti_bytes, pos2)
        if idx2 == -1: break
        vt_va = AVCAM_BASE + idx2 + 4 # vtable starts after typeinfo pointer
        vtables.append(vt_va)
        pos2 = idx2 + 1
    print(f"    vtables pointing to typeinfo:")
    for vt in vtables:
        print(f"      vtable at 0x{vt:08x}")
        # Print first 10 methods in this vtable
        print("      methods:")
        for s in range(10):
            fn = struct.unpack_from('<I', av, (vt + s*4) - AVCAM_BASE)[0]
            print(f"        slot[{s}]: 0x{fn:08x}")

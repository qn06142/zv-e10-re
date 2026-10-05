import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
av = (HERE / "dumps" / "av-cam.bin").read_bytes()
base = 0x635c6000
vtable_va = 0x645739b0
vtable_off = vtable_va - base

print(f"=== CdSeqCtrlEnc vtable at file offset 0x{vtable_off:08x} (VA 0x{vtable_va:08x}) ===")
for i in range(40):
    entry_va = struct.unpack_from('<I', av, vtable_off + i*4)[0]
    entry_off = entry_va - base
    if 0 <= entry_off < len(av):
        print(f"  [{i:2d}] VA 0x{entry_va:08x} (file off 0x{entry_off:08x})")
    else:
        print(f"  [{i:2d}] VA 0x{entry_va:08x} (out of bounds)")

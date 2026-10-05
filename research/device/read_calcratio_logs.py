import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

def read_str(addr):
    if addr < 0 or addr >= len(data): return None
    end = data.find(b'\x00', addr)
    if end != -1 and end > addr:
        chunk = data[addr:end]
        if all(32 <= b < 127 for b in chunk): return chunk.decode('ascii')
    return None

for p in range(0x260a70, 0x260d20, 2):
    hw1 = struct.unpack_from("<H", data, p)[0]
    # Check for LDR r3, [pc, #imm] followed eventually by add r3, pc
    if (hw1 & 0xf800) == 0x4800:
        imm = (hw1 & 0xff) * 4
        tgt = (p & ~3) + 4 + imm
        val = struct.unpack_from("<I", data, tgt)[0]
        # check if (p + 8) + 4 + val is valid string
        for offset_after in [2, 4, 6, 8, 10, 12, 14, 16]:
            s_addr = (p + offset_after) + 4 + val
            s = read_str(s_addr)
            if s and "[ObjRenderer]" in s:
                print(f"0x{p:06x} -> 0x{s_addr:08x}: \"{s}\"")
                break

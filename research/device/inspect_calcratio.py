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

print("=== Strings / Constants in ObjRenderer::CalcRatio ===")
# Check PC relative loads from 0x260a70 to 0x260d20
for p in range(0x260a70, 0x260d20, 2):
    hw = struct.unpack_from("<H", data, p)[0]
    # LDR r3, [pc, #imm]
    if (hw & 0xf800) == 0x4800:
        imm = (hw & 0xff) * 4
        tgt = (p & ~3) + 4 + imm
        val = struct.unpack_from("<I", data, tgt)[0]
        # check if it's add r3, pc
        hw_next = struct.unpack_from("<H", data, p + 2)[0]
        if hw_next == 0x447b: # add r3, pc
            s_addr = (p + 2) + 4 + val
            s = read_str(s_addr)
            print(f"0x{p:06x}: string -> \"{s}\"")
    # VLDR d6, [pc, #imm] -> 0xed9f ...
    hw2 = struct.unpack_from("<H", data, p)[0]
    if hw2 == 0xed9f or hw2 == 0xeddf:
        hw_imm = struct.unpack_from("<H", data, p + 2)[0]
        imm = (hw_imm & 0xff) * 4
        tgt = (p & ~3) + 4 + imm
        f64 = struct.unpack_from("<d", data, tgt)[0]
        print(f"0x{p:06x}: double -> {f64}")

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

print("=== Command Table around 0x01391a98 ===")
for p in range(0x01391a00, 0x01391b50, 4):
    val = struct.unpack_from("<I", data, p)[0]
    # Check if val is a code pointer (Thumb or ARM)
    code_fn = val & ~1
    if 0x100000 <= code_fn < 0xe00000:
        # Check if first instruction has a log string
        print(f"0x{p:07x}: 0x{val:08x} -> code at 0x{code_fn:06x}")
    else:
        s = read_str(val)
        if s:
            print(f"0x{p:07x}: 0x{val:08x} -> \"{s}\"")
        else:
            print(f"0x{p:07x}: 0x{val:08x}")

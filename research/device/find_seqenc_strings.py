from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent.parent.parent
lib_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_path, "rb") as f:
    data = f.read()

def read_str(addr):
    if addr < 0 or addr >= len(data):
        return f"<invalid 0x{addr:x}>"
    end = data.find(b'\x00', addr)
    if end != -1:
        try:
            return data[addr:end].decode('utf-8', errors='replace')
        except:
            return f"<raw: {data[addr:min(addr+40, len(data))].hex()}>"
    return "<no null>"

# Look at PC-relative literal pools in 0x2cca00..0x2cd100
for pc in range(0x2cca00, 0x2cd100, 2):
    # Check if there is an ldr rX, [pc, #imm]
    val = struct.unpack_from("<H", data, pc)[0]
    # Thumb LDR literal: 0100 1xxx iiii iiii -> 0x4800 | (rt << 8) | imm8
    if (val & 0xf800) == 0x4800:
        rt = (val >> 8) & 7
        imm8 = (val & 0xff) * 4
        target_addr = (pc & ~3) + 4 + imm8
        target_val = struct.unpack_from("<I", data, target_addr)[0]
        # check if target_val is an offset or pointer
        # If it's add rX, pc following it:
        # e.g., 0x2ccade: add r3, pc
        str_val = ""
        # if target_val is string pointer:
        if 0 < target_val < len(data):
            s = read_str(target_val)
            if len(s) > 1 and all(32 <= ord(c) < 127 for c in s[:10]):
                str_val = f"-> PTR string: '{s}'"
        # or if target_addr + target_val (relative string)
        # Often: ldr r3, [pc, #imm]; add r3, pc
        # Let's inspect the next instruction:
        next_insn = struct.unpack_from("<H", data, pc + 2)[0]
        # ADD (register) thumb: 44xx
        # e.g. add r3, pc
        if (next_insn & 0xff00) == 0x4400: # ADD
            rm = (next_insn >> 3) & 0xf
            rdn = (next_insn & 7) | ((next_insn >> 4) & 8)
            if rm == 15: # PC
                rel_target = (pc + 2) + 4 + target_val
                s2 = read_str(rel_target)
                if len(s2) > 1 and all(32 <= ord(c) < 127 for c in s2[:10]):
                    str_val = f"-> REL string: '{s2}'"
        if str_val:
            print(f"0x{pc:06x}: ldr r{rt}, [pc, #0x{imm8:x}] ({target_val:#x}) {str_val}")

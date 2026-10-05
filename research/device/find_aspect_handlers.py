from pathlib import Path
import struct
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
cs.detail = True

targets = [
    ("UNKNOWN[0x%04x]", 0x1151e67),
    ("is NULL", 0x1151ebc),
    ("PROXY UNKNOWN", 0x1152341),
    ("UNKNOWN #####", 0x118dc70),
    ("ACT is NULL", 0x1124e55),
]

for name, s_addr in targets:
    print(f"\n=== References to '{name}' (0x{s_addr:07x}) ===")
    # In Thumb PIC, the offset from instruction to s_addr is stored in a literal pool
    # Scan .text (0x10fee0 to 0xe4af08)
    for p in range(0x10fee0, 0xe4af00, 2):
        hw = struct.unpack_from("<H", data, p)[0]
        if (hw & 0xf800) == 0x4800: # LDR rX, [pc, #imm]
            imm = (hw & 0xff) * 4
            tgt = (p & ~3) + 4 + imm
            if tgt + 4 <= len(data):
                val = struct.unpack_from("<I", data, tgt)[0]
                # Check if add rX, pc follows
                # check next 1-4 instructions
                for after in [2, 4, 6, 8]:
                    hw2 = struct.unpack_from("<H", data, p + after)[0]
                    if (hw2 & 0xff00) == 0x4400: # ADD
                        rm = (hw2 >> 3) & 0xf
                        if rm == 15: # PC
                            resolved = (p + after + 4) + val
                            if resolved == s_addr:
                                print(f"  Found reference from 0x{p+after:06x} (LDR at 0x{p:06x})")
                                # Walk back to prologue
                                fn = p
                                for back in range(p, max(0x10fee0, p - 0x400), -2):
                                    hwb = struct.unpack_from("<H", data, back)[0]
                                    if (hwb & 0xff00) == 0xb500 or hwb == 0xe92d:
                                        fn = back
                                        break
                                print(f"    Function starts at 0x{fn:06x}")
                                # Disassemble 20 instructions around reference
                                code = data[p-10:p+40]
                                for ins in cs.disasm(code, p-10):
                                    print(f"      0x{ins.address:06x}: {ins.mnemonic:8s} {ins.op_str}")
                                break

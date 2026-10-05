from pathlib import Path
import struct
import capstone

HERE = Path(__file__).resolve().parent.parent.parent
lib_obj_path = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libObj.so"

with open(lib_obj_path, "rb") as f:
    data = f.read()

target_str = b"[ProcEnterRec] Call"
str_off = data.find(target_str)
print(f"String '[ProcEnterRec] Call' at 0x{str_off:06x}")

# Find PC relative loads or references to str_off
cs = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)

for p in range(0x600000, 0xe4af00, 2):
    hw = struct.unpack_from("<H", data, p)[0]
    if (hw & 0xf800) == 0x4800:
        imm = (hw & 0xff) * 4
        tgt = (p & ~3) + 4 + imm
        if tgt + 4 <= len(data):
            val = struct.unpack_from("<I", data, tgt)[0]
            # check if p + 4 + 4 + val == str_off or similar
            for after in [2, 4, 6]:
                hw2 = struct.unpack_from("<H", data, p + after)[0]
                if (hw2 & 0xff00) == 0x4400 and ((hw2 >> 3) & 0xf) == 15:
                    if (p + after + 4) + val == str_off:
                        print(f"Referenced from 0x{p+after:06x}")
                        # Walk back to function start
                        fn = p
                        for back in range(p, max(0x100000, p - 0x600), -2):
                            hwb = struct.unpack_from("<H", data, back)[0]
                            if (hwb & 0xff00) == 0xb500 or hwb == 0xe92d:
                                fn = back
                                break
                        print(f"  Function starts at 0x{fn:06x}")
                        # Disassemble first 40 instructions
                        for ins in cs.disasm(data[fn:fn+80], fn):
                            print(f"    0x{ins.address:06x}: {ins.mnemonic:8s} {ins.op_str}")
                        break

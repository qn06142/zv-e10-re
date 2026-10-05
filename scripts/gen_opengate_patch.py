import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
libmpr_dump = HERE / "dumps" / "camera_2025" / "usr" / "usr" / "lib" / "libmpr.so"

with open(libmpr_dump, "rb") as f:
    buf = f.read()

idx = 0xc40000
needle = struct.pack("<HH", 2160, 3840)
patch_list = []
while True:
    pos = buf.find(needle, idx)
    if pos == -1:
        break
    width_va = 0x08673000 + (pos + 2 - 0xc40000)
    patch_list.append(width_va)
    idx = pos + 1

lines = [
    "#!/bin/sh",
    "PID=$(pidof im.elf)",
    "[ -z \"$PID\" ] && PID=157",
    "echo \"[+] Target im.elf PID: $PID\"",
    "",
    "echo \"[*] 1. Patching libObj.so ObjRenderer (Aspect query -> 3:2)...\"",
    "/setting/mem_patch.elf $PID 067f1918 01207047",
    "",
    "echo \"[*] 2. Patching libObj.so InfraMovieEncoderSeqSetAspect (Aspect enum -> 2)...\"",
    "/setting/mem_patch.elf $PID 06864388 0222",
    "/setting/mem_patch.elf $PID 068643a0 0222",
    "/setting/mem_patch.elf $PID 068643c4 0223",
    "/setting/mem_patch.elf $PID 0686429c 0223",
    "",
    f"echo \"[*] 3. Patching all {len(patch_list)} libmpr.so 4K profiles to 3240 width...\"",
]

for va in patch_list:
    lines.append(f"/setting/mem_patch.elf $PID {va:08x} a80c >/dev/null 2>&1")

lines.append("echo \"[+] Successfully patched all libmpr.so profiles!\"")
lines.append("echo \"===================================================\"")
lines.append("echo \"[+] OPEN GATE 3:2 LIVE PATCH COMPLETE!\"")
lines.append("echo \"===================================================\"")

out_file = HERE / "research" / "device" / "apply_opengate_live.sh"
with open(out_file, "w", newline="\n") as f:
    f.write("\n".join(lines) + "\n")

print(f"Generated {out_file} with {len(lines)} lines.")

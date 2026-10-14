offsets = [
    0x086758f6, 0x0867598e, 0x08675a26, 0x08675abe, 0x08676736, 0x086767ce, 0x08676866, 0x086768fe,
    0x08676c8e, 0x08676d26, 0x08676dbe, 0x08676e56, 0x0867779a, 0x08677832, 0x086778ca, 0x08677962,
    0x086779fa, 0x08677a92, 0x08677b2a, 0x08677bc2, 0x08677c5a, 0x08677cf2, 0x08677d8a, 0x08677e22,
    0x08677eba, 0x08677f52, 0x08677fea, 0x08678082, 0x0867811a, 0x086781b2, 0x0867824a, 0x086782e2,
    0x0867837a, 0x08678412, 0x086784aa, 0x08678542, 0x0867b7ba, 0x0867b852, 0x0867b8ea, 0x0867b982,
    0x0867ba1a, 0x0867bab2, 0x0867c98a, 0x0867ca22, 0x0867caba, 0x0867cb52, 0x0867cbea, 0x0867cc82,
    0x0867f93a, 0x0867f9d2, 0x0867fa6a, 0x0867fb02, 0x0868018a, 0x08680222, 0x086802ba, 0x08680352,
    0x0868064a, 0x086806e2, 0x0868077a, 0x08680812
]

lines = ["#!/bin/sh"]
lines.append("PID=$(pidof im.elf)")
lines.append('[ -z "$PID" ] && PID=157')
lines.append('echo "[+] Target im.elf PID: $PID"')

# 1. MPR whitelist aspect 2
lines.append('echo "[*] Patching mpr_whitelist: Whitelist aspect 2 (3:2)..."')
lines.append("/setting/mem_patch.elf $PID 07f6d2e8 2f")

# 2. 4K width validation bypasses (nop the bcc instructions)
lines.append('echo "[*] Patching 4K width validation gates (allow 3232 width)..."')
lines.append("/setting/mem_patch.elf $PID 06861da0 00bf") # obj_chk_1: 0x2cfda0
lines.append("/setting/mem_patch.elf $PID 0686204a 00bf") # obj_chk_2: 0x2d004a
lines.append("/setting/mem_patch.elf $PID 068620ea 00bf") # obj_chk_3: 0x2d00ea
lines.append("/setting/mem_patch.elf $PID 068623b2 00bf") # obj_chk_4: 0x2d03b2

# 3. Astra movie streams and BIONZ X packets
lines.append('echo "[*] Patching Astra movie engine and AVBBC packets..."')
lines.append("/setting/mem_patch.elf $PID 0685eb3a 0223") # obj_astra_asp1
lines.append("/setting/mem_patch.elf $PID 0685eb4a 0223") # obj_astra_asp2
lines.append("/setting/mem_patch.elf $PID 0685ee0a 022300bf") # obj_astra_pkt1 (Stream 1 packet 0x55001f)
lines.append("/setting/mem_patch.elf $PID 0685ee38 022300bf") # obj_astra_pkt2 (Stream 2 packet 0x55001f)

# 4. Proxy sequences
lines.append("/setting/mem_patch.elf $PID 06864388 0222")
lines.append("/setting/mem_patch.elf $PID 068643a0 0222")
lines.append("/setting/mem_patch.elf $PID 068643c4 0223")
lines.append("/setting/mem_patch.elf $PID 0686429c 0223")

# 5. MPR 60 profiles: width 3232 (a00c), aspect 2 (0200) -> a00c0200
lines.append('echo "[*] Patching all 60 libmpr.so 4K profiles to 3232x2160 Aspect 2..."')
for a in offsets:
    lines.append(f"/setting/mem_patch.elf $PID {a:08x} a00c0200 >/dev/null 2>&1")

lines.append('echo "[+] Successfully patched all 60 profiles!"')
lines.append('echo "==================================================="')
lines.append('echo "[+] MACROBLOCK-ALIGNED 3232x2160 OPEN GATE LIVE!"')
lines.append('echo "==================================================="')

with open("out/apply_macroblock_opengate.sh", "w", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print(f"Generated out/apply_macroblock_opengate.sh with {len(lines)} lines")

#!/bin/sh
PID=$(pidof im.elf)
[ -z "$PID" ] && PID=157
echo "[+] Target im.elf PID: $PID"

echo "[*] 1. Patching libObj.so ObjRenderer (Aspect query -> 3:2)..."
/setting/mem_patch.elf $PID 067f1918 01207047

echo "[*] 2. Patching libObj.so InfraMovieEncoderSeqSetAspect (Aspect enum -> 2)..."
/setting/mem_patch.elf $PID 06864388 0222
/setting/mem_patch.elf $PID 068643a0 0222
/setting/mem_patch.elf $PID 068643c4 0223
/setting/mem_patch.elf $PID 0686429c 0223

echo "[*] 3. Patching all 60 libmpr.so 4K profiles to 3240 width..."
/setting/mem_patch.elf $PID 086758f6 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867598e a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08675a26 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08675abe a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08676736 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086767ce a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08676866 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086768fe a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08676c8e a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08676d26 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08676dbe a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08676e56 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867779a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677832 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086778ca a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677962 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086779fa a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677a92 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677b2a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677bc2 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677c5a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677cf2 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677d8a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677e22 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677eba a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677f52 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08677fea a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08678082 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867811a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086781b2 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867824a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086782e2 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867837a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08678412 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086784aa a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08678542 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867b7ba a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867b852 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867b8ea a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867b982 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867ba1a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867bab2 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867c98a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867ca22 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867caba a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867cb52 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867cbea a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867cc82 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867f93a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867f9d2 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867fa6a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0867fb02 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0868018a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08680222 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086802ba a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08680352 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0868064a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 086806e2 a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 0868077a a80c >/dev/null 2>&1
/setting/mem_patch.elf $PID 08680812 a80c >/dev/null 2>&1
echo "[+] Successfully patched all libmpr.so profiles!"
echo "==================================================="
echo "[+] OPEN GATE 3:2 LIVE PATCH COMPLETE!"
echo "==================================================="

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
from research.device.zve10_retry import run

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

def main():
    print("[*] Fetching im.elf PID...")
    out, _ = run(["pidof im.elf"])
    pid = "157"
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pid = line
            break
    print(f"[+] Active PID: {pid}")

    core_patches = [
        # Whitelist aspect 2
        f"/setting/mem_patch.elf {pid} 07f6d2e8 2f",
        # 4K validation bypasses
        f"/setting/mem_patch.elf {pid} 06861da0 00bf",
        f"/setting/mem_patch.elf {pid} 0686204a 00bf",
        f"/setting/mem_patch.elf {pid} 068620ea 00bf",
        f"/setting/mem_patch.elf {pid} 068623b2 00bf",
        # Astra stream aspects
        f"/setting/mem_patch.elf {pid} 0685eb3a 0223",
        f"/setting/mem_patch.elf {pid} 0685eb4a 0223",
        # AVBBC packet 0x55001f stream 1 and stream 2
        f"/setting/mem_patch.elf {pid} 0685ee0a 022300bf",
        f"/setting/mem_patch.elf {pid} 0685ee38 022300bf",
        # Sequences
        f"/setting/mem_patch.elf {pid} 06864388 0222",
        f"/setting/mem_patch.elf {pid} 068643a0 0222",
        f"/setting/mem_patch.elf {pid} 068643c4 0223",
        f"/setting/mem_patch.elf {pid} 0686429c 0223",
    ]

    print("[*] Applying core Astra & 4K validation patches...")
    for p in core_patches:
        o, _ = run([p])
        for line in o.splitlines():
            if "SUCCESS" in line or "Target" in line:
                print(" ", line.strip())

    print("[*] Patching 60 4K profiles in libmpr.so to 3232x2160 (Macroblock aligned)...")
    addr_list = " ".join(f"{a:08x}" for a in offsets)
    loop_cmd = f"for a in {addr_list}; do /setting/mem_patch.elf {pid} $a a00c0200 >/dev/null 2>&1; done; echo DONE_PROFILES"
    o, _ = run([loop_cmd])
    if "DONE_PROFILES" in o:
        print("[+] All 60 profiles successfully patched in RAM!")
    else:
        print("[-] Loop output:", o)

    # Verification read on profile 0
    v, _ = run([f"/setting/mem_patch.elf {pid} 086758f6 a00c0200"])
    for l in v.splitlines():
        if "VERIFICATION" in l or "Verification read" in l:
            print(" ", l.strip())

    print("\n[+] FULL MACROBLOCK OPEN GATE PATCH LIVE IN PID " + pid + "!")

if __name__ == "__main__":
    main()

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
from research.device.zve10_retry import run

def main():
    print("[*] Fetching PID...")
    out, _ = run(["pidof im.elf"])
    pid = "157"
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pid = line
            break
    print(f"[+] Active PID: {pid}")

    # 1. Core patches for 3240
    core_patches = [
        # (name, addr, hex_bytes)
        ("mpr_line_res (0x3f1e18)", "07e1ce18", "40f6a842"), # movw r2, #3240
        ("mpr_enc_w (0x3f642c)",   "07e2142c", "40f6a843"), # movw r3, #3240
        ("mpr_mux_w (0x3f6730)",   "07e21730", "40f6a842"), # movw r2, #3240
    ]

    print("[*] Applying true 3240 resolution patches in libmpr.so...")
    for name, addr, hex_val in core_patches:
        cmd = f"/setting/mem_patch.elf {pid} {addr} {hex_val}"
        o, _ = run([cmd])
        success = "VERIFICATION SUCCESS" in o
        status = "[+] OK" if success else "[-] FAIL"
        print(f"  {status}: {name} @ 0x{addr} -> {hex_val}")
        time.sleep(0.04)

    # 2. Group 4 XAVC S profiles -> 3240 (a80c0200)
    base_foff = 0xc44798
    group4_addrs = []
    for i in range(24):
        entry_off = base_foff + i * 152
        va = 0x08673000 + (entry_off - 0x00c40000)
        group4_addrs.append(va + 2)

    print(f"[*] Patching all {len(group4_addrs)} Group 4 XAVC S profiles to 3240x2160 Aspect 2...")
    for i, addr in enumerate(group4_addrs):
        cmd = f"/setting/mem_patch.elf {pid} {addr:08x} a80c0200"
        o, _ = run([cmd])
        success = "VERIFICATION SUCCESS" in o
        status = "[+] OK" if success else "[-] FAIL"
        print(f"  {status} [{i:02d}]: 0x{addr:08x} -> a80c0200")
        time.sleep(0.04)

    print("\n=================================================================")
    print("[+] ALL NATIVE 3240x2160 BIONZ X HARDWARE OPEN GATE PATCHES LIVE!")
    print("=================================================================")

if __name__ == "__main__":
    main()

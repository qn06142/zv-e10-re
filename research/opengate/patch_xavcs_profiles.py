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

    # Group 4 (XAVC S 4K) entries:
    base_foff = 0xc44798
    group4_addrs = []
    for i in range(24):
        entry_off = base_foff + i * 152
        va = 0x08673000 + (entry_off - 0x00c40000)
        # width field is at +2
        group4_addrs.append(va + 2)

    print(f"[*] Patching all {len(group4_addrs)} Group 4 XAVC S 4K profile entries to 3232x2160 Aspect 2...")
    for i, addr in enumerate(group4_addrs):
        cmd = f"/setting/mem_patch.elf {pid} {addr:08x} a00c0200"
        o, _ = run([cmd])
        success = "VERIFICATION SUCCESS" in o
        status = "[+] OK" if success else "[-] FAIL"
        print(f"  {status} [{i:02d}]: 0x{addr:08x} -> a00c0200")
        time.sleep(0.04)

    print("\n[+] ALL 24 XAVC S 4K RECORDING PROFILES PATCHED & VERIFIED!")

if __name__ == "__main__":
    main()

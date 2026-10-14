import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
from research.device.zve10_retry import run

def main():
    print("[*] Checking im.elf PID...")
    out, _ = run(["pidof im.elf"])
    pid = "157"
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pid = line
            break
    print(f"[+] im.elf PID is {pid}")

    patches = [
        # (name, addr, hex_bytes)
        ("mpr_whitelist", "07f6d2e8", "2f"),
        ("obj_chk_1 (0x2cfda0)", "06861da0", "00bf"),
        ("obj_chk_2 (0x2d004a)", "0686204a", "00bf"),
        ("obj_chk_3 (0x2d00ea)", "068620ea", "00bf"),
        ("obj_chk_4 (0x2d03b2)", "068623b2", "00bf"),
        ("obj_astra_asp1", "0685eb3a", "0223"),
        ("obj_astra_asp2", "0685eb4a", "0223"),
        ("obj_astra_pkt1", "0685ee0a", "022300bf"),
        ("obj_astra_pkt2", "0685ee38", "022300bf"),
        ("obj_seq_1", "06864388", "0222"),
        ("obj_seq_2", "068643a0", "0222"),
        ("obj_seq_3", "068643c4", "0223"),
        ("obj_seq_4", "0686429c", "0223"),
        # Top 4K profiles: 24p 100M, 24p 60M, 30p 100M, 30p 60M
        ("profile_4k_24p_100m", "086758f6", "a00c0200"),
        ("profile_4k_24p_60m",  "0867598e", "a00c0200"),
        ("profile_4k_30p_100m", "08675a26", "a00c0200"),
        ("profile_4k_30p_60m",  "08675abe", "a00c0200"),
    ]

    print(f"[*] Applying {len(patches)} targeted macroblock Open Gate patches...")
    for name, addr, hex_val in patches:
        cmd = f"/setting/mem_patch.elf {pid} {addr} {hex_val}"
        o, _ = run([cmd])
        success = False
        for line in o.splitlines():
            if "VERIFICATION SUCCESS" in line:
                success = True
                break
        status = "[+] OK" if success else "[-] FAILED"
        print(f"  {status}: {name} @ 0x{addr} -> {hex_val}")
        time.sleep(0.05)

    print("\n=======================================================")
    print("[+] ALL TARGET 4K OPEN GATE PATCHES APPLIED & VERIFIED!")
    print("=======================================================")

if __name__ == "__main__":
    main()

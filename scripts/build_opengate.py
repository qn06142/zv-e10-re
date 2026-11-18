#!/usr/bin/env python3
"""
Build & Staging Script for Sony ZV-E10 Open Gate Hook (opengate.so)
Compiles research/device/opengate_hook.c using ARM GCC against target glibc.
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CC = os.environ.get("CC") or shutil.which("arm-none-eabi-gcc") or shutil.which("arm-linux-gnueabihf-gcc") or r"C:\msys64\ucrt64\bin\arm-none-eabi-gcc.EXE"
SRC = ROOT / "research" / "device" / "opengate_hook.c"
OUT_DIR = ROOT / '.local/out'
OUT_SO = OUT_DIR / "opengate.so"
STAGED_DIR = ROOT / '.local/dumps' / "staged" / "opengate"
STAGED_SO = STAGED_DIR / "opengate.so"
SYSROOT_LIB = ROOT / '.local/build_sysroot' / "lib"


def hash_file(path: str | Path) -> tuple[str, str]:
    with open(path, "rb") as f:
        data = f.read()
    md5 = hashlib.md5(data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    return md5, sha256


def main():
    print("=== Building Sony ZV-E10 Open Gate Hook (opengate.so) ===")

    if not os.path.exists(CC):
        print(f"[-] Cross-compiler not found at {CC}")
        sys.exit(1)

    if not os.path.exists(SRC):
        print(f"[-] Source file not found: {SRC}")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STAGED_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(CC),
        "-mcpu=cortex-a7",
        "-mthumb",
        "-mfloat-abi=softfp",
        "-mfpu=vfpv3-d16",
        "-O2",
        "-fPIC",
        "-shared",
        "-nostartfiles",
        "-Wl,-soname,opengate.so",
        f"-L{SYSROOT_LIB}",
        "-lc",
        "-o",
        str(OUT_SO),
        str(SRC),
    ]

    print(f"[*] Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("[-] Compilation failed:")
        print(res.stderr)
        sys.exit(res.returncode)

    print("[+] Successfully compiled .local/out/opengate.so")

    # Copy to staging
    shutil.copyfile(OUT_SO, STAGED_SO)
    print(f"[+] Staged to {STAGED_SO}")

    md5, sha256 = hash_file(STAGED_SO)
    size = os.path.getsize(STAGED_SO)
    print(f"[+] Size:   {size} bytes ({size/1024:.2f} KB)")
    print(f"[+] MD5:    {md5}")
    print(f"[+] SHA256: {sha256}")
    print("=== Build Completed Successfully ===")


if __name__ == "__main__":
    main()

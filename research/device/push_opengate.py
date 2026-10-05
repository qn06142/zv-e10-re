"""
Transfer & Deploy Open Gate Patch to Live Sony ZV-E10 Camera
Transfers out/opengate.so and config via base64 chunks directly to /setting/
"""

import base64
import hashlib
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent.parent)]
from research.device.zve10_retry import run


def push_file_b64(local_path: str, remote_path: str, chunk_size: int = 380):
    data = Path(local_path).read_bytes()
    want_md5 = hashlib.md5(data).hexdigest()
    b64_str = base64.b64encode(data).decode("ascii")

    chunks = [b64_str[i : i + chunk_size] for i in range(0, len(b64_str), chunk_size)]
    print(f"[*] Deploying {local_path} -> {remote_path}")
    print(f"    Size: {len(data)} bytes, {len(chunks)} chunks, MD5: {want_md5}")

    tmp_b64 = f"/tmp/{Path(remote_path).name}.b64"
    cmds = [f"rm -f {tmp_b64} {remote_path}"]

    for c in chunks:
        cmds.append(f"echo -n '{c}' >> {tmp_b64}")

    cmds.append(f"busybox base64 -d {tmp_b64} > {remote_path}")
    cmds.append(f"chmod 755 {remote_path}")
    cmds.append(f"rm -f {tmp_b64}")
    cmds.append(f"busybox md5sum {remote_path}")

    out, tries = run(cmds)
    if want_md5 in out:
        print(f"[+] SUCCESS: {remote_path} deployed and MD5 verified ({want_md5})!")
        return True
    else:
        print(f"[-] FAILED to deploy {remote_path}! Output:\n{out}")
        return False


def main():
    print("==========================================================")
    print(" Deploying Open Gate 3:2 Video Unlock to Live Camera")
    print("==========================================================")

    # 1. Push opengate.so
    so_ok = push_file_b64("out/opengate.so", "/setting/opengate.so")
    if not so_ok:
        sys.exit(1)

    # 2. Push opengate.conf
    conf_ok = push_file_b64("dumps/staged/opengate/opengate.conf", "/setting/opengate.conf")
    if not conf_ok:
        sys.exit(1)

    # 3. Configure bootloader developer hooks in /setting/mode
    print("[*] Configuring developer boot hooks in /setting/mode/...")
    setup_cmds = [
        "mkdir -p /setting/mode",
        "echo '/setting/opengate.so' > /setting/mode/preload",
        "echo '3p' > /setting/mode/dmode",
        "sync",
        "ls -la /setting/opengate.so /setting/opengate.conf /setting/mode/",
        "echo 'dmode:   ' $(cat /setting/mode/dmode)",
        "echo 'preload: ' $(cat /setting/mode/preload)",
        "echo 'config:  ' $(cat /setting/opengate.conf)",
    ]

    out, tries = run(setup_cmds)
    print(out)
    if "3p" in out and "/setting/opengate.so" in out:
        print("==========================================================")
        print(" [+] OPEN GATE INSTALLATION SUCCESSFUL!")
        print(" [+] Mode: 3:2 Open Gate Full Sensor Readout (aspect=2)")
        print(" [+] Ready to reboot camera.")
        print("==========================================================")
    else:
        print("[-] Verification failed after hook setup!")


if __name__ == "__main__":
    main()

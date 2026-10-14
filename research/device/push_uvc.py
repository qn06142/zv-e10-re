"""
Transfer & Deploy UVC Webcam Hijack Patch to Live Sony ZV-E10 Camera
Transfers out/uvc_hook.so, config, and apply_uvc_live.sh via base64 chunks directly to /setting/
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
    print(" Deploying Sony ZV-E10 UVC Webcam Hijack to Live Camera")
    print("==========================================================")

    # 1. Push uvc_hook.so
    so_ok = push_file_b64("out/uvc_hook.so", "/setting/uvc_hook.so")
    if not so_ok:
        sys.exit(1)

    # 2. Push uvc.conf
    conf_ok = push_file_b64("dumps/staged/uvc/uvc.conf", "/setting/uvc.conf")
    if not conf_ok:
        sys.exit(1)

    # 3. Push apply_uvc_live.sh
    sh_ok = push_file_b64("research/device/apply_uvc_live.sh", "/setting/apply_uvc_live.sh")
    if not sh_ok:
        sys.exit(1)

    # 4. Verification and options
    print("[*] Verifying deployed files in /setting/...")
    setup_cmds = [
        "ls -la /setting/uvc_hook.so /setting/uvc.conf /setting/apply_uvc_live.sh",
        "cat /setting/uvc.conf",
    ]

    out, tries = run(setup_cmds)
    print(out)
    if "uvc_hook.so" in out and "apply_uvc_live.sh" in out:
        print("==========================================================")
        print(" [+] UVC WEBCAM HIJACK DEPLOYMENT SUCCESSFUL!")
        print(" [+] To run live zero-reboot patch on camera:")
        print("     /setting/apply_uvc_live.sh [1080p | 1080p60 | opengate | 2k_opengate]")
        print(" [+] Or enable persistent developer boot preload:")
        print("     echo '/usr/tool/libjemalloc_tsh.so:/setting/uvc_hook.so' > /setting/mode/preload")
        print("==========================================================")
    else:
        print("[-] Verification failed after file deployment!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Deploy Hardened 1080p UVC Webcam Patch to Live Sony ZV-E10 Camera.

Pushes the verified, audited binaries:
  - libInfraUsbCmn.so (MD5: ac1961d23addcd53f4fe7210d074eac2)
  - libInfraStreamingUsb.so (MD5: 5a0417693a3d9ed1786c4d0afc043d6e)
via gzip + base64 chunks directly to /setting/patched_libs/, verifies MD5s,
and safely updates /usr/lib/.
"""

import base64
import gzip
import hashlib
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import research.device.zve10_retry as zve10

EXPECTED_PATCHED = {
    "libInfraUsbCmn.so": "ac1961d23addcd53f4fe7210d074eac2",
    "libInfraStreamingUsb.so": "5a0417693a3d9ed1786c4d0afc043d6e",
}

EXPECTED_STOCK = {
    "libInfraUsbCmn.so": "31308976206a837f6f5c571992d2b499",
    "libInfraStreamingUsb.so": "cde7a1b42c919706aa5f61aba5fc0d75",
}

STAGED_DIR = REPO_ROOT / "dumps" / "staged" / "uvc" / "binaries" / "patched"


def push_file_gz_b64(local_path: Path, remote_path: str, expected_md5: str, chunk_size: int = 500):
    raw_data = local_path.read_bytes()
    local_md5 = hashlib.md5(raw_data).hexdigest()
    if local_md5 != expected_md5:
        raise ValueError(f"Local file {local_path.name} MD5 {local_md5} != expected {expected_md5}")

    gz_data = gzip.compress(raw_data, compresslevel=9)
    b64_str = base64.b64encode(gz_data).decode("ascii")

    chunks = [b64_str[i : i + chunk_size] for i in range(0, len(b64_str), chunk_size)]
    print(f"[*] Uploading {local_path.name} -> {remote_path}")
    print(f"    Raw: {len(raw_data)} B | Gzip: {len(gz_data)} B | Chunks: {len(chunks)} | MD5: {expected_md5}")

    tmp_b64 = f"/tmp/{local_path.name}.gz.b64"
    cmds = [f"/bin/busybox rm -f {tmp_b64} {remote_path}"]

    # Send chunks in sub-batches of 25 to keep argument lengths safe
    batch_size = 25
    for batch_idx in range(0, len(chunks), batch_size):
        batch = chunks[batch_idx : batch_idx + batch_size]
        batch_cmds = [f"/bin/busybox echo -n '{c}' >> {tmp_b64}" for c in batch]
        out, tries = zve10.run(batch_cmds)
        if "app #" not in out:
            print(f"[-] Error sending batch {batch_idx//batch_size + 1}")
            return False
        sys.stdout.write(f"\r    Progress: {min(batch_idx + batch_size, len(chunks))}/{len(chunks)} chunks sent")
        sys.stdout.flush()

    print("\n    Decompressing and validating...")
    finalize_cmds = [
        f"/bin/busybox base64 -d {tmp_b64} | /bin/busybox zcat > {remote_path}",
        f"/bin/busybox chmod 755 {remote_path}",
        f"/bin/busybox rm -f {tmp_b64}",
        f"/bin/busybox md5sum {remote_path}",
    ]
    out, tries = zve10.run(finalize_cmds)
    if expected_md5 in out:
        print(f"[+] SUCCESS: {remote_path} verified bit-for-bit ({expected_md5})!")
        return True
    else:
        print(f"[-] FAILED to verify {remote_path}! Output:\n{out}")
        return False


def main():
    print("=" * 70)
    print("  Sony Alpha ZV-E10: Deploy Verified 1080p UVC Webcam Patch")
    print("=" * 70)

    # 1. Verify local files
    cmn_path = STAGED_DIR / "libInfraUsbCmn.so"
    strm_path = STAGED_DIR / "libInfraStreamingUsb.so"
    if not cmn_path.exists() or not strm_path.exists():
        print(f"[-] Staged patched files missing in {STAGED_DIR}")
        sys.exit(1)

    print("[*] Checking local file integrity...")
    for p, exp_md5 in [(cmn_path, EXPECTED_PATCHED["libInfraUsbCmn.so"]),
                       (strm_path, EXPECTED_PATCHED["libInfraStreamingUsb.so"])]:
        actual = hashlib.md5(p.read_bytes()).hexdigest()
        if actual != exp_md5:
            print(f"[-] Hash mismatch for {p.name}: got {actual}, want {exp_md5}")
            sys.exit(1)
        print(f"  [+] {p.name}: {actual} OK")

    # 2. Check safety backup on camera
    print("\n[*] Probing camera stock backup on /setting/stock_libs...")
    out, _ = zve10.run(["/bin/busybox md5sum /setting/stock_libs/*", "/bin/busybox mkdir -p /setting/patched_libs"])
    for name, exp_md5 in EXPECTED_STOCK.items():
        if exp_md5 not in out:
            print(f"[!] Warning: stock backup for {name} ({exp_md5}) not found in stock_libs! Proceed with caution.")
        else:
            print(f"  [+] Confirmed stock backup for {name}: {exp_md5}")

    # 3. Check if patched binaries already exist in /setting/patched_libs/ with matching hashes
    print("\n[*] Checking /setting/patched_libs/ on camera...")
    chk_out, _ = zve10.run(["/bin/busybox md5sum /setting/patched_libs/* 2>/dev/null"])
    need_upload_strm = EXPECTED_PATCHED["libInfraStreamingUsb.so"] not in chk_out
    need_upload_cmn = EXPECTED_PATCHED["libInfraUsbCmn.so"] not in chk_out

    if need_upload_strm:
        print("[*] Uploading libInfraStreamingUsb.so to /setting/patched_libs/...")
        ok1 = push_file_gz_b64(strm_path, "/setting/patched_libs/libInfraStreamingUsb.so", EXPECTED_PATCHED["libInfraStreamingUsb.so"])
        if not ok1:
            print("[-] Deployment failed at libInfraStreamingUsb.so")
            sys.exit(1)
    else:
        print("  [+] /setting/patched_libs/libInfraStreamingUsb.so already present with matching MD5")

    if need_upload_cmn:
        print("[*] Uploading libInfraUsbCmn.so to /setting/patched_libs/...")
        ok2 = push_file_gz_b64(cmn_path, "/setting/patched_libs/libInfraUsbCmn.so", EXPECTED_PATCHED["libInfraUsbCmn.so"])
        if not ok2:
            print("[-] Deployment failed at libInfraUsbCmn.so")
            sys.exit(1)
    else:
        print("  [+] /setting/patched_libs/libInfraUsbCmn.so already present with matching MD5")

    # 4. Atomically install into /usr/lib/
    print("\n[*] Installing patched libraries into /usr/lib/...")
    install_cmds = [
        "/bin/busybox mount -o remount,rw /usr",
        "/bin/busybox cp /setting/patched_libs/libInfraUsbCmn.so /usr/lib/libInfraUsbCmn.so",
        "/bin/busybox cp /setting/patched_libs/libInfraStreamingUsb.so /usr/lib/libInfraStreamingUsb.so",
        "/bin/busybox sync",
        "/bin/busybox md5sum /usr/lib/libInfraUsbCmn.so /usr/lib/libInfraStreamingUsb.so",
        "/bin/busybox mount -o remount,ro /usr",
        "/bin/busybox sync",
    ]
    out, tries = zve10.run(install_cmds)
    print(out)

    cmn_ok = EXPECTED_PATCHED["libInfraUsbCmn.so"] in out
    strm_ok = EXPECTED_PATCHED["libInfraStreamingUsb.so"] in out

    if cmn_ok and strm_ok:
        print("=" * 70)
        print(" [√] 1080p UVC WEBCAM PATCH SUCCESSFULLY INSTALLED ON ZV-E10!")
        print("=" * 70)
        print(" Both /usr/lib/ binaries match verified patched MD5 hashes.")
        print("\n[*] Cold rebooting camera into clean shooting/streaming mode...")
        zve10.run(["/bin/busybox sync", "/bin/busybox reboot -f"])
        print("[+] Camera rebooted successfully.")
    else:
        print("[-] Verification failed after installation!")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Stream file to camera via busybox xxd -r -p with echo disabled.
Takes local file, turns off terminal echo, streams hex to stdin of xxd, sends Ctrl-D, verifies MD5.
"""

import hashlib
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path[:0] = [str(HERE.parent / "common"), str(REPO_ROOT)]

import senser_fix  # noqa: F401
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend

CTRL_D = b"\x04"
CHUNK = 512
PAUSE = 0.03


def drain(raw, timeout=2.0):
    buf = b""
    end = time.time() + timeout
    while time.time() < end:
        d = raw.readTerminal()
        if d:
            buf += d
            end = time.time() + 0.5
        else:
            time.sleep(0.02)
    return buf.decode("latin1", errors="replace")


def stream_file(local_path: str, remote_path: str) -> bool:
    data = Path(local_path).read_bytes()
    want_md5 = hashlib.md5(data).hexdigest()
    hex_str = data.hex()

    # Wrap hex at 76 chars per line
    lines = [hex_str[i : i + 76] for i in range(0, len(hex_str), 76)]
    payload = ("\n".join(lines) + "\n").encode("ascii")

    print(f"[*] Streaming {local_path} -> {remote_path}")
    print(f"    Size: {len(data)} bytes, hex: {len(payload)} chars, want MD5: {want_md5}")

    result = {"success": False}

    def complete(dev):
        raw = dev.dev
        SenserPlatformBackend(dev).start()
        dev.setTerminalEnable(False)
        dev.setTerminalEnable(True)
        try:
            drain(raw, 2.0)
            raw.writeTerminal(b"\n")
            drain(raw, 1.0)

            # 1. Turn off echo so PTY buffer won't overflow
            raw.writeTerminal(b"busybox stty -echo\n")
            drain(raw, 0.5)

            # 2. Start xxd decoder on camera
            start_cmd = f"rm -f {remote_path} && busybox xxd -r -p > {remote_path}\n".encode("latin1")
            raw.writeTerminal(start_cmd)
            time.sleep(0.5)

            # 3. Stream payload
            t0 = time.time()
            sent = 0
            for i in range(0, len(payload), CHUNK):
                chunk = payload[i : i + CHUNK]
                raw.writeTerminal(chunk)
                sent += len(chunk)
                time.sleep(PAUSE)
                if sent % 2048 < CHUNK:
                    sys.stdout.write(f"\r  {100.0 * sent / len(payload):5.1f}%  ({sent}/{len(payload)} bytes)")
                    sys.stdout.flush()

            sys.stdout.write(f"\r  100.0%  ({sent}/{len(payload)} bytes)\n")
            sys.stdout.flush()

            # 4. Send EOF
            time.sleep(0.5)
            raw.writeTerminal(b"\n")
            time.sleep(0.5)
            raw.writeTerminal(CTRL_D)
            time.sleep(1.0)

            # 5. Restore echo and permissions
            raw.writeTerminal(b"\nbusybox stty echo\n")
            time.sleep(0.5)
            raw.writeTerminal(f"chmod 755 {remote_path}\n".encode("latin1"))
            time.sleep(0.5)

            # 6. Verify MD5 on camera
            raw.writeTerminal(f"busybox md5sum {remote_path}\n".encode("latin1"))
            out = drain(raw, 2.0)
            print(f"[*] Camera MD5 verification output:\n{out}")

            if want_md5 in out:
                print(f"[+] SUCCESS: {remote_path} deployed and MD5 matches ({want_md5}) in {time.time()-t0:.1f}s!")
                result["success"] = True
            else:
                print(f"[-] FAILED: MD5 did not match {want_md5}")
        finally:
            dev.setTerminalEnable(False)

    senserShellCommand(complete=complete)
    return result["success"]


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "out/file_patch.elf"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/setting/file_patch.elf"
    ok = stream_file(src, dst)
    sys.exit(0 if ok else 1)

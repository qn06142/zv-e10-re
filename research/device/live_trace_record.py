"""Sony ZV-E10 Live Staged Logging & Diagnostics Harness

Prepares, triggers, and captures low-level diagnostics during Open Gate video recording.
Captures:
  1. libBizFw live BizPrintf diagnostic stream
  2. libObj global debug output (unmasked at 0x172a4c)
  3. MPR hardware encoder logs via /usr/bin/mpr_viewLog.elf
  4. Sony unified logger (ulogio) subsystems via /usr/bin/appdbglv.sh
  5. Linux kernel dmesg / BIONZ X co-processor driver messages
"""
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path[:0] = [str(REPO_ROOT)]
from research.device.zve10_retry import run


TRACE_SHELL_SCRIPT = """#!/bin/sh
LOGDIR=/tmp/opengate_trace
mkdir -p $LOGDIR
rm -f $LOGDIR/*

echo "[*] Unmasking Sony unified logging (ulogio)..."
/usr/bin/appdbglv.sh all info >/dev/null 2>&1
/usr/bin/ulogio.elf filter on 0 0 info >/dev/null 2>&1

echo "[*] Capturing baseline MPR hardware encoder state..."
/usr/bin/mpr_viewLog.elf > $LOGDIR/mpr_before.log 2>&1

echo "[*] Flushing and starting dmesg capture..."
dmesg -c > $LOGDIR/dmesg_prev.log 2>&1

echo "[+] LOG HARNESS ARMED in $LOGDIR"
echo "[+] Ready for Record button press."
"""

COLLECT_SHELL_SCRIPT = """#!/bin/sh
LOGDIR=/tmp/opengate_trace

echo "[*] Dumping dmesg post-record..."
dmesg > $LOGDIR/dmesg_post.log 2>&1

echo "[*] Dumping post-record MPR hardware encoder state..."
/usr/bin/mpr_viewLog.elf > $LOGDIR/mpr_after.log 2>&1

echo "[*] Dumping active process status..."
pidof im.elf > $LOGDIR/im_pid.log 2>&1

echo "[+] Captured files:"
ls -la $LOGDIR
"""


def arm_harness():
    print("[*] Uploading and arming diagnostic log harness on device...")
    cmd = f"cat << 'EOF' > /tmp/arm_trace.sh\n{TRACE_SHELL_SCRIPT}EOF\n/bin/busybox sh /tmp/arm_trace.sh"
    res, tries = run([cmd])
    for line in res.splitlines():
        if "[+]" in line or "[*]" in line:
            print("   " + line.strip())


def collect_harness():
    print("[*] Collecting diagnostics from device...")
    cmd = f"cat << 'EOF' > /tmp/collect_trace.sh\n{COLLECT_SHELL_SCRIPT}EOF\n/bin/busybox sh /tmp/collect_trace.sh"
    res, tries = run([cmd])
    for line in res.splitlines():
        if "[+]" in line or "[*]" in line:
            print("   " + line.strip())

    # Read the captured files back
    print("\n[*] Fetching captured logs:")
    for fname in ["dmesg_post.log", "mpr_after.log"]:
        print(f"\n--- {fname} ---")
        content, _ = run([f"/bin/busybox cat /tmp/opengate_trace/{fname}"])
        lines = [l for l in content.splitlines() if not l.startswith("app #")]
        if len(lines) > 40:
            print("\n".join(lines[:20]))
            print(f"   ... [{len(lines)-40} lines omitted] ...")
            print("\n".join(lines[-20:]))
        else:
            print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Sony ZV-E10 Live Logging Harness")
    parser.add_argument("--arm", action="store_true", help="Arm logging harness prior to pressing record")
    parser.add_argument("--collect", action="store_true", help="Collect logs after recording attempt")
    parser.add_argument("--auto", action="store_true", help="Arm, wait 15 seconds for record test, and collect")
    args = parser.parse_args()

    if args.arm:
        arm_harness()
    elif args.collect:
        collect_harness()
    elif args.auto:
        arm_harness()
        print("\n>>> PRESS THE RECORD BUTTON ON CAMERA NOW <<<")
        for i in range(15, 0, -1):
            sys.stdout.write(f"\rWaiting {i:2d}s for transition...")
            sys.stdout.flush()
            time.sleep(1.0)
        print("\n")
        collect_harness()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

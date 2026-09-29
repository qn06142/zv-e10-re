#!/usr/bin/env python3
"""run_after_reboot.py - workflow gate: nag for reboot, then run a probe.

Usage:
    python run_after_reboot.py <probe_script.py> [extra args...]

It blocks on the reboot nag (you physically replug the camera and click OK),
then runs the named probe in the same process-safe way and reports. This makes
"the user restarted the device" a hard gate before any probe that needs a
fresh MTP session.

Example:
    python run_after_reboot.py ptp_unlock.py -d libusb
"""
import sys, subprocess, os, time

HERE = os.path.dirname(os.path.abspath(__file__))

def wait_for_device(timeout=20, interval=1.0):
    """Poll libusb until the Sony W830 enumerates (handles the post-replug
    enumeration delay). Returns True if seen, False on timeout."""
    import usb.core
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if usb.core.find(idVendor=0x054c, idProduct=0x094b) is not None:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_after_reboot.py <probe_script.py> [args...]")
        return 2
    probe = sys.argv[1]
    probe_path = probe if os.path.isabs(probe) else os.path.join(HERE, probe)
    if not os.path.exists(probe_path):
        print("Probe not found:", probe_path); return 2

    # 1) GATE: block until the user confirms a reboot
    print("[run_after_reboot] Nagging for device reboot...")
    subprocess.run([sys.executable, os.path.join(HERE, 'nag_reboot.py')], check=True)
    print("[run_after_reboot] Reboot confirmed. Waiting for device to enumerate...")

    # 1b) SETTLE: the camera may still be enumerating after replug
    if not wait_for_device():
        print("[run_after_reboot] Device not seen after 20s. Proceeding anyway (probe may report 'No Sony device').")
    else:
        print("[run_after_reboot] Device present. Launching probe.")

    # 2) RUN the probe (after the nag returns and the device is visible)
    args = [sys.executable, probe_path] + sys.argv[2:]
    rc = subprocess.run(args).returncode
    print("[run_after_reboot] Probe exited rc=%d" % rc)
    return rc

if __name__ == '__main__':
    sys.exit(main())

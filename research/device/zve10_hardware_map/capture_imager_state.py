"""Capture imager profiles, code identity and selected registers through Senser.

No camera file writes, Backup writes, sensor starts or MMIO writes are issued.
Entering Senser changes the application mode; this does not sample shooting.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "research/common")]
from extract_imager_profile import PROFILE_IDS, PROFILE_VAS
from capture_display_state import TerminalSession, read_registers, irq_counts

# Previously sampled sensor banks plus native sequencer RMW accessors. The
# DFE priority/acknowledge port is deliberately omitted from polling.
BANKS = (0xf3002380, 0xf3102380, 0xf3020200, 0xf3020280, 0xf3020300,
         0xfc0a9200, 0xf3441280, 0xf3441580, 0xf3441200, 0xf3441500, 0xf3441300)
REGISTERS = sorted({b + o for b in BANKS for o in (0, 4, 0x10)} |
                   {0xfc088300, 0xfc088304, 0xfc088308, 0xfc08830c, 0xfc088f04, 0xfc088f08} |
                   {b + o for b in (0xfc0a9200, 0xf3020280) for o in (0x20, 0x24, 0x28, 0x2c)})
FILES = ("/log/zve10-ram-boot/rtos.bin", "/log/zve10-ram-boot/boot.ko")
SCALAR_IDS = (0xf90343, 0xf90381, 0xf90345, 0xf90349, 0xf90347, 0xf9034b, 0xf9046d,
              0xf90344, 0xf90382, 0xf90346, 0xf9034a, 0xf90348, 0xf9034c, 0xf9046e,
              0xf900e0, 0xf900d9)
# Read only the known singleton and fields used by its mode/readout routines.
RAM_WORDS = [0x0426b384 + off for off in (0, 0x11c, 0x120, 0x124, 0x128, 0x134,
             0x138, 0x13c, 0x140, 0x144, 0x148, 0x14c, 0x150, 0x154,
             0x158, 0x15c, 0x160, 0x164, 0x168, 0x22c, 0x230, 0x234,
             0x238, 0x23c, 0x240, 0x244, 0x248, 0x24c, 0x250, 0x254)]
RAM_COMMAND = f"/tmp/busybox hexdump -v -n 1088 -s {0x0426b384} /dev/mem"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"utc": datetime.now(timezone.utc).isoformat(), "mode": "Senser",
              "camera_file_writes": False, "backup_writes": False, "mmio_writes": False,
              "status": "not-connected", "profiles": [], "samples": []}
    import senser_fix  # noqa: F401
    from zve10_dumpall import _preflight
    from pmca.commands.usb import senserShellCommand
    from pmca.platform.backend.senser import SenserPlatformBackend

    def complete(device):
        SenserPlatformBackend(device).start()
        report["status"] = "capturing"
        # Retain raw proprietary inputs locally; reports contain hashes only.
        reference = (ROOT / ".local/dumps/av-cam.bin").read_bytes()
        buffer = io.BytesIO()
        device.readFile("/system/av-cam.bin", buffer)
        body = buffer.getvalue()
        if len(body) != len(reference): raise ValueError("Unexpected body firmware size")
        report["body_sha256"] = hashlib.sha256(body).hexdigest()
        (args.out / "av-cam-body.bin").write_bytes(body)
        pages = (0x1e0000, 0x1e1000, 0x1e2000, 0x1e3000, 0x1e4000,
                 0x1e5000, 0x1e6000, 0x1e7000, 0x1e8000, 0x1ee000,
                 0x1ef000, 0x762000, 0x763000, 0x764000, 0x765000,
                 0x8b1000, 0xfcc000, 0xffd000, 0x1001000)
        report["code_pages"] = [
            {"offset": hex(off), "sha256": hashlib.sha256(body[off:off + 4096]).hexdigest(),
             "reference_match": body[off:off + 4096] == reference[off:off + 4096]}
            for off in pages]
        for key, va in zip(PROFILE_IDS, PROFILE_VAS):
            first = device.readBackup(key)
            second = device.readBackup(key)
            if first != second: raise ValueError(f"Unstable imager property {key:x}")
            (args.out / f"profile-{key:08x}.bin").write_bytes(first)
            report["profiles"].append({"id": hex(key), "native_va": hex(va), "bytes": len(first),
                                       "sha256": hashlib.sha256(first).hexdigest()})
        for key in SCALAR_IDS:
            first, second = device.readBackup(key), device.readBackup(key)
            if first != second: raise ValueError(f"Unstable imager scalar {key:x}")
            (args.out / f"profile-{key:08x}.bin").write_bytes(first)
            report.setdefault("scalars", []).append({"id": hex(key), "bytes": len(first),
                "sha256": hashlib.sha256(first).hexdigest()})
        print(f"Captured firmware identity and {len(report['profiles'])} stable sensor profiles", flush=True)
        for path in FILES:
            buffer = io.BytesIO()
            device.readFile(path, buffer)
            data = buffer.getvalue()
            (args.out / Path(path).name).write_bytes(data)
            report.setdefault("installed", {})[path] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        commands = {"test -x /tmp/busybox", "busybox cat /proc/uptime",
                    "busybox cat /proc/interrupts", "busybox cat /proc/modules"}
        commands |= {f"/tmp/busybox devmem {a:#010x} 32" for a in REGISTERS + RAM_WORDS}
        commands.add(RAM_COMMAND)
        device.setTerminalEnable(False)
        device.setTerminalEnable(True)
        try:
            session = TerminalSession(device.dev, commands)
            rc, _ = session.run("test -x /tmp/busybox")
            if rc: raise RuntimeError("Existing /tmp/busybox is unavailable")
            rc, text = session.run("busybox cat /proc/modules")
            if rc: raise RuntimeError("Cannot read module state")
            report["modules"] = text
            report["imager_singleton_physical_words"] = {}
            rc, text = session.run(RAM_COMMAND, timeout=45)
            if rc: raise RuntimeError("Cannot read imager object")
            raw = bytearray()
            for line in text.splitlines():
                fields = line.split()
                if len(fields) == 9 and all(re.fullmatch(r"[0-9a-fA-F]{4}", h) for h in fields[1:]):
                    raw.extend(struct.pack("<8H", *(int(h, 16) for h in fields[1:])))
            if len(raw) != 1088: raise RuntimeError(f"Incomplete object read: {len(raw)} bytes")
            if struct.unpack_from("<I", raw)[0] != 0x64588e88:
                raise RuntimeError("Native imager singleton vtable mismatch")
            (args.out / "imager-object.bin").write_bytes(raw)
            report["imager_singleton_physical_words"] = {
                hex(a): hex(struct.unpack_from("<I", raw, a - 0x0426b384)[0]) for a in RAM_WORDS}
            for _ in range(2):
                sample = {"host_start": time.monotonic(), "registers": {}}
                report["samples"].append(sample)
                for name in ("uptime", "interrupts"):
                    rc, text = session.run(f"busybox cat /proc/{name}")
                    if rc: raise RuntimeError(f"Cannot read {name}")
                    sample[name] = text
                read_registers(session, "/tmp/busybox devmem", REGISTERS, sample["registers"])
                sample["host_end"] = time.monotonic()
            before, after = [irq_counts(s["interrupts"]) for s in report["samples"]]
            report["irq_deltas"] = {k: {"label": label, "delta": count - before[k][0]}
                                    for k, (count, label) in after.items() if k in before and count != before[k][0]}
            report["status"] = "captured"
        finally:
            device.setTerminalEnable(False)

    _preflight()
    try:
        senserShellCommand(complete=complete)
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        (args.out / "capture.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report["status"] != "captured": raise RuntimeError("Capture did not complete")
    print("Read-only Senser sensor capture completed", flush=True)


if __name__ == "__main__":
    main()

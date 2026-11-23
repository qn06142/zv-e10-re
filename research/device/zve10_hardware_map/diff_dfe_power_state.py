"""Capture read-only CRG/PMU/DFE register differences between idle and CAMERA_SCN_EE_START_STOP b:1 b:0 over Senser."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "research/common"), str(Path(__file__).resolve().parent)]

import senser_fix  # noqa: F401
from capture_display_state import TerminalSession, read_registers
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
from zve10_dumpall import _preflight

READER = "/tmp/busybox devmem"
INIT = ("cd /usr/bin", 'sc(){ /tmp/busybox timeout 28 ./scenario.elf "$@"; }')
START_STILL = "sc CAMERA_SCN_EE_START_STOP b:1 b:0"
STOP = "sc CAMERA_SCN_EE_START_STOP b:16 b:0"

CRG_DOMAINS = (
    0xF2901000, 0xF2902000,
    0xF2A01000, 0xF2A11000, 0xF2A12000,
    0xF2A21000, 0xF2A22000, 0xF2A31000, 0xF2A32000,
)
CRG_RESET_BASES = (0xF2900000, 0xF2A00000, 0xF2A10000, 0xF2A20000, 0xF2A30000)
UPM_PMU_BASES = (0xF2908000, 0xF290C000, 0xF290E000, 0xF2916000)
DFE_CHECKS = (
    0xFC020028, 0xFC021000, 0xFC021010, 0xFC021014, 0xFC021024,
    0xFC0A0000, 0xFC0A1100, 0xFC0A1120, 0xFC0A9200, 0xFC0A9220,
)

ADDRESSES = (
    [base + off for base in CRG_DOMAINS for off in (0x00, 0x04, 0x08, 0x0C, 0x30)]
    + [base + off for base in CRG_RESET_BASES for off in (0x00, 0x04, 0x08, 0x0C, 0x10)]
    + [base + off for base in UPM_PMU_BASES for off in (0x00, 0x04, 0x08, 0x0C)]
    + list(DFE_CHECKS)
)

COMMANDS = {*INIT, START_STILL, STOP} | {f"{READER} {addr:#010x} 32" for addr in ADDRESSES}


def probe(device, report):
    SenserPlatformBackend(device).start()
    device.setTerminalEnable(False)
    device.setTerminalEnable(True)
    session = TerminalSession(device.dev, COMMANDS)

    def run(command, timeout=20):
        rc, output = session.run(command, timeout=timeout)
        report["commands"].setdefault(command, []).append({"exit": rc, "output": output})
        print(command, rc, output.strip()[-180:], flush=True)
        return rc

    def snapshot(name):
        values = {}
        for address in ADDRESSES:
            for attempt in range(4):
                try:
                    read_registers(session, READER, [address], values)
                except (RuntimeError, TimeoutError):
                    if attempt == 3:
                        raise
                else:
                    break
        report["samples"][name] = values
        print(f"Captured {name}: {len(values)} registers", flush=True)
        return values

    try:
        for command in INIT:
            if run(command):
                raise RuntimeError(f"Preflight failed: {command}")
        idle = snapshot("idle")
        started = False
        try:
            if run(START_STILL, timeout=36):
                raise RuntimeError("CAMERA_SCN_EE_START_STOP b:1 b:0 failed")
            started = True
            active = snapshot("active")
        finally:
            if started:
                run(STOP, timeout=36)
        diffs = {
            addr: {"idle": idle[addr], "active": active[addr]}
            for addr in sorted(idle)
            if idle[addr] != active[addr]
        }
        report["diffs"] = diffs
        print(f"Changed registers ({len(diffs)}):", flush=True)
        for addr, pair in diffs.items():
            print(f"  {addr}: {pair['idle']} -> {pair['active']}", flush=True)
    finally:
        device.setTerminalEnable(False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "commands": {},
        "samples": {},
        "diffs": {},
    }
    try:
        _preflight()
        senserShellCommand(complete=lambda device: probe(device, report))
        if "active" not in report["samples"]:
            raise RuntimeError("No Senser session completed the hardware diff")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (args.out / "diff.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

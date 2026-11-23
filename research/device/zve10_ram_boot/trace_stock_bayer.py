"""Record DMA register changes across one Sony still RAW capture in Senser."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import re
import struct
import time
import uuid

from test_bayer_senser import (
    TerminalSession, _preflight, build_runner, senserShellCommand,
)

START = "sc CAMERA_SCN_EE_START_STOP b:1 b:0"
STOP = "sc CAMERA_SCN_EE_START_STOP b:16 b:0"
TRIGGER = "adj 0x404 0x4e"
BUSY = "adj 0x404 0x1"
WORD = struct.Struct("<III")
DMA_PORTS = {
    "isp0_aif3": 0xF3002380,
    "isp1_aif6": 0xF3102200,
    "dfecore_rdcw0": 0xFC0A9200,
}


def decode(trace):
    magic, count, polls, ticks = struct.unpack_from("<4I", trace)
    if magic != 0x31545342 or len(trace) != 16 + WORD.size * count:
        raise ValueError("Incomplete stock capture trace")
    events = list(WORD.iter_unpack(trace[16:]))
    def changes(address):
        return [[t, f"{v:#010x}"] for t, a, v in events if a == address]

    return {
        "polls": polls, "ticks": ticks, "events": count,
        "active_modes": [v for _, addr, v in events if addr == 0x0426B4A4],
        "handles": [v & 0xFFFF for _, addr, v in events if addr == 0x043D7320],
        "published_buffer": {
            "base": changes(0x043BBC8C),
            "extent": changes(0x043BBC90),
        },
        "dma_ports": {
            name: {
                f"+{offset:#04x}": changes(base + offset)
                for offset in (0, 4, 0x0C, 0x10, *range(0x20, 0x44, 4))
            }
            for name, base in DMA_PORTS.items()
        },
        "raw_aperture_values": sorted({
            f"{a:#010x}" for _, a, v in events
            if 0x0B000000 <= v < 0x0E000000 and a >= 0xF0000000
        }),
    }


def capture(device, runner, output, report):
    path = "/tmp_bt/s" + uuid.uuid4().hex[:5]
    allowed = set()
    device.setTerminalEnable(False)
    device.setTerminalEnable(True)
    terminal = TerminalSession(device.dev, allowed)
    preview = created = False

    def run(cmd, timeout=15, expected=0):
        allowed.add(cmd)
        status, value = terminal.run(cmd, timeout=timeout)
        report["commands"].append([cmd, status, value])
        print(cmd, status, value[-220:], flush=True)
        if expected is not None and status != expected:
            raise RuntimeError(f"Command failed: {cmd}")
        return status, value

    def setup(cmd):
        # Early kernel console output can interrupt command echo or its marker.
        for attempt in range(3):
            try:
                return run(cmd, timeout=4)
            except TimeoutError:
                if attempt == 2:
                    raise

    def read(path):
        data = BytesIO()
        device.readFile(path, data)
        return data.getvalue()

    try:
        _, uptime = run("busybox cat /proc/uptime")
        report["uptime"] = uptime
        _, identity = run("/tmp/busybox devmem 0x0426b384 32")
        if "0x64588e88" not in identity.lower():
            raise RuntimeError("Unexpected IMX284 object identity")
        _, idle = run("/tmp/busybox devmem 0xfc0a9200 32")
        if not re.search(r"(?m)^0x00000000\s*$", idle):
            raise RuntimeError("Still capture needs a clean boot after the bare-metal trial")
        _, mounts = run("grep /tmp_bt /proc/mounts")
        if " /tmp_bt tmpfs " not in mounts:
            raise RuntimeError("Expected RAM-backed scratch absent")
        run(f"mkdir -m 700 {path}")
        created = True
        run(f"d={path}")
        device.writeFile(path + "/probe", runner)
        if read(path + "/probe") != runner:
            raise RuntimeError("Trace runner readback mismatch")
        run('chmod 700 "$d/probe"')
        setup("cd /usr/bin")
        setup('sc(){ /tmp/busybox timeout 28 ./scenario.elf "$@"; }')
        setup('adj(){ /tmp/busybox timeout 15 ./adjstctl.elf "$@"; }')
        _, state = run(BUSY)
        if re.search(r"(?m)^0x01\s*$", state):
            run("adj 0x404 0x0")
            time.sleep(.5)
        preview = True
        _, reply = run(START, timeout=36)
        if not re.search(r"(?m)^0x01\s*$", reply):
            raise RuntimeError("Still preview start was not acknowledged")
        run('"$d/probe" stock-trace "$d/trace" >"$d/log" 2>&1 & p=$!')
        time.sleep(.35)
        run('kill -0 "$p"')
        try:
            _, reply = run(TRIGGER, timeout=20)
            if not re.search(r"(?m)^res:\s+0x01\s*$", reply):
                raise RuntimeError("RAW trigger was not acknowledged")
            for _ in range(18):
                _, state = run(BUSY)
                if re.search(r"(?m)^0x00\s*$", state):
                    report["capture_idle_after_trigger"] = True
                    break
                time.sleep(.1)
        finally:
            run('wait "$p"', timeout=13, expected=None)
            data = read(path + "/trace")
            (output / "stock-trace.bin").write_bytes(data)
            report["trace"] = decode(data)
            print(f"Captured {report['trace']['events']} register samples", flush=True)
    finally:
        try:
            if preview:
                run(STOP, timeout=36, expected=None)
            if created:
                run('rm -f "$d/probe" "$d/trace" "$d/log"', expected=None)
                run('rmdir "$d"', expected=None)
        finally:
            device.setTerminalEnable(False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"commands": []}
    try:
        runner = build_runner()
        _preflight()
        senserShellCommand(complete=lambda dev: capture(dev, runner, args.out, report))
        if "trace" not in report:
            raise RuntimeError("No trace was acquired")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

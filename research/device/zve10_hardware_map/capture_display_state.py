"""Capture display state through an existing Senser shell and MMIO reader."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[3]
READERS = (
    ("/tmp/busybox", "/tmp/busybox devmem"),
    ("/log/yuy2_640_v27snap/busybox", "/log/yuy2_640_v27snap/busybox devmem"),
    ("/tmp/sd/tools/busybox-armel", "/tmp/sd/tools/busybox-armel devmem"),
    ("busybox", "busybox devmem"),
)
PROC = {
    "uptime": "/proc/uptime",
    "boot_id": "/proc/sys/kernel/random/boot_id",
    "version": "/proc/version",
    "modules": "/proc/modules",
    "interrupts": "/proc/interrupts",
    "iomem": "/proc/iomem",
    "fb": "/proc/fb",
}
# Native RMW load/store sites and the documented GPIO11 data words.
# Bulk AIF offsets with only a store or no decoded access are excluded.
NEW_DISPLAY_WORDS = {
    0xf3440400, 0xf3440404, 0xf3440408, 0xf3440410, 0xf3440414,
    0xf344124c, 0xf34412cc, 0xf344144c, 0xf34414cc, 0xf344154c, 0xf34415cc,
    0xf3441300, 0xf3441348, 0xf344134c, 0xf3441350, 0xf3441370,
    0xf3441380, 0xf34413c8, 0xf34413cc, 0xf34413d0, 0xf34413f0,
    0xf3446000, 0xf3446100, 0xf3446104,
}
# Verified body-matched pure-ldr and AIF table-indexed [ch_base + off] / [top_base + off]
# registers (0x493622, 0x493632, 0x41bf98..0x41c404) not indexed in native-accessors.json.
VERIFIED_AIF_AND_TOP_READS = (
    {0xf3440048, 0xf3440068}
    | set(range(0xf3441000, 0xf3441018, 4))
    | {
        base + off
        for base in (0xf3441200, 0xf3441280, 0xf3441300, 0xf3441380, 0xf3441400, 0xf3441480, 0xf3441500, 0xf3441580)
        for off in (0x00, 0x04, 0x08, 0x10, 0x14, 0x1c, 0x44, 0x5c)
    }
)
GPIO11_DATA = {0xf2910b00, 0xf2910b10, 0xf2910b20, 0xf2910b30, 0xf2910b40}
# The verified graphics clock-up routine loads these five words.
GRAPHICS_CLOCK_READS = {0xf28040c4, 0xf28041a8, 0xf28050b8, 0xf280518c, 0xf3400080}

OFFLINE_EXPECTATIONS = {
    "/usr/kmod/grm_gles.ko": {
        "md5": "a7f1258b348f06aa8eb61941a778318c",
        "sha256": "4e4b99e5e17e170ddc13dc432178299512525debd6fb19512521b38867da7a65",
    },
    "/usr/kmod/grm_ma.ko": {
        "md5": "5c6a7de3783868a69e3899809e19d83f",
        "sha256": "c21479fea7b0bc081f72315c0b0b514b383a58b5a3bb5f2fefbfd26e20711879",
    },
    "/usr/lib/dataflowInfraFramework.so": {
        "md5": "f70f50f931e9c2cf415cc2728e324f60",
        "sha256": "3a7235ab96ed87606fc598f45db8e318afacc1e58a07e51b541923a43de76941",
    },
    "/system/av-cam.bin": {
        "reference_md5": "cdcae9d4fdbf66a33704a4c7564e346d",
        "reference_sha256": "bc6cba98c1ce5ef9c7692b9701ed855c25958d285a646ef90dc3fdf398f5c4fa",
        "known_body_2025_md5": "90096db2c76148f4f9db5d104e5c608c",
    },
    "/usr/lib/viewUnified6.so": {
        "md5": "ec8090bbde9b78e2e25a0b33cf735333",
        "sha256": "e6459c22859d8978195baa1ef2e93ad6d5f4fcb3dd89c2c2f02c325b46616090",
    },
    "/log/zve10-ram-loader/payload.bin": {},
    "/log/zve10-ram-boot/boot.ko": {},
}

def _build_register_groups() -> dict[str, list[int]]:
    osd_offsets = [
        0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x1C,
        0x20, 0x24, 0x28, 0x2C,
        0x30, 0x34, 0x38, 0x3C,
        0x40, 0x44, 0x48, 0x4C,
        0x50, 0x54, 0x58, 0x5C,
        0x70,
    ]
    other_ch_offsets = [0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x44, 0x48, 0x4C, 0x50, 0x5C, 0x70]
    vph_aif = list(range(0xF3441000, 0xF3441020, 4))
    for base in (0xF3441200, 0xF3441280, 0xF3441300, 0xF3441380, 0xF3441400, 0xF3441480, 0xF3441500, 0xF3441580):
        offs = osd_offsets if base in (0xF3441300, 0xF3441380) else other_ch_offsets
        vph_aif.extend(base + o for o in offs)

    def out_bank(base: int) -> list[int]:
        addrs = list(range(base + 0x00, base + 0x64, 4))
        addrs.extend([base + 0x100, base + 0x104, base + 0x108, base + 0x10C, base + 0x110, base + 0x1A8, base + 0x340])
        addrs.extend(range(base + 0x500, base + 0x544, 4))
        return addrs

    return {
        "VPH_TOP_MIXER": (
            [0xF3440000, 0xF3440004, 0xF3440008, 0xF344000C, 0xF3440010, 0xF3440038, 0xF3440048, 0xF3440068]
            + list(range(0xF3440144, 0xF3440170, 4))
            + list(range(0xF3440184, 0xF34401B0, 4))
            + [
                0xF34401E4, 0xF34401EC,
                0xF3440400, 0xF3440404, 0xF3440408, 0xF3440410, 0xF3440414,
                0xF3440420, 0xF3440424, 0xF3440428, 0xF344042C,
                0xF3440430, 0xF3440434, 0xF3440440, 0xF3440448, 0xF344044C,
                0xF3440700, 0xF3440708, 0xF3440714,
            ]
        ),
        "VPH_AIF": vph_aif,
        "VPH_OUT0": out_bank(0xF3445000),
        "VPH_OUT1": out_bank(0xF3446000),
        "GPIO11_AND_CLKS": [
            0xF2910B00, 0xF2910B10, 0xF2910B20, 0xF2910B30, 0xF2910B40,
            0xF2912000, 0xF2912010, 0xF2912020, 0xF2912030, 0xF2912040, 0xF2912050,
            0xF2915000, 0xF2915010, 0xF2915050,
            0xF28040C4, 0xF28041A8, 0xF28050B8, 0xF280518C,
            0xF3400080, 0xF3400280,
            0xF2A30020, 0xF2A30030, 0xF2A30040, 0xF2A30050,
            0xF2A30060, 0xF2A30070, 0xF2A30080, 0xF2A300B0,
            0xF2A31030,
        ],
    }


def capture_plan():
    prior_path = REPO_ROOT / "research/device/zve10_hardware_map/evidence/20261118-senser-registers.json"
    prior = {entry["address"] for entry in json.loads(prior_path.read_text())["register_reads"]}
    accessors_path = REPO_ROOT / "docs/hardware/data/native-accessors.json"
    rmw = {int(entry["register"], 0) for entry in json.loads(accessors_path.read_text())["accessors"]}
    groups = _build_register_groups()
    admitted = prior | (NEW_DISPLAY_WORDS & rmw) | VERIFIED_AIF_AND_TOP_READS | GPIO11_DATA | GRAPHICS_CLOCK_READS
    selected = {name: [addr for addr in addresses if addr in admitted] for name, addresses in groups.items()}
    omitted = {name: [hex(addr) for addr in addresses if addr not in admitted] for name, addresses in groups.items()}
    return selected, omitted


class TerminalTimeout(TimeoutError):
    def __init__(self, command, output):
        super().__init__(f"No terminal completion marker for {command!r}")
        self.output = output


class TerminalSession:
    def __init__(self, raw, commands):
        self.raw = raw
        self.commands = commands
        self.sequence = 0

    def run(self, command, timeout=20):
        if command not in self.commands or len(command) > 68:
            raise ValueError(f"Command outside the capture plan: {command!r}")
        self.sequence += 1
        marker = f"C{self.sequence}"
        wire_command = f"{command};echo {marker}=$?"
        if len(wire_command) > 68:
            raise ValueError(f"Command and completion marker exceed terminal limit: {command!r}")
        self.raw.writeTerminal(wire_command.encode("ascii") + b"\n")
        deadline = time.monotonic() + timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            chunk = self.raw.readTerminal()
            if not chunk:
                time.sleep(0.02)
                continue
            buffer.extend(chunk)
            output = buffer.decode("latin1").replace("\r", "").replace("^J", "\n")
            match = re.search(rf"(?m)^{marker}=(\d+)\n", output)
            if match:
                lines = output[:match.start()].splitlines()
                body = "\n".join(line for line in lines if line and not line.endswith(wire_command)
                                 and not line.endswith(f"echo {marker}=$?")
                                 and not line.strip().endswith("#"))
                return int(match.group(1)), body
        raise TerminalTimeout(command, buffer.decode("latin1").replace("\r", "").replace("^J", "\n"))


def read_registers(session, reader, addresses, values):
    for address in addresses:
        rc, body = session.run(f"{reader} {address:#010x} 32")
        matches = re.findall(r"(?mi)^\s*(0x[0-9a-f]{1,8})\s*$", body)
        if rc or len(matches) != 1:
            raise RuntimeError(f"32-bit read failed at {address:#010x} (rc={rc}): {body!r}")
        values[f"{address:#010x}"] = f"{int(matches[0], 16):#010x}"


def allowed_commands(groups):
    addresses = {a for group in groups.values() for a in group}
    commands = {"command -v devmem", "busybox --list"}
    commands.update(f"busybox cat {path}" for path in PROC.values())
    commands.update(f"busybox {tool} {path}" for path in OFFLINE_EXPECTATIONS for tool in ("md5sum", "sha256sum"))
    for binary, _ in READERS:
        if binary.startswith("/"):
            commands.update({f"test -x {binary}", f"{binary} --list"})
    readers = [reader for _, reader in READERS] + ["devmem"]
    commands.update(f"{reader} {addr:#010x} 32" for addr in addresses for reader in readers)
    if any(len(cmd + ";echo C999=$?") > 68 for cmd in commands):
        raise ValueError("Capture plan exceeds the terminal command length limit")
    return commands


def discover_reader(session, report, stock_applets):
    # Probe the historically used full binary and persistent copies first.
    for binary, reader in READERS:
        if binary == "busybox":
            if "devmem" in stock_applets:
                return reader
            continue
        present, _ = session.run(f"test -x {binary}")
        report["tool_probe"][binary] = {"executable": present == 0}
        if present == 0:
            rc, applets = session.run(f"{binary} --list")
            report["tool_probe"][binary]["devmem_applet"] = rc == 0 and "devmem" in applets.splitlines()
            if report["tool_probe"][binary]["devmem_applet"]:
                return reader
    rc, output = session.run("command -v devmem")
    report["tool_probe"]["command_v_devmem"] = output.strip()
    return "devmem" if rc == 0 and re.search(r"(?m)^/\S+/devmem$", output) else None


def irq_counts(output):
    rows = {}
    for line in output.splitlines():
        match = re.match(r"^\s*(\d+):\s+((?:\d+\s+)+)(.+)$", line)
        if match:
            rows[match[1]] = (sum(map(int, match[2].split())), match[3].strip())
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=False)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    groups, omitted = capture_plan()
    commands = allowed_commands(groups)
    if args.plan:
        print(json.dumps({"included": {k: list(map(hex, v)) for k, v in groups.items()},
                          "omitted": omitted, "commands_validated": len(commands)}, indent=2))
        return 0
    if args.out is None:
        parser.error("--out is required for a live capture")
    if args.out.exists():
        parser.error("choose a new --out path to preserve existing evidence")

    sys.path[:0] = [str(REPO_ROOT / "research/common"), str(REPO_ROOT)]
    import senser_fix  # noqa: F401
    from zve10_dumpall import _preflight
    from pmca.commands.usb import senserShellCommand

    _preflight()
    report = {"schema_version": 2, "captured_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "Senser", "camera_writes": False, "status": "no-session",
              "proc": {}, "file_hashes": {}, "tool_probe": {}, "register_reader": None,
              "register_groups": {}, "omitted_words": omitted}

    def complete(device):
        device.setTerminalEnable(False)
        device.setTerminalEnable(True)
        try:
            session = TerminalSession(device.dev, commands)
            report["status"] = "partial"
            rc, applets = session.run("busybox --list")
            stock_applets = set(applets.splitlines()) if rc == 0 else set()
            report["tool_probe"]["stock_busybox_devmem"] = "devmem" in stock_applets
            reader = discover_reader(session, report, stock_applets)
            report["register_reader"] = reader
            for key, path in PROC.items():
                rc, output = session.run(f"busybox cat {path}")
                report["proc"][key] = {"rc": rc, "output": output.strip()}
            for path, expected in OFFLINE_EXPECTATIONS.items():
                entry = report["file_hashes"].setdefault(path, {"expected": expected})
                for algorithm in ("md5", "sha256"):
                    rc, output = session.run(f"busybox {algorithm}sum {path}", timeout=45)
                    length = 32 if algorithm == "md5" else 64
                    match = re.search(rf"(?m)^([a-f0-9]{{{length}}})\s+{re.escape(path)}$", output)
                    entry[algorithm] = match.group(1) if not rc and match else None
            if reader is None:
                report["status"] = "no-existing-mmio-reader"
                return
            identity = report["file_hashes"]["/system/av-cam.bin"]["sha256"]
            if identity != "98f05bebd113cb5b4911d71384e5ae7cec21dd4494b0f0569bb2f1b2b3231c6b":
                report["status"] = "unrecognized-body-firmware"
                return
            for name, addresses in groups.items():
                values = report["register_groups"].setdefault(name, {})
                read_registers(session, reader, addresses, values)
            # Capture actual host timing as sequential USB commands add latency.
            samples = report["repeat_samples"] = []
            addresses = [addr for addr in (0xf3440000, 0xf3441300, 0xf3441380, 0xf3445000, 0xf3446000)
                         if any(addr in group for group in groups.values())]
            for _ in range(2):
                sample = {"host_start_s": time.monotonic(), "registers": {}}
                samples.append(sample)
                rc, uptime = session.run("busybox cat /proc/uptime")
                sample["uptime"] = uptime if rc == 0 else None
                rc, interrupts = session.run("busybox cat /proc/interrupts")
                sample["interrupts"] = interrupts if rc == 0 else None
                read_registers(session, reader, addresses, sample["registers"])
                sample["host_stop_s"] = time.monotonic()
                if len(samples) == 1:
                    time.sleep(0.1)
            report["repeat_start_delta_s"] = samples[1]["host_start_s"] - samples[0]["host_start_s"]
            before, after = (irq_counts(sample["interrupts"] or "") for sample in samples)
            report["interrupt_deltas"] = {
                irq: {"label": label, "delta": count - before[irq][0]}
                for irq, (count, label) in after.items()
                if irq in before and label == before[irq][1] and count > before[irq][0]
            }
            report["status"] = "selected-registers-captured"
        finally:
            device.setTerminalEnable(False)

    try:
        senserShellCommand(complete=complete)
    except (RuntimeError, TimeoutError) as e:
        report["error"] = str(e)
    finally:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(report["status"])
    return 0 if report["status"] == "selected-registers-captured" else 1


if __name__ == "__main__":
    raise SystemExit(main())

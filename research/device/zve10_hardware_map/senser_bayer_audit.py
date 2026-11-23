"""Capture read-only live stock preview vs v8 Bayer table register diffs over USB Senser."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO), str(REPO / "research/common"), str(Path(__file__).resolve().parent)]

import senser_fix  # noqa: F401
from capture_display_state import TerminalSession, read_registers
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
from zve10_dumpall import _preflight

READER = "/tmp/busybox devmem"
CHECK_BB = "test -x /tmp/busybox"
LINK_BB = "ln -s /log/yuy2_640_v27snap/busybox /tmp/busybox"
CD_BIN = "cd /usr/bin"
DEF_SC = 'sc(){ /tmp/busybox timeout 28 ./scenario.elf "$@"; }'
CAT_IOMEM = "busybox cat /proc/iomem"
CAT_MEMINFO = "busybox cat /proc/meminfo"
START_STILL = "sc CAMERA_SCN_EE_START_STOP b:1 b:0"
STOP_STILL = "sc CAMERA_SCN_EE_START_STOP b:16 b:0"

TABLES_HEADER = REPO / "research/device/zve10_ram_boot/bayer_sensor_tables.h"
TABLE_EXEC_ORDER = (
    "imx284_power_on_ops",
    "dfe_mode5_pll_phy_writes",
    "dfe_mode5_clock_sgc_writes",
    "dfe_mode5_setup_writes",
    "imx284_mode5_pre_writes",
    "imx284_wake_pre_writes",
    "imx284_wake_post_writes",
    "dfe_mode5_start_writes",
)

IDLE_ADDRESSES = (
    # SoC CRG / PMU / GPIO
    0xF2900040, 0xF29000A0, 0xF290E000, 0xF290E004, 0xF290E008, 0xF290E00C,
    0xF2910F30, 0xF2910F38, 0xF2912F04,
    0xF292A010, 0xF292A040, 0xF292A070, 0xF292A080,
    0xF2931100, 0xF2931104, 0xF293112C, 0xF2931130,
    0xF2A00020, 0xF2A000A0, 0xF2A30020, 0xF2A300A0,
    # DFE CRG & PLLs
    0xFC020028, 0xFC020104, 0xFC020114, 0xFC020124, 0xFC020134, 0xFC020144,
    0xFC020154, 0xFC020164, 0xFC020174, 0xFC020184, 0xFC020194,
    0xFC021000, 0xFC021008, 0xFC02100C, 0xFC021010, 0xFC021014, 0xFC02101C,
    0xFC021024, 0xFC021050, 0xFC021054, 0xFC021058,
    # IMX284 power/pinmux & analog PHY
    0xFC029000, 0xFC029004, 0xFC029008, 0xFC02900C, 0xFC029010, 0xFC029014,
    0xFC029018, 0xFC02901C, 0xFC029020, 0xFC029024, 0xFC029028, 0xFC02902C,
    0xFC02A008, 0xFC02A040, 0xFC02A044, 0xFC02A048, 0xFC02A04C, 0xFC02A054,
    0xFC02A058, 0xFC02A05C, 0xFC02A060, 0xFC02A064, 0xFC02A068, 0xFC02A06C,
    0xFC02A070, 0xFC02A080, 0xFC02A0D0,
    # Sequencer & 0xFC080xxx / 0xFC098xxx
    0xFC08001C, 0xFC080020, 0xFC080028,
    0xFC088300, 0xFC088304, 0xFC088308, 0xFC08830C, 0xFC088E00, 0xFC088F04, 0xFC088F08,
    0xFC098000, 0xFC098008, 0xFC098800, 0xFC098808,
    # DFE Core / SGC / SensorIF / RdcW0
    0xFC0A0000, 0xFC0A0014, 0xFC0A0018, 0xFC0A002C, 0xFC0A0030,
    0xFC0A1100, 0xFC0A1108, 0xFC0A1110, 0xFC0A1120, 0xFC0A1124,
    0xFC0A1140, 0xFC0A114C, 0xFC0A1150,
    0xFC0A1200, 0xFC0A1210, 0xFC0A1300, 0xFC0A1310, 0xFC0A1400, 0xFC0A1410,
    0xFC0A3000, 0xFC0A3008, 0xFC0A301C, 0xFC0A3200, 0xFC0A3204, 0xFC0A3208,
    0xFC0A3214, 0xFC0A3300,
    0xFC0A8700, 0xFC0A8704, 0xFC0A8804, 0xFC0A8900, 0xFC0A9000,
    0xFC0A9200, 0xFC0A9204, 0xFC0A9208, 0xFC0A9210,
    0xFC0A9220, 0xFC0A9224, 0xFC0A9228, 0xFC0A922C,
    0xFC0AD600, 0xFC0AD610,
)

ACTIVE_ONLY_ADDRESSES = (
    0xFC02D000, 0xFC02D004, 0xFC02D008, 0xFC02D00C, 0xFC02D010,
    0xFC02D014, 0xFC02D028, 0xFC02D02C, 0xFC02D040, 0xFC02D044,
    0xFC0F0000, 0xFC0F0004, 0xFC0F0008, 0xFC0F0010, 0xFC0F001C, 0xFC0F0020,
    0xFC0F0024, 0xFC0F0028, 0xFC0F002C, 0xFC0F0030, 0xFC0F0034, 0xFC0F0038,
    0xFC0F003C, 0xFC0F0040, 0xFC0F0044, 0xFC0F0048, 0xFC0F0050, 0xFC0F0054,
    0xFC0F0058, 0xFC0F005C, 0xFC0F0060, 0xFC0F0064, 0xFC0F0068, 0xFC0F006C,
    0xFC0F0074, 0xFC0F0084, 0xFC0F0088, 0xFC0F008C, 0xFC0F00C4,
    0xFC0F0150, 0xFC0F0154, 0xFC0F0158, 0xFC0F015C, 0xFC0F0174, 0xFC0F0184,
    0xFC0F0188, 0xFC0F018C, 0xFC0F01C4,
    0xF3122000, 0xF3122130, 0xF3122138, 0xF3122144, 0xF3122148, 0xF3122160,
    0xF3123000, 0xF3123130, 0xF3123138, 0xF3123144, 0xF3123148, 0xF3123160,
)

ALL_ADDRESSES = IDLE_ADDRESSES + ACTIVE_ONLY_ADDRESSES
COMMANDS = (
    {CHECK_BB, LINK_BB, CD_BIN, DEF_SC, CAT_IOMEM, CAT_MEMINFO, START_STILL, STOP_STILL}
    | {f"{READER} {addr:#010x} 32" for addr in ALL_ADDRESSES}
)
if any(len(cmd + ";echo C999=$?") > 68 for cmd in COMMANDS):
    raise ValueError("Senser audit command exceeds 68-byte terminal limit")


def parse_v8_tables(path: Path) -> dict[str, dict[str, str]]:
    """Replay v8 bayer_sensor_tables.h write tables in C execution order to get final expected register values."""
    text = path.read_text(encoding="utf-8")
    final: dict[str, dict[str, str]] = {}
    for table in TABLE_EXEC_ORDER:
        match = re.search(rf"\b{re.escape(table)}\[\]\s*=\s*\{{(.*?)\}};", text, re.S)
        if not match:
            raise ValueError(f"Missing table {table} in {path}")
        for addr_s, val_s in re.findall(r"\{\s*(0x[0-9a-fA-F]+)U,\s*(0x[0-9a-fA-F]+)U\s*\}", match.group(1)):
            addr = int(addr_s, 16)
            if addr == 0:
                continue
            final[f"{addr:#010x}"] = {"table": table, "value": f"{int(val_s, 16):#010x}"}
    return final


def probe(device, report):
    SenserPlatformBackend(device).start()
    device.setTerminalEnable(False)
    device.setTerminalEnable(True)
    session = TerminalSession(device.dev, COMMANDS)

    def run(command, timeout=20, allow_nonzero=False):
        rc, output = session.run(command, timeout=timeout)
        report["commands"].setdefault(command, []).append({"exit": rc, "output": output})
        if rc != 0 and not allow_nonzero:
            raise RuntimeError(f"Command failed (rc={rc}): {command!r} -> {output!r}")
        return rc, output

    def snapshot(name, addresses):
        values = {}
        for address in addresses:
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
        rc, _ = run(CHECK_BB, allow_nonzero=True)
        if rc != 0:
            run(LINK_BB)
        run(CD_BIN)
        run(DEF_SC)
        _, iomem = run(CAT_IOMEM)
        _, meminfo = run(CAT_MEMINFO)
        report["proc"] = {"iomem": iomem, "meminfo": meminfo}

        idle = snapshot("idle", IDLE_ADDRESSES)
        started = False
        try:
            run(START_STILL, timeout=36)
            started = True
            active = snapshot("active", ALL_ADDRESSES)
        finally:
            if started:
                run(STOP_STILL, timeout=36)

        idle_to_active = {
            addr: {"idle": idle[addr], "active": active[addr]}
            for addr in sorted(idle)
            if idle[addr] != active[addr]
        }
        v8_final = parse_v8_tables(TABLES_HEADER)
        v8_vs_stock = {}
        for addr in sorted(set(active) & set(v8_final)):
            if active[addr] != v8_final[addr]["value"]:
                v8_vs_stock[addr] = {
                    "stock_active": active[addr],
                    "stock_idle": idle.get(addr),
                    "v8_value": v8_final[addr]["value"],
                    "v8_last_table": v8_final[addr]["table"],
                }

        report["diffs"] = {"idle_to_active": idle_to_active, "v8_vs_stock_active": v8_vs_stock}

        print("\n=== /proc/iomem ===", flush=True)
        print(iomem, flush=True)
        print(f"\n=== idle -> active diffs ({len(idle_to_active)}) ===", flush=True)
        for addr, pair in idle_to_active.items():
            print(f"  {addr}: {pair['idle']} -> {pair['active']}", flush=True)
        print(f"\n=== v8 bayer_sensor_tables.h vs live stock active diffs ({len(v8_vs_stock)}) ===", flush=True)
        for addr, pair in v8_vs_stock.items():
            print(
                f"  {addr}: v8={pair['v8_value']} ({pair['v8_last_table']}) "
                f"vs stock_active={pair['stock_active']} (idle={pair['stock_idle']})",
                flush=True,
            )
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
        "proc": {},
        "samples": {},
        "diffs": {},
    }
    try:
        _preflight()
        senserShellCommand(complete=lambda device: probe(device, report))
        if "active" not in report["samples"]:
            raise RuntimeError("No Senser session completed the Bayer audit")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (args.out / "audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

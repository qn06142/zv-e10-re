"""Build and test IMX284 Bayer RAW readout over USB Senser."""
import argparse
from array import array
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from elftools.elf.elffile import ELFFile

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(REPO),
    str(REPO / "research/common"),
    str(REPO / "research/device/zve10_hardware_map"),
]

import senser_fix  # noqa: F401
from capture_display_state import TerminalSession, TerminalTimeout
from pmca.commands.usb import senserShellCommand
from pmca.platform.backend.senser import SenserPlatformBackend
from zve10_dumpall import _preflight

GCC = Path("C:/msys64/ucrt64/bin/arm-none-eabi-gcc.exe")
RUNNER_SRC = Path(__file__).resolve().parent / "senser_bayer_runner.c"
RUNNER_BIN = REPO / ".local/out/senser_bayer_runner/bayer_test"

BAYER_WIDTH = 1996
BAYER_HEIGHT = 1122
BAYER_STRIDE_PIXELS = 2016
MODE5_GEOMETRY = (BAYER_WIDTH, BAYER_HEIGHT, BAYER_STRIDE_PIXELS)
MODE37_GEOMETRY = (6048, 360, 6048)
MODE37_FALLBACK = "MODE5 PIX nonzero=0 -> trying MODE37 ISP0_AIF3"


def build_runner() -> bytes:
    """Compile standalone static Linux ARM ELF binary and verify its ELF headers."""
    RUNNER_BIN.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(GCC),
        "-mcpu=cortex-a5",
        "-marm",
        "-O2",
        "-Wall",
        "-Wextra",
        "-nostdlib",
        "-ffreestanding",
        "-static",
        "-Wl,-e,_start",
        "-Wl,-Ttext=0x00010000",
        "-Wl,--build-id=none",
        str(RUNNER_SRC),
        "-o",
        str(RUNNER_BIN),
    ]
    subprocess.run(cmd, check=True)
    with RUNNER_BIN.open("rb") as stream:
        elf = ELFFile(stream)
        assert elf.header["e_type"] == "ET_EXEC", elf.header["e_type"]
        assert elf.header["e_machine"] == "EM_ARM", elf.header["e_machine"]
        segs = [seg["p_type"] for seg in elf.iter_segments()]
        assert "PT_INTERP" not in segs, segs
    data = RUNNER_BIN.read_bytes()
    print(f"Built {RUNNER_BIN} ({len(data)} bytes)", flush=True)
    return data


def save_bayer_preview(raw_bytes: bytes, out_dir: Path, stem: str, *,
                       geometry=MODE5_GEOMETRY, green_only=False) -> Path:
    """Render one pixel per Bayer cell using the supplied row geometry."""
    width, height, stride = geometry
    if len(raw_bytes) != stride * height * 2:
        raise ValueError(f"Unexpected RAW length for {width}x{height}, stride {stride}")
    out_w, out_h = width // 2, height // 2
    words = array("H")
    words.frombytes(raw_bytes)
    if sys.byteorder != "little":
        words.byteswap()
    if green_only:
        max_val = max(
            (words[y * stride + x + 1] + words[(y + 1) * stride + x]) >> 1
            for y in range(0, height, 4)
            for x in range(0, width, 4)
        )
    else:
        max_val = max(words[y * stride + x] for y in range(0, height, 4) for x in range(0, width, 4))
    white = max(max_val, 1)
    rgb = bytearray(out_w * out_h * 3)
    idx = 0
    for dy in range(out_h):
        r0 = (dy * 2) * stride
        r1 = r0 + stride
        for dx in range(out_w):
            sx = dx * 2
            p_g = (words[r0 + sx + 1] + words[r1 + sx]) >> 1
            p_r = p_g if green_only else words[r0 + sx]
            p_b = p_g if green_only else words[r1 + sx + 1]
            rgb[idx] = min(255, p_r * 255 // white)
            rgb[idx + 1] = min(255, p_g * 255 // white)
            rgb[idx + 2] = min(255, p_b * 255 // white)
            idx += 3

    try:
        from PIL import Image  # type: ignore

        png_path = out_dir / f"{stem}.png"
        Image.frombytes("RGB", (out_w, out_h), bytes(rgb)).save(png_path)
        return png_path
    except ImportError:
        ppm_path = out_dir / f"{stem}.ppm"
        header = f"P6\n{out_w} {out_h}\n255\n".encode("ascii")
        ppm_path.write_bytes(header + bytes(rgb))
        return ppm_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=["rdcw0", "full", "full-sgc3", "still", "check"], default="full")
    args = parser.parse_args()

    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    runner_bytes = build_runner()

    log_lines: list[str] = []
    report: dict = {"runner_bytes": len(runner_bytes), "runs": {}, "previews": {}}

    def session_worker(device):
        SenserPlatformBackend(device).start()
        device.setTerminalEnable(False)
        device.setTerminalEnable(True)
        commands: set[str] = set()
        terminal = TerminalSession(device.dev, commands)

        def drain():
            while device.dev.readTerminal():
                pass

        def run(cmd: str, *, allow_failure: bool = False, timeout: int = 30) -> tuple[int, str]:
            if len(cmd + ";echo C999=$?") > 68:
                raise ValueError(f"Command exceeds 68-byte terminal limit: {cmd!r}")
            commands.add(cmd)
            try:
                rc, body = terminal.run(cmd, timeout=timeout)
            except TerminalTimeout as error:
                log_lines.append(f"$ {cmd}  # timed out\n{error.output}\n")
                print(f"$ {cmd} -> timed out\n{error.output}", flush=True)
                raise
            log_lines.append(f"$ {cmd}  # rc={rc}\n{body}\n")
            print(f"$ {cmd} -> rc={rc}\n{body}", flush=True)
            if rc != 0 and not allow_failure:
                raise RuntimeError(f"Command failed (rc={rc}): {cmd}")
            return rc, body

        def read_remote(remote_path: str) -> bytes:
            buf = BytesIO()
            device.readFile(remote_path, buf)
            drain()
            return buf.getvalue()

        def maybe_fetch_raw(remote_path, tag, capture_log, *, geometry=MODE5_GEOMETRY, green_only=False):
            marker = re.search(rf"(?m)^SAVED {re.escape(remote_path)} bytes=(\d+)\s*$", capture_log)
            if not marker:
                if re.search(r"(?m)^PIX nonzero=[1-9]\d*", capture_log):
                    raise RuntimeError(f"{tag} reported pixels without a complete {remote_path} dump")
                return
            width, height, stride = geometry
            expected_bytes = stride * height * 2
            if int(marker.group(1)) != expected_bytes:
                raise ValueError(f"{tag} dump reported {marker.group(1)} bytes, expected {expected_bytes}")
            raw = read_remote(remote_path)
            if len(raw) != expected_bytes:
                raise ValueError(f"{tag} readback was {len(raw)} bytes, expected {expected_bytes}")
            raw_out = out / Path(remote_path).name
            raw_out.write_bytes(raw)
            preview = save_bayer_preview(raw, out, f"preview_{tag}", geometry=geometry, green_only=green_only)
            report["previews"][tag] = {
                "raw": str(raw_out), "bytes": len(raw), "preview": str(preview),
                "width": width, "height": height, "stride_pixels": stride,
                "green_only": green_only,
            }
            print(f"Downloaded {raw_out} ({len(raw)} bytes) -> {preview}", flush=True)
            run(f"rm -f {remote_path}", allow_failure=True)

        preview_started = False
        try:
            rc_bb, _ = run("test -x /tmp/busybox", allow_failure=True)
            if rc_bb != 0:
                run("ln -s /log/yuy2_640_v27snap/busybox /tmp/busybox")
            run("cd /usr/bin")
            run('sc(){ /tmp/busybox timeout 28 ./scenario.elf "$@"; }')

            rc_bt, _ = run("test -f /tmp/bayer_test", allow_failure=True)
            existing = read_remote("/tmp/bayer_test") if rc_bt == 0 else None
            if existing != runner_bytes:
                run("rm -f /tmp/bayer_test", allow_failure=True)
                device.writeFile("/tmp/bayer_test", runner_bytes)
                drain()
                if read_remote("/tmp/bayer_test") != runner_bytes:
                    raise RuntimeError("/tmp/bayer_test upload readback mismatch")
            run("chmod 755 /tmp/bayer_test")
            _, cmdline_out = run("busybox cat /proc/cmdline", allow_failure=True)
            report["cmdline"] = cmdline_out.strip()

            _, check_out = run("/tmp/bayer_test check")
            report["runs"]["check"] = check_out

            if args.mode in ("full", "full-sgc3", "still"):
                _, full_out = run(f"/tmp/bayer_test {args.mode}", timeout=40)
                report["runs"]["full"] = full_out
                if args.mode == "still" or MODE37_FALLBACK in full_out:
                    report["full_capture_mode"] = "0x37"
                    dma = re.search(
                        r"(?m)^M37 DMA busy_seen=([01]) idle_after_busy=([01]) "
                        r"peak_offset=(\d+) errors=([0-9a-fA-F]{8})", full_out,
                    )
                    if dma:
                        busy, idle, peak, errors = dma.groups()
                        report["mode37_dma"] = {
                            "busy_seen": busy == "1", "idle_after_busy": idle == "1",
                            "peak_offset": int(peak), "error_register_or": int(errors, 16),
                        }
                    maybe_fetch_raw("/tmp/bayer_m37.raw", "mode37", full_out,
                                    geometry=MODE37_GEOMETRY, green_only=True)
                else:
                    report["full_capture_mode"] = "0x05"
                    maybe_fetch_raw("/tmp/bayer_full.raw", "full", full_out)

                m_nz = re.search(r"(?m)^PIX nonzero=(\d+)", full_out)
                report["full_nonzero"] = int(m_nz.group(1)) if m_nz else 0

            if args.mode == "rdcw0":
                try:
                    run("sc CAMERA_SCN_EE_START_STOP b:1 b:0", timeout=36)
                    preview_started = True
                    _, rdcw0_out = run("/tmp/bayer_test rdcw0", timeout=30)
                    report["runs"]["rdcw0"] = rdcw0_out
                    maybe_fetch_raw("/tmp/bayer_rdcw0.raw", "rdcw0", rdcw0_out)
                    m_rnz = re.search(r"(?m)^PIX nonzero=(\d+)", rdcw0_out)
                    report["rdcw0_nonzero"] = int(m_rnz.group(1)) if m_rnz else 0
                finally:
                    if preview_started:
                        run("sc CAMERA_SCN_EE_START_STOP b:16 b:0", timeout=36, allow_failure=True)
                        preview_started = False
        finally:
            failed = sys.exc_info()[0] is not None
            try:
                device.setTerminalEnable(False)
            except Exception as error:
                if not failed:
                    raise
                report["terminal_cleanup_error"] = str(error)

    try:
        _preflight()
        expected_key = "check" if args.mode == "check" else ("rdcw0" if args.mode == "rdcw0" else "full")
        for _attempt in range(3):
            senserShellCommand(complete=session_worker)
            if expected_key in report["runs"]:
                break
            time.sleep(2.5)
        if expected_key not in report["runs"]:
            raise RuntimeError("No Senser test session completed")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (out / "log.txt").write_text("\n".join(log_lines), encoding="utf-8")
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

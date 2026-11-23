"""Opaque-box helpers, oracles, probe builders, and integrity guards for E2E QEMU tests."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
DUMPS_DIR = REPO_ROOT / ".local" / "dumps"
ZVE10_QEMU_DIR = Path(r"D:\02_Development_And_Projects\zve10-qemu")
QEMU_BIN = REPO_ROOT / ".local" / "emulator" / "bin" / "qemu-system-arm.exe"
UCRT64_BIN = Path(r"C:\msys64\ucrt64\bin")
ARM_GCC = UCRT64_BIN / "arm-none-eabi-gcc.exe"
ARM_OBJCOPY = UCRT64_BIN / "arm-none-eabi-objcopy.exe"
ZVOS_DIR = REPO_ROOT / "research" / "device" / "zve10_ram_boot"
BUILD_RTOS_PY = ZVOS_DIR / "build_rtos.py"

QEMU_TARBALL_SHA256 = "731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016"

R3_EXPECTED_HEAD = "42554a639e005455a1cc492744bd77341e7c41d2"
R3_ALLOWED_DIRTY_STATUS = frozenset(
    {
        " M scripts/menu_build.py",
        " M scripts/menu_host.py",
        " M scripts/menu_run.py",
        "?? scripts/win_prepare.py",
        "?? start-zve10-menu.ps1",
        "?? start-zve10.ps1",
    }
)
# Local 2026-11-16 21:36:52.442626 -> epoch 1794839812.442626; allow sub-second within :52
R3_MAX_MTIME_EPOCH = 1794839812.999999

LINUX_PANIC_MARKERS = (
    "Kernel panic",
    "Unable to handle kernel",
    "Oops:",
    "VFS: Cannot open root device",
)

RTOS_DISPLAY_PALETTE_RGBA4444 = (
    0xFFFF,  # White
    0xFF0F,  # Yellow
    0x0FFF,  # Cyan
    0x0F0F,  # Green
    0xF0FF,  # Magenta
    0xF00F,  # Red
    0x00FF,  # Blue
    0x000F,  # Black
)
RTOS_DISPLAY_PALETTE_RGB = tuple(
    (((w >> 12) & 0xF) * 17, ((w >> 8) & 0xF) * 17, ((w >> 4) & 0xF) * 17)
    for w in RTOS_DISPLAY_PALETTE_RGBA4444
)

ZVRT_HEADER_STRUCT = struct.Struct("<8I")
ZVRT_MAGIC = 0x5452565A
ZVRT_PROBE_OK = 0x4F4B5254
ZVRT_PROBE_FAIL = 0x4641494C

DUMP_BASELINE_FILES = (
    "firmware/vmlinux.bin",
    "firmware/initrd.img",
    "firmware/av-cam.bin",
    "firmware/bootrom",
    "nflasha7.img",
    "nflasha15.img",
)


def ucrt64_env(extra_env: dict[str, str] | None = None, *, strip_ucrt64: bool = False) -> dict[str, str]:
    """Return environment dict with or without C:\\msys64\\ucrt64\\bin on PATH."""
    env = os.environ.copy()
    path_parts = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    if strip_ucrt64:
        norm_ucrt = os.path.normcase(os.path.normpath(str(UCRT64_BIN)))
        path_parts = [
            p for p in path_parts
            if os.path.normcase(os.path.normpath(p)) != norm_ucrt
        ]
    elif str(UCRT64_BIN) not in path_parts:
        path_parts.insert(0, str(UCRT64_BIN))
    env["PATH"] = os.pathsep.join(path_parts)
    if extra_env:
        env.update(extra_env)
    return env


def run_subprocess_deadline(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_s: float = 15.0,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute subprocess with strict deadline and guaranteed kill on timeout."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="latin1",
        errors="replace",
        env=env,
        cwd=str(cwd) if cwd else None,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise AssertionError(
            f"Subprocess timed out after {timeout_s}s: {' '.join(cmd)}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def free_tcp_port() -> int:
    """Allocate an ephemeral loopback TCP port on Windows."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def list_qemu_pids() -> set[int]:
    """Return PIDs of running qemu-system-arm.exe processes on Windows."""
    if os.name != "nt":
        return set()
    res = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq qemu-system-arm.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    pids: set[int] = set()
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("INFO:"):
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == "qemu-system-arm.exe":
            try:
                pids.add(int(parts[1]))
            except ValueError:
                pass
    return pids


def enforce_no_qemu_leak(baseline_pids: set[int] | None = None) -> None:
    """Verify no new qemu-system-arm.exe processes were leaked; kill and fail if found."""
    base = baseline_pids or set()
    current = list_qemu_pids()
    leaked = sorted(current - base)
    if leaked:
        for pid in leaked:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=5,
            )
        raise AssertionError(
            f"Orphan qemu-system-arm.exe process(es) leaked after test teardown: {leaked}"
        )


def _scan_max_mtime(root: Path) -> tuple[float, Path | None]:
    """Fast os.scandir walk excluding .git returning (max_mtime, offending_path)."""
    max_mtime = 0.0
    max_path: Path | None = None
    stack = [root]
    while stack:
        cur = stack.pop()
        with os.scandir(cur) as it:
            for entry in it:
                if entry.name == ".git":
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                else:
                    st = entry.stat(follow_symlinks=False)
                    if st.st_mtime > max_mtime:
                        max_mtime = st.st_mtime
                        max_path = Path(entry.path)
    return max_mtime, max_path


def check_r3_snapshot(
    repo_dir: Path,
    *,
    expected_head: str | None = R3_EXPECTED_HEAD,
    allowed_dirty: frozenset[str] = R3_ALLOWED_DIRTY_STATUS,
    max_mtime: float = R3_MAX_MTIME_EPOCH,
) -> dict[str, Any]:
    """Verify git HEAD, git status --short allowlist, and file mtime ceiling."""
    head_proc = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if head_proc.returncode != 0:
        raise AssertionError(f"git rev-parse HEAD failed on {repo_dir}: {head_proc.stderr}")
    head = head_proc.stdout.strip()
    if expected_head is not None and head != expected_head:
        raise AssertionError(
            f"R3 violation in {repo_dir}: HEAD {head!r} != expected {expected_head!r}"
        )

    status_proc = subprocess.run(
        ["git", "-C", str(repo_dir), "status", "--short"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if status_proc.returncode != 0:
        raise AssertionError(f"git status failed on {repo_dir}: {status_proc.stderr}")
    observed_lines = {
        line.rstrip("\r\n")
        for line in status_proc.stdout.splitlines()
        if line.strip()
    }
    unexpected = sorted(observed_lines - allowed_dirty)
    missing = sorted(allowed_dirty - observed_lines)
    if unexpected or missing:
        raise AssertionError(
            f"R3 git status mismatch in {repo_dir}: unexpected={unexpected}, missing={missing}"
        )

    observed_max_mtime, max_file = _scan_max_mtime(repo_dir)
    if observed_max_mtime > max_mtime:
        raise AssertionError(
            f"R3 timestamp violation in {repo_dir}: {max_file} has mtime "
            f"{observed_max_mtime:.6f} > allowed {max_mtime:.6f}"
        )
    return {
        "head": head,
        "status": sorted(observed_lines),
        "max_mtime": observed_max_mtime,
        "max_file": str(max_file) if max_file else None,
    }


def assert_r3_zve10_qemu_unmodified(zve10_qemu_dir: Path = ZVE10_QEMU_DIR) -> dict[str, Any]:
    """Enforce R3 read-only baseline on D:\\02_Development_And_Projects\\zve10-qemu."""
    if not zve10_qemu_dir.is_dir():
        raise AssertionError(f"Reference repo missing: {zve10_qemu_dir}")
    return check_r3_snapshot(
        zve10_qemu_dir,
        expected_head=R3_EXPECTED_HEAD,
        allowed_dirty=R3_ALLOWED_DIRTY_STATUS,
        max_mtime=R3_MAX_MTIME_EPOCH,
    )


def file_sha256(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def snapshot_dumps_hashes(
    dumps_dir: Path = DUMPS_DIR,
    rel_paths: Iterable[str] = DUMP_BASELINE_FILES,
) -> dict[str, tuple[int, int, str]]:
    """Capture (size, mtime_ns, sha256) snapshot for read-only .local/dumps/ files."""
    snap: dict[str, tuple[int, int, str]] = {}
    for rel in rel_paths:
        target = dumps_dir / rel
        if not target.is_file():
            raise AssertionError(f"Expected read-only dump missing: {target}")
        st = target.stat()
        snap[rel] = (st.st_size, st.st_mtime_ns, file_sha256(target))
    return snap


def assert_dumps_unmodified(
    baseline: dict[str, tuple[int, int, str]],
    dumps_dir: Path = DUMPS_DIR,
) -> None:
    """Assert every tracked dump in .local/dumps/ has identical size, mtime, and SHA-256."""
    current = snapshot_dumps_hashes(dumps_dir, baseline.keys())
    diffs = []
    for rel, old_vals in baseline.items():
        new_vals = current[rel]
        if new_vals != old_vals:
            diffs.append(f"{rel}: before={old_vals} after={new_vals}")
    if diffs:
        raise AssertionError("Read-only .local/dumps/ files were modified:\n" + "\n".join(diffs))


class QmpClient:
    """Lightweight JSON-line TCP QMP client with strict timeouts and cleanup."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, timeout_s: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self._sock: socket.socket | None = None
        self._stream: Any = None
        self._ticket = 0

    def connect(self, connect_timeout_s: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + connect_timeout_s
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout_s)
            try:
                sock.connect((self.host, self.port))
                self._sock = sock
                self._stream = sock.makefile("rwb")
                greeting_raw = self._stream.readline()
                if not greeting_raw:
                    raise ConnectionError("QMP closed before greeting")
                greeting = json.loads(greeting_raw.decode("utf-8"))
                if "QMP" not in greeting:
                    raise RuntimeError(f"Unexpected QMP greeting: {greeting}")
                self.command("qmp_capabilities")
                return greeting
            except (OSError, ValueError, RuntimeError) as exc:
                last_err = exc
                self.close()
                time.sleep(0.05)
        raise TimeoutError(
            f"Timed out connecting QMP to {self.host}:{self.port} after {connect_timeout_s}s: {last_err}"
        )

    def command(self, execute: str, arguments: dict[str, Any] | None = None) -> Any:
        if self._stream is None:
            raise RuntimeError("QMP client is not connected")
        self._ticket += 1
        payload: dict[str, Any] = {"execute": execute, "id": self._ticket}
        if arguments:
            payload["arguments"] = arguments
        self._stream.write((json.dumps(payload) + "\n").encode("utf-8"))
        self._stream.flush()
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            line = self._stream.readline()
            if not line:
                raise ConnectionError(f"QMP connection closed during {execute!r}")
            reply = json.loads(line.decode("utf-8"))
            if "event" in reply:
                continue
            if reply.get("id") != self._ticket:
                continue
            if "error" in reply:
                err = reply["error"]
                raise RuntimeError(f"QMP error ({err.get('class')}): {err.get('desc')}")
            return reply.get("return")
        raise TimeoutError(f"QMP command {execute!r} timed out after {self.timeout_s}s")

    def query_status(self) -> dict[str, Any]:
        return self.command("query-status")

    def query_machines(self) -> list[dict[str, Any]]:
        return self.command("query-machines")

    def query_version(self) -> dict[str, Any]:
        return self.command("query-version")

    def screendump(self, out_path: Path, fmt: str = "png") -> Any:
        args: dict[str, Any] = {"filename": str(out_path)}
        if fmt:
            args["format"] = fmt
        return self.command("screendump", args)

    def pmemsave(self, val: int, size: int, filename: Path) -> Any:
        return self.command("pmemsave", {"val": val, "size": size, "filename": str(filename)})

    def qom_get(self, path: str, prop: str) -> Any:
        return self.command("qom-get", {"path": path, "property": prop})

    def qom_set(self, path: str, prop: str, value: Any) -> Any:
        return self.command("qom-set", {"path": path, "property": prop, "value": value})

    def stop_vm(self) -> Any:
        return self.command("stop")

    def cont_vm(self) -> Any:
        return self.command("cont")

    def quit(self) -> Any:
        return self.command("quit")

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
            self._stream = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> "QmpClient":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def assert_clean_linux_serial(serial_output: str) -> None:
    """Assert guest Linux serial contains no panic/oops/root-mount failure markers."""
    for marker in LINUX_PANIC_MARKERS:
        assert marker not in serial_output, (
            f"Unexpected kernel failure marker {marker!r} in serial output:\n"
            f"{serial_output[-2000:]}"
        )


def rgba4444_bytes_to_rgb_array(
    raw_bytes: bytes,
    width: int = 640,
    height: int = 480,
) -> np.ndarray:
    """Decode little-endian RRRRGGGGBBBBAAAA uint16 buffer into (H, W, 3) uint8 RGB."""
    expected = width * height * 2
    assert len(raw_bytes) == expected, f"Expected {expected} bytes, got {len(raw_bytes)}"
    words = np.frombuffer(raw_bytes, dtype="<u2").reshape((height, width))
    r = ((words >> 12) & 0xF).astype(np.uint8) * 17
    g = ((words >> 8) & 0xF).astype(np.uint8) * 17
    b = ((words >> 4) & 0xF).astype(np.uint8) * 17
    return np.stack([r, g, b], axis=-1)


def verify_png_frame(
    png_path: Path,
    expected_size: tuple[int, int] = (640, 480),
    min_distinct_colors: int = 2,
) -> np.ndarray:
    """Verify captured image exists, matches dimensions, and return (H, W, 3) uint8 array."""
    assert png_path.is_file(), f"Captured frame missing: {png_path}"
    assert png_path.stat().st_size > 0, f"Captured frame is empty: {png_path}"
    with Image.open(png_path) as img:
        assert img.size == expected_size, f"Expected size {expected_size}, got {img.size}"
        rgb_img = img.convert("RGB")
        arr = np.asarray(rgb_img, dtype=np.uint8)
    unique_colors = np.unique(arr.reshape(-1, 3), axis=0)
    assert len(unique_colors) >= min_distinct_colors, (
        f"Expected >= {min_distinct_colors} distinct RGB colors in {png_path}, "
        f"found {len(unique_colors)}: {unique_colors.tolist()}"
    )
    return arr


def verify_rtos_display_frame(rgb: np.ndarray) -> None:
    """Verify 640x480 8-bar color pattern from rtos_display.S."""
    assert rgb.shape == (480, 640, 3), f"Unexpected shape {rgb.shape}"
    for bar_idx, expected_rgb in enumerate(RTOS_DISPLAY_PALETTE_RGB):
        x = bar_idx * 80 + 40
        sample = tuple(int(v) for v in rgb[240, x])
        assert sample == expected_rgb, (
            f"Bar {bar_idx} at (x={x}, y=240): expected {expected_rgb}, got {sample}"
        )
    non_black_ratio = float(np.any(rgb != 0, axis=-1).mean())
    assert abs(non_black_ratio - 0.875) < 0.02, (
        f"Expected ~87.5% non-black pixels for 8-bar pattern, got {non_black_ratio:.3f}"
    )


def verify_os_shell_status_frame(
    rgb: np.ndarray,
    *,
    expected_sel: int = 0,
    has_clip: bool = False,
) -> None:
    """Verify os_shell.c Mode 0 (Status) banner, body, title, and yellow highlight."""
    assert rgb.shape == (480, 640, 3), f"Unexpected shape {rgb.shape}"
    banner_px = tuple(int(v) for v in rgb[10, 10])
    body_px = tuple(int(v) for v in rgb[440, 600])
    assert banner_px == (17, 34, 68), f"Expected banner (17,34,68), got {banner_px}"
    assert body_px == (0, 0, 34), f"Expected body (0,0,34), got {body_px}"

    title_region = rgb[36:52, 32:400]
    assert np.any(np.all(title_region == (255, 255, 255), axis=-1)), (
        "Expected white title pixels in os_shell banner (y=36..52, x=32..400)"
    )

    row0_region = rgb[88:104, 32:352]
    row1_region = rgb[120:136, 32:288]
    row0_yellow = bool(np.any(np.all(row0_region == (255, 255, 0), axis=-1)))
    row1_yellow = bool(np.any(np.all(row1_region == (255, 255, 0), axis=-1)))
    if expected_sel == 0:
        assert row0_yellow and not row1_yellow, (
            f"Expected row 0 yellow highlight (row0={row0_yellow}, row1={row1_yellow})"
        )
    elif expected_sel == 1:
        assert not row0_yellow, "Did not expect row 0 yellow when sel==1"
        if has_clip:
            assert row1_yellow, "Expected row 1 yellow highlight when sel==1 and has_clip=True"


def build_baremetal_arm_probe(
    out_dir: Path,
    name: str,
    c_source: str | None = None,
    *,
    asm_source: str | None = None,
    link_addr: int = 0x00010000,
    with_irq_vector: bool = False,
) -> Path:
    """Compile a standalone ARMv7 bare-metal probe ELF into out_dir."""
    if not ARM_GCC.is_file():
        raise AssertionError(f"ARM cross-compiler missing: {ARM_GCC}")
    out_dir.mkdir(parents=True, exist_ok=True)
    elf_path = out_dir / f"{name}.elf"

    sources: list[str] = []
    if c_source is not None:
        if with_irq_vector:
            start_s = """\
.syntax unified
.arm
.section .text.boot, "ax"
.global _start
_start:
    ldr r0, =_vectors
    mcr p15, 0, r0, c12, c0, 0
    isb
    cps #0x12
    ldr sp, =0x00FF0000
    cps #0x13
    ldr sp, =0x01000000
    bl probe_main
1:
    wfi
    b 1b

fault_irq:
    sub lr, lr, #4
    stmfd sp!, {r0-r3, r12, lr}
    bl probe_irq_handler
    ldmfd sp!, {r0-r3, r12, pc}^

.align 5
.global _vectors
_vectors:
    b _start
    b _start
    b _start
    b _start
    b _start
    b _start
    b fault_irq
    b _start
"""
        else:
            start_s = """\
.syntax unified
.arm
.section .text.boot, "ax"
.global _start
_start:
    ldr sp, =0x01000000
    bl probe_main
1:
    wfi
    b 1b
"""
        crt_path = out_dir / f"{name}_crt0.S"
        c_path = out_dir / f"{name}.c"
        ld_path = out_dir / f"{name}.ld"
        crt_path.write_text(start_s, encoding="utf-8")
        c_path.write_text(c_source, encoding="utf-8")
        ld_path.write_text(
            f"""\
ENTRY(_start)
SECTIONS {{
    . = 0x{link_addr:08x};
    .text : {{ *(.text.boot) *(.text*) }}
    .rodata : {{ *(.rodata*) }}
    .data : {{ *(.data*) }}
    .bss : {{ *(.bss*) *(COMMON) }}
}}
""",
            encoding="utf-8",
        )
        sources = [str(crt_path), str(c_path)]
        cmd = [
            str(ARM_GCC),
            "-march=armv7-a",
            "-marm",
            "-O2",
            "-nostdlib",
            "-ffreestanding",
            "-Wl,--build-id=none",
            "-T",
            str(ld_path),
            *sources,
            "-o",
            str(elf_path),
        ]
    elif asm_source is not None:
        s_path = out_dir / f"{name}.S"
        s_path.write_text(asm_source, encoding="utf-8")
        cmd = [
            str(ARM_GCC),
            "-march=armv7-a",
            "-marm",
            "-nostdlib",
            "-ffreestanding",
            "-Wl,--build-id=none",
            f"-Wl,-Ttext=0x{link_addr:08x}",
            str(s_path),
            "-o",
            str(elf_path),
        ]
    else:
        raise ValueError("Either c_source or asm_source must be provided")

    res = run_subprocess_deadline(cmd, env=ucrt64_env(), timeout_s=20.0)
    if res.returncode != 0:
        raise AssertionError(
            f"Failed compiling bare-metal probe {name}:\n{res.stdout}\n{res.stderr}"
        )
    return elf_path


# Common C prelude for UART0 PL011 probes
UART0_PROBE_C_PRELUDE = """\
#include <stdint.h>
#define UART0_DR   (*(volatile uint32_t *)0xF2000000U)
#define UART0_FR   (*(volatile uint32_t *)0xF2000018U)
static inline void mmio_w32(uint32_t addr, uint32_t val) {
    *(volatile uint32_t *)addr = val;
}
static inline uint32_t mmio_r32(uint32_t addr) {
    return *(volatile uint32_t *)addr;
}
static inline void mmio_w16(uint32_t addr, uint16_t val) {
    *(volatile uint16_t *)addr = val;
}
static inline uint16_t mmio_r16(uint32_t addr) {
    return *(volatile uint16_t *)addr;
}
static void uart_putc(char c) {
    while (UART0_FR & (1U << 5)) {}
    UART0_DR = (uint32_t)(uint8_t)c;
}
static void uart_puts(const char *s) {
    while (*s) {
        if (*s == '\\n') uart_putc('\\r');
        uart_putc(*s++);
    }
}
static void uart_puthex(uint32_t v) {
    static const char hx[] = "0123456789abcdef";
    for (int i = 28; i >= 0; i -= 4) uart_putc(hx[(v >> i) & 0xfU]);
}
"""


def build_zvos_payload(out_dir: Path, source_name: str, *, display: bool = True) -> Path:
    """Build ZVOS rtos.bin into out_dir using read-only research/device/zve10_ram_boot/build_rtos.py."""
    src = ZVOS_DIR / source_name
    assert src.is_file(), f"ZVOS source missing: {src}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(BUILD_RTOS_PY), "--source", str(src), "--out", str(out_dir)]
    if display:
        cmd.append("--display")
    res = run_subprocess_deadline(cmd, env=ucrt64_env(), timeout_s=30.0)
    if res.returncode != 0:
        raise AssertionError(
            f"build_rtos.py failed for {source_name}:\n{res.stdout}\n{res.stderr}"
        )
    rtos_bin = out_dir / "rtos.bin"
    assert rtos_bin.is_file(), f"Missing built ZVOS image: {rtos_bin}"
    return rtos_bin


def build_zvos_baremetal_elf(
    out_dir: Path,
    rtos_bin: Path,
    *,
    name: str = "zvos_boot",
    clip_bytes: bytes | None = None,
    arena_bytes: int = 0x10000,
    corrupt_handoff_magic: bool = False,
    handoff_pa: int = 0x02000000,
    pl310_on: bool = False,
) -> Path:
    """Package a ZVRT payload inside an opaque-box bare-metal ARM trampoline ELF.

    Sets up the exact hardware/ABI preconditions expected by ZVOS (`zvrt_handoff`,
    AIF mode table at 0x643EB19C, OSD0 Route-1 slot at 0x6441B27C, L1 1:1 + +0x60000000
    MMU map, sony-hwtimer #1 running, and initial VPH MMIO) and transfers control to
    the ZVRT entry point with r0 = &zvrt_handoff.
    """
    raw = rtos_bin.read_bytes()
    magic, version, hdr_bytes, code_bytes, entry, _crc, flags, _res = ZVRT_HEADER_STRUCT.unpack_from(raw)
    assert magic == ZVRT_MAGIC and version == 1, f"Invalid ZVRT header in {rtos_bin}"
    code = raw[hdr_bytes : hdr_bytes + code_bytes]

    out_dir.mkdir(parents=True, exist_ok=True)
    payload_bin = out_dir / f"{name}_payload.bin"
    payload_bin.write_bytes(code)

    clip_inc = ""
    has_clip = 0
    clip_len = 0
    if clip_bytes is not None:
        clip_path = out_dir / f"{name}_clip.bin"
        clip_path.write_bytes(clip_bytes)
        has_clip = 1
        clip_len = len(clip_bytes)
        clip_inc = f'.incbin "{clip_path.as_posix()}"'

    h_magic = 0xDEADBEEF if corrupt_handoff_magic else 0x4852565A
    h_bytes = 48 if has_clip else 40
    h_flags = 7 if has_clip else 3

    c_src = f"""\
#include <stdint.h>
{UART0_PROBE_C_PRELUDE}
extern const uint8_t zvos_payload_start[];
extern const uint8_t zvos_payload_end[];
extern const uint8_t zvos_clip_start[];
extern const uint8_t zvos_clip_end[];

typedef int (*zvos_entry_fn)(void *handoff);

void probe_main(void) {{
    /* 1. Build 16 KiB L1 page table at 0x00020000:
     *    0x000..0x3ff -> 1:1 DDR0 (Normal non-cacheable 0x00000C02)
     *    0x600..0x9ff -> +0x60000000 alias to DDR0 0x000..0x3ff
     *    0xf00..0xfff -> Device MMIO 0xf0000000..0xffffffff (0x00000406)
     */
    volatile uint32_t *l1 = (volatile uint32_t *)0x00020000U;
    for (uint32_t i = 0; i < 4096U; i++) l1[i] = 0U;
    for (uint32_t i = 0; i < 0x400U; i++) {{
        uint32_t desc = (i << 20) | 0x00000C02U;
        l1[i] = desc;
        l1[0x600U + i] = desc;
    }}
    for (uint32_t i = 0xF00U; i < 0x1000U; i++) {{
        l1[i] = (i << 20) | 0x00000406U;
    }}

    uint32_t dacr = 0x55555555U;
    uint32_t ttbcr = 0U;
    uint32_t ttbr0 = 0x00020000U;
    __asm__ volatile(
        "mcr p15, 0, %0, c3, c0, 0\\n"
        "mcr p15, 0, %1, c2, c0, 2\\n"
        "mcr p15, 0, %2, c2, c0, 0\\n"
        "mov r0, #0\\n"
        "mcr p15, 0, r0, c8, c7, 0\\n"
        "dsb sy\\n"
        "mrc p15, 0, r0, c1, c0, 0\\n"
        "orr r0, r0, #1\\n"
        "mcr p15, 0, r0, c1, c0, 0\\n"
        "isb sy\\n"
        :: "r"(dacr), "r"(ttbcr), "r"(ttbr0) : "r0", "memory"
    );

    /* 2. Start sony-hwtimer #1 (0xf2403100) at 4 MHz so zvrt_timer_ticks advances. */
    mmio_w32(0xF2403100U, 0x80001030U);
    mmio_w32(0xF2403100U, 0x00001030U);

    /* 3. Populate AIF mode table (0x643EB19C) and Route-1 OSD0 slot (0x6441B27C). */
    for (uint32_t ch = 0x39U; ch <= 0x40U; ch++) {{
        mmio_w32(0x643EB19CU + ch * 4U, 0x22BU);
    }}
    static const uint32_t slot_desc[14] = {{
        0x22C48000U, 0x01E00280U, 0U, 0x01E00280U, 0U, 0U, 0U, 0U, 0U, 0U,
        1U, 0x5F04001EU, 0x63733989U, 0U
    }};
    for (uint32_t i = 0; i < 14U; i++) {{
        mmio_w32(0x6441B27CU + i * 4U, slot_desc[i]);
    }}

    /* 4. Initialize VPH / OSD0 MMIO preconditions. */
    mmio_w32(0xF3445000U, 0x00010114U);
    mmio_w32(0xF3446000U, 0x00000000U);
    mmio_w32(0xF3440144U, 0x02000233U);
    mmio_w32(0xF3440404U, 0x00000000U);
    mmio_w32(0xF344042CU, 0x000001E0U);
    mmio_w32(0xF3441300U, 0x00000000U);
    mmio_w32(0xF3441304U, 0x00000000U);
    mmio_w32(0xF3441310U, 0x22C84E80U);
    if ({1 if pl310_on else 0}) {{
        mmio_w32(0xF8002100U, 1U);
    }}

    /* 5. Copy ZVRT code to 0x03100000 and optional clip to 0x1C000000. */
    uint32_t load_addr = 0x03100000U;
    uint32_t sz = (uint32_t)(zvos_payload_end - zvos_payload_start);
    const uint32_t *src = (const uint32_t *)zvos_payload_start;
    volatile uint32_t *dst = (volatile uint32_t *)load_addr;
    for (uint32_t i = 0; i < (sz + 3U) / 4U; i++) dst[i] = src[i];

    uint32_t clip_va = 0U;
    if ({has_clip}) {{
        clip_va = 0x1C000000U;
        const uint32_t *csrc = (const uint32_t *)zvos_clip_start;
        volatile uint32_t *cdst = (volatile uint32_t *)clip_va;
        uint32_t csz = (uint32_t)(zvos_clip_end - zvos_clip_start);
        for (uint32_t i = 0; i < (csz + 3U) / 4U; i++) cdst[i] = csrc[i];
    }}

    /* 6. Write zvrt_handoff at 0x{handoff_pa:08x}. */
    volatile uint32_t *h = (volatile uint32_t *)0x{handoff_pa:08x}U;
    h[0] = 0x{h_magic:08x}U;
    h[1] = 1U;
    h[2] = {h_bytes}U;
    h[3] = {h_flags}U;
    h[4] = 0x05000000U; /* arena_va */
    h[5] = 0x05000000U; /* arena_pa */
    h[6] = 0x{arena_bytes:08x}U;
    h[7] = 0U;          /* result */
    h[8] = 0x02100000U; /* clean_frame */
    h[9] = 614400U;
    h[10] = clip_va;
    h[11] = {clip_len}U;

    __asm__ volatile("mov r0, #0\\n mcr p15, 0, r0, c7, c5, 0\\n dsb sy\\n isb sy\\n" ::: "r0", "memory");
    zvos_entry_fn fn = (zvos_entry_fn)(load_addr + 0x{entry:x}U);
    int rc = fn((void *)0x{handoff_pa:08x}U);
    uart_puts("ZVOS_RET=");
    uart_puthex((uint32_t)rc);
    uart_puts(" RESULT=");
    uart_puthex(h[7]);
    uart_puts("\\n");
    while (1) {{ __asm__ volatile("wfi"); }}
}}
"""

    asm_blob = f"""\
.section .rodata
.balign 16
.global zvos_payload_start
.global zvos_payload_end
zvos_payload_start:
.incbin "{payload_bin.as_posix()}"
zvos_payload_end:
.balign 16
.global zvos_clip_start
.global zvos_clip_end
zvos_clip_start:
{clip_inc}
zvos_clip_end:
"""
    crt_s = """\
.syntax unified
.arm
.section .text.boot, "ax"
.global _start
_start:
    ldr sp, =0x01000000
    bl probe_main
1:
    wfi
    b 1b
"""
    crt_p = out_dir / f"{name}_crt0.S"
    blob_p = out_dir / f"{name}_blob.S"
    c_p = out_dir / f"{name}.c"
    ld_p = out_dir / f"{name}.ld"
    elf_p = out_dir / f"{name}.elf"
    crt_p.write_text(crt_s, encoding="utf-8")
    blob_p.write_text(asm_blob, encoding="utf-8")
    c_p.write_text(c_src, encoding="utf-8")
    ld_p.write_text(
        """\
ENTRY(_start)
SECTIONS {
    . = 0x00010000;
    .text : { *(.text.boot) *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
}
""",
        encoding="utf-8",
    )
    res = run_subprocess_deadline(
        [
            str(ARM_GCC),
            "-march=armv7-a",
            "-marm",
            "-O2",
            "-nostdlib",
            "-ffreestanding",
            "-Wl,--build-id=none",
            "-T",
            str(ld_p),
            str(crt_p),
            str(c_p),
            str(blob_p),
            "-o",
            str(elf_p),
        ],
        env=ucrt64_env(),
        timeout_s=20.0,
    )
    if res.returncode != 0:
        raise AssertionError(f"Failed compiling ZVOS trampoline {name}:\n{res.stdout}\n{res.stderr}")
    return elf_p


def _cpio_newc_entry(name: str, data: bytes, mode: int) -> bytes:
    name_b = name.encode("ascii") + b"\x00"
    hdr = (
        f"070701{0:08x}{mode:08x}{0:08x}{0:08x}"
        f"{1:08x}{0:08x}{len(data):08x}"
        f"{0:08x}{0:08x}{0:08x}{0:08x}"
        f"{len(name_b):08x}{0:08x}"
    ).encode("ascii")
    out = hdr + name_b
    out += b"\x00" * ((4 - (len(out) % 4)) % 4)
    out += data
    out += b"\x00" * ((4 - (len(out) % 4)) % 4)
    return out


def build_minimal_initrd_cpio(
    out_dir: Path,
    init_c_source: str,
    *,
    name: str = "initrd.cpio",
) -> Path:
    """Compile a minimal static Linux ARM EABI /init (zero libc) and pack as CPIO."""
    if not ARM_GCC.is_file():
        raise AssertionError(f"ARM cross-compiler missing: {ARM_GCC}")
    out_dir.mkdir(parents=True, exist_ok=True)
    start_s = """\
.syntax unified
.arm
.global _start
_start:
    bl init_main
    mov r0, #0
    mov r7, #1
    swi #0
1:
    wfi
    b 1b
"""
    s_path = out_dir / f"{name}_start.S"
    c_path = out_dir / f"{name}_init.c"
    elf_path = out_dir / f"{name}_init"
    cpio_path = out_dir / name
    s_path.write_text(start_s, encoding="utf-8")
    c_path.write_text(init_c_source, encoding="utf-8")
    res = run_subprocess_deadline(
        [
            str(ARM_GCC),
            "-march=armv7-a",
            "-marm",
            "-O2",
            "-nostdlib",
            "-ffreestanding",
            "-static",
            str(s_path),
            str(c_path),
            "-o",
            str(elf_path),
        ],
        env=ucrt64_env(),
        timeout_s=20.0,
    )
    if res.returncode != 0:
        raise AssertionError(f"Failed compiling minimal /init:\n{res.stdout}\n{res.stderr}")
    archive = (
        _cpio_newc_entry("init", elf_path.read_bytes(), 0o100755)
        + _cpio_newc_entry("TRAILER!!!", b"", 0)
    )
    cpio_path.write_bytes(archive)
    return cpio_path


LINUX_EABI_MINIMAL_C_PRELUDE = """\
#include <stdint.h>
static inline int sys_write(int fd, const void *buf, uint32_t count) {
    register int r0 __asm__("r0") = fd;
    register const void *r1 __asm__("r1") = buf;
    register uint32_t r2 __asm__("r2") = count;
    register int r7 __asm__("r7") = 4;
    __asm__ volatile("swi #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return r0;
}
static inline int sys_open(const char *path, int flags, int mode) {
    register const char *r0 __asm__("r0") = path;
    register int r1 __asm__("r1") = flags;
    register int r2 __asm__("r2") = mode;
    register int r7 __asm__("r7") = 5;
    __asm__ volatile("swi #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return r0;
}
static inline int sys_read(int fd, void *buf, uint32_t count) {
    register int r0 __asm__("r0") = fd;
    register void *r1 __asm__("r1") = buf;
    register uint32_t r2 __asm__("r2") = count;
    register int r7 __asm__("r7") = 3;
    __asm__ volatile("swi #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return r0;
}
static inline int sys_close(int fd) {
    register int r0 __asm__("r0") = fd;
    register int r7 __asm__("r7") = 6;
    __asm__ volatile("swi #0" : "+r"(r0) : "r"(r7) : "memory");
    return r0;
}
static inline int sys_mount(const char *src, const char *tgt, const char *fs, uint32_t flags, const void *data) {
    register const char *r0 __asm__("r0") = src;
    register const char *r1 __asm__("r1") = tgt;
    register const char *r2 __asm__("r2") = fs;
    register uint32_t r3 __asm__("r3") = flags;
    register const void *r4 __asm__("r4") = data;
    register int r7 __asm__("r7") = 21;
    __asm__ volatile("swi #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r7) : "memory");
    return r0;
}
static inline int sys_mkdir(const char *path, int mode) {
    register const char *r0 __asm__("r0") = path;
    register int r1 __asm__("r1") = mode;
    register int r7 __asm__("r7") = 39;
    __asm__ volatile("swi #0" : "+r"(r0) : "r"(r1), "r"(r7) : "memory");
    return r0;
}
static void out_str(const char *s) {
    uint32_t n = 0;
    while (s[n]) n++;
    sys_write(1, s, n);
}
static void dump_proc_file(const char *path) {
    char buf[512];
    int fd = sys_open(path, 0, 0);
    if (fd < 0) { out_str("OPEN_FAIL\\n"); return; }
    int n;
    while ((n = sys_read(fd, buf, sizeof(buf))) > 0) {
        sys_write(1, buf, (uint32_t)n);
    }
    sys_close(fd);
}
"""


def encode_zvba_test_clip(width: int = 320, height: int = 240, fps: int = 24) -> bytes:
    """Encode a valid 2-frame 1-bit XOR-PackBits ZVBA clip matching os_shell.c."""
    row_bytes = width // 8
    raw_frames = [b"\xFF" * (row_bytes * height), b"\x00" * (row_bytes * height)]
    prev = bytearray(len(raw_frames[0]))
    out = bytearray(struct.pack("<IHHII", 0x4142565A, width, height, fps, len(raw_frames)))
    for frame in raw_frames:
        xor_buf = bytes(a ^ b for a, b in zip(frame, prev))
        prev[:] = frame
        encoded = bytearray()
        i = 0
        while i < len(xor_buf):
            run = 1
            while i + run < len(xor_buf) and run < 128 and xor_buf[i + run] == xor_buf[i]:
                run += 1
            if run >= 3:
                encoded.append(257 - run)
                encoded.append(xor_buf[i])
                i += run
            else:
                lit_start = i
                i += 1
                while i < len(xor_buf) and (i - lit_start) < 128:
                    if i + 2 < len(xor_buf) and xor_buf[i] == xor_buf[i + 1] == xor_buf[i + 2]:
                        break
                    i += 1
                chunk = xor_buf[lit_start:i]
                encoded.append(len(chunk) - 1)
                encoded.extend(chunk)
        out.extend(struct.pack("<I", len(encoded)))
        out.extend(encoded)
    return bytes(out)


def prepare_stock_kernel_with_boot_stub(boot_stub_mod: Any, vmlinux_path: Path, out_dir: Path) -> Path:
    """Invoke emulator.boot_stub public interface to wrap stock vmlinux.bin into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for fn_name in ("build_boot_image", "create_boot_image", "prepare_kernel", "wrap_vmlinux", "build_stub"):
        fn = getattr(boot_stub_mod, fn_name, None)
        if callable(fn):
            out_path = out_dir / "vmlinux_atags.bin"
            try:
                res = fn(vmlinux_path, out_path)
            except TypeError:
                res = fn(vmlinux_path=vmlinux_path, out_path=out_path)
            if isinstance(res, (str, Path)):
                return Path(res)
            if out_path.is_file():
                return out_path
    raise AssertionError(
        "emulator.boot_stub does not expose a recognized public wrapper function "
        "(expected build_boot_image / create_boot_image / prepare_kernel / wrap_vmlinux / build_stub)"
    )


def prepare_staged_storage(storage_mod: Any, dumps_dir: Path, work_dir: Path, **options: Any) -> Any:
    """Invoke emulator.storage public interface to stage writable storage artifacts into work_dir."""
    work_dir.mkdir(parents=True, exist_ok=True)
    for fn_name in ("stage_storage", "prepare_storage", "build_storage_images", "create_storage_bundle"):
        fn = getattr(storage_mod, fn_name, None)
        if callable(fn):
            return fn(dumps_dir=dumps_dir, work_dir=work_dir, **options)
    raise AssertionError(
        "emulator.storage does not expose a recognized public staging function "
        "(expected stage_storage / prepare_storage / build_storage_images / create_storage_bundle)"
    )


def run_probe_with_runner(
    runner_cls: type,
    *,
    kernel: Path,
    workdir: Path,
    wait_pattern: str | None = None,
    timeout_s: float = 10.0,
    append: str = "",
    initrd: Path | None = None,
    smp: int = 1,
    memory: str = "1024",
    display: str = "none",
    qmp_port: int | None = None,
    extra_args: list[str] | None = None,
) -> Any:
    """Instantiate QemuRunner via PROJECT.md contract, run, and always stop in finally."""
    serial_log = workdir / "serial.log"
    kwargs: dict[str, Any] = {
        "kernel": kernel,
        "append": append,
        "smp": smp,
        "memory": memory,
        "display": display,
        "serial_log": serial_log,
        "timeout_s": timeout_s,
    }
    if initrd is not None:
        kwargs["initrd"] = initrd
    if qmp_port is not None:
        kwargs["qmp_port"] = qmp_port
    if extra_args:
        kwargs["extra_args"] = extra_args
    runner = runner_cls(**kwargs)
    runner.start()
    try:
        if wait_pattern is not None:
            return runner.wait_for_serial(wait_pattern, timeout_s=timeout_s)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(0.05)
        return runner.stop()
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def run_qemu_and_qmp_capture(
    runner_cls: type,
    *,
    kernel: Path,
    workdir: Path,
    out_png: Path,
    wait_s: float = 1.5,
    timeout_s: float = 12.0,
) -> tuple[Any, Path]:
    """Boot QEMU headlessly, wait for guest rendering, capture OSD0 PNG, and stop."""
    qmp_port = free_tcp_port()
    runner = runner_cls(
        kernel=kernel,
        display="none",
        serial_log=workdir / "serial.log",
        qmp_port=qmp_port,
        timeout_s=timeout_s,
    )
    runner.start()
    try:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            time.sleep(0.05)
        if hasattr(runner, "capture_osd0_png"):
            runner.capture_osd0_png(out_png)
        else:
            runner.capture_screendump(out_png)
        result = runner.stop()
        return result, out_png
    finally:
        try:
            runner.stop()
        except Exception:
            pass


def drive_adc_gpio_stimulus(
    runner: Any,
    *,
    qmp_client: QmpClient | None = None,
    adc1_b3: int | None = None,
    adc1_b0: int | None = None,
    adc0_a4: int | None = None,
    gpio_g00: int | None = None,
) -> None:
    """Inject host-side ADC0/ADC1/GPIO stimulus via QemuRunner or QMP qom-set contract."""
    # Prefer public QemuRunner injection method if provided by M3, else standard QMP qom-set.
    if hasattr(runner, "set_input_state"):
        runner.set_input_state(
            adc1_b3=adc1_b3,
            adc1_b0=adc1_b0,
            adc0_a4=adc0_a4,
            gpio_g00=gpio_g00,
        )
        return

    def _qom(path: str, prop: str, val: int) -> None:
        if qmp_client is not None:
            qmp_client.qom_set(path, prop, val)
        else:
            runner.qmp_command("qom-set", {"path": path, "property": prop, "value": val})

    if adc1_b3 is not None:
        _qom("/machine/soc/adc1", "ch3", adc1_b3)
    if adc1_b0 is not None:
        _qom("/machine/soc/adc1", "ch0", adc1_b0)
    if adc0_a4 is not None:
        _qom("/machine/soc/adc0", "ch4", adc0_a4)
    if gpio_g00 is not None:
        _qom("/machine/soc/gpio", "g00", gpio_g00)

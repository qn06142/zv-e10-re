"""Non-interactive QEMU runner, QMP client, OSD0 PNG decoder, and R3 guard."""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QEMU_BIN = REPO_ROOT / ".local" / "emulator" / "bin" / "qemu-system-arm.exe"
DEFAULT_ZVE10_QEMU_DIR = Path(r"D:\02_Development_And_Projects\zve10-qemu")
DEFAULT_MSYS_UCRT64_BIN = Path(r"C:\msys64\ucrt64\bin")

EXPECTED_ZVE10_QEMU_HEAD = "42554a639e005455a1cc492744bd77341e7c41d2"
ALLOWED_ZVE10_QEMU_DIRTY = frozenset(
    {
        " M scripts/menu_build.py",
        " M scripts/menu_host.py",
        " M scripts/menu_run.py",
        "?? scripts/win_prepare.py",
        "?? start-zve10-menu.ps1",
        "?? start-zve10.ps1",
    }
)
# Max mtime in zve10-qemu (2026-11-16 21:36:52.442626 +07:00 == 1794839812.442626)
MAX_ZVE10_QEMU_MTIME_EPOCH = 1794839812.999999


class QemuRunnerError(RuntimeError):
    """Raised when QEMU startup, QMP, or serial I/O fails."""


class R3ViolationError(RuntimeError):
    """Raised when D:\\02_Development_And_Projects\\zve10-qemu appears modified."""


@dataclass(frozen=True)
class BootResult:
    returncode: int | None
    serial_output: str
    timed_out: bool
    elapsed_s: float
    serial_bytes: bytes = b""


@dataclass(frozen=True)
class R3Status:
    ok: bool
    repo_path: Path
    head: str
    dirty_entries: tuple[str, ...]
    unexpected_dirty: tuple[str, ...]
    max_mtime_epoch: float
    file_count: int
    newest_file: str
    errors: tuple[str, ...]


def verify_zve10_qemu_unmodified(
    repo_path: Path | str = DEFAULT_ZVE10_QEMU_DIR,
    *,
    raise_on_error: bool = True,
) -> R3Status:
    """Verify R3: D:\\02_Development_And_Projects\\zve10-qemu is 100% untouched."""
    repo = Path(repo_path)
    errors: list[str] = []
    head = ""
    dirty_entries: list[str] = []
    unexpected_dirty: list[str] = []
    max_mtime = 0.0
    file_count = 0
    newest_file = ""

    if not repo.is_dir():
        errors.append(f"Reference directory does not exist: {repo}")
    else:
        try:
            head_proc = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            head = head_proc.stdout.strip()
            if head != EXPECTED_ZVE10_QEMU_HEAD:
                errors.append(
                    f"HEAD mismatch: expected {EXPECTED_ZVE10_QEMU_HEAD}, got {head!r}"
                )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"Failed to read git HEAD: {exc}")

        try:
            status_proc = subprocess.run(
                ["git", "-C", str(repo), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            dirty_entries = [
                line.rstrip("\r")
                for line in status_proc.stdout.splitlines()
                if line.strip()
            ]
            unexpected_dirty = [
                entry for entry in dirty_entries if entry not in ALLOWED_ZVE10_QEMU_DIRTY
            ]
            if unexpected_dirty:
                errors.append(
                    "Unexpected dirty/untracked entries: " + ", ".join(unexpected_dirty)
                )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"Failed to read git status: {exc}")

        try:
            stack = [str(repo)]
            while stack:
                current = stack.pop()
                with os.scandir(current) as it:
                    for entry in it:
                        if entry.name == ".git":
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            file_count += 1
                            st = entry.stat(follow_symlinks=False)
                            if st.st_mtime > max_mtime:
                                max_mtime = st.st_mtime
                                newest_file = entry.path
            if max_mtime > MAX_ZVE10_QEMU_MTIME_EPOCH:
                errors.append(
                    f"File mtime {max_mtime:.6f} exceeds R3 cutoff "
                    f"{MAX_ZVE10_QEMU_MTIME_EPOCH:.6f}: {newest_file}"
                )
        except OSError as exc:
            errors.append(f"Failed scanning files under {repo}: {exc}")

    status = R3Status(
        ok=not errors,
        repo_path=repo,
        head=head,
        dirty_entries=tuple(dirty_entries),
        unexpected_dirty=tuple(unexpected_dirty),
        max_mtime_epoch=max_mtime,
        file_count=file_count,
        newest_file=newest_file,
        errors=tuple(errors),
    )
    if raise_on_error and not status.ok:
        raise R3ViolationError("; ".join(status.errors))
    return status


def rgba4444_to_png(
    raw: bytes,
    out_path: Path | str,
    *,
    width: int = 640,
    height: int = 480,
) -> Path:
    """Decode little-endian CXD90045 OSD0 RGBA4444 pixels into a PNG file."""
    expected = width * height * 2
    if len(raw) != expected:
        raise ValueError(
            f"RGBA4444 buffer length mismatch: expected {expected} bytes ({width}x{height}x2), got {len(raw)}"
        )
    words = np.frombuffer(raw, dtype="<u2").reshape((height, width))
    r = (((words >> 12) & 0xF) * 17).astype(np.uint8)
    g = (((words >> 8) & 0xF) * 17).astype(np.uint8)
    b = (((words >> 4) & 0xF) * 17).astype(np.uint8)
    a = ((words & 0xF) * 17).astype(np.uint8)
    rgba = np.stack((r, g, b, a), axis=-1)

    dst = Path(out_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(dst, format="PNG")
    return dst


def _free_tcp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


class QmpClient:
    """Minimal thread-safe JSON QMP client over TCP or an existing socket."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        timeout_s: float = 15.0,
        *,
        sock: socket.socket | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._ticket = 0
        self._timeout_s = timeout_s
        if sock is None:
            if port <= 0:
                raise ValueError("port must be > 0 when sock is not provided")
            sock = socket.create_connection((host, port), timeout=timeout_s)
        else:
            sock.settimeout(timeout_s)
        self._sock = sock
        self._reader = sock.makefile("r", encoding="utf-8", errors="replace", newline="\n")
        self._negotiate()

    @classmethod
    def from_socket(cls, sock: socket.socket, timeout_s: float = 15.0) -> QmpClient:
        return cls(timeout_s=timeout_s, sock=sock)

    def _read_msg(self) -> dict[str, Any]:
        line = self._reader.readline()
        if not line:
            raise QemuRunnerError("QMP connection closed unexpectedly (EOF)")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QemuRunnerError(f"Invalid QMP JSON line: {line!r}") from exc
        if not isinstance(obj, dict):
            raise QemuRunnerError(f"Expected QMP JSON object, got {type(obj).__name__}")
        return obj

    def _negotiate(self) -> None:
        greeting = self._read_msg()
        if "QMP" not in greeting:
            raise QemuRunnerError(f"Unexpected QMP greeting: {greeting!r}")
        self.call("qmp_capabilities")

    def call(self, cmd: str, args: Mapping[str, Any] | None = None) -> Any:
        with self._lock:
            self._ticket += 1
            req_id = self._ticket
            payload: dict[str, Any] = {"execute": cmd, "id": req_id}
            if args:
                payload["arguments"] = dict(args)
            raw = (json.dumps(payload) + "\n").encode("utf-8")
            try:
                self._sock.sendall(raw)
                while True:
                    msg = self._read_msg()
                    if "event" in msg and "id" not in msg:
                        continue
                    if msg.get("id") is not None and msg.get("id") != req_id:
                        continue
                    if "error" in msg:
                        raise QemuRunnerError(f"QMP error for {cmd}: {msg['error']}")
                    if "return" in msg:
                        return msg["return"]
            except OSError as exc:
                raise QemuRunnerError(f"QMP socket error during {cmd}: {exc}") from exc

    def close(self) -> None:
        try:
            self._reader.close()
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass


class QemuRunner:
    """Non-interactive controller for QEMU (`-M zve10`) with serial & QMP."""

    def __init__(
        self,
        *,
        qemu_bin: Path | str | None = None,
        machine: str = "zve10",
        cpu: str | None = "cortex-a9",
        smp: int = 1,
        memory: str | int = "1024",
        kernel: Path | str | None = None,
        initrd: Path | str | None = None,
        append: str | None = None,
        drives: Sequence[str | Mapping[str, Any]] = (),
        sd: Path | str | None = None,
        pflash: Sequence[str | Path] | Path | str | None = None,
        device_loader: Sequence[str | Mapping[str, Any]] = (),
        display: str = "none",
        serial_log: Path | str | None = None,
        qmp_socket: Path | str | None = None,
        qmp_port: int | None = None,
        serial_port: int | None = None,
        timeout_s: float = 30.0,
        no_reboot: bool = True,
        nodefaults: bool = False,
        extra_args: Sequence[str] = (),
        env: Mapping[str, str] | None = None,
        msys_ucrt64_bin: Path | str = DEFAULT_MSYS_UCRT64_BIN,
    ) -> None:
        self.qemu_bin = Path(qemu_bin) if qemu_bin is not None else DEFAULT_QEMU_BIN
        self.machine = machine
        self.cpu = cpu
        self.smp = int(smp)
        self.memory = str(memory)
        self.kernel = Path(kernel) if kernel is not None else None
        self.initrd = Path(initrd) if initrd is not None else None
        self.append = append
        self.drives = tuple(drives)
        self.sd = Path(sd) if sd is not None else None
        self.pflash = pflash
        self.device_loader = tuple(device_loader)
        self.display = display
        self.serial_log = Path(serial_log) if serial_log is not None else None
        self.qmp_socket = Path(qmp_socket) if qmp_socket is not None else None
        self.qmp_port = qmp_port
        self.serial_port = serial_port
        self.timeout_s = float(timeout_s)
        self.no_reboot = no_reboot
        self.nodefaults = nodefaults
        self.extra_args = tuple(extra_args)
        self.env = dict(env) if env is not None else None
        self.msys_ucrt64_bin = Path(msys_ucrt64_bin)

        self._proc: subprocess.Popen[bytes] | None = None
        self._qmp: QmpClient | None = None
        self._serial_sock: socket.socket | None = None
        self._serial_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._serial_log_fh: Any = None
        self._serial_cond = threading.Condition()
        self._serial_buf = bytearray()
        self._serial_eof = False
        self._stderr_lines: deque[str] = deque(maxlen=100)
        self._start_monotonic: float | None = None
        self._active_serial_port: int | None = None
        self._active_qmp_port: int | None = None

    def build_env(self) -> dict[str, str]:
        env = dict(self.env) if self.env is not None else os.environ.copy()
        prepend: list[str] = [str(self.qemu_bin.parent)]
        if self.msys_ucrt64_bin.is_dir():
            prepend.append(str(self.msys_ucrt64_bin))
        existing = env.get("PATH", "")
        env["PATH"] = os.pathsep.join([*prepend, existing]) if existing else os.pathsep.join(prepend)
        return env

    def _resolve_ports(self) -> tuple[int, int]:
        serial_port = self.serial_port if self.serial_port else _free_tcp_port()
        qmp_port = self.qmp_port if self.qmp_port else _free_tcp_port()
        while qmp_port == serial_port:
            qmp_port = _free_tcp_port()
        return serial_port, qmp_port

    def build_command(
        self,
        *,
        serial_port: int | None = None,
        qmp_port: int | None = None,
    ) -> list[str]:
        s_port = serial_port if serial_port is not None else (self._active_serial_port or self.serial_port or 0)
        q_port = qmp_port if qmp_port is not None else (self._active_qmp_port or self.qmp_port or 0)

        cmd: list[str] = [
            str(self.qemu_bin),
            "-M",
            self.machine,
        ]
        if self.cpu:
            cmd.extend(["-cpu", self.cpu])
        cmd.extend(["-smp", str(self.smp), "-m", self.memory])

        if self.kernel is not None:
            cmd.extend(["-kernel", str(self.kernel)])
        if self.initrd is not None:
            cmd.extend(["-initrd", str(self.initrd)])
        if self.append is not None:
            cmd.extend(["-append", self.append])

        for drv in self.drives:
            if isinstance(drv, Mapping):
                spec = ",".join(f"{k}={v}" for k, v in drv.items())
            else:
                spec = str(drv)
            cmd.extend(["-drive", spec])

        if self.sd is not None:
            cmd.extend(["-sd", str(self.sd)])

        if self.pflash is not None:
            pflash_items = (
                [self.pflash]
                if isinstance(self.pflash, (str, Path))
                else list(self.pflash)
            )
            for pf in pflash_items:
                cmd.extend(["-pflash", str(pf)])

        for loader in self.device_loader:
            if isinstance(loader, Mapping):
                parts = []
                for k, v in loader.items():
                    if k == "addr" and isinstance(v, int):
                        parts.append(f"addr=0x{v:x}")
                    else:
                        parts.append(f"{k}={v}")
                cmd.extend(["-device", "loader," + ",".join(parts)])
            else:
                spec = str(loader)
                if not spec.startswith("loader,"):
                    spec = "loader," + spec
                cmd.extend(["-device", spec])

        if self.display == "none":
            cmd.extend(["-display", "none"])
        elif self.display == "vnc":
            cmd.extend(["-display", "none", "-vnc", "127.0.0.1:0"])
        elif self.display.startswith("vnc:"):
            disp = self.display.split(":", 1)[1]
            cmd.extend(["-display", "none", "-vnc", f"127.0.0.1:{disp}"])
        else:
            cmd.extend(["-display", self.display])

        cmd.extend(["-serial", f"tcp:127.0.0.1:{s_port},server=on,wait=on"])
        if os.name != "nt" and self.qmp_socket is not None:
            cmd.extend(["-qmp", f"unix:{self.qmp_socket},server=on,wait=off"])
        else:
            cmd.extend(["-qmp", f"tcp:127.0.0.1:{q_port},server=on,wait=off"])

        cmd.extend(["-monitor", "none"])
        if self.nodefaults:
            cmd.append("-nodefaults")
        if self.no_reboot:
            cmd.append("-no-reboot")
        cmd.extend(self.extra_args)
        return cmd

    def _connect_tcp(self, port: int, timeout_s: float) -> socket.socket:
        deadline = time.monotonic() + timeout_s
        last_exc: OSError | None = None
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                stderr_tail = "\n".join(self._stderr_lines)
                raise QemuRunnerError(
                    f"QEMU exited early (rc={self._proc.returncode}) while connecting to port {port}:\n{stderr_tail}"
                )
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=1.0)
                sock.settimeout(None)
                return sock
            except OSError as exc:
                last_exc = exc
                time.sleep(0.02)
        raise QemuRunnerError(f"Timed out connecting to QEMU port {port}: {last_exc}")

    def _serial_reader_loop(self, sock: socket.socket) -> None:
        try:
            while True:
                try:
                    data = sock.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                if self._serial_log_fh is not None:
                    try:
                        self._serial_log_fh.write(data)
                        self._serial_log_fh.flush()
                    except OSError:
                        pass
                with self._serial_cond:
                    self._serial_buf.extend(data)
                    self._serial_cond.notify_all()
        finally:
            with self._serial_cond:
                self._serial_eof = True
                self._serial_cond.notify_all()

    def _stderr_reader_loop(self, pipe: Any) -> None:
        try:
            for raw_line in iter(pipe.readline, b""):
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                self._stderr_lines.append(line)
        except OSError:
            pass
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    def start(self) -> QemuRunner:
        if self._proc is not None:
            raise QemuRunnerError("QemuRunner already started")
        if not self.qemu_bin.is_file():
            raise FileNotFoundError(f"QEMU binary not found: {self.qemu_bin}")

        last_err: Exception | None = None
        max_attempts = 3 if (not self.serial_port or not self.qmp_port) else 1

        for attempt in range(max_attempts):
            self._serial_buf.clear()
            self._serial_eof = False
            self._stderr_lines.clear()

            s_port, q_port = self._resolve_ports()
            self._active_serial_port = s_port
            self._active_qmp_port = q_port

            if self.serial_log is not None:
                self.serial_log.parent.mkdir(parents=True, exist_ok=True)
                self._serial_log_fh = self.serial_log.open("wb")

            cmd = self.build_command(serial_port=s_port, qmp_port=q_port)
            env = self.build_env()
            self._start_monotonic = time.monotonic()

            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                if self._proc.stdout is not None:
                    self._stderr_thread = threading.Thread(
                        target=self._stderr_reader_loop,
                        args=(self._proc.stdout,),
                        daemon=True,
                        name="qemu-stderr-reader",
                    )
                    self._stderr_thread.start()

                connect_timeout = min(15.0, max(5.0, self.timeout_s))
                self._serial_sock = self._connect_tcp(s_port, connect_timeout)
                self._serial_thread = threading.Thread(
                    target=self._serial_reader_loop,
                    args=(self._serial_sock,),
                    daemon=True,
                    name="qemu-serial-reader",
                )
                self._serial_thread.start()

                qmp_sock = self._connect_tcp(q_port, connect_timeout)
                self._qmp = QmpClient.from_socket(qmp_sock, timeout_s=connect_timeout)
                return self
            except Exception as exc:
                last_err = exc
                self.stop()
                if attempt + 1 < max_attempts:
                    continue
                raise

        assert last_err is not None
        raise last_err

    @property
    def serial_bytes(self) -> bytes:
        with self._serial_cond:
            return bytes(self._serial_buf)

    @property
    def serial_output(self) -> str:
        return self.serial_bytes.decode("utf-8", errors="replace")

    def wait_for_serial(
        self,
        pattern: str | bytes | re.Pattern[str] | re.Pattern[bytes],
        timeout_s: float | None = None,
        *,
        regex: bool = False,
        start_pos: int = 0,
    ) -> str:
        """Wait until pattern appears in UART0 serial output."""
        wait_limit = self.timeout_s if timeout_s is None else float(timeout_s)
        deadline = time.monotonic() + wait_limit

        with self._serial_cond:
            while True:
                if isinstance(pattern, re.Pattern):
                    if isinstance(pattern.pattern, bytes):
                        m = pattern.search(bytes(self._serial_buf), start_pos)
                        if m:
                            return m.group(0).decode("utf-8", errors="replace")
                    else:
                        text = self._serial_buf.decode("utf-8", errors="replace")
                        m = pattern.search(text, start_pos)
                        if m:
                            return m.group(0)
                elif isinstance(pattern, bytes):
                    if regex:
                        m = re.search(pattern, bytes(self._serial_buf)[start_pos:])
                        if m:
                            return m.group(0).decode("utf-8", errors="replace")
                    else:
                        if pattern in self._serial_buf[start_pos:]:
                            return pattern.decode("utf-8", errors="replace")
                else:
                    text = self._serial_buf.decode("utf-8", errors="replace")
                    if regex:
                        m = re.search(pattern, text[start_pos:])
                        if m:
                            return m.group(0)
                    else:
                        if pattern in text[start_pos:]:
                            return pattern

                if self._serial_eof or (self._proc is not None and self._proc.poll() is not None):
                    tail = self._serial_buf.decode("utf-8", errors="replace")[-1000:]
                    raise QemuRunnerError(
                        f"Serial stream ended before pattern {pattern!r} appeared; tail:\n{tail}"
                    )

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    tail = self._serial_buf.decode("utf-8", errors="replace")[-1000:]
                    raise TimeoutError(
                        f"Timed out after {wait_limit:.2f}s waiting for {pattern!r}; tail:\n{tail}"
                    )
                self._serial_cond.wait(timeout=min(remaining, 0.25))

    def send_serial(self, text: str | bytes) -> None:
        if self._serial_sock is None:
            raise QemuRunnerError("Serial socket is not connected")
        data = text.encode("utf-8") if isinstance(text, str) else text
        try:
            self._serial_sock.sendall(data)
        except OSError as exc:
            raise QemuRunnerError(f"Failed sending serial data: {exc}") from exc

    def qmp_command(self, cmd: str, args: Mapping[str, Any] | None = None) -> Any:
        if self._qmp is None:
            raise QemuRunnerError("QMP client is not connected")
        return self._qmp.call(cmd, args)

    def pmemsave(
        self,
        addr: int,
        size: int,
        out_path: Path | str,
        *,
        pause: bool = True,
    ) -> bytes:
        dst = Path(out_path).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        paused = False
        try:
            if pause:
                status = self.qmp_command("query-status")
                if status.get("status") != "paused":
                    self.qmp_command("stop")
                    paused = True
            self.qmp_command(
                "pmemsave",
                {"val": int(addr), "size": int(size), "filename": str(dst)},
            )
        finally:
            if paused:
                try:
                    self.qmp_command("cont")
                except QemuRunnerError:
                    pass
        data = dst.read_bytes()
        if len(data) != size:
            raise QemuRunnerError(
                f"pmemsave size mismatch: expected {size} bytes, got {len(data)}"
            )
        return data

    def capture_screendump(
        self,
        out_path: Path | str,
        *,
        device: str | None = None,
        head: int | None = None,
    ) -> Path:
        dst = Path(out_path).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        args: dict[str, Any] = {}
        if device is not None:
            args["device"] = device
        if head is not None:
            args["head"] = int(head)

        if dst.suffix.lower() == ".png":
            fd, tmp_name = tempfile.mkstemp(suffix=".ppm", dir=str(dst.parent))
            os.close(fd)
            tmp_ppm = Path(tmp_name)
            try:
                args["filename"] = str(tmp_ppm)
                self.qmp_command("screendump", args)
                with Image.open(tmp_ppm) as img:
                    img.save(dst, format="PNG")
            finally:
                try:
                    tmp_ppm.unlink(missing_ok=True)
                except OSError:
                    pass
            return dst

        args["filename"] = str(dst)
        self.qmp_command("screendump", args)
        return dst

    def capture_osd0_png(
        self,
        out_path: Path | str,
        *,
        fb_addr: int | None = None,
        width: int = 640,
        height: int = 480,
    ) -> Path:
        dst = Path(out_path).resolve()
        if fb_addr is None:
            return self.capture_screendump(dst)

        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(suffix=".raw", dir=str(dst.parent))
        os.close(fd)
        tmp_raw = Path(tmp_name)
        try:
            raw = self.pmemsave(fb_addr, width * height * 2, tmp_raw, pause=True)
            return rgba4444_to_png(raw, dst, width=width, height=height)
        finally:
            try:
                tmp_raw.unlink(missing_ok=True)
            except OSError:
                pass

    def stop(self, *, timed_out: bool = False) -> BootResult:
        returncode: int | None = None
        if self._qmp is not None:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    self._qmp.call("quit")
                except QemuRunnerError:
                    pass
            self._qmp.close()
            self._qmp = None

        if self._proc is not None:
            if self._proc.poll() is None:
                try:
                    self._proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                        self._proc.wait(timeout=3.0)
            returncode = self._proc.returncode
            self._proc = None

        if self._serial_sock is not None:
            try:
                self._serial_sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._serial_sock.close()
            except OSError:
                pass
            self._serial_sock = None

        if self._serial_thread is not None:
            self._serial_thread.join(timeout=2.0)
            self._serial_thread = None

        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1.0)
            self._stderr_thread = None

        if self._serial_log_fh is not None:
            try:
                self._serial_log_fh.flush()
                self._serial_log_fh.close()
            except OSError:
                pass
            self._serial_log_fh = None

        elapsed = (
            time.monotonic() - self._start_monotonic
            if self._start_monotonic is not None
            else 0.0
        )
        raw = self.serial_bytes
        return BootResult(
            returncode=returncode,
            serial_output=raw.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            elapsed_s=elapsed,
            serial_bytes=raw,
        )

    def run(
        self,
        wait_pattern: str | bytes | re.Pattern[str] | re.Pattern[bytes] | None = None,
        *,
        timeout_s: float | None = None,
    ) -> BootResult:
        limit = self.timeout_s if timeout_s is None else float(timeout_s)
        timed_out = False
        self.start()
        try:
            if wait_pattern is not None:
                try:
                    self.wait_for_serial(wait_pattern, timeout_s=limit)
                except TimeoutError:
                    timed_out = True
            else:
                assert self._proc is not None
                try:
                    self._proc.wait(timeout=limit)
                except subprocess.TimeoutExpired:
                    timed_out = True
        finally:
            result = self.stop(timed_out=timed_out)
        return result

    def __enter__(self) -> QemuRunner:
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

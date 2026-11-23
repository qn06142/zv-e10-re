"""Launch and inspect the adapted original Sony menu on standalone QEMU.

Run `python -m emulator.menu --window` for a pixel viewer with arrow keys. This profile does not claim unattended stock boot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time

from PIL import Image, ImageChops

from emulator.build_menu import DEFAULT_MENU_WORK, build_menu
from emulator.runner import QemuRunner, rgba4444_to_png

MENU_CMDLINE = (
    "console=ttyAM0,115200n8 cfg.uart=1 mem=1G@0 "
    "memrsv=0x1A5E000@0x02E68000 memrsv=128M@0x20000000:uc "
    "rdinit=/init loglevel=8"
)


class MenuSession:
    """Own one adapted guest, native input sequence, and verified OSD capture."""

    def __init__(self, build: dict, *, log_path: Path):
        self.sequence = 0
        self.ready = None
        self.build = build
        self.runner = QemuRunner(
            machine="zve10,strict-cpu=off", cpu=None, smp=1, memory="1024",
            kernel=build["kernel"], initrd=build["initrd"], append=MENU_CMDLINE,
            serial_log=log_path, timeout_s=180,
        )

    def __enter__(self):
        self.runner.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def _json(self, prefix: str, *, start: int = 0, timeout: float = 25) -> dict:
        matched = self.runner.wait_for_serial(
            re.escape(prefix) + r"(\{[^\r\n]+\})", regex=True,
            start_pos=start, timeout_s=timeout,
        )
        return json.loads(matched[len(prefix):])

    def wait_ready(self, timeout: float = 180) -> dict:
        self.ready = self._json("NE_READY ", timeout=timeout)
        if self.ready.get("native_glyph_images", 0) < 13:
            raise ValueError("Native menu has not completed its initial glyph images")
        return self.ready

    def press(self, key: str) -> dict:
        if key not in {"DOWN", "UP", "LEFT", "RIGHT"}:
            raise ValueError(f"Unsupported menu key: {key}")
        # The reference wire labels are reversed relative to Sony FunctionIDs:
        # native vertical IDs 1/2 mean Up/Down; horizontal wire labels already match.
        wire_key = {"DOWN": "UP", "UP": "DOWN", "LEFT": "LEFT", "RIGHT": "RIGHT"}[key]
        before = self.state()
        self.sequence += 1
        start = len(self.runner.serial_output)
        self.runner.send_serial(f"KEY {self.sequence} {wire_key}\n")
        self._json("NE_KEY_SENT ", start=start)
        consumed = self.runner.wait_for_serial(
            rf'NE_INPUT_CONSUMED \{{"sequence":{self.sequence},[^\r\n]+\}}',
            regex=True, start_pos=start, timeout_s=25,
        )
        event = json.loads(consumed[len("NE_INPUT_CONSUMED "):])
        # Consumption precedes the deferred view action and renderer work.
        # Wait for after_draw to observe this input on a later retired frame.
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            observed = self.state()
            if observed["last_input"] >= self.sequence and observed["frame"] > before["frame"]:
                event["completed_frame"] = observed["frame"]
                return event
            time.sleep(0.1)
        raise TimeoutError("Native input was consumed without a completed view frame")

    def state(self) -> dict:
        start = len(self.runner.serial_output)
        self.runner.send_serial("STATE\n")
        return self._json("NE_SNAPSHOT ", start=start)

    def capture(self, path: Path) -> dict:
        """Compare QEMU's display with the guest-owned physical framebuffer."""
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.runner.qmp_command("stop")
        try:
            text = self.runner.qmp_command("human-monitor-command", {"command-line": "xp /1wx 0xf3441320"})
            address = int(text.split()[-1], 16)
            if not 0x20000000 <= address <= 0x28000000 - 640 * 480 * 2:
                raise ValueError(f"Guest menu has not published an OSD framebuffer: {address:#x}")
            self.runner.capture_screendump(path)
            with tempfile.TemporaryDirectory(prefix="menu-frame-") as folder:
                root = Path(folder)
                raw = self.runner.pmemsave(address, 640 * 480 * 2, root / "frame.raw", pause=False)
                rgba4444_to_png(raw, root / "expected.png")
                with Image.open(path) as screen, Image.open(root / "expected.png") as expected:
                    if screen.size != (640, 480) or ImageChops.difference(
                            screen.convert("RGB"), expected.convert("RGB")).getbbox():
                        raise ValueError("QEMU scanout differs from guest RGBA4444 framebuffer")
                    colors = len(screen.convert("RGB").getcolors(640 * 480) or [])
                    if colors < 16:
                        raise ValueError("Menu frame is blank or lacks native UI detail")
        finally:
            self.runner.qmp_command("cont")
        return {"framebuffer": f"0x{address:08x}", "width": 640, "height": 480,
                "raw_sha256": hashlib.sha256(raw).hexdigest(), "colors": colors,
                "qmp_matches_guest_memory": True, "png": str(path)}

    def capture_settled(self, path: Path, *, timeout: float = 25) -> dict:
        """Wait for a stable menu frame rather than capturing mid-redraw."""
        deadline = time.monotonic() + timeout
        previous = None
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            frame = self.capture(path)
            if frame["raw_sha256"] != previous:
                stable_since = time.monotonic()
            previous = frame["raw_sha256"]
            if time.monotonic() - stable_since >= 3.0:
                return frame
            time.sleep(0.3)
        raise TimeoutError("Menu did not settle to a stable framebuffer")

    def close(self) -> dict:
        stopped = False
        try:
            if self.ready is not None:
                self.ready = None
                start = len(self.runner.serial_output)
                self.runner.send_serial("STOP\n")
                self.runner.wait_for_serial("NE_STOPPED", start_pos=start, timeout_s=15)
                stopped = True
                self.ready = None
        finally:
            result = self.runner.stop()
        if result.returncode not in (0, None):
            raise RuntimeError(f"QEMU exited with {result.returncode}")
        return {"guest_transport_stopped": stopped, "qemu_returncode": result.returncode}


def show_window(session: MenuSession, path: Path) -> None:
    import tkinter as tk
    from PIL import ImageTk
    root = tk.Tk()
    root.title("Sony ZV-E10 — adapted original menu")
    label = tk.Label(root)
    label.pack()
    tk.Label(root, text="Arrow keys navigate").pack()
    def refresh():
        session.capture(path)
        with Image.open(path) as picture:
            label.image = ImageTk.PhotoImage(picture.copy())
        label.configure(image=label.image)
        root.after(300, refresh)
    def key(event):
        mapping = {"Down": "DOWN", "Up": "UP", "Left": "LEFT", "Right": "RIGHT",
                   "KP_Down": "DOWN", "KP_Up": "UP"}
        if event.keysym in mapping:
            session.press(mapping[event.keysym])
    root.bind("<KeyPress>", key)
    root.after(0, refresh)
    root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_MENU_WORK)
    parser.add_argument("--output", type=Path, default=DEFAULT_MENU_WORK / "menu.png")
    parser.add_argument("--window", action="store_true")
    parser.add_argument("--key", action="append", choices=["DOWN", "UP", "LEFT", "RIGHT"], default=[])
    parser.add_argument("--language", choices=["english", "captured"], default="english")
    args = parser.parse_args()
    build = build_menu(work_dir=args.work_dir, language=args.language)
    session = MenuSession(build, log_path=args.work_dir / "serial.log")
    report = {"profile": "adapted-original-menu", "stock_normal_boot": False,
              "build": build, "inputs": [], "frames": []}
    with session:
        report["ready"] = session.wait_ready()
        report["frames"].append(session.capture_settled(args.output))
        for index, key in enumerate(args.key, 1):
            report["inputs"].append(session.press(key))
            report["frames"].append(session.capture_settled(
                args.output.with_name(f"{args.output.stem}-{index}-{key.lower()}.png")))
        if args.window:
            show_window(session, args.output)
        report["shutdown"] = session.close()
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ready": report["ready"], "frames": report["frames"],
                      "shutdown": report["shutdown"]}, indent=2))


if __name__ == "__main__":
    main()

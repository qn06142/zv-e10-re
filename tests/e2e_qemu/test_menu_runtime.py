"""Regression for actual Sony menu pixels, guest OSD scanout, and native input."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image
import pytest

from emulator.build_menu import build_menu, digest
from emulator.menu import MenuSession
from emulator.runner import DEFAULT_QEMU_BIN, DEFAULT_ZVE10_QEMU_DIR, verify_zve10_qemu_unmodified

pytestmark = [pytest.mark.e2e_qemu, pytest.mark.tier1, pytest.mark.skipif(
    not DEFAULT_QEMU_BIN.is_file() or not DEFAULT_ZVE10_QEMU_DIR.is_dir(),
    reason="Built standalone QEMU and pinned local menu reference are required",
)]

# Bound to the pinned English Sony menu resources and visually reviewed PNG.
# These checks reject blank frames and transitional frames missing row text.
TITLE_SHA = "8b51026430b6eeaf03bf0a5307e5b3ebec7b09cdaddb1626e0d1886d55bf063d"
FORMAT_ROW_SHA = "9512337f0f717ad9562d473ccd24e7f8067d532cef05825d0c9524c6f063e977"


def test_original_menu_pixels_scanout_and_navigation(qemu_workdir: Path) -> None:
    build = build_menu()
    immutable = {Path(build[key]): digest(Path(build[key])) for key in ("kernel", "initrd")}
    verify_zve10_qemu_unmodified()
    try:
        session = MenuSession(build, log_path=qemu_workdir / "menu-serial.log")
        with session:
            ready = session.wait_ready()
            assert ready["native_glyph_images"] >= 13
            initial = session.capture_settled(qemu_workdir / "menu.png")
            assert initial["raw_sha256"] == "2a87fa9405312a096e9cd8b3d3300ccb387172e481934613dddbd69fdd879189"
            with Image.open(initial["png"]) as image:
                rgb = image.convert("RGB")
                assert hashlib.sha256(rgb.crop((0, 0, 640, 125)).tobytes()).hexdigest() == TITLE_SHA
                assert hashlib.sha256(rgb.crop((17, 126, 623, 175)).tobytes()).hexdigest() == FORMAT_ROW_SHA
            event = session.press("DOWN")
            assert event["sequence"] == 1 and event["function"] == 2
            down = session.capture_settled(qemu_workdir / "menu-down.png")
            assert down["raw_sha256"] != initial["raw_sha256"]
            assert initial["qmp_matches_guest_memory"] and down["qmp_matches_guest_memory"]
            session.press("UP")
            restored = session.capture_settled(qemu_workdir / "menu-up.png")
            with Image.open(restored["png"]) as image:
                assert hashlib.sha256(image.convert("RGB").crop((17, 126, 623, 175)).tobytes()).hexdigest() == FORMAT_ROW_SHA
            session.press("RIGHT")
            right = session.capture_settled(qemu_workdir / "menu-right.png")
            assert right["raw_sha256"] != restored["raw_sha256"]
            with Image.open(right["png"]) as image:
                assert hashlib.sha256(image.convert("RGB").crop((0, 0, 640, 125)).tobytes()).hexdigest() == "d08a1a729c8ce0da06e6e8c1727dcc0ad5cc1a5820f037a732849b2b6cf5120c"
            session.press("LEFT")
            left = session.capture_settled(qemu_workdir / "menu-left.png")
            with Image.open(left["png"]) as image:
                assert hashlib.sha256(image.convert("RGB").crop((0, 0, 640, 125)).tobytes()).hexdigest() == TITLE_SHA
            assert "NE_ERROR" not in session.runner.serial_output
            shutdown = session.close()
            assert shutdown == {"guest_transport_stopped": True, "qemu_returncode": 0}
    finally:
        assert {p: digest(p) for p in immutable} == immutable
        verify_zve10_qemu_unmodified()

"""Build the explicit original-menu adapter from a pinned read-only reference.

This is a separate guest profile from stock /sbin/init. Firmware and kernel
binaries remain in ignored local storage. The runtime uses pmca-re's QEMU.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from emulator.boot_stub import CpioEntry, build_cpio_newc, build_uimage
from emulator.runner import DEFAULT_ZVE10_QEMU_DIR, verify_zve10_qemu_unmodified

HERE = Path(__file__).resolve().parent
DEFAULT_MENU_WORK = HERE.parent / ".local/emulator/menu"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_menu(*, work_dir: Path = DEFAULT_MENU_WORK,
               reference: Path = DEFAULT_ZVE10_QEMU_DIR, language: str = "english") -> dict:
    """Copy pinned inputs, build locally, and add guest-driven OSD scanout."""
    if language not in {"english", "captured"}:
        raise ValueError("Menu language must be english or captured")
    work = Path(work_dir).resolve()
    reference = Path(reference).resolve()
    if work.is_relative_to(reference):
        raise ValueError("Menu output must be outside the read-only reference")
    verify_zve10_qemu_unmodified(reference)
    pins = json.loads((HERE / "menu_reference.json").read_text(encoding="utf-8"))
    for relative, expected in pins.items():
        source = reference / relative
        if digest(source) != expected:
            raise ValueError(f"Menu reference input changed: {relative}")
        destination = work / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file() or digest(destination) != expected:
            shutil.copyfile(source, destination)

    # The copied Windows CPIO writer is isolated from the reference's fwtool
    # imports. No Python module is imported or executed from the reference.
    source = (reference / "scripts/win_prepare.py").read_text(encoding="utf-8")
    function = next(n for n in ast.parse(source).body
                    if isinstance(n, ast.FunctionDef) and n.name == "cpio_newc_entry")
    (work / "scripts/win_prepare.py").write_text(
        "import stat\n" + ast.get_source_segment(source, function) + "\n", encoding="utf-8")
    adapter_id = hashlib.sha256((json.dumps(pins, sort_keys=True) + language +
                                (digest(HERE / "menu_osd.h") + digest(Path(__file__)))).encode()).hexdigest()[:12]
    out = work / f"build-{adapter_id}"
    receipt_path = out / "pmca-build.json"
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if all((out / name).is_file() and digest(out / name) == value
               for name, value in receipt["artifacts"].items()):
            return receipt
        raise ValueError("Menu build artifacts changed; choose a fresh work directory")
    if out.exists():
        raise ValueError(f"Incomplete menu build at {out}; choose a fresh work directory")

    env = os.environ.copy()
    env["PATH"] = r"C:\msys64\ucrt64\bin" + os.pathsep + env.get("PATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(work / "scripts")
    subprocess.run([sys.executable, "-B", "-c",
                    "from pathlib import Path; import sys, menu_build; "
                    "menu_build.build(Path(sys.argv[1]), None, Path(sys.argv[2]))",
                    str(work), str(out)], env=env, check=True)

    code_path = out / "observer-derived.c"
    code = code_path.read_text(encoding="utf-8")
    # Select the coherent final transaction, not the last intermediate GPE
    # pass. Multi-pass menu rendering may present an incomplete buffer last.
    transport_path = out / "transport.inc"
    transport = transport_path.read_text(encoding="utf-8")
    seam = "            ne_retired_frame = frame;"
    if transport.count(seam) != 1:
        raise ValueError("Pinned framebuffer retirement seam changed")
    transport_path.write_text(transport.replace(
        seam, seam + "\n            if (ne_latest_valid && ne_latest.frame == frame)\n"
                     "                pmca_menu_present(ne_latest.physical);"), encoding="utf-8")
    code = '#include "menu_osd.h"\n' + code
    code_path.write_text(code, encoding="utf-8")
    shutil.copyfile(HERE / "menu_osd.h", out / "menu_osd.h")
    original_build = json.loads((out / "build.json").read_text(encoding="utf-8"))
    command = original_build["command"]
    built = subprocess.run(command, env=env, capture_output=True, text=True)
    (out / "pmca-compile.log").write_text(built.stdout + built.stderr, encoding="utf-8")
    built.check_returncode()
    # The inherited diagnostic script forks cat for every process/thread.
    # This old UI kernel has a bounded ASID pool: the dump eventually kills
    # PID 1 with "Cannot allocate ASID". Keep PID 1 waiting on its application.
    init_path = out / "init-native.sh"
    init_text = init_path.read_text(encoding="utf-8")
    init_seam = 'echo "BOOTIN_PID=$!"\n'
    if init_text.count(init_seam) != 1:
        raise ValueError("Pinned menu init ownership seam changed")
    init_path.write_text(init_text.split(init_seam)[0] + init_seam +
                         "wait\nwhile :; do sleep 3600; done\n", encoding="utf-8")
    overlay = build_cpio_newc([
        CpioEntry("usr", stat.S_IFDIR | 0o755),
        CpioEntry("usr/lib", stat.S_IFDIR | 0o755),
        CpioEntry("init", stat.S_IFREG | 0o755,
                  (out / "init-native.sh").read_bytes().replace(b"\r\n", b"\n")),
        CpioEntry("usr/lib/libnativeentry.so", stat.S_IFREG | 0o755,
                  (out / "libnativeentry.so").read_bytes()),
    ])
    text_banks = {}
    language_overlay = b""
    if language == "english":
        wanted = {"usr/share/app/string_english.uxc", "usr/share/app/string_english_f.uxc"}
        banks = extract_newc_files(work / "work/ui.cpio", wanted)
        entries = []
        for source_name, data in banks.items():
            destination = source_name.replace("string_english", "string_japanese")
            entries.append(CpioEntry(destination, stat.S_IFREG | 0o644, data))
            text_banks[destination] = {"original_bank": source_name,
                                       "sha256": hashlib.sha256(data).hexdigest()}
        language_overlay = build_cpio_newc(entries)
    initrd = out / "menu.cpio"
    shutil.copyfile(work / "work/ui.cpio", initrd)
    with initrd.open("ab") as stream:
        stream.write(overlay)
        stream.write(language_overlay)
    kernel = out / "menu.uImage"
    kernel.write_bytes(build_uimage((work / "work/kbuild-ui/arch/arm/boot/Image").read_bytes(),
                                   load_addr=0x138000, entry_addr=0x138000))
    receipt = {
        "language": language, "text_banks": text_banks,
        "profile": "adapted-original-menu", "stock_normal_boot": False,
        "reference_head": "42554a639e005455a1cc492744bd77341e7c41d2",
        "kernel": str(kernel), "initrd": str(initrd),
        "source_manifest_sha256": digest(HERE / "menu_reference.json"),
        "guest_osd_bridge_sha256": digest(HERE / "menu_osd.h"),
        "artifacts": {p.name: digest(p) for p in (kernel, initrd, out / "libnativeentry.so")},
        "original_menu_resources": True, "host_draws_menu": False,
        "input_model": "adapted native function events; physical panel mapping unverified",
    }
    verify_zve10_qemu_unmodified(reference)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def extract_newc_files(archive: Path, wanted: set[str]) -> dict[str, bytes]:
    """Read selected original resource banks without extracting the archive."""
    found = {}
    with archive.open("rb") as stream:
        while len(found) < len(wanted):
            start = stream.tell()
            header = stream.read(110)
            if len(header) != 110 or header[:6] != b"070701":
                raise ValueError("Original menu archive is missing requested language banks")
            fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
            size, name_size = fields[6], fields[11]
            name = stream.read(name_size).rstrip(b"\0").decode().removeprefix("./")
            data_start = (stream.tell() + 3) & ~3
            if name == "TRAILER!!!":
                raise ValueError("Original menu archive is missing requested language banks")
            stream.seek(data_start)
            if name in wanted:
                data = stream.read(size)
                if len(data) != size:
                    raise ValueError("Truncated original language bank")
                found[name] = data
            stream.seek((data_start + size + 3) & ~3)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_MENU_WORK)
    parser.add_argument("--reference", type=Path, default=DEFAULT_ZVE10_QEMU_DIR)
    parser.add_argument("--language", choices=["english", "captured"], default="english")
    args = parser.parse_args()
    print(json.dumps(build_menu(work_dir=args.work_dir, reference=args.reference, language=args.language), indent=2))


if __name__ == "__main__":
    main()

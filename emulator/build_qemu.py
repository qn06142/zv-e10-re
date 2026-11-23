"""Reproducible MSYS2 UCRT64 build pipeline for QEMU 11.1.2 (-M zve10).

Stages upstream qemu-11.1.2.tar.xz from the read-only reference workspace (or
explicit --tarball), extracts safely on Windows via a two-pass tarfile
extractor (handling forward/dangling symlinks without WinError 1314), overlays
tracked emulator/qemu/ files, applies 0001-register-zve10.patch idempotently,
builds qemu-system-arm.exe via MSYS2 UCRT64, and stages the standalone binary +
transitive UCRT64 DLL closure into .local/emulator/bin/.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile

QEMU_TARBALL_SHA256 = "731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016"
DEFAULT_SOURCE_TARBALL = Path(r"D:\02_Development_And_Projects\zve10-qemu\work\qemu-11.1.2.tar.xz")
DEFAULT_MSYS2_ROOT = Path(r"C:\msys64")

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACKED_QEMU_DIR = REPO_ROOT / "emulator" / "qemu"
DEFAULT_WORK_DIR = REPO_ROOT / ".local" / "emulator"

_DLL_NAME_RE = re.compile(r"^\s*DLL Name:\s*(\S+)\s*$", re.MULTILINE)


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def stage_tarball(
    source_tarball: Path,
    dest_tarball: Path,
    expected_sha256: str = QEMU_TARBALL_SHA256,
) -> Path:
    dest_tarball.parent.mkdir(parents=True, exist_ok=True)
    if dest_tarball.is_file():
        actual = compute_sha256(dest_tarball)
        if actual == expected_sha256:
            return dest_tarball
        print(f"[build_qemu] Existing tarball SHA-256 mismatch ({actual}); re-copying...")

    if not source_tarball.is_file():
        raise FileNotFoundError(f"Source QEMU tarball not found: {source_tarball}")

    print(f"[build_qemu] Copying {source_tarball} -> {dest_tarball} (read-only source)...")
    shutil.copy2(source_tarball, dest_tarball)
    actual = compute_sha256(dest_tarball)
    if actual != expected_sha256:
        raise ValueError(
            f"Tarball SHA-256 mismatch for {dest_tarball}: expected {expected_sha256}, got {actual}"
        )
    return dest_tarball


def _safe_rel_member(name: str, strip_prefix: str = "qemu-11.1.2") -> Path | None:
    posix = PurePosixPath(name)
    parts = [p for p in posix.parts if p not in ("", ".")]
    if not parts:
        return None
    if parts[0] == strip_prefix:
        parts = parts[1:]
    if not parts:
        return None
    if posix.is_absolute() or ".." in parts:
        raise ValueError(f"Unsafe tar member path: {name}")
    return Path(*parts)


def extract_tarball_two_pass(
    tarball: Path,
    dest_dir: Path,
    msys2_root: Path = DEFAULT_MSYS2_ROOT,
    force: bool = False,
) -> Path:
    stamp = dest_dir / ".extracted_ok"
    if stamp.is_file() and not force:
        print(f"[build_qemu] Source tree already extracted at {dest_dir}")
        return dest_dir

    if dest_dir.exists() and force:
        print(f"[build_qemu] Removing existing source tree {dest_dir}...")
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_resolved = dest_dir.resolve()
    symlinks: list[tuple[Path, str]] = []
    hardlinks: list[tuple[Path, str]] = []
    file_count = 0

    xz_exe = msys2_root / "ucrt64" / "bin" / "xz.exe"
    xz_proc: subprocess.Popen[bytes] | None = None
    try:
        if xz_exe.is_file():
            print(f"[build_qemu] Extracting {tarball.name} (two-pass via xz -T0)...")
            xz_proc = subprocess.Popen(
                [str(xz_exe), "-dc", "-T0", str(tarball)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            tf = tarfile.open(fileobj=xz_proc.stdout, mode="r|*")
        else:
            print(f"[build_qemu] Extracting {tarball.name} (two-pass via python tarfile)...")
            tf = tarfile.open(tarball, mode="r:xz")

        with tf:
            for member in tf:
                rel = _safe_rel_member(member.name)
                if rel is None:
                    continue
                target_path = (dest_dir / rel).resolve()
                if not target_path.is_relative_to(dest_resolved):
                    raise ValueError(f"Tar member escapes destination: {member.name}")

                if member.isdir():
                    target_path.mkdir(parents=True, exist_ok=True)
                elif member.isreg():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    src_f = tf.extractfile(member)
                    if src_f is not None:
                        with src_f, target_path.open("wb") as out_f:
                            shutil.copyfileobj(src_f, out_f, length=65536)
                        file_count += 1
                elif member.issym():
                    symlinks.append((rel, member.linkname))
                elif member.islnk():
                    hardlinks.append((rel, member.linkname))

        if xz_proc is not None:
            rc = xz_proc.wait()
            stderr_out = xz_proc.stderr.read().decode("utf-8", errors="replace") if xz_proc.stderr else ""
            if rc != 0:
                raise RuntimeError(f"xz decompression failed (rc={rc}): {stderr_out}")
    finally:
        if xz_proc is not None and xz_proc.poll() is None:
            xz_proc.kill()
            xz_proc.wait()

    # Pass 2: resolve hardlinks and symlinks safely without requiring SeCreateSymbolicLinkPrivilege
    for rel, linkname in hardlinks:
        link_rel = _safe_rel_member(linkname)
        if link_rel is None:
            continue
        src = (dest_dir / link_rel).resolve()
        dst = (dest_dir / rel).resolve()
        if src.is_relative_to(dest_resolved) and src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)

    resolved_syms = 0
    skipped_syms = 0
    for rel, linkname in symlinks:
        dst = (dest_dir / rel).resolve()
        if linkname.startswith("/"):
            skipped_syms += 1
            continue
        candidate = (dst.parent / linkname).resolve()
        if not candidate.is_relative_to(dest_resolved) or not candidate.exists():
            skipped_syms += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() or dst.is_symlink():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        try:
            os.symlink(linkname, dst, target_is_directory=candidate.is_dir())
        except OSError:
            if candidate.is_dir():
                shutil.copytree(candidate, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(candidate, dst)
        resolved_syms += 1

    stamp.write_text(f"files={file_count} symlinks_resolved={resolved_syms} symlinks_skipped={skipped_syms}\n", encoding="utf-8")
    print(f"[build_qemu] Extracted {file_count} files, resolved {resolved_syms} symlinks (skipped {skipped_syms} dangling/external).")
    return dest_dir


def overlay_and_patch(
    qemu_src: Path,
    tracked_qemu_dir: Path = TRACKED_QEMU_DIR,
    msys2_root: Path = DEFAULT_MSYS2_ROOT,
) -> None:
    hw_src = tracked_qemu_dir / "hw"
    if not hw_src.is_dir():
        raise FileNotFoundError(f"Tracked QEMU hw directory missing: {hw_src}")

    copied = 0
    for src_file in sorted(hw_src.rglob("*")):
        if src_file.is_file():
            rel = src_file.relative_to(tracked_qemu_dir)
            dst_file = qemu_src / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1
    print(f"[build_qemu] Overlaid {copied} tracked source file(s) into {qemu_src}")

    patch_file = tracked_qemu_dir / "0001-register-zve10.patch"
    if not patch_file.is_file():
        raise FileNotFoundError(f"Registration patch missing: {patch_file}")

    patch_exe = msys2_root / "usr" / "bin" / "patch.exe"
    if not patch_exe.is_file():
        raise FileNotFoundError(f"MSYS2 patch.exe not found: {patch_exe}")

    patch_bytes = patch_file.read_bytes().replace(b"\r\n", b"\n")

    kconfig_text = (qemu_src / "hw" / "arm" / "Kconfig").read_text(encoding="utf-8")
    arm_meson_text = (qemu_src / "hw" / "arm" / "meson.build").read_text(encoding="utf-8")
    timer_meson_text = (qemu_src / "hw" / "timer" / "meson.build").read_text(encoding="utf-8")
    if (
        "config ZVE10" in kconfig_text
        and "CONFIG_ZVE10" in arm_meson_text
        and "CONFIG_ZVE10" in timer_meson_text
    ):
        print("[build_qemu] 0001-register-zve10.patch already applied.")
        return

    apply_res = subprocess.run(
        [str(patch_exe), "-p1", "--forward", "--batch", "--binary"],
        cwd=str(qemu_src),
        input=patch_bytes,
        capture_output=True,
    )
    if apply_res.returncode != 0:
        raise RuntimeError(
            "Failed to apply 0001-register-zve10.patch:\n"
            + apply_res.stdout.decode("utf-8", errors="replace")
            + apply_res.stderr.decode("utf-8", errors="replace")
        )
    print("[build_qemu] Applied 0001-register-zve10.patch cleanly.")


def _patch_win_symlink_install_tree(qemu_src: Path) -> None:
    """Handle WinError 1314 in upstream scripts/symlink-install-tree.py on Windows."""
    script = qemu_src / "scripts" / "symlink-install-tree.py"
    if not script.is_file():
        return
    text = script.read_text(encoding="utf-8")
    if "1314" in text:
        return
    old_block = (
        "    except BaseException as e:\n"
        "        if not isinstance(e, OSError) or e.errno != errno.EEXIST:\n"
        "            if os.name == 'nt':\n"
        "                print('Please enable Developer Mode to support soft link '\n"
        "                      'without Administrator permission')\n"
        "            print(f'error making symbolic link {dest}', file=sys.stderr)\n"
        "            raise e"
    )
    new_block = (
        "    except OSError as e:\n"
        "        if getattr(e, 'winerror', None) == 1314:\n"
        "            import shutil\n"
        "            if os.path.isdir(source):\n"
        "                shutil.copytree(source, bundle_dest, dirs_exist_ok=True)\n"
        "            elif os.path.isfile(source):\n"
        "                shutil.copy2(source, bundle_dest)\n"
        "        elif e.errno != errno.EEXIST:\n"
        "            print(f'error making symbolic link {dest}', file=sys.stderr)\n"
        "            raise e"
    )
    if old_block in text:
        script.write_text(text.replace(old_block, new_block, 1), encoding="utf-8")
        print("[build_qemu] Patched scripts/symlink-install-tree.py for WinError 1314 fallback.")


def to_msys_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1]
    return f"/{drive}{tail}"


def _run_msys2_ucrt64(command: str, msys2_root: Path = DEFAULT_MSYS2_ROOT) -> None:
    bash_exe = msys2_root / "usr" / "bin" / "bash.exe"
    if not bash_exe.is_file():
        raise FileNotFoundError(f"MSYS2 bash not found: {bash_exe}")

    env = os.environ.copy()
    env["MSYSTEM"] = "UCRT64"
    env["CHERE_INVOKING"] = "1"
    proc = subprocess.run([str(bash_exe), "-lc", command], env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"MSYS2 UCRT64 command failed (rc={proc.returncode}): {command}")


def configure_and_build(
    qemu_src: Path,
    build_dir: Path,
    msys2_root: Path = DEFAULT_MSYS2_ROOT,
    reconfigure: bool = False,
) -> Path:
    build_dir.mkdir(parents=True, exist_ok=True)
    build_posix = to_msys_path(build_dir)
    configure_posix = to_msys_path(qemu_src / "configure")

    if reconfigure or not (build_dir / "build.ninja").is_file():
        pyvenv_dir = build_dir / "pyvenv"
        if pyvenv_dir.exists():
            shutil.rmtree(pyvenv_dir)
        print("[build_qemu] Running QEMU configure (UCRT64, arm-softmmu)...")
        cmd = (
            f"cd {shlex.quote(build_posix)} && "
            f"{shlex.quote(configure_posix)} "
            "--target-list=arm-softmmu --disable-docs --disable-werror"
        )
        _run_msys2_ucrt64(cmd, msys2_root=msys2_root)
    else:
        print("[build_qemu] Reusing existing build.ninja (pass --reconfigure to re-run configure).")

    print("[build_qemu] Building qemu-system-arm.exe with ninja...")
    _run_msys2_ucrt64(f"ninja -C {shlex.quote(build_posix)} qemu-system-arm.exe", msys2_root=msys2_root)

    exe_path = build_dir / "qemu-system-arm.exe"
    if not exe_path.is_file():
        raise FileNotFoundError(f"Expected built binary missing: {exe_path}")
    return exe_path


def compute_ucrt64_dll_closure(
    exe_path: Path,
    ucrt64_bin: Path,
    objdump_exe: Path,
) -> list[Path]:
    if not objdump_exe.is_file():
        raise FileNotFoundError(f"objdump.exe not found: {objdump_exe}")

    available = {p.name.lower(): p for p in ucrt64_bin.glob("*.dll")}
    visited: set[str] = set()
    closure: dict[str, Path] = {}
    queue: deque[Path] = deque([exe_path])

    while queue:
        current = queue.popleft()
        res = subprocess.run(
            [str(objdump_exe), "-p", str(current)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        for dll_name in _DLL_NAME_RE.findall(res.stdout):
            key = dll_name.lower()
            if key in visited:
                continue
            visited.add(key)
            if key in available:
                dll_path = available[key]
                closure[key] = dll_path
                queue.append(dll_path)

    return sorted(closure.values(), key=lambda p: p.name.lower())


def stage_binary_and_dlls(
    exe_src: Path,
    qemu_src: Path,
    work_dir: Path,
    msys2_root: Path = DEFAULT_MSYS2_ROOT,
) -> Path:
    bin_dir = work_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe_dst = bin_dir / "qemu-system-arm.exe"
    shutil.copy2(exe_src, exe_dst)

    ucrt64_bin = msys2_root / "ucrt64" / "bin"
    objdump_exe = ucrt64_bin / "objdump.exe"
    dlls = compute_ucrt64_dll_closure(exe_src, ucrt64_bin, objdump_exe)
    total_bytes = exe_dst.stat().st_size
    for dll in dlls:
        dst = bin_dir / dll.name
        shutil.copy2(dll, dst)
        total_bytes += dst.stat().st_size

    keymaps_src = qemu_src / "pc-bios" / "keymaps"
    if keymaps_src.is_dir():
        keymaps_dst = work_dir / "share" / "qemu" / "keymaps"
        shutil.copytree(keymaps_src, keymaps_dst, dirs_exist_ok=True)

    print(
        f"[build_qemu] Staged {exe_dst} + {len(dlls)} UCRT64 DLLs "
        f"({total_bytes / (1024 * 1024):.2f} MiB total)."
    )
    return exe_dst


def verify_standalone(exe_path: Path) -> None:
    clean_env = {
        "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        "PATH": r"C:\Windows\System32;C:\Windows",
    }
    ver = subprocess.run(
        [str(exe_path), "--version"],
        env=clean_env,
        capture_output=True,
        text=True,
        check=True,
    )
    if "11.1.2" not in ver.stdout:
        raise RuntimeError(f"Unexpected QEMU --version output: {ver.stdout!r}")

    machines = subprocess.run(
        [str(exe_path), "-M", "help"],
        env=clean_env,
        capture_output=True,
        text=True,
        check=True,
    )
    if "zve10" not in machines.stdout:
        raise RuntimeError(f"'zve10' machine missing from -M help:\n{machines.stdout}")
    print(f"[build_qemu] Standalone verification passed (stripped PATH): {ver.stdout.splitlines()[0]}")


def build_qemu(
    *,
    source_tarball: Path = DEFAULT_SOURCE_TARBALL,
    work_dir: Path = DEFAULT_WORK_DIR,
    msys2_root: Path = DEFAULT_MSYS2_ROOT,
    reconfigure: bool = False,
    reextract: bool = False,
    verify: bool = True,
) -> Path:
    staged_tarball = stage_tarball(source_tarball, work_dir / "qemu-11.1.2.tar.xz")
    qemu_src = extract_tarball_two_pass(
        staged_tarball,
        work_dir / "qemu-src",
        msys2_root=msys2_root,
        force=reextract,
    )
    overlay_and_patch(qemu_src, TRACKED_QEMU_DIR, msys2_root=msys2_root)
    _patch_win_symlink_install_tree(qemu_src)
    exe_src = configure_and_build(
        qemu_src,
        work_dir / "build",
        msys2_root=msys2_root,
        reconfigure=reconfigure,
    )
    exe_dst = stage_binary_and_dlls(exe_src, qemu_src, work_dir, msys2_root=msys2_root)
    if verify:
        verify_standalone(exe_dst)
    return exe_dst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tarball", type=Path, default=DEFAULT_SOURCE_TARBALL)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--msys2-root", type=Path, default=DEFAULT_MSYS2_ROOT)
    parser.add_argument("--reconfigure", action="store_true")
    parser.add_argument("--reextract", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args(argv)

    build_qemu(
        source_tarball=args.tarball,
        work_dir=args.work_dir,
        msys2_root=args.msys2_root,
        reconfigure=args.reconfigure,
        reextract=args.reextract,
        verify=not args.skip_verify,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

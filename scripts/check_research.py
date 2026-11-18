"""Check evidence identities, experiment records and tracked generated artifacts.

Runs with the Python standard library and never connects to a camera.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def repository_file(root, name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Expected a repository-relative POSIX file path")
    parts = PurePosixPath(name)
    if parts.is_absolute() or PureWindowsPath(name).drive or ".." in parts.parts:
        raise ValueError(f"Path escapes repository: {name}")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing repository file: {name}")
    return path


def check_identity(root, row):
    path = repository_file(root, row["path"])
    expected = row["sha256"]
    if not isinstance(expected, str) or not re.fullmatch("[0-9a-f]{64}", expected):
        raise ValueError(f"Invalid SHA-256 for {row['path']}")
    content = path.read_bytes()
    if "bytes" in row and (type(row["bytes"]) is not int or len(content) != row["bytes"]):
        raise ValueError(f"Size mismatch: {row['path']}")
    mode = row.get("hash_mode", "exact")
    if mode not in {"exact", "lf-normalized"}:
        raise ValueError(f"Unknown hash mode for {row['path']}")
    if mode == "lf-normalized":
        content = content.replace(b"\r\n", b"\n")
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f"SHA-256 mismatch: {row['path']}")


def check_evidence(root):
    manifests = sorted((root / "research/firmware/evidence").glob("*/manifest.json"))
    if not manifests:
        raise ValueError("No evidence manifests found")
    count = 0
    for manifest in manifests:
        rows = json.loads(manifest.read_text(encoding="utf-8"))["files"]
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Empty or invalid evidence manifest: {manifest}")
        seen = set()
        for row in rows:
            if row["path"] in seen:
                raise ValueError(f"Duplicate evidence path: {row['path']}")
            seen.add(row["path"])
            check_identity(root, row)
            count += 1
    return count


def experiment_directories(root):
    firmware = root / "research/firmware"
    names = {"4k12bit_baseline_20261027", "raw_uvc_v01", "usb3_24fps_transport", "yc_observer"}
    paths = [p for p in firmware.iterdir()
             if p.is_dir() and (p.name.startswith("yuy2_transport_") or p.name in names)]
    bayer = firmware / "raw_frame_source/verified_bayer"
    paths += [p for p in (bayer / "live_bayer_tap_v01", bayer / "raw_receiver_v01")
              if p.is_dir()]
    return sorted(paths)


def check_experiments(root):
    count = 0
    for directory in experiment_directories(root):
        record = json.loads((directory / "EXPERIMENT.json").read_text(encoding="utf-8"))
        if record["id"] != directory.name:
            raise ValueError(f"Experiment ID mismatch: {directory}")
        if record["status"] not in {"historical", "offline-candidate", "hardware-observed", "failed"}:
            raise ValueError(f"Unknown experiment status: {directory}")
        for key in ("hardware_result", "rollback", "firmware_inputs"):
            if not isinstance(record[key], str) or not record[key].strip():
                raise ValueError(f"Missing {key}: {directory}")
        reproduction = record["reproduction"]
        if not reproduction.get("command") and not reproduction.get("unresolved"):
            raise ValueError(f"Missing reproduction command or unresolved reason: {directory}")
        if not isinstance(record["source_inputs"], list) or not record["source_inputs"]:
            raise ValueError(f"Missing source identities: {directory}")
        for row in record["source_inputs"]:
            check_identity(root, row)
        for identity in record["firmware_hashes"]:
            length = {"md5": 32, "sha256": 64}.get(identity["algorithm"])
            if not length or not re.fullmatch(f"[0-9a-f]{{{length}}}", identity["value"]):
                raise ValueError(f"Invalid firmware identity: {directory}")
        for reference in record["evidence"]:
            repository_file(root, reference)
        count += 1
    if not count:
        raise ValueError("No experiment records found")
    return count


def forbidden_artifact(name):
    path = PurePosixPath(name)
    return (
        name.startswith((".local/", "dumps/", "outputs/", "out/", "build_sysroot/",
                         "work/", "scratch/", "kmod/", "udtrbody_extract/"))
        or (name.startswith("research/captures/") and path.suffix not in {".json", ".md", ".tsv"})
        or (name.startswith(("scripts/staging/", "research/"))
            and path.suffix in {".exe", ".dll", ".elf", ".so", ".ko", ".bin", ".a"})
    )


def check_tracked_artifacts(root):
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True
    )
    names = result.stdout.decode("utf-8").split("\0")
    forbidden = [name for name in names if forbidden_artifact(name)]
    if forbidden:
        raise ValueError("Tracked generated artifacts: " + ", ".join(forbidden))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        evidence = check_evidence(root)
        experiments = check_experiments(root)
        check_tracked_artifacts(root)
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        print(f"FAILED: {error}")
        return 1
    print(f"Verified {evidence} evidence files and {experiments} experiment records.")
    print("Tracked artifact check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Configuration loading for retool.

All paths in reconf.toml are relative to the project root (the directory that
contains reconf.toml), so the whole tree is relocatable.  Environment overrides:
  RETOOL_CONFIG   - alternate config file
  RETOOL_RIZIN    - override rizin.exe path
"""
from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def project_root() -> Path:
    """Directory containing reconf.toml (walks up from cwd)."""
    env = os.environ.get("RETOOL_CONFIG")
    if env:
        return Path(env).resolve().parent
    here = Path.cwd().resolve()
    for cand in (here, *here.parents):
        if (cand / "reconf.toml").is_file():
            return cand
    return here


@dataclass
class Target:
    name: str
    path: Path
    arch: str = "arm"
    bits: int = 16
    cpu: str = "cortex"
    endian: str = "little"
    runtime_base: int = 0
    seeds: list[int] = field(default_factory=list)

    def va(self, file_off: int) -> int:
        return file_off + self.runtime_base

    def off(self, va: int) -> int:
        return va - self.runtime_base


@dataclass
class Config:
    root: Path
    rizin: Path
    rzbin: Path | None
    project_dir: Path
    export_dir: Path
    symdb_dir: Path
    targets: dict[str, Target]

    def target(self, name: str) -> Target:
        if name not in self.targets:
            known = ", ".join(sorted(self.targets)) or "<none>"
            raise SystemExit(f"unknown target {name!r}; known: {known}")
        return self.targets[name]


def _resolve(root: Path, p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else (root / p)


def _discover_rizin(root: Path) -> Path | None:
    """Probe scripts/tools/rizin/**/rizin.exe, scripts/tools/rizin/bin/rizin.exe, and PATH."""
    tools_dir = root / 'scripts/tools' / "rizin"
    if tools_dir.is_dir():
        cand = tools_dir / 'bin' / "rizin.exe"
        if cand.is_file():
            return cand
        for cand in tools_dir.rglob("rizin.exe"):
            if cand.is_file():
                return cand
    dot_tools_dir = root / ".tools" / "rizin"
    if dot_tools_dir.is_dir():
        for cand in dot_tools_dir.rglob("rizin.exe"):
            if cand.is_file():
                return cand
    which = shutil.which("rizin") or shutil.which("rizin.exe")
    return Path(which).resolve() if which else None


def _discover_rzbin(root: Path, rizin_path: Path | None = None) -> Path | None:
    """Probe sibling rz-bin.exe, scripts/tools/rizin/**/rz-bin.exe, and PATH."""
    if rizin_path and rizin_path.is_file():
        sib = rizin_path.parent / "rz-bin.exe"
        if sib.is_file():
            return sib
    tools_dir = root / 'scripts/tools' / "rizin"
    if tools_dir.is_dir():
        cand = tools_dir / 'bin' / "rz-bin.exe"
        if cand.is_file():
            return cand
        for cand in tools_dir.rglob("rz-bin.exe"):
            if cand.is_file():
                return cand
    dot_tools_dir = root / ".tools" / "rizin"
    if dot_tools_dir.is_dir():
        for cand in dot_tools_dir.rglob("rz-bin.exe"):
            if cand.is_file():
                return cand
    which = shutil.which("rz-bin") or shutil.which("rz-bin.exe")
    return Path(which).resolve() if which else None


def load(config_path: str | Path | None = None) -> Config:
    # Assign back to config_path, not a separate name: an earlier version bound
    # the default to `cfg_path` inside this branch and then unconditionally did
    # `cfg_path = Path(cfg_path)`, which raised UnboundLocalError for every
    # explicit path and (after a partial fix) reset the default back to None.
    if config_path is None:
        env = os.environ.get("RETOOL_CONFIG")
        config_path = Path(env) if env else (project_root() / "reconf.toml")
    cfg_path = Path(config_path).resolve()
    if not cfg_path.is_file():
        raise SystemExit(f"config not found: {cfg_path}")
    root = cfg_path.parent
    data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))

    eng = data.get("engine", {})
    paths = data.get("paths", {})

    rizin_raw = os.environ.get("RETOOL_RIZIN") or eng.get("rizin", "")
    rizin = _resolve(root, rizin_raw) if rizin_raw else Path("")
    if not rizin.is_file():
        discovered_rz = _discover_rizin(root)
        if discovered_rz:
            rizin = discovered_rz

    rzbin_raw = os.environ.get("RETOOL_RZBIN") or eng.get("rzbin", "")
    rzbin = _resolve(root, rzbin_raw) if rzbin_raw else None
    if not rzbin or not rzbin.is_file():
        discovered_rzbin = _discover_rzbin(root, rizin)
        if discovered_rzbin:
            rzbin = discovered_rzbin

    targets: dict[str, Target] = {}
    for name, t in (data.get("target", {}) or {}).items():
        targets[name] = Target(
            name=name,
            path=_resolve(root, t["path"]),
            arch=t.get("arch", "arm"),
            bits=int(t.get("bits", 16)),
            cpu=t.get("cpu", "cortex"),
            endian=t.get("endian", "little"),
            runtime_base=int(t.get("runtime_base", 0)),
            seeds=[int(s) for s in t.get("seeds", [])],
        )

    return Config(
        root=root,
        rizin=rizin,
        rzbin=rzbin,
        project_dir=_resolve(root, paths.get("project_dir", ".local/re_out/projects")),
        export_dir=_resolve(root, paths.get("export_dir", ".local/re_out/exports")),
        symdb_dir=_resolve(root, paths.get("symdb_dir", "research/symbols")),
        targets=targets,
    )


def find_rizin(cfg: Config) -> str | None:
    """Return a usable rizin executable path, or None."""
    if cfg.rizin.is_file():
        return str(cfg.rizin)
    disc = _discover_rizin(cfg.root)
    if disc:
        return str(disc)
    return shutil.which("rizin") or shutil.which("rizin.exe")

"""rizin driver for retool.

Analysis of a 17 MB raw ARM/Thumb image is expensive (~4 min for 66k funcs), so
results are cached in a rizin project (.rzdb).  Every command runs headless,
non-interactively (-N to ignore user rizinrc, -q to quit) so output is
reproducible and never depends on the invoking shell's environment.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import Config, Target


class EngineError(RuntimeError):
    pass


class Rizin:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.bin = str(cfg.rizin)
        if not Path(self.bin).is_file():
            raise EngineError(f"rizin not found at {self.bin} (set RETOOL_RIZIN or fix reconf.toml)")

    # ---- low level ----
    def _base_flags(self, t: Target) -> list[str]:
        return [
            self.bin,
            "-N",              # ignore user rizinrc -> reproducible
            "-n",              # raw file, no bin plugin
            "-q",
            "-a", t.arch,
            "-b", str(t.bits),
            "-e", f"asm.cpu={t.cpu}",
        ]

    def run(self, t: Target, cmds: str, timeout: int = 3600) -> str:
        """Run a ';'-separated command string against the target file."""
        argv = self._base_flags(t) + ["-c", cmds, str(t.path)]
        try:
            p = subprocess.run(
                argv, capture_output=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired as e:
            raise EngineError(f"rizin timed out after {timeout}s: {e}") from e
        if p.returncode != 0:
            raise EngineError(f"rizin exit {p.returncode}\n{p.stderr[-2000:]}")
        return p.stdout

    def run_project(self, t: Target, project: Path, cmds: str, timeout: int = 3600) -> str:
        """Run commands against a cached .rzdb project (must already exist)."""
        argv = self._base_flags(t) + ["-p", str(project), "-c", cmds]
        try:
            p = subprocess.run(
                argv, capture_output=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired as e:
            raise EngineError(f"rizin timed out after {timeout}s: {e}") from e
        if p.returncode != 0:
            raise EngineError(f"rizin exit {p.returncode}\n{p.stderr[-2000:]}")
        return p.stdout

    def run_json(self, t: Target, cmds: str, timeout: int = 3600):
        """Run commands and parse the first JSON value printed (e.g. 'aflj')."""
        out = self.run(t, cmds, timeout=timeout)
        return _extract_json(out)

    def run_project_json(self, t: Target, project: Path, cmds: str, timeout: int = 3600):
        out = self.run_project(t, project, cmds, timeout=timeout)
        return _extract_json(out)

    # ---- project cache ----
    def project_path(self, t: Target) -> Path:
        return self.cfg.project_dir / f"{t.name}.rzdb"

    def has_project(self, t: Target) -> bool:
        return self.project_path(t).is_file()

    def analyze_to_project(self, t: Target, progress=None) -> Path:
        """Seeded recursive-descent analysis; save to .rzdb and return its path.

        Seeds are declared as functions first, then 'aar' (references) + 'aac'
        (call graph) expands the set.  This is the verified recipe (66k funcs).
        """
        proj = self.project_path(t)
        proj.parent.mkdir(parents=True, exist_ok=True)
        if proj.is_file():
            proj.unlink()

        seed_cmds = "; ".join(f"af @ {s:#x}" for s in t.seeds)
        script = f"{seed_cmds}; aar; aac; aflc; Ps {proj}"
        if progress:
            progress(f"analyzing {t.name} ({t.path.name}) with {len(t.seeds)} seeds ...")
        self.run(t, script, timeout=7200)
        if not proj.is_file():
            raise EngineError(f"rizin did not produce project at {proj}")
        if progress:
            progress(f"saved project {proj}")
        return proj

    def open_and_save(self, t: Target, cmds: str, project: Path) -> None:
        """Open the cached project, run `cmds`, then save back.

        The save MUST be part of the same single `-c` string.  Passing a second
        `-c` flag is silently dropped by rizin, which loses every rename
        without any error -- verified against rizin 0.9.1.
        """
        if not project.is_file():
            raise EngineError(f"no cached project at {project}; run analyze first")
        script = f"{cmds}; Ps {project}"
        argv = self._base_flags(t) + ["-p", str(project), "-c", script]
        p = subprocess.run(argv, capture_output=True, timeout=7200,
                           encoding="utf-8", errors="replace")
        if p.returncode != 0:
            raise EngineError(f"rizin exit {p.returncode}\n{p.stderr[-2000:]}")


def _extract_json(out: str):
    """Pull the first top-level JSON value out of rizin stdout."""
    out = out.strip()
    if not out:
        return None
    # rizin may emit progress/terminal escapes; find first '[' or '{'
    starts = [i for i, c in enumerate(out) if c in "[{"]
    if not starts:
        return None
    start = starts[0]
    opener = out[start]
    closer = "]" if opener == "[" else "}"
    # naive brace matching that respects strings
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(out)):
        c = out[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(out[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None

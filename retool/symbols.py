"""Machine-readable symbol database.

This is the durable replacement for the Ghidra project that used to hold the
~120 renamed functions.  Those names existed only inside a Ghidra project that
was lost with the original machine; they survived as prose in
avcam_re/RE_STATE.md and avcam_re/pipeline.md.  This module stores them as
versioned JSON keyed by FILE OFFSET, and applies them to a rizin project.

Schema (per symbol):
    off      int    file offset (canonical key)
    name     str    identifier
    kind     str    "func" | "data" | "auto"  (auto = let retool decide)
    comment  str    optional prose/notes
    source   str    provenance, e.g. "RE_STATE.md:32"
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

SCHEMA = 1
VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _as_int(v) -> int:
    """Accept 42, "42", "0x2a" (the DB stores runtime_base as a hex string)."""
    if isinstance(v, int):
        return v
    s = str(v).strip()
    return int(s, 16) if s.lower().startswith("0x") else int(s)


@dataclass
class Symbol:
    off: int
    name: str
    kind: str = "auto"
    comment: str = ""
    source: str = ""

    def to_json(self) -> dict:
        d = asdict(self)
        d["va"] = hex(self.off)  # placeholder; caller adds runtime base
        return d


@dataclass
class SymDB:
    target: str
    symbols: list[Symbol] = field(default_factory=list)
    runtime_base: int = 0
    schema: int = SCHEMA
    path: Path | None = None

    # ---- io ----
    @classmethod
    def load(cls, path: str | Path) -> "SymDB":
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        syms = [
            Symbol(
                off=int(s["off"]),
                name=s["name"],
                kind=s.get("kind", "auto"),
                comment=s.get("comment", ""),
                source=s.get("source", ""),
            )
            for s in data.get("symbols", [])
        ]
        return cls(
            target=data.get("target", ""),
            symbols=syms,
            runtime_base=_as_int(data.get("runtime_base", 0)),
            schema=int(data.get("schema", SCHEMA)),
            path=p,
        )

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path or self.path or "")
        if not str(p):
            raise ValueError("no path to save symbol db")
        p.parent.mkdir(parents=True, exist_ok=True)
        self.symbols.sort(key=lambda s: s.off)
        doc = {
            "schema": self.schema,
            "target": self.target,
            "runtime_base": hex(self.runtime_base),
            "note": "Addresses are FILE OFFSETS (base 0x0). Runtime VA = off + runtime_base.",
            "symbols": [
                {
                    "off": s.off,
                    "va": hex(s.off + self.runtime_base),
                    "name": s.name,
                    "kind": s.kind,
                    "comment": s.comment,
                    "source": s.source,
                }
                for s in self.symbols
            ],
        }
        p.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        self.path = p
        return p

    # ---- helpers ----
    def add(self, off: int, name: str, kind: str = "auto", comment: str = "", source: str = "") -> bool:
        """Add a symbol. Returns False if it collides with an existing one."""
        if any(s.off == off or s.name == name for s in self.symbols):
            return False
        self.symbols.append(Symbol(off=off, name=name, kind=kind, comment=comment, source=source))
        return True

    def by_off(self) -> dict[int, Symbol]:
        return {s.off: s for s in self.symbols}

    def by_name(self) -> dict[str, Symbol]:
        return {s.name: s for s in self.symbols}

    def validate(self, file_size: int | None = None) -> list[str]:
        problems: list[str] = []
        seen_off: dict[int, Symbol] = {}
        seen_name: dict[str, Symbol] = {}
        for s in self.symbols:
            if not VALID_NAME.match(s.name):
                problems.append(f"{s.name!r} is not a valid identifier")
            if s.off in seen_off:
                problems.append(f"duplicate offset {s.off:#x}: {seen_off[s.off].name} / {s.name}")
            seen_off[s.off] = s
            if s.name in seen_name:
                problems.append(f"duplicate name {s.name!r} at {seen_name[s.name].off:#x} / {s.off:#x}")
            seen_name[s.name] = s
            if file_size is not None and not (0 <= s.off < file_size):
                problems.append(f"{s.name} off {s.off:#x} outside file (size {file_size:#x})")
            if s.kind not in ("func", "data", "auto"):
                problems.append(f"{s.name} has unknown kind {s.kind!r}")
        return problems

"""Artifact export: rizin analysis -> CSV/JSON files for downstream tooling.

Emits the same shapes the old disasm*.py produced, but from rizin's real
function/xref graph and with BOTH address forms (file offset + runtime VA)
present, plus symbol names where the symbol DB supplies them.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import Target
from .engine import Rizin
from .symbols import SymDB


def _write_csv(path: Path, header: list[str], rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def export_all(
    rz: Rizin,
    t: Target,
    project: Path,
    symdb: SymDB | None = None,
    progress=None,
) -> dict[str, Path]:
    """Export functions, calls, xrefs, strings, and pointer tables.

    Each artifact is independent: a rizin command that this build does not
    support degrades that one file instead of failing the whole export.
    """
    out = rz.cfg.export_dir / t.name
    out.mkdir(parents=True, exist_ok=True)
    names = symdb.by_off() if symdb else {}
    written: dict[str, Path] = {}

    def _try(label, fn):
        if progress:
            progress(f"export: {label}")
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - one bad command must not kill export
            _warn(f"{label}: {type(e).__name__}: {e}")

    def _warn(msg):
        print(f"  [warn] {msg}", flush=True)

    # ---- functions (also the source of data xrefs) ----
    funcs: list = []

    def _funcs():
        nonlocal funcs
        funcs = rz.run_project_json(t, project, "aflj") or []
        rows = []
        for f in funcs:
            off = int(f["offset"])
            s = names.get(off)
            rows.append([
                f"{off:08x}", hex(off + t.runtime_base),
                s.name if s else "", f.get("name", ""),
                f.get("size", 0), f.get("nbbs", 0), f.get("cc", 0),
                s.comment if s else "",
            ])
        _write_csv(out / "functions.csv",
                   ["off_hex", "va_hex", "sym_name", "rz_name", "size", "nbbs", "cc", "comment"],
                   rows)
        written["functions"] = out / "functions.csv"

    _try("functions", _funcs)

    # ---- call graph edges ----
    # Derived from the aflj records (codexrefs with type CALL) rather than a
    # separate call-graph command: 'agCj' is not supported in every rizin build
    # and silently yields an empty file, which is worse than not having one.
    def _calls():
        rows = []
        for f in funcs:
            src = int(f["offset"])
            for cx in f.get("codexrefs") or []:
                if cx.get("type") != "CALL":
                    continue
                dst = int(cx["to"])
                rows.append([f"{src:08x}", f"{cx['from']:08x}", f"{dst:08x}",
                             hex(dst + t.runtime_base)])
        _write_csv(out / "calls.csv", ["src_fn", "from", "dst", "dst_va"], rows)
        written["calls"] = out / "calls.csv"

    _try("calls", _calls)

    # ---- data xrefs (embedded in the function records) ----
    def _dxrefs():
        rows = []
        for f in funcs:
            for dx in f.get("dataxrefs") or []:
                rows.append([
                    f"{int(f['offset']):08x}", f"{int(dx['from']):08x}",
                    f"{int(dx['to']):08x}", hex(int(dx["to"]) + t.runtime_base),
                    dx.get("type", ""),
                ])
        _write_csv(out / "data_xrefs.csv", ["from_fn", "from", "to", "to_va", "type"], rows)
        written["data_xrefs"] = out / "data_xrefs.csv"

    _try("data xrefs", _dxrefs)

    # ---- strings ----
    def _strings():
        ss = rz.run_project_json(t, project, "izj") or []
        rows = []
        for s in ss:
            off = int(s.get("vaddr", 0))
            txt = s.get("string", "")
            if isinstance(txt, bytes):
                txt = txt.decode("utf-8", "replace")
            rows.append([f"{off:08x}", hex(off + t.runtime_base), len(txt),
                         txt.replace("\n", "\\n")[:200]])
        _write_csv(out / "strings.csv", ["off_hex", "va_hex", "len", "string"], rows)
        written["strings"] = out / "strings.csv"

    _try("strings", _strings)

    # ---- pointer tables: runs of aligned in-range pointers (dispatch tables) ----
    def _ptrs():
        written["ptr_tables"] = _export_ptr_tables(t, out)

    _try("pointer tables", _ptrs)

    return written


def _export_ptr_tables(t: Target, out: Path) -> Path:
    """Find runs of >=4 consecutive 32-bit words that point into the image.

    A pointer table is a dispatch/vtable structure — exactly the thing that
    defeated static xref resolution in the old notes.  Flag them explicitly.
    This is a pure-Python scan of the file (no engine round-trip), so it is fast
    and always available.
    """
    import struct

    size = t.path.stat().st_size
    data = t.path.read_bytes()
    lo, hi = t.runtime_base, t.runtime_base + size
    rows = []
    run_start = None
    run_len = 0
    for off in range(0, size - 3, 4):
        (v,) = struct.unpack_from("<I", data, off)
        if lo <= v < hi:
            if run_start is None:
                run_start, run_len = off, 0
            run_len += 1
        else:
            if run_start is not None and run_len >= 4:
                rows.append([f"{run_start:08x}", hex(run_start + t.runtime_base), run_len])
            run_start, run_len = None, 0
    if run_start is not None and run_len >= 4:
        rows.append([f"{run_start:08x}", hex(run_start + t.runtime_base), run_len])
    rows.sort(key=lambda r: -int(r[2]))
    p = out / "ptr_tables.csv"
    _write_csv(p, ["off_hex", "va_hex", "count"], rows)
    return p

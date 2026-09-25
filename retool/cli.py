"""retool CLI — one entry point for the whole binary pipeline.

    python -m retool doctor                  # verify engine + targets
    python -m retool analyze   avcam         # build/refresh cached rizin project
    python -m retool export    avcam         # dump CSV/JSON artifacts
    python -m retool symbols   list          # show the symbol database
    python -m retool symbols   apply avcam   # push names+comments into the project
    python -m retool migrate   avcam         # scrape markdown -> symbol DB
    python -m retool funcs     avcam [filt]  # search functions
    python -m retool xrefs     avcam <addr>  # xrefs to an address
    python -m retool strings   avcam [filt]  # search strings
    python -m retool all       avcam         # migrate+analyze+symbols+export
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import __version__, config, engine, export, migrate, consts
from .symbols import SymDB


def _p(msg: str) -> None:
    print(msg, flush=True)


def _load_symdb(cfg: config.Config, target_name: str) -> SymDB | None:
    p = cfg.symdb_dir / f"{target_name}.json"
    if not p.is_file():
        return None
    db = SymDB.load(p)
    db.runtime_base = cfg.target(target_name).runtime_base
    return db


# ---------------------------------------------------------------- commands
def cmd_doctor(cfg):
    ok = True
    rz = config.find_rizin(cfg)
    _p(f"retool {__version__}")
    _p(f"root        : {cfg.root}")
    if rz:
        _p(f"rizin       : OK  {rz}")
    else:
        _p("rizin       : MISSING  (set RETOOL_RIZIN or fix reconf.toml)")
        ok = False
    if cfg.rzbin and cfg.rzbin.is_file():
        _p(f"rz-bin      : OK  {cfg.rzbin}")
    else:
        _p("rz-bin      : (optional, not configured)")
    _p(f"projects    : {cfg.project_dir}")
    _p(f"exports     : {cfg.export_dir}")
    _p(f"symdb       : {cfg.symdb_dir}")
    _p("targets:")
    for name, t in sorted(cfg.targets.items()):
        exists = t.path.is_file()
        size = t.path.stat().st_size if exists else 0
        _p(f"  - {name}: {'OK' if exists else 'MISSING'} {t.path} ({size} bytes, "
           f"runtime_base={hex(t.runtime_base)}, {len(t.seeds)} seeds)")
        if not exists:
            ok = False
    sys.exit(0 if ok else 1)


def cmd_analyze(cfg, name, force=False):
    t = cfg.target(name)
    rz = engine.Rizin(cfg)
    proj = rz.project_path(t)
    if rz.has_project(t) and not force:
        _p(f"project exists: {proj}  (use --force to re-analyze)")
        return
    rz.analyze_to_project(t, progress=_p)
    _p(f"done -> {proj}")


def cmd_export(cfg, name):
    t = cfg.target(name)
    rz = engine.Rizin(cfg)
    if not rz.has_project(t):
        _p(f"no cached project; run: python -m retool analyze {name}")
        sys.exit(1)
    db = _load_symdb(cfg, name)
    written = export.export_all(rz, t, rz.project_path(t), symdb=db, progress=_p)
    for k, v in written.items():
        _p(f"  {k:<12} {v}")


def cmd_migrate(cfg, name, out_path=None):
    t = cfg.target(name)
    sources = [t.path.parent.parent / "avcam_re" / "RE_STATE.md",
               t.path.parent.parent / "avcam_re" / "pipeline.md",
               t.path.parent.parent / "avcam_re" / "OPENGATE_3_2_ANALYSIS.md"]
    sources = [s for s in sources if s.is_file()]
    if not sources:
        _p("no source markdown found")
        sys.exit(1)
    _p(f"scraping {len(sources)} markdown source(s) for {name} ...")
    db, unparsed = migrate.migrate(name, sources, t.runtime_base)
    size = t.path.stat().st_size
    problems = db.validate(size)
    _p(f"collected {len(db.symbols)} symbols; {len(problems)} validation problem(s)")
    for pr in problems[:20]:
        _p(f"  ! {pr}")
    if unparsed:
        _p(f"{len(unparsed)} line(s) looked like symbols but were not parsed:")
        for u in unparsed[:15]:
            _p(f"  ? {u}")
    dest = Path(out_path) if out_path else (cfg.symdb_dir / f"{name}.json")
    db.save(dest)
    _p(f"wrote {dest}")
    return unparsed


def cmd_symbols(cfg, action, name=None):
    if action == "list":
        if not name:
            name = sorted(cfg.targets)[0]
        db = _load_symdb(cfg, name)
        if not db:
            _p(f"no symbol db for {name}; run: python -m retool migrate {name}")
            sys.exit(1)
        t = cfg.target(name)
        _p(f"{len(db.symbols)} symbols in {cfg.symdb_dir / (name + '.json')} (base {hex(t.runtime_base)})")
        for s in sorted(db.symbols, key=lambda s: s.off)[:500]:
            _p(f"  {s.off:08x}  {hex(s.off + t.runtime_base):>10}  {s.name:<44} {s.comment[:60]}")
        return
    if action == "apply":
        t = cfg.target(name)
        rz = engine.Rizin(cfg)
        if not rz.has_project(t):
            _p(f"no cached project; run: python -m retool analyze {name}")
            sys.exit(1)
        db = _load_symdb(cfg, name)
        if not db:
            _p(f"no symbol db for {name}; run: python -m retool migrate {name}")
            sys.exit(1)
        # Push names + comments into the cached project.
        #
        # rizin's command parser treats '@' as a seek modifier anywhere on the
        # line, so a comment containing '@' aborts the ENTIRE -c string --
        # including the trailing 'Ps' save, which loses every rename silently.
        # Measured against rizin 0.9.1: '@', '`', '"', "'", '(' and ')' break
        # parsing; ';' silently truncates the comment (and would split the
        # ';'-joined command list).  Rewrite those; the untouched original text
        # remains authoritative in re_symbols/<target>.json.
        def _sanitize(text: str) -> str:
            t = text
            for ch in ("@", "`", '"', "'", ";"):
                t = t.replace(ch, " ")
            t = t.replace("(", "[").replace(")", "]")
            t = re.sub(r"\s+", " ", t).strip()
            return t

        cmds = []
        renamed = flagged = 0
        # Only afn works where rizin actually has a function; elsewhere the name
        # would be dropped without a word.  Ask the project where its functions
        # are and flag everything else, so all 105 symbols end up greppable.
        known = {int(f["offset"]) for f in (rz.run_project_json(t, rz.project_path(t), "aflj") or [])}
        for s in db.symbols:
            if s.kind == "data" or s.off not in known:
                cmds.append(f"f {s.name} @ {s.off:#x}")
                flagged += 1
            else:
                cmds.append(f"afn {s.name} @ {s.off:#x}")
                renamed += 1
            if s.comment:
                safe = _sanitize(s.comment)
                if safe:
                    cmds.append(f"CCu {safe} @ {s.off:#x}")
        script = "; ".join(cmds)
        _p(f"applying {len(db.symbols)} symbols to project "
           f"({renamed} function renames, {flagged} flags) ...")
        rz.open_and_save(t, script, rz.project_path(t))
        _p("applied + saved")


def cmd_funcs(cfg, name, filt=None):
    t = cfg.target(name)
    rz = engine.Rizin(cfg)
    funcs = rz.run_project_json(t, rz.project_path(t), "aflj") or []
    db = _load_symdb(cfg, name)
    names = db.by_off() if db else {}
    for f in funcs:
        off = int(f["offset"])
        rn = f.get("name", "")
        sn = names[off].name if off in names else ""
        line = f"{off:08x} {hex(off + t.runtime_base):>10} {f.get('size',0):>7}  {rn}"
        if sn:
            line += f"   <{sn}>"
        if not filt or filt.lower() in line.lower():
            _p(line)
    _p(f"-- {len(funcs)} functions")


def cmd_xrefs(cfg, name, addr):
    t = cfg.target(name)
    rz = engine.Rizin(cfg)
    a = int(addr, 0)
    res = rz.run_project_json(t, rz.project_path(t), f"axtj @ {a:#x}") or []
    for r in res:
        frm = int(r.get("from", 0))
        _p(f"  from {frm:08x} (va {hex(frm + t.runtime_base)})  type={r.get('type')}  fn={r.get('fcn_name','')}")
    _p(f"-- {len(res)} xref(s) to {hex(a)}")


def cmd_strings(cfg, name, filt=None):
    t = cfg.target(name)
    rz = engine.Rizin(cfg)
    ss = rz.run_project_json(t, rz.project_path(t), "izj") or []
    for s in ss:
        off = int(s.get("vaddr", 0))
        txt = s.get("string", "")
        if isinstance(txt, bytes):
            txt = txt.decode("utf-8", "replace")
        if not filt or filt.lower() in txt.lower():
            _p(f"  {off:08x} {hex(off + t.runtime_base):>10}  {txt[:120]}")
    _p(f"-- {len(ss)} strings")


def cmd_consts(cfg, name, addr, values, whole=False):
    """Locate immediate constants -- used to verify firmware patch points."""
    t = cfg.target(name)
    rz = engine.Rizin(cfg)
    if whole:
        start, size = 0, t.path.stat().st_size
        label = "whole image"
    else:
        a = int(addr, 0)
        fns = rz.run_project_json(t, rz.project_path(t), f"afij @ {a:#x}") or []
        if fns:
            f = fns[0]
            start = int(f["offset"])
            size = int(f["size"])
            label = f"{f['name']} @ {start:#x} (size {size})"
        else:
            start, size = a, 0x200
            label = f"raw @ {a:#x} (no function; scanning 0x200)"
    targets = [int(v, 0) for v in values]
    hits = consts.scan(t.path.read_bytes(), t.runtime_base, start, size, targets)
    _p(f"scanning {label} for {[hex(v) for v in targets]}")
    if not hits:
        _p("  no encoding of those values found in range")
        return
    for h in sorted(hits, key=lambda h: (h["value"], h["off"])):
        _p(f"  {h['off']:08x}  va {h['va']:>10}  {h['value']:>8} "
           f"({hex(h['value'])})  {h['kind']:<12} bytes={h['bytes']}")


def cmd_disasm(cfg, name, addr, count=40):
    """Disassemble N instructions at a file offset (the workhorse for reading code)."""
    t = cfg.target(name)
    rz = engine.Rizin(cfg)
    out = rz.run(t, f"pd {int(count)} @ {int(addr, 0):#x}", timeout=300)
    # strip ANSI colour so it is readable in a terminal or pipe
    out = re.sub(r"\x1b\[[0-9;]*m", "", out)
    _p(out.rstrip())


def cmd_all(cfg, name):
    cmd_migrate(cfg, name)
    cmd_analyze(cfg, name, force=True)
    cmd_symbols(cfg, "apply", name)
    cmd_export(cfg, name)
    _p("all done")


# ---------------------------------------------------------------- main
def build_parser():
    ap = argparse.ArgumentParser(prog="retool", description="pmca-re binary pipeline")
    ap.add_argument("--config", help="path to reconf.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor")

    p = sub.add_parser("analyze"); p.add_argument("target")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("export"); p.add_argument("target")

    p = sub.add_parser("migrate"); p.add_argument("target")
    p.add_argument("--out")

    p = sub.add_parser("symbols")
    p.add_argument("action", choices=["list", "apply"])
    p.add_argument("target", nargs="?")

    p = sub.add_parser("funcs"); p.add_argument("target")
    p.add_argument("filter", nargs="?")

    p = sub.add_parser("xrefs"); p.add_argument("target"); p.add_argument("addr")

    p = sub.add_parser("strings"); p.add_argument("target")
    p.add_argument("filter", nargs="?")

    p = sub.add_parser("disasm"); p.add_argument("target"); p.add_argument("addr")
    p.add_argument("-n", type=int, default=40, help="instruction count")

    p = sub.add_parser("consts"); p.add_argument("target"); p.add_argument("addr")
    p.add_argument("values", nargs="+", help="integers, e.g. 3376 0x870")
    p.add_argument("--whole", action="store_true", help="scan the entire image")

    p = sub.add_parser("all"); p.add_argument("target")
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    cfg = config.load(a.config)

    try:
        if a.cmd == "doctor":
            cmd_doctor(cfg)
        elif a.cmd == "analyze":
            cmd_analyze(cfg, a.target, a.force)
        elif a.cmd == "export":
            cmd_export(cfg, a.target)
        elif a.cmd == "migrate":
            cmd_migrate(cfg, a.target, a.out)
        elif a.cmd == "symbols":
            name = a.target or sorted(cfg.targets)[0]
            cmd_symbols(cfg, a.action, name)
        elif a.cmd == "funcs":
            cmd_funcs(cfg, a.target, a.filter)
        elif a.cmd == "xrefs":
            cmd_xrefs(cfg, a.target, a.addr)
        elif a.cmd == "strings":
            cmd_strings(cfg, a.target, a.filter)
        elif a.cmd == "disasm":
            cmd_disasm(cfg, a.target, a.addr, a.n)
        elif a.cmd == "consts":
            cmd_consts(cfg, a.target, a.addr, a.values, a.whole)
        elif a.cmd == "all":
            cmd_all(cfg, a.target)
    except engine.EngineError as e:
        _p(f"engine error: {e}")
        sys.exit(2)
    except KeyboardInterrupt:
        _p("interrupted")
        sys.exit(130)


if __name__ == "__main__":
    main()

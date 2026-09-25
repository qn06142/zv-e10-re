"""Scrape renamed symbols out of the RE markdown into a machine-readable SymDB.

The Ghidra project that held these names is gone.  The names survive only as
prose in avcam_re/RE_STATE.md and avcam_re/pipeline.md.  This recovers them so
the knowledge is versioned, diffable, and greppable instead of trapped in a
binary database.  Re-runnable: it regenerates the DB from the markdown, so
editing the notes and re-running `retool migrate` is the intended workflow.

Recognised shapes (all addresses are file offsets):
  A  0x007e8e88 -> ISP_WriteRegister (comment)
  B  FUN_007e8e88 -> ISP_WriteRegister (comment)
  C  ISP_WriteRegister (FUN_006be8a0) -- comment
  D  DFE_ISP_apply (0x42bff4), DFE_core (0x42de50)
  E  **FUN_004402f0** = DFE_get_block_id
  F  SET_PROISP_MODE: 0x933927, 0x933950 -> FUN_00035cec   (string anchor ->
     handler; this is the table-driven dispatch that static xref could not
     resolve, and which the old notes listed as "deferred")
  G  DFE_SET_RAWB: 0x9b4a54 (no xref; indirect)             (anchor, no handler)
  H  FUN_000ad5d8 <- chromaFormat string @0x95ace1           (handler + anchor)

Anything that looks like a symbol but matches nothing is reported as
`unparsed` so nothing is silently lost.
"""
from __future__ import annotations

import re
from pathlib import Path

from .symbols import SymDB, VALID_NAME

# "0x007e8e88 -> Name"  /  "FUN_007e8e88 -> Name"
# NB: the FUN_ form has no \b before the hex (underscore is a word char), so
# the prefix must be matched explicitly rather than via a word boundary.
RE_ARROW = re.compile(
    r"(?:0x([0-9a-fA-F]{6,8})|FUN_([0-9a-fA-F]{6,8}))\s*(?:→|->)\s*([A-Za-z_][A-Za-z0-9_]*)"
)
# "Name (0x000b31b4)"  /  "Name (FUN_006be8a0)"  /  "Name (0x423bac -- prose)"
# The lookbehind stops filename extensions matching: in
# "/lens/fixed_lensfile.bin (0x8c2160+)" the candidate name is "bin".
RE_NAME_ADDR = re.compile(
    r"(?<![.\w])([A-Za-z_][A-Za-z0-9_]*)\s*"
    r"\(\s*(?:0x([0-9a-fA-F]{6,8})|FUN_([0-9a-fA-F]{6,8}))\b"
)


def _bad_name_boundary(text: str, end: int) -> bool:
    """Reject a captured name that is really the head of a hyphenated word or
    the tail of a range, e.g. 'Sub-processor' or '0x10..0x2C -> X'."""
    tail = text[end:end + 2]
    return tail.startswith("..") or tail[:1] in ("-", ".")


# "**FUN_007e8e88** = ISP_WriteRegister"  (pipeline.md prose form)
RE_BOLD_FUN = re.compile(
    r"\*\*FUN_([0-9a-fA-F]{6,8})\*\*\s*=\s*([A-Za-z_][A-Za-z0-9_]*)"
)

# A label: one or more identifier-ish words, an optional parenthetical gloss,
# then a colon.  It must start at the bullet marker so prose like
# "3 directly pointer-referenced: 0x1055d8c" is not mistaken for a label.
_LABEL = r"((?:[A-Za-z_][A-Za-z0-9_]*\s+)*[A-Za-z_][A-Za-z0-9_]*)(?:\s*\([^)]*\))?\s*:\s*"

# "SET_PROISP_MODE: 0x933927, 0x933950 -> FUN_00035cec (handler)"
# These string->handler anchor tables are exactly the table-driven dispatch that
# static xref could not resolve; capturing them turns "deferred" into data.
RE_ANCHOR = re.compile(
    r"^[-*]\s*" + _LABEL
    + r"((?:0x[0-9a-fA-F]+)(?:\s*,\s*0x[0-9a-fA-F]+)*)"
    + r"\s*(?:→|->)\s*(?:FUN_|@)([0-9a-fA-F]+)"
)

# "- FUN_000ad5d8  <- chromaFormat string @0x95ace1 (ref @0xad972)"
RE_HANDLER_STR = re.compile(
    r"FUN_([0-9a-fA-F]{6,8})\s*<-.*?@0x([0-9a-fA-F]{6,8})"
)

# "DFE_SET_RAWB: 0x9b4a54"  /  "LIRO RTOS markers: 0x945dcd"  /
# "GInv (grid inv/shading):0x9aba8d"  /  "capture_gamma (CODEC V):0x95e85a"
RE_ANCHOR_PLAIN = re.compile(r"^[-*]\s*" + _LABEL + r"(0x[0-9a-fA-F]{5,8})\b")


def _slug(label: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", label.strip()).strip("_")
    if not s:
        s = "anchor"
    if not re.match(r"^[A-Za-z_]", s):
        s = "a_" + s
    return s[:60]

# Lines that are prose/code, not symbol declarations.
SKIP_HINT = re.compile(r"```|^\s*[-*]?\s*#{1,6}\s")


def _strip_comment(text: str) -> str:
    """Pull the trailing prose comment off a line, if any."""
    m = re.search(r"\)\s*[—–-]{1,2}\s*(.+)$", text)
    if m:
        return m.group(1).strip().rstrip(".")
    m = re.search(r"\(\s*(?:0x[0-9a-fA-F]{6,8}|FUN_[0-9a-fA-F]{6,8})\s*[,;]\s*([^)]+)\)", text)
    if m:
        return m.group(1).strip().rstrip(".")
    return ""


def _clean(s: str) -> str:
    s = s.replace("`", "").replace("*", "").strip()
    s = re.sub(r"\s+", " ", s)
    # drop trailing parenthetical noise
    return s[:400]


def scrape_file(path: Path, db: SymDB) -> tuple[int, int, list[str]]:
    """Scrape one markdown file into db. Returns (added, dup, unparsed_lines)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    added = dup = 0
    unparsed: list[str] = []
    stem = path.name

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        # Only consider bullet lines (the symbol-map convention in these docs)
        if not line.startswith(("-", "*")):
            continue

        found_any = False
        # Pattern A: "addr -> Name"
        for m in RE_ARROW.finditer(line):
            addr = int(m.group(1) or m.group(2), 16)
            name = m.group(3)
            if name.startswith("FUN_") or _bad_name_boundary(line, m.end()):
                continue
            comment = _clean(_strip_comment(line))
            src = f"{stem}:{lineno}"
            if db.add(addr, name, kind="auto", comment=comment, source=src):
                added += 1
            else:
                dup += 1
            found_any = True

        # Pattern B: "Name (addr)"
        # Handles the shorthand family form: "ISP_stream_start_handler_c
        # (0x6adb72), _d (0x6adb9a)" -- a leading-underscore name is a suffix of
        # the first full name on the same line, so expand it before storing.
        base_name = None
        for m in RE_NAME_ADDR.finditer(line):
            name = m.group(1)
            addr = int(m.group(2) or m.group(3), 16)
            if name.startswith("FUN_") or name.startswith("PTR_") or name.startswith("fcn"):
                continue
            if not VALID_NAME.match(name):
                continue
            if name.startswith("_"):
                if not base_name:
                    continue
                # "..._c (0x..), _d (0x..)" -> substitute the family suffix
                # (ISP_stream_start_handler_d), not concatenate.
                fam = re.match(r"^(.*_)[A-Za-z0-9]$", base_name)
                sfx = re.match(r"^_[A-Za-z0-9]$", name)
                if fam and sfx:
                    name = fam.group(1) + sfx.group(0)[1:]
                else:
                    name = base_name + name
            else:
                base_name = name
            comment = _clean(_strip_comment(line))
            src = f"{stem}:{lineno}"
            if db.add(addr, name, kind="auto", comment=comment, source=src):
                added += 1
            else:
                dup += 1
            found_any = True

        # Pattern C: "**FUN_007e8e88** = Name"
        for m in RE_BOLD_FUN.finditer(line):
            addr = int(m.group(1), 16)
            name = m.group(2)
            comment = _clean(_strip_comment(line))
            src = f"{stem}:{lineno}"
            if db.add(addr, name, kind="auto", comment=comment, source=src):
                added += 1
            else:
                dup += 1
            found_any = True

        # Pattern D: string anchor -> handler.  Label the FIRST anchor address
        # as a data symbol so the dispatch site is findable by name.
        for m in RE_ANCHOR.finditer(line):
            label = m.group(1).strip()
            anchors = re.findall(r"0x([0-9a-fA-F]+)", m.group(2))
            handler = int(m.group(3), 16)
            if not anchors or not label:
                continue
            first = int(anchors[0], 16)
            name = "str_" + _slug(label)
            extra = f" +{len(anchors)-1} more" if len(anchors) > 1 else ""
            comment = f"{label} string anchor{extra}; handler FUN_{handler:08x}"
            src = f"{stem}:{lineno}"
            if db.add(first, name, kind="data", comment=comment, source=src):
                added += 1
            else:
                dup += 1
            found_any = True

        # Pattern E: "FUN_000ad5d8 <- chromaFormat string @0x95ace1"
        for m in RE_HANDLER_STR.finditer(line):
            addr = int(m.group(1), 16)
            name = f"handler_{m.group(2).lower()}"
            comment = _clean(line.lstrip("-* "))[:200]
            src = f"{stem}:{lineno}"
            if db.add(addr, name, kind="auto", comment=comment, source=src):
                added += 1
            else:
                dup += 1
            found_any = True

        # Pattern F: "DFE_SET_RAWB: 0x9b4a54 (no xref; indirect)" — a string
        # anchor with no resolved handler.  Still worth naming so the location
        # is greppable.  Label must be a single identifier (optionally with a
        # parenthetical gloss) so prose like "Ghidra load:" never matches.
        if "->" not in line and "→" not in line:
            for m in RE_ANCHOR_PLAIN.finditer(line):
                label = m.group(1)
                first = int(m.group(2), 16)
                if "no xref" not in line.lower() and "indirect" not in line.lower():
                    # only capture the explicitly-deferred indirect anchors
                    if len(label) < 3:
                        continue
                name = "str_" + _slug(label)
                comment = f"{label} string anchor; no static xref (indirect dispatch)"
                src = f"{stem}:{lineno}"
                if db.add(first, name, kind="data", comment=comment, source=src):
                    added += 1
                else:
                    dup += 1
                found_any = True

        # Flag bullet lines that look like symbol lists but matched nothing
        if not found_any and re.search(r"\b(?:FUN_|0x)[0-9a-fA-F]{6,8}\b", line):
            unparsed.append(f"{stem}:{lineno}: {line[:120]}")

    return added, dup, unparsed


def migrate(target: SymDB, sources: list[Path], runtime_base: int) -> SymDB:
    """Scrape all sources into a fresh SymDB for `target`."""
    db = SymDB(target=target, runtime_base=runtime_base)
    all_unparsed: list[str] = []
    for src in sources:
        if not src.is_file():
            print(f"  [skip] {src} (missing)")
            continue
        added, dup, unparsed = scrape_file(src, db)
        all_unparsed.extend(unparsed)
        print(f"  {src.name}: +{added} new, {dup} dup")
    db.path = None
    return db, all_unparsed

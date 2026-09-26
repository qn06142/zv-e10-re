"""Tests for retool. Run: python -m retool.selftest   (or: python -m pytest tests)

These cover the parts that do not need a rizin round-trip: config, the address
convention, the symbol DB, and the markdown scraper.  The scraper tests pin the
exact prose shapes found in avcam_re/RE_STATE.md and avcam_re/pipeline.md, so a
future edit that silently stops recovering names will fail here.
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retool import config, migrate, consts, xrefs  # noqa: E402
from retool.symbols import SymDB, Symbol, VALID_NAME, _as_int  # noqa: E402

FAILURES: list[str] = []


def check(cond, label):
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILURES.append(label)


# ---------------------------------------------------------------- config
def test_config():
    print("config")
    cfg = config.load()
    check(cfg.root.is_dir(), "project root resolves")
    t = cfg.target("avcam")
    check(t.path.is_file(), f"target avcam path exists ({t.path.name})")
    # The single most important invariant: file offset is canonical, runtime VA
    # is derived.  0x7e8e88 is the documented ISP_WriteRegister offset.
    check(t.off(t.va(0x7E8E88)) == 0x7E8E88, "off(va(x)) round-trips")
    check(t.va(0x7E8E88) == 0x635C6000 + 0x7E8E88, "va() adds runtime_base")
    check(len(t.seeds) == 9, "9 entry seeds configured")
    check(all(0 <= s < t.path.stat().st_size for s in t.seeds),
          "all seeds land inside the file")


# ---------------------------------------------------------------- symbols
def test_symbols():
    print("symbols")
    check(_as_int("0x635c6000") == 0x635C6000, "_as_int parses hex string")
    check(_as_int(42) == 42, "_as_int passes int through")
    check(_as_int("42") == 42, "_as_int parses decimal string")

    db = SymDB(target="t", runtime_base=0x635C6000)
    check(db.add(0x7E8E88, "ISP_WriteRegister", comment="c"), "add symbol")
    check(not db.add(0x7E8E88, "other"), "rejects duplicate offset")
    check(not db.add(0x1234, "ISP_WriteRegister"), "rejects duplicate name")
    check(db.validate(0x2000000) == [], "clean db validates")

    # round-trip through disk, including the hex runtime_base
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json"
        db.save(p)
        raw = json.loads(p.read_text())
        check(raw["runtime_base"] == "0x635c6000", "runtime_base stored as hex")
        # 'off' is canonical (file offset); 'va' is the derived runtime address
        check(raw["symbols"][0]["off"] == 0x7E8E88, "off stored as canonical file offset")
        check(raw["symbols"][0]["va"] == hex(0x7E8E88 + 0x635C6000),
              "va derived as off + runtime_base")
        db2 = SymDB.load(p)
        check(len(db2.symbols) == 1, "round-trip preserves count")
        check(db2.symbols[0].name == "ISP_WriteRegister", "round-trip preserves name")
        check(db2.runtime_base == 0x635C6000, "round-trip parses runtime_base")

    # validation must catch real problems
    bad = SymDB(target="t")
    bad.symbols = [Symbol(off=1, name="a"), Symbol(off=1, name="b"),
                   Symbol(off=2, name="c"), Symbol(off=0x99999999, name="ok")]
    probs = bad.validate(0x1000)
    check(any("duplicate offset" in p for p in probs), "detects duplicate offset")
    check(any("outside file" in p for p in probs), "detects out-of-range offset")
    check(not VALID_NAME.match("9bad"), "VALID_NAME rejects leading digit")
    check(VALID_NAME.match("_ok9"), "VALID_NAME accepts underscore/leading _")


# ---------------------------------------------------------------- scraper
SCRAPES = [
    # (markdown line, expected [(hex_addr, name, kind)])
    ("- 0x00000004 -> LIRO_Header_Magic_0x04 (Data Tag `0x4C49524F`)",
     [(0x4, "LIRO_Header_Magic_0x04", "auto")]),
    ("- FUN_007e8e88 -> ISP_WriteRegister (register-write primitive)",
     [(0x7E8E88, "ISP_WriteRegister", "auto")]),
    ("- VideoEncode_Start (FUN_006be8a0) -- builds 272B param",
     [(0x6BE8A0, "VideoEncode_Start", "auto")]),
    ("- DFE_ISP_apply (0x42bff4), DFE_core (0x42de50)",
     [(0x42BFF4, "DFE_ISP_apply", "auto"), (0x42DE50, "DFE_core", "auto")]),
    ("- DFE_apply_pipeline_registers (0x423bac -- 9.9KB DFE container loop)",
     [(0x423BAC, "DFE_apply_pipeline_registers", "auto")]),
    ("**FUN_004402f0** = DFE_get_block_id", [(0x4402F0, "DFE_get_block_id", "auto")]),
    # string anchor -> handler (the "deferred" table-driven dispatch)
    ("- SET_PROISP_MODE: 0x933927, 0x933950 -> FUN_00035cec (handler)",
     [(0x933927, "str_SET_PROISP_MODE", "data")]),
    ("- shading_correction: 0xa30320 -> FUN_0065dee0",
     [(0xA30320, "str_shading_correction", "data")]),
    # indirect anchors with no handler
    ("- DFE_SET_RAWB: 0x9b4a54 (no Ghidra xref; indirect)",
     [(0x9B4A54, "str_DFE_SET_RAWB", "data")]),
    ("- GInv (grid inv/shading):0x9aba8d (no xref; indirect)",
     [(0x9ABA8D, "str_GInv", "data")]),
    # shorthand family suffix: "_d" expands against the first full name
    ("- ISP_stream_start_handler_c (0x006adb72), _d (0x006adb9a) -- more handlers",
     [(0x6ADB72, "ISP_stream_start_handler_c", "auto"),
      (0x6ADB9A, "ISP_stream_start_handler_d", "auto")]),
]

MUST_NOT_PARSE = [
    # ranges: no single address, and "Sub-processor" is a hyphenated word
    "- 0x00000010..0x0000002C -> Sub-processor Exception Vector Pointer Array",
    # prose, not a symbol table
    "- Path: `C:\\Users\\x\\dumps\\av-cam.bin` (17,289,388 bytes, 0x107D0AC)",
    "- Ghidra load: raw `ARM:LE:32:v7`, **image base 0x00000000**",
    # a filename extension must not be scraped as a symbol name
    "- lens files: /lens/fixed_lensfile.bin (0x8c2160+)",
]


def test_scraper():
    print("scraper")
    for line, expected in SCRAPES:
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "x.md"
            src.write_text(line + "\n", encoding="utf-8")
            db = SymDB(target="t", runtime_base=0x635C6000)
            migrate.scrape_file(src, db)
            got = [(s.off, s.name, s.kind) for s in db.symbols]
            check(got == expected, f"{line[:58]!r} -> {got}")

    for line in MUST_NOT_PARSE:
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "x.md"
            src.write_text(line + "\n", encoding="utf-8")
            db = SymDB(target="t", runtime_base=0x635C6000)
            migrate.scrape_file(src, db)
            check(not db.symbols, f"correctly ignores: {line[:52]!r}")

    # provenance must be recorded
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "RE_STATE.md"
        src.write_text("- FUN_007e8e88 -> ISP_WriteRegister (x)\n", encoding="utf-8")
        db = SymDB(target="t")
        migrate.scrape_file(src, db)
        check(db.symbols[0].source == "RE_STATE.md:1", "records source provenance")


# ---------------------------------------------------------------- real db
def test_consts():
    """The MOVW decoder is load-bearing: a wrong one makes a negative search
    result meaningless (it once reported 117888 for a `movw #0x303`)."""
    print("consts / MOVW decoder")
    # real instruction from av-cam.bin: 'movw r3, #0x303' at 0x8a60c
    # halfwords 0xf240 / 0x3303 -> imm16 = imm4:i:imm3:imm8 = 0:0:3:0x03
    check(consts._thumb_movw_imm16(0xF240, 0x3303) == 0x303,
          "decodes movw r3,#0x303 from f240/3303")
    check(consts._thumb_movw_imm16(0xF240, 0x3303) == 771, "same, decimal 771")
    # imm4 path: 0xf248 -> imm4=8
    check(consts._thumb_movw_imm16(0xF248, 0x0001) == 0x8001,
          "decodes imm4 in the top bits")
    # i bit (imm16 bit 11)
    check(consts._thumb_movw_imm16(0xF640, 0x0000) == 0x0800, "decodes the i bit")
    check(consts._thumb_movw_imm16(0xF000, 0x0000) is None, "rejects non-MOVW")
    mt = consts._thumb_movw_imm16(0xF2C0, 0x3303)
    check(mt is not None and mt < 0, "MOVT decoded and flagged negative")

    # end-to-end on a synthetic buffer
    import struct as _s
    buf = _s.pack("<HH", 0xF240, 0x3303) + b"\x00" * 8
    hits = consts.scan(buf, 0, 0, len(buf), [0x303])
    check(any(h["kind"] == "thumb-movw" and h["off"] == 0 for h in hits),
          "scan() finds the MOVW immediate in a buffer")

    # the real binary: 2160 / 3376 / 135 must NOT appear as MOVW immediates
    cfg2 = config.load()
    t2 = cfg2.target("avcam")
    if t2.path.is_file():
        data = t2.path.read_bytes()
        for v in (2160, 3376, 135):
            hs = consts.scan(data, t2.runtime_base, 0, len(data), [v])
            check(not any(h["kind"].startswith("thumb-mov") for h in hs),
                  f"{v} is never a Thumb MOVW immediate in av-cam.bin")

    # packing convention the patch surface relies on
    check(((0x08700F00 >> 16) & 0xFFFF, 0x08700F00 & 0xFFFF) == (2160, 3840),
          "(h<<16)|w decodes 0x08700f00 as 2160x3840")
    check(((0x0A000F00 >> 16) & 0xFFFF, 0x0A000F00 & 0xFFFF) == (2560, 3840),
          "patched 0x0a000f00 would be 2560x3840")


def test_xrefs_delta_resolution():
    """PC-relative delta resolution.

    Two bugs here invalidated real conclusions before they were caught, so both
    are pinned: a halfword index used as a byte address, and an `add rX, pc`
    mask that could never match.  A delta also looks exactly like a pointer
    (plausible value, often bit 0 set), which is how a "handler vtable" turned
    out to be a list of unrelated strings.
    """
    print("xrefs / PC-relative delta resolution")
    import struct as _s

    # Build a real ldr+add-pc pair.
    #   ldr r0, [pc, #imm8]  at 0x00 : base=(0+4)&~3=4, so imm8=1 -> pool at 0x08
    #   add r0, pc           at 0x02 : PC = (0x02+4)&~3 = 0x04
    #   pool word at 0x08 = 0x1000 -> target = 0x1000 + 0x04 = 0x1004
    buf = bytearray(0x10)
    buf[0:2] = _s.pack("<H", 0x4801)      # ldr r0, [pc, #1]
    buf[2:4] = _s.pack("<H", 0x4478)      # add r0, pc
    buf[8:12] = _s.pack("<I", 0x1000)     # pool delta
    refs = list(xrefs.iter_references(bytes(buf)))
    check(len(refs) == 1, "one reference resolved")
    if refs:
        check(refs[0][2] == 8, f"pool slot is a BYTE address (got {refs[0][2]}, want 8)")
        check(refs[0][3] == 0x1004, f"target = delta + PC (got {refs[0][3]:#x}, want 0x1004)")

    # Real instance from av-cam.bin: fcn.0008f5f8 id 0x0a
    #   ldr @0x8f65e, add @0x8f660, pool @0x8f6cc = 0x8c4d32
    #   PC = (0x8f660+4)&~3 = 0x8f664  ->  target 0x954396 = 'NAMESURO'
    cfg2 = config.load()
    t2 = cfg2.target("avcam")
    if t2.path.is_file():
        data = t2.path.read_bytes()
        got = [r for r in xrefs.iter_references(data)
               if r[0] == 0x8F65E]
        check(len(got) == 1, "found the reference at 0x8f65e")
        if got:
            check(got[0][2] == 0x8F6CC, f"pool byte address 0x8f6cc (got {got[0][2]:#x})")
            check(got[0][3] == 0x954396, f"resolves to 0x954396 (got {got[0][3]:#x})")
            check(xrefs.read_cstring(data, got[0][3]) == "NAMESURO",
                  "and that address holds the string 'NAMESURO'")
        # read_cstring must return the WHOLE string even from a mid-string pointer
        check(xrefs.read_cstring(data, 0x954397) == "NAMESURO",
              "read_cstring walks back to the string start")

        # the mode table really is referenced (this was missed while buggy)
        hits = xrefs.refs_to(data, 0x89DADE, 0x140)
        check(len(hits) >= 1, "mode table at 0x89DADE has an inbound reference")


def test_real_symdb():
    print("real symbol db")
    cfg = config.load()
    t = cfg.target("avcam")
    p = cfg.symdb_dir / "avcam.json"
    if not p.is_file():
        print("  skip (no db yet -- run: retool migrate avcam)")
        return
    db = SymDB.load(p)
    check(len(db.symbols) > 80, f"recovered >=80 symbols (got {len(db.symbols)})")
    check(db.validate(t.path.stat().st_size) == [], "real db has no validation problems")
    check(all(s.source for s in db.symbols), "every symbol has provenance")
    by_name = db.by_name()
    check("ISP_WriteRegister" in by_name, "recovered ISP_WriteRegister")
    check(by_name["ISP_WriteRegister"].off == 0x7E8E88,
          "ISP_WriteRegister at documented 0x7e8e88")
    check(any(s.kind == "data" for s in db.symbols),
          "recovered table-driven string anchors (the 'deferred' work)")
    check(not any(s.name in ("bin", "_d") for s in db.symbols),
          "no filename-extension / shorthand-suffix artifacts")
    check(any(s.name == "ISP_stream_start_handler_d" for s in db.symbols),
          "shorthand '_d' expanded to full name")
    check(any(s.name.startswith("ISP_mode_4k") for s in db.symbols),
          "recovered the 4K video mode descriptors")
    # The mode table base is 0x89DADE (from the consumer's base+stride), not the
    # 0x89dae0 the earlier content-only guess produced.
    check(db.by_off().get(0x89DADE) is not None,
          "mode table base is 0x89DADE, per the consuming code")
    check(not db.by_off().get(0x8C4440),
          "unverified 0x8c4440 'stream cfg table' symbol was retracted")
    check(any(s.name == "ISP_resolve_mode_by_width" for s in db.symbols),
          "the mode-table consumer is named")


def main():
    test_config()
    test_symbols()
    test_scraper()
    test_consts()
    test_xrefs_delta_resolution()
    test_real_symdb()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all retool tests passed")


if __name__ == "__main__":
    main()

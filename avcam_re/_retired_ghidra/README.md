# Retired Ghidra / legacy-disasm infrastructure

Everything in this directory is **dead** and is kept only for reference.
Nothing here runs, and nothing here is imported by `retool`.

## Why it was retired

Checked on 2026-09-25 against the current machine:

| Problem | Detail |
|---|---|
| Ghidra is not installed | `GHIDRA_HOME` pointed at `C:\Users\Minhsnguhoa\Downloads\ghidra_12.1.2_PUBLIC` — a different user account, absent from this box. No Ghidra anywhere on disk. |
| Hardcoded foreign paths | Every script hardcoded `C:\Users\Minhsnguhoa\...`; the project now lives at `D:\02_Development_And_Projects\pmca-re`. |
| Broken JDK path | `JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot` does not exist. |
| It never ran | `ghidra_run.log` = `EXIT=127`, `analyzeHeadless.bat: No such file or directory`. |
| The project was empty | `ghidra_proj/` was 359 bytes / 4 files, `NEXT-ID:0`, MD5 `d41d8cd9...` (the empty string). The claimed "63,533 functions" was **not** on disk. |
| Names were trapped | The ~120 renamed functions existed only inside that lost project — surviving purely as prose in `../RE_STATE.md` and `../pipeline.md`. |
| Base address conflict | `ghidra_headless.py` and the `disasm*.py` scripts used `BASE=0x635c6000`, while `../pipeline.md` documents the real session as base `0x0`. Every documented address was therefore incompatible with the CSVs. |

`out/` held the output of a single aborted run: 8 functions, 1 pointer table.

## What replaced it

`retool/` (rizin-based) at the repo root:

```powershell
python -m retool doctor              # verify engine + targets
python -m retool analyze   avcam     # build cached analysis project
python -m retool symbols   apply avcam
python -m retool export    avcam
```

- rizin 0.9.1 static build lives in `.tools/rizin/` (gitignored, self-contained, no JDK).
- Addresses are canonicalised to **file offset (base 0x0)**, with the runtime VA
  (`+0x635c6000`) printed alongside.
- The renamed functions were recovered out of the markdown into
  `re_symbols/avcam.json` — versioned, diffable, and no longer trapped in a
  binary Ghidra database.

## Files here

- `ghidra_headless.py` — GhidraScript that set image base and dumped functions/xrefs/strings to JSON. Superseded by `retool export`.
- `run_ghidra_headless.bat` — self-contained headless launcher. Superseded by `python -m retool`.
- `ghidra_run.log` — the failure log quoted above.
- `ghidra_proj/` — the empty project shell.
- `out/` — output of the aborted run.
- `disasm.py` / `disasm2.py` / `disasm3.py` — capstone recursive-descent attempts. Their logic is superseded by rizin's `aar`+`aac` seeded descent (66,800 functions, ~4 min, vs. these scripts' 8-function aborted output).

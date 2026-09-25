# retool — binary analysis pipeline

Replaces the retired Ghidra setup. Single engine (**rizin**), single addressing
convention (**file offset**), everything reproducible and version-controlled.

```powershell
retool.cmd doctor            # verify engine + targets
retool.cmd analyze avcam     # build cached analysis project (~5 min, once)
retool.cmd symbols apply avcam
retool.cmd export avcam
```

Use `retool.cmd`. A `retool.ps1` wrapper is also provided, but this machine's
PowerShell execution policy blocks `.ps1` by default — if you prefer it:
`powershell -ExecutionPolicy Bypass -File .\retool.ps1 doctor`.

## Why this replaced Ghidra

The old infra did not run on this machine at all: Ghidra was never installed
here, every path was hardcoded to a different user account
(`C:\Users\Minhsnguhoa\...`), the JDK it referenced was gone, and the project
directory was an empty 359-byte shell. Its last run logged `EXIT=127`.

The cost was not the tooling — it was that **~120 renamed functions were trapped
inside the lost project**. They survived only as prose in
`avcam_re/RE_STATE.md` and `avcam_re/pipeline.md`. `retool migrate` scrapes that
prose back into machine-readable data.

Full detail: `avcam_re/_retired_ghidra/README.md`.

## Addressing

**Canonical key is the file offset (base `0x0`).** This is what all the
addresses already written in `pipeline.md` / `RE_STATE.md` mean, so nothing
documented had to change. The runtime load address is reported alongside.

```
0x7e8e88    = file offset (canonical)
0x63DAEE88  = runtime VA    = 0x7e8e88 + 0x635c6000
```

Exports carry both (`off_hex`, `va_hex`). The old scripts used
`BASE=0x635c6000` for *everything*, which silently made every documented
address unusable against their CSVs — that contradiction is now gone.

## Install

rizin 0.9.1, static Windows build, self-contained (no JDK, no installer, no
admin). Lives in `.tools/rizin/` and is gitignored.

```powershell
# already done on this machine; for a fresh clone:
New-Item -ItemType Directory -Force .tools
Invoke-WebRequest -Uri https://github.com/rizinorg/rizin/releases/download/v0.9.1/rizin-windows-static-v0.9.1.zip -OutFile .tools/rz.zip
Expand-Archive .tools/rz.zip .tools/rizin -Force
Remove-Item .tools/rz.zip

python -m venv .venv-re        # msys2 layout: .venv-re/bin/python.exe
```

`capstone` is **optional** (cross-check only). It has no cp314 wheel, so
`pip install capstone` fails to build on Python 3.14; install it via pacman
(`mingw-w64-ucrt-x86_64-python-capstone`) if you want it. Nothing in the
pipeline requires it.

## Commands

| Command | Purpose |
|---|---|
| `doctor` | Verify rizin, rz-bin, and every configured target |
| `analyze <t> [--force]` | Seeded recursive-descent analysis → cached `.rzdb` |
| `export <t>` | `functions.csv`, `calls.csv`, `data_xrefs.csv`, `strings.csv`, `ptr_tables.csv` |
| `migrate <t> [--out f]` | Scrape symbols out of the RE markdown → `re_symbols/<t>.json` |
| `symbols list\|apply <t>` | Inspect / push names+comments into the project |
| `funcs <t> [filter]` | Search the function list |
| `xrefs <t> <addr>` | Cross-references to an address |
| `strings <t> [filter]` | Search strings |
| `all <t>` | migrate → analyze → apply → export |

## How the analysis works

The image is raw ARM/Thumb with no entry-point metadata, so rizin's `aaa` is
useless (>15 min, found nothing — it needs something to start from). The
pipeline instead seeds functions explicitly and lets rizin expand:

```
af @ 0x28 ; af @ 0x58 ; ...   # reset stub + 7 exception vectors
aar                          # follow data references
aac                          # follow the call graph
```

That yields **66,800 functions in ~4 minutes** — independently corroborating
the 63,533 figure the old Ghidra session claimed, at the same addresses
(rizin resolves `fcn.007e8e88` at the documented `ISP_WriteRegister` offset).

The seeds are the vector table at `0x10..0x2c`, whose entries are absolute
pointers into the `0x635c6000` window, plus the reset stub at `0x28`.
`reconf.toml` holds them per target.

## Symbol database

`re_symbols/avcam.json` is the durable replacement for the Ghidra project.

```json
{
  "schema": 1,
  "target": "avcam",
  "runtime_base": "0x635c6000",
  "symbols": [
    { "off": 8289416, "va": "0x7e8e88", "name": "ISP_WriteRegister",
      "kind": "func", "comment": "register-write primitive, ~120 callers",
      "source": "RE_STATE.md:32" }
  ]
}
```

`kind` is `func`, `data`, or `auto`. Every symbol records its provenance
(`source`) so you can always trace a name back to the note that justified it.
`source` is why the DB is trustworthy — it is not a bag of magic constants.

### Recovered content

105 symbols, including the string→handler **anchor tables** that the old notes
listed as *"NOT yet labeled (deferred)"* because the dispatch is table-driven
and static xref could not resolve it:

```json
{ "off": 9657671, "name": "str_SET_PROISP_MODE", "kind": "data",
  "comment": "SET_PROISP_MODE string anchor +3 more; handler FUN_00035cec" }
```

Those are now greppable data instead of a TODO. `migrate` prints anything it
could not parse, so nothing is silently dropped — the leftovers are ranges
(`0x10..0x2C`) and multi-word prose labels.

## Adding a target

```toml
[[target.mydll]]
path   = "dumps/libBizFw.so"
arch   = "arm"
bits   = 32
runtime_base = 0x0
seeds   = [0x0]
```

Point `seeds` at the real entry points, then `retool.cmd analyze mydll`.

## Tests

```powershell
.venv-re\bin\python.exe tests\test_retool.py
```

```powershell
retool.cmd doctor
```

Covers the address convention, symbol-DB round-trip and validation, and pins
every markdown prose shape the scraper must recognise (so a future edit that
silently stops recovering names fails the suite). No rizin required.

## Two things worth knowing

**rizin's command parser treats `@` as a seek modifier anywhere on the line.**
A comment containing `@` aborts the *entire* `-c` string — including a trailing
`Ps` save — so every rename is lost with no error. Measured unsafe characters
(rizin 0.9.1): `@`, `` ` ``, `"`, `'`, `(`, `)`; `;` silently truncates.
`retool` rewrites these when pushing comments. The original text stays
authoritative in `re_symbols/<target>.json`.

**Only pass one `-c` flag.** A second `-c` is silently dropped by rizin, so a
trailing save never runs. Commands are joined with `;` inside a single string.

## Cross-check against the old session

| | old Ghidra | retool / rizin |
|---|---|---|
| functions | 63,533 | **66,805** |
| `ISP_WriteRegister` call sites | "~120 callers" | **4,220** xrefs |
| pointer/dispatch tables | 1 (from an 8-function run) | **3,688** |
| strings | — | 220,593 |
| call edges | — | 319,397 |

Independent agreement on `0x7e8e88 = ISP_WriteRegister` is the strongest
evidence that the recovered addresses are right: a completely different engine,
reached by a different method, lands on the same offsets.

# Handoff: ZV-E10 reverse engineering

State as of the last commit. Written for an agent picking this up cold.

**Repo:** `D:\02_Development_And_Projects\pmca-re` · **Python:** `.venv\Scripts\python.exe`
(always pass `-B` to skip stale bytecode) · **Tests:** 69 pass, ~60 s
**Git:** clean tree, 8 commits this session

```powershell
cd D:\02_Development_And_Projects\pmca-re
& ".venv\Scripts\python.exe" -B research\firmware\sysdef_tables.py
& ".venv\Scripts\python.exe" -m pytest -q
```

---

## 1. What was done, in order

| commit | what |
|---|---|
| `8b7e0f1` | Proved an attack path: writable `/usr/lib` → `dlopen` → root code exec |
| `25e4cc7` | Documented how these binaries are read (`docs/RE_METHOD.md`); corrected a stale capstone claim |
| `51496f3`, `d761327`, `552712c` | Repo cleanup: made 78 scripts path-independent, `.gitattributes`, `.gitignore` |
| `0da94a3` | Decoded the 35 scenario plugins' command vocabulary |
| `7104fda` | Recovered the MWF category/message pairs from the MPR plugins |
| `27d5d8d` | Named every id in that vocabulary, from `libSysDef.so` |
| `56235e5` | Joined the object table to `libObj.so`; found the IMCFG device table |

The RE arc is a chain — each step needed the previous one:

1. **`scenario.elf` does not `dlopen` the plugins.** `libtestcmd.so` imports no
   `dlopen`/`dlsym`, only `osal_*`. It sends the name over the UIPC bus; the
   peer that would load the plugin is not running in service mode. So the
   plugins had to be read directly.
2. **Their message ids are immediates, not data.** Sweeping `movw`/`movt`
   across all 35 gave 96 values. Anchored against five
   `HDMI::PAYLOAD<MSG<id,1>>` template ids carried in mangled names — 2 of 5
   matched an immediate in exactly the right plugin.
3. **`libSysDef.so` names them.** Three exported MWF tables, self-describing.
4. **The object table joins to `libObj.so`** exactly: 25 implemented, 20
   declared-only, zero orphans.

## 2. Findings, by file

| doc | contents |
|---|---|
| `docs/SERVICE_AUDIT.md` | 44 KB. The service-mode audit. Attack path, mounts, persistence, init recipe |
| `docs/SCENARIO_VOCAB.md` | 96-value id vocabulary; DataflowInfra vs MWF; the two cross-validate on 3 ids |
| `docs/MWF_TABLES.md` | 33 categories, 45 objects, 12 pins; which are implemented |
| `docs/IMCFG_BLOCK.md` | 70 device names incl. all 32 `nflasha`; 7 `/nondev/` pseudo-devices; 16-id array |
| `docs/RE_METHOD.md` | **Read this first.** The decoding traps, all verified |
| `docs/FLASH_ICON_FONT.md` | The patched icon font and its transport |

Headline results:

- **Attack path (proved, not theorised).** `/usr/lib` is ext2 on `nflasha15`,
  remountable rw, and *not* wiped at boot. Replace a `.so` there and the loader
  runs it as root. Demonstrated with a 66-byte Thumb-2 payload of raw `svc #0`
  syscalls injected into `libtestcmd.so`'s `cmdline_show_revision`; marker file
  appeared; restored and md5-verified.
- **`libIMDB.so` is the application manifest.** 174 libraries, 16 kernel
  modules, 22 paths. `imdb_raw` is 132 bytes of `u16` offsets naming nine
  modes. `im.elf` (PID 157) `dlopen`s what it names — that is the real target,
  and it is a one-way door (if it breaks, the service shell never appears).
- **The application core is not deployed.** `appFw.so`, `gui.so`, `libNVM.so`,
  `libInfraWebApi.so` are all absent. The service filesystem has the rendering
  engine and the assets, not the program.
- **Two bus namespaces.** `0x0094xxxx` = Linux (89 hits), `0x00dcxxxx` = the
  liro/RTOS endpoint (**0** hits in the Linux dump — the RTOS keeps its own
  queues). `sndcmd` returning RC=0 means the firmware accepted the message.
- **`0x2004` = `PIN_SOUND`**, the most common id in the whole vocabulary at 76
  uses.

## 3. Tooling

### Read these binaries

```powershell
# the four extraction tools, all run clean with no arguments
& ".venv\Scripts\python.exe" -B research\firmware\sysdef_tables.py    # MWF tables -> names
& ".venv\Scripts\python.exe" -B research\firmware\imcfg_block.py     # device table + id array
& ".venv\Scripts\python.exe" -B research\firmware\scenario_vocab.py  # flat movw/movt sweep
& ".venv\Scripts\python.exe" -B research\firmware\mwf_ids.py         # MWF category/message pairs

# annotated disassembly: <elf> <symbol>
& ".venv\Scripts\python.exe" -B research\firmware\annotate.py `
    dumps\camera_2025\usr\usr\lib\libtestcmd.so testcmd_run_scenario
& ".venv\Scripts\python.exe" -B research\firmware\annotate.py `
    dumps\engine\libObj.so ObjMedia_RegisterCommand

& ".venv\Scripts\python.exe" -B research\firmware\elf_catalog.py      # 648-ELF inventory
```

`annotate.py` resolves PLT stubs to symbol names, decodes literal pools to
`u32`, and names branch targets. Requires a symbol that exists — the symbol
must be in `.dynsym`/`.symtab` with a nonzero size, or it raises `KeyError`.

Importable helpers (used by the tools above):

- `annotate.plt_map(f, data, segs)` → `{stub_vaddr: symbol_name}`
- `annotate.v2o(segs, vaddr)` → file offset, via `PT_LOAD`
- `scenario_vocab.immediates(path)` → `({mnemonic: u16} counts, {u32: count})`
- `sysdef_tables.Obj(path)` → `.pairs(vaddr, size, stride)` yields
  `(id, [names], words)`
- `cpp_demangle.demangle(name)` — use this, **not** `cxxfilt`, which shells out
  to a C++ demangler that isn't installed and fails

### Talk to the camera

The SD card is in the PC, not the camera. Service mode gives a root shell over
the USB serial console; `/usr/share/app` is the cwd.

```powershell
# one command per arg; accepts a run only when a prompt returns
& ".venv\Scripts\python.exe" research\device\zve10_retry.py `
    "ls -l /usr/lib/libtestcmd.so" "busybox md5sum /usr/lib/libtestcmd.so"
```

**Read the log, not the console.** The wrapper truncates console at 25 lines
and writes the whole session to `zve10_shell.log` in the repo root. Four
claims in this project were wrong purely from trusting the console.

Camera-side essentials:

- BusyBox 1.34.1 ash. `xxd`, `tr`, `tail`, `wc`, `head` are **listed by
  `busybox --help` but not linked** — use `busybox <applet>`, which does work
  for `md5sum`, `tail`, `dd`, `od`.
- `xxd -r -p` is unusable: mangles 132 hex chars into 30 bytes. Use
  `printf '\200\265...'` (3-digit octal) to write binary, and
  `busybox tail -c +N` / `dd bs=1 count=N` to slice.
- Mount the card by hand: `mkdir -p /tmp/sd; mount /dev/mmca1 /tmp/sd`
  (`/dev/mmcca1` is a different controller and fails).
- `/usr` is ext2 on `nflasha15`; `mount -o remount,rw /usr` works and persists.
- `dd` has no `conv=notrunc` — any `dd of=<live file>` truncates. Use `cp`.
- PowerShell eats `$` in camera commands; `echo RC=$?` arrives as `RC=\True`.

## 4. The traps — this is the part that will bite you

Every one of these **fails silently**: a wrong answer looks exactly like a
right one. Full detail in `docs/RE_METHOD.md`.

1. **These objects are Thumb.** `.dynsym` sets bit 0 of `st_value`; all 25
   `STT_FUNC` in `libtestcmd.so` are odd. Decode at `st_value & ~1`. Decoding
   at the odd address in ARM mode gives a full, evenly sized, *fictional*
   instruction stream that does not fail.

2. **PLT stubs are ARM even in a Thumb library**, in three encodings (12-byte,
   8-byte, inline in `.text`). To resolve one, decode its
   `ldr pc, [ip, #imm]!`, compute the GOT address, look *that* up in
   `.rel.plt`. **Do not assume stub order == relocation order.** Writing the
   `ldr` test as a single mask against `0xE5BCC000` is wrong twice: it pins the
   register field so the common `e5bcf...` encoding never matches, and W is
   bit 21 not 20. Four wrong versions were tried, all returning `{}` — which
   reads as "this object has no PLT". Sanity check: `AVBB_SCN_START_HDMI.so`
   must give **122** entries.

3. **capstone's `op_str` for `movw r2, #0x1022` leaves a trailing comma** on
   the register name. Split on `#` and every later lookup for `"r2"` misses,
   so the id silently falls back to the category: `0x1022` reported as `0x3700`.

4. **`pop` may be spelled `pop.w`.** Match `mnemonic.split('.')[0]`. On
   capstone 5.0.7 the wide form reports as `pop`, so `== 'pop'` happens to
   work *here* and breaks on a build that spells it otherwise. Don't "fix"
   `thumb.py` — it's already correct.

5. **`pc` in `op_str` is not a return.** Every PC-relative literal load prints
   as `ldr r3, [pc, #0x10c]`. Check the destination register, not the text.

6. **vaddr ≠ file offset.** The shortcut holds for the two `.so` files and is
   **wrong for `im.elf`** (off by 0x8000). Always go through `PT_LOAD`.

7. **Table strides differ and lie.** `libSysDef.so`: `m_cateTbl` 8,
   `m_objTbl` 12, `m_pinTbl` 16. At the wrong stride `m_pinTbl` yields
   `\x7fELF` (it followed a zero to vaddr 0) or interleaves id and name
   columns. `m_objTbl` records carry **two** names — `{id, CATEID_*, Obj*}` —
   so a positional read reports `ObjCntMgr` where the category is
   `CATEID_CNT_MGR`.

8. **Array bounds: the two ends are inconsistent.** In a walk that stops on a
   predicate, the forward end lands on the first word that *failed* while the
   backward end lands on the first word *included*. `(hi - lo)//4 + 1` pulls
   the rejected word back in — this put `0x46434d49` (`IMCF`, the first four
   bytes of a marker) into an id list that read as 17 entries instead of 16.

9. **Watch for truncated dumps.** `dumps/camera_2025/usr/usr/lib/libObj.so`
   is **81,920 bytes** and does not parse; the real 21 MB one is
   `dumps/engine/libObj.so`. Check size before believing an `ELFParseError`
   is a real finding.

10. **`cxxfilt` is useless here** — it shells out to a binary that isn't
    installed. Use `cpp_demangle`.

## 5. Open items

Ordered by value. None are guesses; each is stated with what is known.

1. **The plugin message vocabulary is still unnamed.** `0x1022`, `0x102a`,
   `0x81000`, `0x81003` are message ids, not categories, and no table names
   them. The IMCFG id array contains `0x1001` but *not* the others, so it is a
   different space that overlaps. Each object registers its own commands, so
   the registry is in `libObj.so` per-object — start at
   `ObjMedia_RegisterCommand` (vaddr `0xa3ea25`, Thumb bit set, so decode at
   `0xa3ea24`; 12 bytes, one `bl`).
2. **A `0x4xxx` id family exists and nothing names it.** Seen in the IMCFG
   array: `0x4000 0x4100 0x4200 0x4300 0x4400`.
3. **`0x2000`** is used by `MPR_SCN_INSTALL_MAP_DEMOMOVIE` and is in none of the
   three MWF tables. Pins are `0x2001`–`0x200c`, so it is plausibly a pin
   *group* — that is an inference, not a finding.
4. **`DefInh::sm_refTbl`** (3,158,400 B, 96.7% of `libSysDef.so`) and
   **`DefRsrc::scm_refTbl`** (98,778 B) are exported and untouched. Indexed by
   `AcsrId_t`, so resource id rather than message id.
5. **Boot mode.** `BOOTMODE=NORM`, no `/setting/sen/smode`, no `dmode`, no
   kernel flag — yet the app is not loaded. Either the reported mode is wrong or
   the service USB personality itself holds the system in the launcher. Testing
   costs the shell; the SD card is the recovery route.
6. **Reachable but untested:** the `tmonitor` RTOS tracer (16 writable
   params; `mask=0`, `autostop_tasklist=N`; `autostop_tasklist=Y` plus a dump
   path would give the firmware's task list), and the `BK4` settings format in
   `/setting/Backup.bin` (1,235,740 B, md5 `bdc524e5cdcf3b290aed1c9271ccf921`,
   staged on the card as `F:\RE_DUMP\audit\Backup.bin`). An earlier snapshot
   `Backup.bak` was referred to in earlier notes but is **not** in the dumps or
   on the card — treat it as unverified until produced from the device.

## 6. Camera state

**Unchanged, verified.** `/usr/lib/libtestcmd.so` is stock md5
`f370de888ae662e7f509f2274846eac6`, mode `-r-xr-xr-x 1 57285 1000`, original
ownership (`cp` had reset both; `chown`/`chmod` put them back). The `.orig`
copy was removed and `/tmp` scratch cleaned. Five persistence markers from
earlier work remain in place: `/setting/_audit1`, `/system/_audit2`,
`/usr/bin/_marker3`, `/usr/share/_marker4`, `/usr/share/pmbp/_marker2`.

The SD card (`PMCA`, was `F:`) holds `F:\RE_DUMP\` with the audit files and the
patched/stock fonts.

## 7. House rules that were violated before they were learned

- **Verify every number before it goes in a doc.** Four claims in this project
  were wrong from trusting truncated or mis-strided output. Two of my own
  commits in this session shipped a wrong number and had to be corrected
  (`0x110` in `START_HDMI_INPUT`; the two-names-per-record layout).
- **A negative result needs a positive control.** "0 IDs found" means the
  predicate is wrong until proven otherwise — see trap 2, where an empty
  `plt_map` nearly produced a completely wrong conclusion.
- **Prefer formats that round-trip** over inferences about unreadable code.
- **Same-length edits, and label unquantified side effects.**
- **Never** `dd of=<live file>`; never leave a patched library installed.

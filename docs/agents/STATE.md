# STATE — ZV-E10 reverse engineering, consolidated

**Self-contained.** Everything an agent needs to pick the thread up, on one page.
Nothing here requires opening another file; the topic docs are for depth.

Repo `D:\02_Development_And_Projects\pmca-re` · Python `.venv\Scripts\python.exe`,
**always pass `-B`** (stale bytecode bit once) · 68 tests pass, 4 skipped
(they need an SD card).

Long version by subject: [`../01`](../01-hardware.md) ·
[`../02`](../02-service-shell.md) · [`../03`](../03-binaries.md) ·
[`../04`](../04-messaging.md) · [`../05`](../05-formats.md) ·
[`../06`](../06-method.md) · [`../07`](../07-modification.md) ·
[`../08`](../08-camera-interfaces.md)

---

## The one fact that explains most dead ends

**The service-mode filesystem carries the camera's rendering engine, its view
layer and 81 MB of resources — but not the application that uses them.**
`appFw.so`, `gui.so`, `libNVM.so`, `libSaveLoadSettings.so` and
`libInfraWebApi.so` are all named by the manifest and simply not present. The
files do not exist; this is not a permissions or mount problem.

So: no camera application in `comm`, `LMSGQ`/`LSEM` empty, `scenario.elf`
fire-and-forget, no TCP listener, and **a patched icon font cannot appear because
`gui.so` — the thing that draws labels — is not installed.** A whole-file
`md5sum` is not evidence that a string is drawn.

## Where things stand

| | status |
|---|---|
| run our own code as root | **done, proved** |
| persistent code execution at boot | blocked on a deliberate decision + the camera |
| command the RTOS subsystems | blocked on the RTOS message format |
| command the application | blocked: entry point absent, and boot mode unexplained — but the engine underneath is **resident and in use**, so this is narrower than it was |
| observe the firmware | `tmonitor` is writable and idle (`mask=0`) — untested |
| offline RE | **not blocked**; everything below can proceed with the camera disconnected |

## The camera is attached

`research/device/zve10_retry.py` reaches the service shell, `/proc/modules` lists
**47** modules, and the imaging manager is PID 157. Device work is unblocked;
everything below that was gated on the camera being present is now live.

**Camera state:** unchanged and as found. `libtestcmd.so` stock
(`f370de888ae662e7f509f2274846eac6`), mode and ownership restored, no `.orig`
left, `/tmp` scratch removed. The five persistence markers are still in place
(`/setting/_audit1`, `/system/_audit2`, `/usr/bin/_marker3`, `/usr/share/_marker4`,
`/usr/share/pmbp/_marker2`). `libIMDB.so` has **not** been touched.

**The SD card does not release.** It stays mounted with `OperationalStatus:
Unknown` and a blank volume label, and an eject never completes. Reads still work,
so dumps can be taken, but the card is not being handed back — and recovery from
the `libIMDB.so` one-way door depends on it. Treat "card confirmed working" as
unproven.

---

## The attack path — proved, not theorised

Writable `/usr/lib` (ext2 on `nflasha15`, remountable rw, **not** wiped at boot)
→ `dlopen` → root. No exploit, no memory corruption, no race: the camera loads
its own libraries by name from a directory the service shell can write to, and
that directory survives reboot.

A 66-byte Thumb-2 payload of **raw `svc #0` syscalls only** (no PLT, no libc, no
new relocations, so the loader has nothing extra to bind) was injected into
`libtestcmd.so`'s `cmdline_show_revision`:

```asm
push {r7, lr}
sub  sp, sp, #16
movw r1, #0x742f ; movt r1, #0x706d ; str r1, [sp, #0]   "/tmp/ox\0"
movw r1, #0x6f2f ; movt r1, #0x0078 ; str r1, [sp, #4]
movw r1, #0x504f ; movt r1, #0x0a58 ; str r1, [sp, #8]   "OPX\n"
mov  r0, sp ; movw r1, #0x0241 ; mov r7, #5 ; svc #0     open(path, O_WRONLY|O_CREAT|O_TRUNC)
add  r1, sp, #8 ; mov r2, #4 ; mov r7, #4 ; svc #0       write(fd, body, 4)
mov  r0, #0 ; add sp, sp, #16 ; pop {r7, pc}              return 0, as the original did
```

66 of 10,128 bytes changed, all inside `0x1a48..0x1a8b`; length unchanged; all
25 exports still resolve. `/tmp/ox` containing `OPX` appeared, created in the
`scenario.elf` process as root. Restored and md5-verified against stock
`f370de888ae662e7f509f2274846eac6`.

Builder: `research/firmware/opx_payload.py`. Used rather than `libIMDB.so`
**precisely to avoid the one-way door** — `im.elf` does not link `libtestcmd.so`.

### The real target, and why it has not been done

Replacing `/usr/lib/libIMDB.so` would execute code at startup, on the next boot,
as root, **inside PID 157** — the process that owns 417 message queues, 134
semaphores and 310 callbacks and mounts every filesystem. That is the path to the
subsystems, and the same primitive is all that is required.

**It is a one-way door.** If the replacement is malformed, `im.elf` does not
start, the service shell never appears, and recovery is the SD card. The
`crypter.elf` / `udtrbody.bin` updater door has the identical shape. Both need
the camera present **and a deliberate decision**, not more analysis.

---

## Established, in the order the chain was built

1. **`scenario.elf` does not `dlopen` the plugins.** `libtestcmd.so` imports no
   `dlopen`/`dlsym`, only `osal_*`. It sends the name over the bus; the peer that
   would load the plugin is not running in service mode. So the 35 plugins had to
   be read directly.
2. **Their message ids are immediates, not data.** Sweeping `movw`/`movt` across
   all 35 gave **96 distinct values**, anchored against five
   `HDMI::PAYLOAD<MSG<id,1>>` template ids carried in mangled names — 2 of 5
   matched an immediate in exactly the right plugin.
3. **`libSysDef.so` names them.** Three exported MWF tables, self-describing.
   The object table then joins to `libObj.so` **exactly**: 25 implemented, 20
   declared-only, **zero orphans in either direction**. Two independent symbol
   lists agreeing exactly is unlikely by accident.
4. **`libIMDB.so` is the application manifest** — 174 libraries, 16 kernel
   modules, 22 paths, in boot order.
5. **The `.uxc` container round-trips.** 302/302 files, 12,082/12,082 index
   entries landing inside the file.
6. **The palette is authoritative**, proved on hardware by a colour that appears
   nowhere in Sony's palette.
7. **The engine is not dormant.** `libIMDB.so` names 174 libraries `im.elf` *may*
   load; `/proc/157/maps` shows **97** actually resident, including `libObj.so`,
   `libMWF.so`, `libSysDef.so` and two of the seven `viewUnified*` engines. What is
   absent is the application *entry point*, not the machinery. `im.elf` also holds
   `/dev/dmpgles2` open (fd 31) with `grm_gles` at refcount 2, so the DMP 2D engine
   and the VDF OSD port are reachable in a live process that is not the application
   — which makes an OSD injection a concrete option.

Details in [`REFERENCE.md`](REFERENCE.md).

## Blockers that need hardware

| # | blocker | why it needs the camera |
|---|---|---|
| 1 | `libIMDB.so` → `im.elf` persistent root | needs the device, and a decision about the one-way door |
| 2 | boot mode | `BOOTMODE=NORM`, no forcing file, no kernel flag — yet the application is not loaded. Either the reported mode is wrong or the service USB personality holds the system in the launcher. **Testing means giving up the shell.** This is the actual reason the subsystems are unreachable, and the one open question no amount of offline RE will answer. |
| 3 | `/proc/osal/uipc` write grammar | the node is read-write and the module has `__k_cmd_debug`, but the command grammar is unknown and it is a write into a kernel interface |
| 4 | host-tunnel code for `GetLensVersion` | must be determined live; read-only once found |
| 5 | `tmonitor` | 32 KB at `0xF00000`, `mask=0`, a kernel module loaded under that name. Cheapest untried observation knob. |

## Open offline, by value

1. **The RTOS message format in `av-cam.bin` (17,289,388 B, on disk).** What
   `sndcmd.elf` speaks. Highest value, needs no hardware, and gates issuing real
   commands. `sndcmd` returning RC=0 to `0x00dc0000` shows the firmware
   *accepts* messages — not that they do anything.
2. **The id→record index for `DefInh::sm_refTbl`.** Geometry is recovered
   (3,158,400 B / 800 = **3948 records exactly**, 88.2% populated, 24 field
   offsets, bimodal field count → tagged union). 6381 factor ids against 3948
   records fits an indirection rather than a direct array.
3. **`DefRsrc::scm_refTbl`** (98,778 B), indexed by `AcsrId_t`.
4. **The `0x4xxx` id family** — real, named by nothing.
5. **`ObjFaceRecorder` dispatch geometry** — the four `MSGID_*FACE*` strings are
   at `0xf03a41`–`0xf03bcc` and the pointer table is near `0x13dc660`, but the
   record layout is not established. (`0x13dc504` is a *different* table: its
   word 0 is `0x1000` and word 3 resolves to `MSGID_OPEN`.)
6. **`BK4` format** in `/setting/Backup.bin` (1,235,740 B, staged on the card).
7. **The style TLV** in `style_cmn.uxc` — 186 aligned 4-byte quads across 301
   files match a palette colour, 9,212× above chance, but the record is
   variable-length.
8. **Real member names for the class ids and property keys.** The blocker is
   named: `libJiritsuUIView.so` is not in the archive and was not in `/usr`
   either.

## What to do when the camera comes back

**In one session, in this order.**

1. **Do not touch `libIMDB.so` yet.** Collect the risk-free device state first:
   - `tmonitor` params (addr / size / mask, and whether it is writable)
   - a second `/proc/osal/uipc` capture, to diff against the stored one
   - the `0x4xxx` ids
2. Then decide on `libIMDB.so` **deliberately**, with the SD card confirmed
   working as the recovery path.
3. Read [`../08-camera-interfaces.md`](../08-camera-interfaces.md) for the WiFi
   Direct link (`192.168.122.1`) — zero risk, and the main firmware's own
   interface. The camera runs a DHCP server there and nothing else listens.

The offline work continues regardless. Item 1 in the open-offline list is where
the time goes.

---

## Tooling

```powershell
# the five extraction tools, all run clean with no arguments
& ".venv\Scripts\python.exe" -B research\firmware\sysdef_tables.py    # MWF tables -> names
& ".venv\Scripts\python.exe" -B research\firmware\imcfg_block.py     # device table + id array
& ".venv\Scripts\python.exe" -B research\firmware\scenario_vocab.py  # flat movw/movt sweep
& ".venv\Scripts\python.exe" -B research\firmware\mwf_ids.py         # MWF category/message pairs
& ".venv\Scripts\python.exe" -B research\firmware\mwf_catalog.py     # full message vocabulary
& ".venv\Scripts\python.exe" -B research\firmware\factor_table.py    # sm_refTbl
& ".venv\Scripts\python.exe" -B research\firmware\cmd_surface.py     # av-cam.bin SDF/Exec surface
& ".venv\Scripts\python.exe" -B research\firmware\vdf_methods.py     # VDF string-resolved methods
& ".venv\Scripts\python.exe" -B research\firmware\elf_catalog.py     # 648-ELF inventory

# annotated disassembly: <elf> <symbol>
& ".venv\Scripts\python.exe" -B research\firmware\annotate.py `
    dumps\camera_2025\usr\usr\lib\libtestcmd.so testcmd_run_scenario

# the only camera link; one command per arg
& ".venv\Scripts\python.exe" research\device\zve10_retry.py "ls -l /usr/lib"

# what is really resident in im.elf; two sessions, do not merge them
& ".venv\Scripts\python.exe" -B research\device\im_runtime_manifest.py

& ".venv\Scripts\python.exe" -m pytest -q
& ".venv\Scripts\python.exe" -B research\firmware\check_docs.py   # docs integrity
```

`annotate.py` resolves PLT stubs to symbol names, decodes literal pools to `u32`,
and names branch targets. It **requires a symbol that exists** — present in
`.dynsym`/`.symtab` with a non-zero size, or it raises `KeyError`.

Use `cpp_demangle.demangle(name)`, **not** `cxxfilt` — that shells out to a
binary which is not installed.

---

## The traps

**Every trap in this project fails silently.** Four mis-stride and mask bugs this
project returned plausible wrong answers rather than raising. The full list with
derivations is in [`../06-method.md`](../06-method.md); the ones that bite most:

| trap | consequence if wrong |
|---|---|
| `plt_map` mask | ARM P=24, U=23, B=22, W=21, L=20 **by bit position**, plus Rn=ip / Rt=pc. Do **not** mask cond, and do **not** pin the register field in one constant. Sanity check: `plt_map` on `AVBB_SCN_START_HDMI.so` must give **122** entries. |
| `plt_map` on a Thumb lib | PLT stubs are **ARM**, even in a Thumb library. |
| `.dynsym` `st_value` | bit 0 set means Thumb. ARM-mode decode of a Thumb function returns plausible nonsense, not an error. |
| capstone `op_str` | `movw r2, #0x1022` yields a register named `"r2,"` — **with a trailing comma**. |
| table strides | APICD is **36**, not 72. Stride 72 reads every *second* record, still starts in the right place and every name pointer still resolves — it just reports 58 records instead of 115 and pairs each id with the wrong name. Pinned by `tests/test_mwf_catalog.py::test_apicd_stride_is_36_not_72`. |
| vaddr vs file offset | `0x13ec720` is a **file offset**. `libObj.so`'s second PT_LOAD is vaddr `0x1365d8c` / offset `0x135dd8c`. |
| `av-cam.bin` pc-rel | the pool word and `addr` are **both** file offsets; do **not** apply the load base. `pc` is `addr + 4`, **not** `Align(PC,4)`. |
| console output | the shell wrapper truncates at 25 lines. **Never trust a count or an absence from wrapped console output** — re-read through a filter that emits one line, or read `zve10_shell.log`. |
| `dd` on this busybox | **no `conv=notrunc`.** Any `dd of=<live file>` truncates the target to the write offset. Use `cp`. |
| base64 by hand | a single mistyped character once decoded to `0000` at the *id field of the next record*. Generate chunks programmatically; hash on the camera **before** writing. |
| link is lossy at volume | a scan of `/proc/*/fd` across 263 processes floods the serial link and the **next** command's output arrives empty. Put the noisy query and the bulky query in **separate** sessions. |
| `$$` never survives | PowerShell expands it, so `/proc/$$/maps` arrives as `/proc/<pc-pid>/maps` and reports nothing. Use the literal pid. |

The last two are what made the runtime manifest return an empty list three times
before it worked, each time as a *plausible empty result* rather than an error.
Pinned by `tests/test_im_manifest.py`, which intercepts the tool's `run` and
asserts on the commands it really issues — a text search for `$$` in the source
would find it in the comment that documents the trap, and fail for the wrong
reason.

## House rules that were violated before they were learned

- **A claim about a byte pattern needs a computed chance rate.** 14,720 raw
  `0c 40` hits across a 27 MB bitmap atlas, zero of them in a structural word,
  was published as "14,721 references" before a null model existed.
- **A claim about a "constant" needs a cardinality check.** A property reported
  as 100% on a style-index test turned out to have **1 distinct value** across
  10,500 occurrences — a type tag.
- **Structural checks do not always discriminate.** Two of them (offsets inside
  the file; offsets non-decreasing) **both passed on a wrong `data_start`**.
  They constrain the offset array, not where the array ends. The check that
  discriminates is content: record 0 must yield a name that exists on disk.
- **Negative results are results.** Record them, with the null model. Three
  conclusions in this project were wrong in exactly the same way, and the
  correction is procedural.
- **Unquantified side effects get labelled, not omitted.** Same-length edits are
  preferred because they cannot move an offset or change an entry count.
- **A function that silently drops its evidence is worse than the bug it hides.**
  `drain()` returned `None`; three consecutive "transfer failures" were that one
  bug.

## Restore points

- SD card in the PC (`PMCA`, was `F:`) holds `F:\RE_DUMP\audit\Backup.bin`,
  md5 `bdc524e5cdcf3b290aed1c9271ccf921`.
- **`Backup.bak` does not exist** in the dumps or on the card, despite a note
  claiming it is a genuine earlier snapshot. Do not rely on it.
- `udtrbody.bin` is in three local copies plus the card.
- Stock `libtestcmd.so` md5 `f370de888ae662e7f509f2274846eac6`.
- `dumps/camera_2025/usr/usr/lib/libObj.so` is an **81,920-byte truncated
  decoy** that does not parse. The real one is `dumps/engine/libObj.so` (21 MB).

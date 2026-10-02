> **SESSION RECORD - not a reference.** This is a dated log of how a finding was
> reached. Anything still true of it has been extracted into the topic docs; do
> not cite this file as fact. Kept for provenance only, so that a retracted
> claim is not silently re-derived.
>
> Current documentation: [docs/README.md](../README.md)
# Handoff: ZV-E10 reverse engineering

State as of `b6d56a6`. Written for an agent picking this up cold.

**Repo:** `D:\02_Development_And_Projects\pmca-re` · **Python:** `.venv\Scripts\python.exe`
(always pass `-B` to skip stale bytecode) · **Tests:** 139 pass / 8 skip with the
camera attached, 135 / 12 without · **Commits:** 118 · **Scripts:** 322
**Git:** clean tree, `qn06142 <90816999+qn06142@users.noreply.github.com>`, pushed
to `github.com/qn06142/zv-e10-re`, default branch `master`.

```powershell
cd D:\02_Development_And_Projects\pmca-re
& ".venv\Scripts\python.exe" -B -m pytest -q
& ".venv\Scripts\python.exe" -B research\firmware\check_docs.py   # md5-set fingerprint
```

`check_docs.py` must not be edited — its md5-set fingerprint is a regression pin
for the docs restructure.

> **Never quote that fingerprint in full.** `check_docs.py` scans the docs for
> 32-hex-digit strings and hashes the resulting set, so writing the full value
> into any doc *adds it to its own input* and changes it. `09-provenance.md`
> truncates it (`070a0f50…`), which is why that has stayed stable. Writing the
> full value here moved the fingerprint `070a0f50…` → `4bf7d909…`.

---

## 1. The short version

Four modifications were applied and verified, plus root code execution. Only
`DeviceInfo.xml` is still patched; the other three are back to stock because
`/usr/share/app` is boot-wiped. The palette was the only one ever *seen* to work.

The reason nothing further has landed is not analysis. Every remaining door is
one-way with SD-card recovery, and the card does not release cleanly. The
bottleneck is a card eject.

---

## 2. What was done this session, in order

1. **Corrected the "application is not deployed" claim.** `im.elf` holds
   `/dev/dmpgles2` on fd 31, `grm_gles` is loaded at refcount 2, and 97 of the 174
   libraries `libIMDB.so` names are genuinely mapped — including `libObj.so`,
   `libMWF.so`, `libSysDef.so` and `viewUnified2/6`. The engine was never dormant;
   only the application *entry point* is missing.
   → `research/device/im_runtime_manifest.py`, `research/firmware/im_runtime_manifest.txt`
2. **`/proc/tmonitor` is live**, not masked off. `mask=0` means nothing is masked
   out. It returns a ~50 ms RTOS scheduler trace: 60+ tasks, wait channels with
   kernel addresses, 15 `MODULE::task` prefixes, IRQ hot spots.
   → `research/firmware/tmonitor.py`, `research/firmware/tmonitor_trace.txt`
3. **Recovered the `/dev/dmpgles2` ioctl ABI**: 17 commands, all
   `_IOC(dir, 0x82, nr, 4)`. Ruled the ioctl out as a display door.
   → `research/firmware/sugilite_ioctl.py`
4. **Ejected the SD card's dataset** — disk 2 to `IsOffline` / `No Media`. The
   device node stays present; non-admin cannot finish.
5. **Audited all four modifications** against their stated baselines.

---

## 3. Findings by area

### The display path is not OpenGL

`libObj.so` carries a **196-entry table of GL ES 2.0 / EGL entry-point names** at a
uniform 48-byte stride, preceded by `"OpenGL ES2.0"` and `"EGL"` slots. It exports
**none** of them — 0 `gl*` and 0 `egl*` across 650 catalogued ELFs, and no
`libGLESv2.so` / `libEGL.so` exists. The 8 `*DMP` entries are the real vendor
surface: `eglQueryDisplayDMP`, `eglAsyncSwapBuffersDMP`, `eglDrawFrameModeDMP`,
`eglQueryFrameDMP`, `eglInvalidateImageDMP`, `eglSuspendDMP`, `eglResumeDMP`,
`eglSetHardwareStateDMP`.

The renderer is DMP SUGILITE silicon. The drawing API is `libObj.so`'s **517
exported `GRM_*` symbols** — `GRM_gpermRectblit` at `0x684087`, plus
`GRM_bitmapCreate`, `GRM_bitmapGetPhysicalAddress`, `GRM_screenGetOnBitmap`.

### The ioctl is a thin scalar surface

`sugilite_ioctl`, 2,584 bytes at `.text+0x8e4`. Dispatch is a **binary search over
literal-pool constants**, not a jump table.

**Exactly one** of the 17 commands reaches hardware, and it is not a register
write: `nr=15` writes the fixed value `0x20000001` to the fixed BAR offset `0xC0`,
only if the caller passes exactly 1. The module's other 38 register writes are in
`sugilite_register_init` (21), clock gating and the ISR. `nr=17`/`nr=18` are
`down`/`up`. `nr=13` is the only completion wait, and what completes it is
`open`/`close` on the device.

The module also holds a complete **12-byte OSAL request/reply RPC into the RTOS**
— unsymbolised, 416 bytes at `.text+0x744`, endpoints `0x008f013a` / `0x00910042`
/ `0x008f0313` — which is **unreachable**: nothing branches to it *and* it has no
symbol, so no pointer can target it either.

### Two kernels, cleanly separated

Wait channels from `tmonitor` name both kernels. The split is at `0x60000000`,
not fitted to the labels:

| space | range | examples |
|---|---|---|
| LiRo (RTOS + modules) | `0x5f0d`–`0x5f5xxxxx` | `trcv_mbf` `0x5f4dfe34`, `osal_rcv_msg_tmo` `0x5f0484ec`, `osal_wai_sem_tmo` `0x5f049ac4`, `twai_flg`, `tslp_tsk`, `hdmi_workqueue` |
| Linux | `0x60xxxxxx`+ | `run_ksoftirqd`, `irq_thread`, `hrtimer_nanosleep`, `do_wait` |

Cross-checked against `/proc/modules`: `grm_ma` `0x5f3f0000`, `grm_gles`
`0x5f3f8000`. **The LiRo kernel image is in neither `vmlinux.bin` (Linux only) nor
`av-cam.bin`** — a checked negative, so the LiRo addresses cannot be symbolised
offline.

### Modification audit

| mod | reproducible | notes |
|---|---|---|
| `DeviceInfo.xml` | **no** | never staged; a 517-byte pull from the device |
| `string_english_f.uxc` | yes | `staged/strings/…RESTORE` / `…OPENCODE` |
| `Sony_DI_Icons.ttf` | yes | every claimed figure verified at glyph level |
| `color_cmn.uxc` | yes | plus the blue build |

Font, verified by parsing rather than by byte diff: 1732 glyphs either side,
**exactly 138 outlines replaced**, **1594 of 1594** non-target glyphs identical,
cmap 1,684 identical, 0 advance widths moved. The dump's copy is the patched font
plus 5,328 B of sfft zero-padding — not a torn write.

---

## 4. Corrections made this session

These matter: two were errors of my own, and the docs were right.

1. **"The palette — worked, then was reverted."** It was not reverted; it read
   `c169428e`, byte-identical to `MAGENTA_BUILD`, at the last check.
2. **The blue build is not a single-entry edit.** Entry `0x4009` also changes,
   `0000ddff` → `00ffffff`, alongside `0x400c`. Rebuild from
   `color_cmn.STOCK.uxc` for a clean one-entry control.
3. **I read a post-modification dump as stock**, twice — once for the palette,
   once for the font — and concluded "these files are unrelated" both times. The
   palette control was sound all along (`ff00ff` occurs **0 times** in stock).
   Byte-diffing across a recompiled font is meaningless; table offsets shift.
   → recorded as a method note in `07-modification.md`.
4. **`README.md` carried a wrong test count** (109/12). Verified by stashing and
   re-running at HEAD: it was 113/8.
5. **`sugilite_ioctl` was described as jump-table dispatch.** It is a binary
   search over literal-pool constants.

---

## 5. Tooling added

```powershell
# live: what is actually resident in im.elf  (two sessions, do not merge them)
& ".venv\Scripts\python.exe" -B research\device\im_runtime_manifest.py

# live: the /proc/tmonitor RTOS trace; writes the artefact on the spot
& ".venv\Scripts\python.exe" -B research\firmware\tmonitor.py

# offline: the /dev/dmpgles2 ioctl ABI; pure file reader, no camera needed
& ".venv\Scripts\python.exe" -B research\firmware\sugilite_ioctl.py
```

New tests: `tests/test_im_manifest.py` (8), `tests/test_tmonitor.py` (23),
`tests/test_sugilite_ioctl.py` (26).

---

## 6. The traps — this is the part that will bite you

**Every trap in this project fails silently.** The full list with derivations is
in [`../06-method.md`](../06-method.md). The ones added or sharpened recently:

| trap | consequence |
|---|---|
| **`zve10_shell.py` opens `zve10_shell.log` with mode `"w"`** | **every session truncates the last one.** A whole `tmonitor` trace was extracted, summarised, then destroyed by the next three commands. Capture into a tracked artefact *on the spot*, and make the capture the first command of the session. |
| the link is lossy at volume | a scan of `/proc/*/fd` across 263 processes floods it and the **next** command's output arrives empty. Noisy query and bulky query need separate sessions. |
| `$$` never survives | PowerShell expands it, so `/proc/$$/maps` becomes `/proc/<pc-pid>/maps`. Use the literal pid. |
| the shell verb is `E&ject` | accelerator mid-word, so matching `Eject` finds nothing and the eject silently never runs. Hold the `Verbs()` collection; a second call returns a different set. |
| `Set-Content -Encoding UTF8` | adds a UTF-8 BOM. It got into three docs. Check `BOM=` when editing with PowerShell. |
| **a count is not a value check** | with the literal pool read at `addr+4` instead of `addr+8`, the ioctl tool still printed **17 commands** — right number, all wrong values. The pool is contiguous. Only comparing the recovered *set* catches it. |
| ARM PC is `addr+8` | `addr+size` reads the pool one word early and yields *instruction words* as constants (`0x0a000055` is `mov ip,sp`). |
| ARM immediates are `imm8 ROR 2*rot` | `add r3,r3,#0xc0000004` is really `#0x11, 30`. Read the decoded operand. |
| GCC refines one register across compares | `cmp r1,r3; beq E; add r3,r3,#K; cmp r1,r3; beq E2`. Clearing `r3` after the first `cmp` recovers 7 of 17 commands; symbolic execution with a shared `seen` set recovers 1. |
| no symbol means no pointer | the RTOS RPC has no symbol *and* no branch to it. Either alone is weak; together they prove it unreachable. |
| `\S+` drops names with spaces | `-profile user TC::VD_Seq S cpu:0`. Anchor on the trailing `cpu:N`. |
| a symbol name is not an identity | `0x60293424` is emitted as both `tty_insert_flip_string_fixed_flag` and the 31-char `..._fixed_fl`. `vmlinux.bin` has only the long one, NUL-terminated. One occurrence, not a 32-char clip width. |
| `wchan:0(0)` means runnable | and it is the largest group. Dropping it biases every wait statistic towards blocked tasks. |
| `PowerShell -match` is case-insensitive | produced a bogus "10 files contain GLES". Use case-sensitive bytes. |
| the camera shell has no `base64`/`stty`/`md5sum`/`head` | use `busybox <applet>`; `head: applet not found`. Commands ~1022 chars wrap and corrupt. PowerShell eats `$` (`RC=\True`). |

---

## 7. Open items, highest value first

1. **Fix the SD card.** Disk 2 is `IsOffline` with phantom `F:`/`E:` letters.
   Non-admin cannot finish it; needs `Disable-PnpDevice` or `mountvol /p` as
   admin. **This is the reason not to take `libIMDB.so`, and it blocks everything.**
2. **Then take `libIMDB.so` deliberately**, with the card confirmed as recovery.
   Executes at startup inside PID 157 — the process that owns 417 message queues
   and holds the graphics node. One-way: a malformed replacement costs the shell.
3. **Pull `/usr/share/pmbp/DeviceInfo.xml`** (517 B, reads `9b2d8cc0`) to close the
   only reproducibility gap.
4. **Boot mode.** `BOOTMODE=NORM`, no forcing file, no kernel flag, yet the
   application is not loaded. Testing means giving up the shell.
5. **The VDF OSD push entry point.** `vdf_if_port_send_update`,
   `utilDMP2D_rectBlitDraw` and `DMP_2D_Initialize` are **not** dynamic symbols in
   any of 179 scanned user-space ELFs — strings only. `libObj.so`'s `.symtab` is
   stripped. This is the gap on the `GRM_*` route.
6. **Locate the LiRo kernel image.** In neither `vmlinux.bin` nor `av-cam.bin`.
7. `sugilite_ioctl` on a live camera: `/proc/kallsyms` gives authoritative
   addresses, and an indirect caller to the RPC path could exist there.
8. Offline, by value: the RTOS message format in `av-cam.bin`;
   `DefInh::sm_refTbl` id→record index; `DefRsrc::scm_refTbl`; the `0x4xxx` id
   family; `ObjFaceRecorder` dispatch; `BK4` format; the style TLV.

---

## 8. Camera and card state

**The camera link is intermittent.** It has dropped mid-session more than once;
`zve10_retry.py` reports `No devices found` / `link never came up` after six
attempts. Treat every device fact here as *true at the check that produced it*.

At the last successful check: 47 modules in `/proc/modules`; PID 157 = `im.elf`;
`/dev/dmpgles2` present; `string_english_f.uxc` and `Sony_DI_Icons.ttf` back to
stock; `color_cmn.uxc` at the magenta build; `DeviceInfo.xml` still patched.

**SD card:** disk 2, `Generic-Mass-Storage`, FAT32 59 GB, was `F:`, label `PMCA`.
The dataset is released (`IsOffline=True`, `No Media`); the USB device node stays
enumerated and the drive letters linger as phantom volume records.

**Do not take `libIMDB.so` or `udtrbody.bin` without a deliberate decision and a
confirmed recovery path.**

---

## 9. House rules that were violated before they were learned

- **A claim about a byte pattern needs a computed chance rate.**
- **A claim about a "constant" needs a cardinality check.**
- **Structural checks do not always discriminate.** Two passed on a wrong
  `data_start`.
- **Negative results are results.** Record them, with the null model.
- **Diff at the level the claim is about** — content hash for a whole file, glyph
  outlines for a font, palette entries for a palette — **and establish which side
  of the diff is the baseline before reading anything into it.** Learned twice.
- **Unquantified side effects get labelled, not omitted.** Same-length edits are
  preferred because they cannot move an offset.
- **A function that silently drops its evidence is worse than the bug it hides.**
- **A verification check has to be shown to discriminate.** Mutate the thing and
  confirm the test fails; do not assume a count or an invariant is load-bearing.

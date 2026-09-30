# Patched objects — regeneration manifests

Sony's own binaries are **not** committed to this repository. This file records
enough to rebuild each patched object byte-for-byte from a file you pull off
your own camera, so the evidence survives without redistributing Sony's code.

Verify with `md5sum` before and after; the hashes below are what the build
produced when the patches were applied and confirmed on hardware.

---

## `libtestcmd.so` — the service-mode code-execution proof

| | |
|---|---|
| stock source | `/usr/lib/libtestcmd.so` on the device — **not** in git |
| stock md5 | `f370de888ae662e7f509f2274846eac6` |
| stock size | 10,128 B, mode `-r-xr-xr-x 1 57285 1000` |
| patched md5 | `5d776c95847022dbc343e00519289b5f` |
| payload source | `research/firmware/opx_payload.py` (tracked) |

### Rebuild

```powershell
# 1. put the stock library where the script expects it
#    (git-ignored: /dumps/ in .gitignore)
#    dumps/camera_2025/usr/usr/lib/libtestcmd.so   md5 f370de888ae662e7f509f2274846eac6

# 2. build
& ".venv\Scripts\python.exe" -B research\firmware\opx_payload.py
```

The script prints the expected values itself and refuses to be wrong quietly:
it asserts the stock md5, asserts the slot size, and reports the byte diff.

```
assembled 66 bytes (slot is 68)
stock md5 : f370de888ae662e7f509f2274846eac6
patched   : 5d776c95847022dbc343e00519289b5f
size      : 10128 (unchanged)
byte diff 66 of 68, all inside 0x1a48..0x1a8b
```

**Verified reproducible:** a fresh rebuild matched the md5 that was verified on
the camera.

### What it does, and why it is safe to build

The payload replaces `cmdline_show_revision` (vaddr `0x1a48`, 68 bytes, of which
the last 28 are its own literal pool — so the function is self-contained and can
be replaced wholesale). It uses **raw Linux syscalls only**: `open`/`write` via
`svc #0`, no PLT, no libc, no new relocations, so the dynamic loader has nothing
extra to bind. It writes `/tmp/ox` containing `OPX` and returns 0, which is what
the original returned.

`libtestcmd.so` was chosen over `libIMDB.so` **precisely to avoid a one-way
door**: `im.elf` does not link `libtestcmd.so`, so a malformed replacement
cannot stop the application from starting and cost the service shell.

### Restoring

```sh
busybox md5sum /usr/lib/libtestcmd.so        # expect f370de888ae662e7f509f2274846eac6
```

If it does not match, copy the stock library back (do **not** use `dd of=`: this
busybox has no `conv=notrunc`, so it truncates the target to the write offset),
then `chown`/`chmod` to `57285:1000` and `-r-xr-xr-x`. `cp` resets both.

---

## Other binaries used as inputs

None of these are in git. Each is re-pullable from the camera with
`research/device/zve10_retry.py`, or is already present under the git-ignored
`/dumps/` tree.

| what | where it comes from |
|---|---|
| `libObj.so`, `libIMDB.so`, `viewUnified2..8.so`, `libSysDef.so`, `libMWF.so` | `/usr/lib`, pulled to `dumps/camera_2025/` |
| `im.elf`, `crypter.elf`, `sndcmd.elf`, `rcvcmd.elf`, `scenario.elf`, `libtestcmd.so` | `/usr/bin` |
| `av-cam.bin` (17,289,388 B), `vmlinux.bin`, `initrd.img`, `bonobo.bin`, `dfe_*.bin` | `/system` — md5 `cdcae9d4fdbf66a33704a4c7564e346d` for `av-cam.bin` |
| `liro.ko`, `dmm.ko`, `stream*.ko` | `/usr/kmod` and `/kmod` (the latter is on the ramdisk and is freed after boot) |
| `udtrbody.bin` (143,360 B) | `/usr/bin`, Compressed ROMFS, magic `453dcd28` |
| `color_cmn.uxc`, `style_cmn.uxc`, `global.xdb`, `string_*.uxc`, `image_*.uxc` | `/usr/share/app` (81 MB, **wiped at boot**) |
| `Sony_DI_Icons.ttf`, `*.ltt`, `fontlist.dat` | `/usr/share/app` |
| `Backup.bin` (1,235,740 B, magic `BK4`) | `/setting`, also on the SD card |
| `VX*_lensfile.bin` (61 samples) | `/lens` |

## What *is* tracked, and why that is fine

Names, numbers, offsets and structure. Those are facts about Sony's binaries, not
Sony's expression, and they are the actual output of the work:

- `research/firmware/elf_catalog.json`, `prop_table.tsv`, `app_manifest.txt`,
  `libobj_exports.txt` — filenames, sizes, export and symbol names
- `research/firmware/sysdef_tables.py`, `mwf_catalog.py`, … — the tools that
  generate the tables in `docs/04-messaging.md`
- `avcam_re/*.md`, `re_symbols/*.json`, `docs/**` — our own prose and analysis
- `scripts/*.txt`, `verify/*.txt` — device command transcripts we authored

Anything that is Sony's *code* or Sony's *data* stays out.

See [`docs/09-provenance.md`](docs/09-provenance.md) for the full boundary,
including the upstream material that was already published before this work.

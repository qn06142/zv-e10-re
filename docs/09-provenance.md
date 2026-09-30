# 09 — Provenance: what is ours, what is upstream, what is Sony's

The copyright boundary for this repository, recorded so it does not have to be
re-derived. **Sony's code and Sony's data do not go in git.** Names, offsets and
structure do — those are facts, and they are what the work actually produces.

Rule of thumb: if you could paste it into the repo without adding an
explanation, it is probably Sony's. If you had to measure it, it is ours.

## 1. Our own work

| | |
|---|---|
| `docs/**` | the reverse-engineering writeup |
| `avcam_re/**` | `av-cam.bin` findings |
| `re_symbols/**` | recovered symbol names, with per-symbol provenance |
| `retool/**`, `tests/**` | the rizin-based analysis package and its tests |
| `research/**` | the scripts, all authored here |
| `scripts/**`, `verify/**` | device command transcripts and the verification harness |
| `tools/zx`, `tools/README_zx.md` | the service-shell toolbelt (a shell script, written here) |

## 2. Derived facts — tracked on purpose

Inventories of Sony binaries, not Sony binaries:

```
research/firmware/elf_catalog.json     648 ELFs: name, size, e_type, DT_NEEDED
research/firmware/prop_table.tsv       property keys -> type
research/firmware/app_manifest.txt     the 174-library load order
research/firmware/libobj_exports.txt   520 export names
```

Filenames, sizes, symbol names, offsets and table geometry are facts about a
program. The analysis scripts that generate them are tracked too, so every table
in `docs/04-messaging.md` is reproducible rather than transcribed.

## 3. Sony's binaries — never tracked

All re-pullable from the camera, all git-ignored. See
[`research/firmware/PATCHED_OBJECTS.md`](../research/firmware/PATCHED_OBJECTS.md)
for the regeneration manifests.

| what | why it stays out |
|---|---|
| `/usr/lib/*.so`, `/usr/bin/*.elf`, `/usr/kmod/*.ko` | Sony's code |
| `av-cam.bin` and the nine other firmware images | Sony's code |
| `/usr/share/app/*.uxc`, `*.xdb`, `*.ttf`, `*.ltt` | Sony's data — and the `.ltt` bundles embed third-party Monotype TTFs under their own licence |
| `/setting/Backup.bin` | Sony's data |
| `/lens/VX*_lensfile.bin` | Sony's calibration data |
| `udtrbody.bin` | Sony's update body |

**One exception was removed.** `research/firmware/libtestcmd.OPX.so` — a
*modified copy* of Sony's `libtestcmd.so` — was tracked from commit `8b7e0f1` on
the argument that it was "the exact object whose md5 was verified on the camera,
so it is evidence rather than a rebuildable intermediate."

That argument was wrong. `research/firmware/opx_payload.py` rebuilds it
byte-for-byte, and that was verified rather than assumed: a fresh build from the
stock library produced `5d776c95847022dbc343e00519289b5f`, matching the copy that
was committed. The evidence is the recipe and the two hashes, not Sony's bytes.
Both are now recorded in `PATCHED_OBJECTS.md`, and the binary is untracked.

> **The blob was still reachable in history** at `f8dfbc7e` after the tip was
> cleaned, so it was purged from history too before publishing. See
> [§6](#6-history-was-rewritten-before-publishing).

## 4. Upstream `ma1co/Sony-PMCA-RE` — pre-existing

This repository is a fork. `origin` is `https://github.com/ma1co/Sony-PMCA-RE.git`
and the `pmca/`, `updatershell/*.c`, `updatershell/*.cpp`, `updatershell/*.h`,
`pmca-console.py`, `pmca-gui.py` and the build specs are **ma1co's MIT-licensed
work**, committed upstream in 2021 and already public.

Two things in that upstream set are Sony-derived rather than ma1co's:

```
updatershell/fdat/*.dat          6 files,  8.7-13.0 KB, one per camera model
updatershell/fdat/CXD*/*.hdr     ~70 files, 48 B each
```

Encrypted firmware descriptors and per-model headers extracted from Sony's PC
updater, committed by ma1co in 2021 and published under the MIT licence with the
rest of the project.

**Left in place deliberately.** Deleting them would break the upstream updater
tool, and it would not reduce exposure — they have been publicly distributed
since 2021 by the upstream author under a licence that permits it. Removing
another project's published data from its own repository is not this project's
call. If the intent is to publish this fork separately, that decision should be
made consciously, with the upstream author in the loop, and it should be done by
fork-divergence rather than by quietly dropping files.

`updatershell/platform` is a **git submodule** pointing at
`ma1co/OpenMemories-Platform` — correctly isolated, its own history, not
duplicated here.

## 5. Not Sony's, and worth naming

| | |
|---|---|
| `certs/localtest.me.pem` | a public Let's Encrypt certificate for the `localtest.me` domain, from upstream. Not a camera artefact. |
| `LICENSE.txt` | MIT, ma1co 2015 |
| `.venv*/`, `.tools/`, `re_out/`, `out/` | local environments and regenerable analysis caches |

## 6. History was rewritten before publishing

`research/firmware/libtestcmd.OPX.so` was committed in `8b7e0f1`. It was
removed from the tip in `ca041bd`, but that alone leaves the blob reachable —
`git cat-file -p f8dfbc7e` still returns it, and GitHub serves old commits over
HTTP. **A HEAD-only removal is not isolation.**

So it was purged from history as well, before anything was published:

```
git filter-repo --path research/firmware/libtestcmd.OPX.so --invert-paths --force
```

This rewrote every commit, so **all SHAs from `8b7e0f1` onward changed.** A
pre-rewrite backup was taken first and is kept **outside** the repository:

```
%TEMP%\pmca-re-prepublish.bundle     2.56 MB, contains the old history
```

Verified after the rewrite:

| | before | after |
|---|---:|---:|
| commits | 369 | 369 |
| tracked files | 631 | 631 |
| `HEAD` tree entries | 631 | 631, byte-identical |
| docs md5-set fingerprint | `070a0f50…` | `070a0f50…` |

The `HEAD` trees being identical is correct rather than suspicious: the `.so` had
already left the tip in `ca041bd`, so the rewrite only removed it from the
commits *behind* the tip. The check that matters is:

```
git cat-file -t f8dfbc7e                  -> fatal: could not get object info
git log --all --name-only | grep libtestcmd  -> nothing
```

`git filter-repo` also removed the `origin` remote as a safety measure, which is
why no remote is configured now.

The full sweep of **every** non-text path ever committed to this repository:

```
updatershell/fdat/*.dat    12 files   upstream ma1co, published 2021 under MIT
research/firmware/libtestcmd.OPX.so     removed
```

No firmware image, partition dump, `.uxc` UI resource, `.ttf` or `.ltt` font has
ever been committed. The ignore rules were in place from the first commit. `.git`
is 2.91 MB; the working tree is 8.4 GB and none of it was ever committed.

## 7. The rule going forward

1. **Never commit a file you did not write.** If it came off the camera, out of
   the firmware, or out of an SD card, it is not yours.
2. **A hash is evidence; the bytes are not.** A rebuilt artifact plus a recorded
   md5 proves the same thing and redistributes nothing.
3. **Names and numbers are fine.** Inventories are the deliverable.
4. **If in doubt, ask what the file would be worth to a Sony lawyer.** The answer
   for a 10 KB patched `.so` is "not much", but for the whole 8.4 GB dump it is
   "quite a lot", and the principle is the same at both sizes.

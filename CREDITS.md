# Credits

This repository exists because other people built the things it stands on. The
ZV-E10-specific reverse engineering in `docs/`, `avcam_re/` and `research/` is the
new work.

**This file credits two different categories, and they are not the same thing:**

| | |
|---|---|
| **[Contributors](#upstream--code-in-this-repository)** | their **code is in this repository** — they authored the commits and the files |
| **[Sources](#prior-art--consulted-not-contributed)** | we **read and cited** their public work; **nothing of theirs is in this tree** |

Only the first group contributed to this repository. The second are credited for
prior art, which is a different kind of debt and should not be read as
contribution.

---

# Contributors

## Upstream — code in this repository

**[`ma1co/Sony-PMCA-RE`](https://github.com/ma1co/Sony-PMCA-RE)** — MIT License,
© 2015 ma1co. This repository is a fork of it, and `LICENSE.txt` is theirs
unchanged. They authored **260 of the 368 commits** here.

Carried over from upstream:

| | |
|---|---|
| `pmca/` | the Python PMCA library (51 files) |
| `updatershell/*.c`, `*.cpp`, `*.h`, `Makefile` | the native firmware-update shell |
| `updatershell/fdat/*.dat`, `updatershell/fdat/CXD*/*.hdr` | 12 firmware descriptors and ~70 per-model headers from Sony's PC updater |
| `pmca-console.py`, `pmca-gui.py`, `*.spec`, `config.py` | entry points and packaging |
| `certs/localtest.me.pem` | a public certificate for the `localtest.me` domain |
| `.travis.yml`, `appveyor.yml`, `.github/workflows/` | upstream's CI, including its encrypted deploy tokens |
| `requirements.txt`, `reconf.toml`, `build.spec` | packaging |

**Exactly one upstream file has been modified**, in commit `d7ec217`:

```
pmca/usb/driver/generic/libusb.py    +19 lines
```

On Windows, a camera Zadig-bound to libusb-win32 can be *enumerated* through the
libusb-1.0 backend but then fails `claim_interface` with *"The requested resource
is in use"*. The patch probes `usb.backend.libusb0` first and uses it when it can
actually see a Sony device, falling back to the default otherwise. It is a
locality fix and nothing more; MIT permits the modification and the upstream
notice is retained.

Everything else under `pmca/` and `updatershell/` is byte-for-byte upstream.

### Upstream contributors

From the GitHub API on `ma1co/Sony-PMCA-RE`:

| | commits | |
|---|---:|---|
| **[ma1co](https://github.com/ma1co)** | 251 | original author of the PMCA tool, `fwtool.py` and `OpenMemories-Platform` |
| [undingen](https://github.com/undingen) | 1 | |
| [paulbellamy](https://github.com/paulbellamy) | 1 | |
| [kratz00](https://github.com/kratz00) | 1 | |
| [mungewell](https://github.com/mungewell) | 1 | |

Commit author emails for these are in the upstream commit metadata; they are not
republished here.

**[`ma1co/OpenMemories-Platform`](https://github.com/ma1co/OpenMemories-Platform)**
— consumed correctly as a git submodule at `updatershell/platform`, pointing at
`85bcb54`. Not vendored, so not forked.

## Prior art — consulted, not contributed

**Nothing in this section is a contribution to this repository.** These projects
were read, cited, and checked out locally for reference. No source from any of
them was copied into this tree, and none of their authors appear in this
repository's commit history.

They are credited because the work here would not have been possible without
them, and because leaving out the debt would be dishonest — not because they
contributed to this.

These are checked out locally and git-ignored. They informed the work and are
credited here rather than copied in, because copying them would fork someone
else's project and bloat this one.

**[`nex-hack`](https://github.com/erik-smit/nex-hack)** — **Erik Smit**
(<erik-smit>), also published at
[personal-view.com/faqs/sony-hack](http://www.personal-view.com/faqs/sony-hack/).

The foundational public Sony NEX reverse-engineering work, and the direct
ancestor of the unpacking and analysis in this repo. `fwtool.py`'s own README
states it was *"originally ported from nex-hack's fwtool"*, so the lineage is
explicit and acknowledged upstream as well as here. Its `fwtool` unpacking and
the `av-cam` firmware structure are the direct ancestors of the carving and
format work in `research/firmware/` and the findings in `avcam_re/`.

**[`steelcnn/nex-hack`](https://github.com/steelcnn/nex-hack)** — credited by
handle; we did not establish a real name and are not guessing. A separate copy
from Erik Smit's, carrying `av-cam-NEX6-v1.01.idc.zip`, an IDA script for the
NEX-6's `av-cam` firmware. Useful as precedent that the `av-cam` binary is
analysable with IDA on a sibling body.

**[`ma1co/fwtool.py`](https://github.com/ma1co/fwtool.py)** — MIT, © 2015 ma1co.
A firmware-image unpacker for FDAT updates, ported from nex-hack's `fwtool` and
extended to the models this project targets.

---

# What was reverse engineered

Reverse engineered from a **Sony ZV-E10**, firmware 2.02/2.03, kernel
`3.0.27_nl-rt106+`. No Sony source, binary or resource is redistributed here —
see [`docs/09-provenance.md`](docs/09-provenance.md) for the boundary and
[`research/firmware/PATCHED_OBJECTS.md`](research/firmware/PATCHED_OBJECTS.md)
for the regeneration recipes. The `updatershell/fdat/` files are the one
exception, and they predate this project: they came with upstream's MIT release.

`dumps/`, `fw/`, `udtrbody_extract/`, `/usr/share/app` UI resources and the
camera's binaries are all git-ignored and were never committed.

---

# AI disclosure

**The reverse engineering in this repository was carried out with AI coding
agents.** Four were used, in combination: **Hermes Agent**, **OpenCode**,
**Antigravity** and **Codex**. A substantial share of the analysis, the scripts,
the documentation and the refactors were agent-written, including
`research/firmware/*.py`, `docs/**`, `avcam_re/**`, `retool/**` and the tooling
that verifies the rest.

No part of this is a reason to distrust the results without checking, and no part
of it is a reason to skip checking either. So here is what the agent-written work
actually rests on, and how to audit it.

**What is machine-checked.** Every load-bearing claim in `docs/` is reproducible
by a tracked script. The id tables, the format layouts and the offsets are
generated, not transcribed:

```powershell
& ".venv\Scripts\python.exe" -B -m pytest -q        # 68 pass, 4 skip (need the SD card)
& ".venv\Scripts\python.exe" -B research\firmware\check_docs.py
```

`check_docs.py` reports a content fingerprint over every md5 in the docs, resolves
every cross-reference, and checks every in-page anchor against a reproduction of
GitHub's slug algorithm. It exists because an earlier documentation pass had 11 of
22 table-of-contents anchors silently broken.

**What is hardware-verified, and labelled as such.** The parts that touch a real
camera were confirmed on a real camera: the palette edit that changed the
framing guides grey → blue → magenta, the code-execution proof, the mount and
persistence table, the message-bus census. Those are marked *verified* in the docs
and their hashes are in
[`research/firmware/PATCHED_OBJECTS.md`](research/firmware/PATCHED_OBJECTS.md).

**What is inference, and labelled as such.** Boot mode, the meaning of some
register fields, the styling semantics — all marked inferred or hypothesised,
with the test that would settle each one stated alongside.

**The most important caveat.** These agents produced confident wrong answers, and
they failed *silently* — a mis-set mask, a mis-guessed table stride or a
hand-typed byte returned a plausible wrong answer instead of raising. Ten such
traps are catalogued in [`docs/06-method.md`](docs/06-method.md), with Negative
results sections in the topic docs. Four of the worst:

- **An APICD table stride of 72 instead of 36.** It reads every *second* record,
  still starts in the right place, and every name pointer still resolves — so it
  looks like it works. It reports 58 records instead of 115 and pairs each id
  with the wrong name. The giveaway is contiguity: at stride 36 the ids run
  `0x1000, 0x1001, 0x1002` with no gaps. Now pinned by a regression test that
  fails on the old code.
- **A byte-exact round trip that could not fail.** `uxc_color.py` parsed and
  re-packed its own inverse, so it returned the input for *any* stride dividing
  the body evenly. It proved the codec was lossless and nothing at all about
  field boundaries. The real evidence for the palette layout is the magenta
  hardware control.
- **A 14,721-hit claim that was 14,720 coincidences.** A raw two-byte count
  across a 27 MB bitmap atlas, with zero hits inside a structural word, published
  before a null model existed.
- **An ELF header parse reading at the wrong offsets**, reporting
  `e_type = 0x280013` and 44 unnamed PLT stubs — fiction that read exactly like a
  packed binary. The file was an ordinary `.so` all along. The tell was that
  `e_type` is a 16-bit field and no legal value has that bit set: a magic number
  like that is a parse failure, not a file-format fact.

All four retractions are recorded with the null model or control that refuted
each one. That is deliberate: a wrong claim plus the reason it was wrong is worth
more than a correct claim alone, because it stops the same error being made
twice.

**Practical guidance.** Treat the tables as generated and re-runnable. Treat
anything quoted from a disassembly as a claim to re-verify — that is what
`research/firmware/annotate.py` is for. When a document states a negative
result, check that it names its control.

## Licence

This repository is MIT, inherited from upstream, and the upstream notice is
retained in `LICENSE.txt`. Redistribution of the fork is on that basis.

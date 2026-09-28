# The UI engine is found: `viewUnified2.so`

The one genuinely blocked thread is now open. `/usr/bin` has no candidate — its 48
files are tools, the largest being `bsa_server` (4.8 MB, Bluetooth). The engine
is a **family of shared libraries under `/usr/lib`**:

| binary | bytes | note |
|---|---:|---|
| **`viewUnified2.so`** | **14,284,732** | largest non-bitmap ELF; **contains the literal `global.xdb`** |
| `viewUnified3.so` | 941,232 | |
| `viewUnified4.so` | 3,287,604 | |
| `viewUnified5.so` | 749,136 | |
| `viewUnified6.so` | 589,336 | 15.4× enriched over controls |
| `viewUnified7.so` | 579,944 | |
| `viewUnified8.so` | 283,208 | |

Seven engines, presumably one per screen class. `viewUnified2` is the one that
matters.

## Two independent confirmations

**1. The engine names the resource file.** `viewUnified2.so` contains the literal
string `global.xdb` exactly once. That is not a statistical inference — it is
the loader naming the file it opens. `libObj.so` carries the string `uxc` twice,
so the container magic is recognised there too.

**2. `libSysDef.so` is 45.7× enriched in palette ids.**

```
u16, 4-aligned:  823 hits   vs   18 control hits
  0x4000  x1095      0x4004  x27      0x4008  x11      0x4020  x9
  0x400c  x7         0x4010  x4       0x4003  x1       0x4001  x1
```

`viewUnified6.so` is second at 15.4×. The name fits: `libSysDef` = system
defaults, which is exactly where a default colour scheme would live.

Every other library tested sits at or below chance, and this is the discipline
the project has learned the hard way — those are *not* results:

| binary | palette / control |
|---|---:|
| `libSysDef.so` | **45.7×** |
| `viewUnified6.so` | **15.4×** |
| `viewUnified2.so` | 3.7× |
| `CautionConfig.so` | 6.1× |
| `viewUnified8.so` | 2.7× |
| `viewUnified3.so` | 3.5× |
| `viewUnified4.so` | 1.8× |
| `viewUnified7.so` | 0.4× |
| `libmprctrl.so` | 0.6× |
| `libObj.so` | 1.4× |
| `libmpr.so` | 0.6× |
| `libInfraHdmi.so` | 1.4× |

`libObj.so` (21 MB) and `libmpr.so` (13 MB) are large enough that 1.4× is what
noise looks like at that scale. Their hit counts are dominated by `0x4000`,
which is also the most common value in a `0x4000`-range scan generally.

## What this settles, and what it does not

**Settled.** The colour path question that survived the view-format work now has
an answer on the code side. No view property carries a palette id (2.5× chance
across 211,844 windows). The magenta control proved the engine honours
`color_cmn.uxc`. `viewUnified2.so` opens `global.xdb`. `libSysDef.so` holds a
dense, deliberate table of palette ids. The chain is: `libSysDef` defaults →
`viewUnified2` loader → `color_cmn.uxc` values.

**Not settled.** Which specific code path renders the framing guides, and
whether `0x400c` is chosen there by a hard-coded default or looked up. That needs
the `0x400c` references in `viewUnified2.so` traced to their containing function,
which is real disassembly work rather than a search.

## Operational note: `usr.tgz` is truncated on the card

```
size 91,820,032   md5 ddbb62adef9fc94284cbefa43637ad73
MD5SUMS.txt says ddbb62adef9fc94284cbefa43637ad73   MATCH
```

The transfer is good — the md5 matches the camera's own record. The **archive
itself** was written truncated, and `tarfile` aborts with `EOFError` while
seeking to enumerate members. Python's `tarfile` needs to seek; gzip is a
stream. So members are read by a hand-rolled sequential tar reader
(`usr_tar_stream.py`, `engine_colour.py`) which yields the 1,010 members written
before the cut — 214 MB of payload, enough to find the engine.

If a complete tree is wanted, re-dumping `/usr` is a one-line change and 91 MB
is nothing against 58 GB of card.

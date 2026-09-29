# libObj.so's IMCFG block: the device table, and two more id vocabularies

Found by accident, while checking whether `libObj.so` named the message ids
recovered from the scenario plugins. Searching it for `0x1001` returned six
hits, three of them exactly 20 bytes apart:

    0xe4e35c  0x00001001
    0xe4e370  0x00001002
    0xe4e38c  0x00001005

That spacing is a table, not code. Walking out from it over plausible values
gives 16 `u32` ids, and the word immediately after the last one is not an id —
it is ASCII:

    IMCFG   VER:109 CATEGORY:MAIN TYPE:COM CXD:COM
    /dev/ms  /dev/msa  /dev/msb  /dev/mmca  …  /dev/nflasha31
    /dev/sd{a,b,c,d}  /dev/sr{0,1}
    /nondev/dvdmenu  /nondev/simulate  /nondev/pcremote  /nondev/air
    /nondev/streaming  /nondev/iptc  /nondev/ipremote

`research/firmware/imcfg_block.py` extracts it.

## The device table — 70 names

This is the complete set of storage nodes the imaging layer knows about, and
it settles several things the service audit could only partly see:

| family | count | range | what |
|---|---:|---|---|
| `/dev/ms` | 3 | `ms` … `msb` | memory stick |
| `/dev/mmc` | 13 | `mmca` … `mmccd` | SD / MMC |
| `/dev/sata` | 9 | `sata` … `satauhsb` | SATA |
| **`/dev/nflasha`** | **32** | `nflasha` … `nflasha31` | raw nand A |
| `/dev/sd` | 4 | `sda` … `sdd` | SCSI disk |
| `/dev/sr` | 2 | `sr0`, `sr1` | SCSI CD |
| **`/nondev/`** | **7** | `dvdmenu` … `ipremote` | **pseudo-devices, no kernel node** |

Two things worth noting. `nflasha` runs to **31**, and the service audit had
only been able to account for a handful (`nflasha3`, `nflasha5`, `nflasha7`,
`nflasha10`–`nflasha25`); the full 32 explains why partitions kept appearing
that nothing in `im.elf`'s mount table referenced. And there is a
`nflasha` with no digit at all, as the base node.

The seven `/nondev/` entries are the more interesting group: `dvdmenu`,
`simulate`, `pcremote`, `air`, `streaming`, `iptc`, `ipremote`. These are
**media sources with no kernel device behind them** — a virtual DVD menu, a
simulator, PC-remote and IP-remote control, "air" (wireless/streaming source),
and IPTC/streaming. `pcremote` and `ipremote` are the remote-control
transports; `iptc` is the metadata path. `/nondev/` entries are how the
framework addresses a source that is not a block device, which is why the
`libIMDB` manifest can list them alongside real mounts.

## The id array — 16 ids, and it is not the plugins' namespace

    0x1000  0x1001  0x1006  0x1007  0x1200  0x1010  0x1002  0x1004
    0x4000  0x2000  0x4200  0x3001  0x4400  0x1005  0x4100  0x4300

`0x1001` is in it, which is what the search was for. But **`0x1022`, `0x102a`,
`0x81000` and `0x81003` — the other message ids recovered from the plugins —
are not.** So this is a *different* id space that happens to overlap, not the
registry the plugins draw from. Recorded as a partial result rather than a
resolution: the plugin message vocabulary is still unnamed.

The ids are grouped by the same prefixes `libSysDef.so` uses, which suggests
they are categories rather than messages: `0x1000`–`0x1200` matches
`CATEID_APP`…`CATEID_APP_WRAPPERS` territory, `0x2000` is where the pins start,
`0x3001` is in the object range, and `0x4000`/`0x4100`–`0x4400` is a fourth
group with no table entry at all. **A `0x4xxx` family exists and nothing names
it** — that is the new open question.

## Format notes and the trap

`VER:109` appears in all three `IMCFG` markers, so it is a constant in the
format string rather than a version of this block. Only the first marker is
followed by a device list; the other two are bare or differently shaped, and
the script says so rather than pretending the format is uniform.

The trap is in bounding the id array. The word after the last real id is the
first four bytes of the marker, and `IMCF` reads as `0x46434d49` — top nibble
4, so a loose "high nibble in 1,2,3,4,6,8" plausibility test accepts it. Two
guards were needed and the second only bit after the first was in place:

- reject the word if the bytes there really are `IMCF`
- `hi` after the forward walk is the first word that **failed**, so it is not
  part of the array. The backward walk leaves `lo` on the first *included*
  word, so the two ends are inconsistent and `(hi - lo)//4 + 1` includes the
  rejected word. The list came out at 17 entries with a 1.1-billion value in
  it before `hi` was stepped back.

Both fail silently: a wrong id list looks exactly like a right one, just with
an extra impossible entry.

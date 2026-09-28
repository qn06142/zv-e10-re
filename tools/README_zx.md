# zx -- ZV-E10 UX resource toolbelt

## The problem it solves

The camera's service shell **truncates commands at ~1022 characters** and wedges
the session on anything longer. Every operation therefore needed several round
trips, each an independent chance to fail. This project burned 20+ camera
sessions on that, lost two to wedging, and nearly wrote a corrupted palette file
that a staged-hash check happened to catch.

So the toolbelt lives on the SD card and every operation is one short command.

## Installing

From the PC, with the card in a reader:

```sh
cp tools/zx /f/RE_DUMP/tools/zx
```

From the camera's service shell:

```sh
cp /tmp_bt/sd/RE_DUMP/tools/zx /tmp_bt/zx
chmod +x /tmp_bt/zx
/tmp_bt/zx help
```

`/tmp_bt/sd` is the card mount point; if it differs, set `CARD=` in the
environment or edit the `CARD=` line at the top of the script.

## Commands

| | |
|---|---|
| `zx mount [rw\|ro]` | show or set the `/usr` mount state |
| `zx ls` | palette + shared resource listing and hash |
| `zx hash <path>...` | md5 of one or more files |
| `zx send <card-file> <remote> [chunk]` | stage a file as base64, print its hash |
| `zx decode <remote>` | base64 → `/tmp_bt/zx.out`, print hash for comparison |
| `zx put [remote]` | install `/tmp_bt/zx.out`, print resulting hash |
| `zx stock` | report the stock palette state |
| `zx diff <a> <b>` | byte compare |
| `zx dumpx <file>` | hex dump |
| `zx grep <pat> <file>...` | count matches |
| `zx card` | list the toolbelt on the card |
| `zx self` | show the installed script |

## The normal flow for a palette change

Split into two verified phases on purpose, because that is the discipline that
caught the near-miss corruption:

```sh
zx mount rw
zx send  /tmp_bt/sd/RE_DUMP/palette/color_cmn.MAGENTA.uxc \
         /usr/share/app/color_cmn.uxc
zx decode /usr/share/app/color_cmn.uxc     # <- compare hashes
zx put    /usr/share/app/color_cmn.uxc     # <- compare hashes again
# power-cycle the camera, observe
zx mount ro
```

Three hashes, and each is checked against the local one before proceeding. A
mismatch at any stage means stop.

## What the toolbelt deliberately does not do

- It does not remount anything by itself. `zx mount ro` is explicit.
- It does not write to `/system/av-cam.bin`, the display driver, or the VDF
  tables. The confirmed working change is a 4-byte palette edit; nothing here
  broadens the blast radius.
- It does not hand you a stock-restore constant it cannot verify. The stock
  palette is shipped as a real file on the card
  (`RE_DUMP/palette/color_cmn.STOCK.uxc`, md5 `f468bd3e72ca4e5b948a1c9f1f35c0a1`)
  rather than embedded base64, so restoring is a `send`/`put` away and is
  byte-exact by construction.
- It assumes no applets beyond the ones confirmed present: `busybox md5sum`,
  `busybox base64`, `busybox wc`, `busybox cmp`, `busybox od`, `busybox grep`,
  `cat`, `ls`, `mount`, `chmod`. No `head`, `tr`, `find`, `df`, `od` outside
  busybox, `strings` or `applet` — the last two wedge the camera.

## Palette builds shipped on the card

`RE_DUMP/palette/`:

| file | md5 | effect |
|---|---|---|
| `color_cmn.STOCK.uxc` | `f468bd3e72ca4e5b948a1c9f1f35c0a1` | camera original |
| `color_cmn.BLUE_BUILD.uxc` | `9474c2846a1a952179a2408018ff0295` | `0x400c` → blue, guides went **blue** |
| `color_cmn.MAGENTA_BUILD.uxc` | `c169428ea6ef0e924235164a0b33e528` | `0x400c` → magenta, guides went **magenta** |

Both non-stock builds are verified on hardware. The magenta build is the control
that proved the UI resolves colour through palette ids.

## Reconstructing the toolbelt on a new machine

The card holds everything needed:

```
RE_DUMP/
  palette/     the three verified palette builds
  tools/       zx
  usr.tgz      truncated; use a sequential tar reader, see docs
  nflasha*.img raw partitions; nflasha15 is /usr, color_cmn.uxc is inode 4299
  TREES/       extracted trees (root, etc, system, setting, lens, usr_share, usr_bin)
```

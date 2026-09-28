# The root filesystem is writable — the palette route is live

Answers open question 1 in `UI_RESOURCES.md`, which had been blocking the
whole approach and could previously only be settled by a live `mount` that
kept getting consumed by the USB wedge.

## Where the answer came from

`F:\RE_DUMP\` (the camera's SD card) holds the raw flash partitions. Rather
than burn a session on `mount`, the on-flash filesystem was inspected directly.

## nflasha15 is the root, and it is ext4 and writable

`nflasha15.img` (300 MB) has an ext superblock at the canonical offset:

```
superblock magic 0xef53  OK          (0x400 + 0x38, not a coincidence in
state 0x0001  clean                    compressed data)
block size          1024 bytes
blocks              242416  (236.7 MB)
free blocks         10957
free inodes         59700
inode size          128
feature_incompat    0x00000002        RECOVER
feature_ro_compat   0x00000003        DIRTY, COMPAT_HAS_JOURNAL
```

**`EXT4_FEATURE_INCOMPAT_RO_COMPAT` (0x1) is clear** — the filesystem was not
created read-only. 10,957 free blocks means there is room to write.

Only two partitions have a superblock at the genuine 0x438 offset: `nflasha15`
and `nflasha7`. `nflasha7` is 8 MB and cannot hold /usr/share (which is 41 MB
gzipped). `nflasha15` contains **251 uxc-container signatures and 2 literal
`color_cmn.uxc` strings** — it is the root.

The many other "magic" hits in the deep scan are false positives on compressed
data (`romfs`, `cramfs`, `squashfs` byte-swapped patterns appearing inside
other partitions' payloads at arbitrary offsets). Only the 0x438 placement is
diagnostic.

## The target file, located precisely

```
@0x0e47e618  inode 4299  rec_len 24  name_len 13  type 1  'color_cmn.uxc'
```

A well-formed ext4 directory entry: 24-byte record, 13-byte name, type 1
(regular file). Inode 4299 in a 128-byte-inode filesystem.

## Why this closes the question

`global.xdb` stores the image resources as **absolute paths** under
`/usr/share/app`, so the engine opens resources by full path rather than
searching a list of directories. That meant an SD-card copy of
`color_cmn.uxc` would probably never be read, and the whole plan hinged on
whether the root could be written.

It can. The route is:

1. write the patched 312-byte `color_cmn.uxc` into `/usr/share/app/`
2. the engine opens and parses it, as it always does
3. the palette changes, screens change with it

No firmware region, no `av-cam.bin`, no driver, no ioctl, no message id.

## Other findings from the card dump

### nflasha1 is vfat and mounted read-write by the updater

From `/usr/bin/up.sh`, pulled off the card:

```sh
mount -t vfat /dev/nflasha1 -o posix_attr,noatime,nodiratime,shortname=mixed /tmp_updater/upmnt
```

And `change_mode.sh` writes `/setting/mode/dmode` with plain `echo >`, so
**nflasha2 (= `/setting`) is definitively writable** — it is how the camera
changes its own boot mode. The user's earlier instruction to prefer the SD card
over `/setting` remains the right call for staging, since `/setting` holds boot
state.

### A second, simpler visible target: logo.bin

`/usr/share/startbinary/logo.bin` (8,532 B) is a **plain JFIF JPEG** — Sony's
startup logo, drawn on screen at boot. No container format to reverse. If the
palette route proves fiddly, replacing this is a one-file JPEG swap that is
trivially reversible and unambiguously ours.

### The boot chain, from etc/procs.txt and change_mode.sh

```
pid 1   launch_shell.elf
        kernel -> global infra -> LIRO boot -> appFw boot
        60+ threads named liro-kliro_*    <- the UI engine lives here
mode 3g /setting/mode/dmode              <- target gdb
mode 3s                                   <- gdbserver
mode 3p + PRELOAD_FILE                    <- LD_PRELOAD injection
```

`change_mode.sh` supports `echo 3s > /setting/mode/dmode` for a **gdbserver**
target and `3p` with `PRELOAD_FILE=/setting/mode/preload` for **LD_PRELOAD
injection**. Both are Sony's own supported debug entry points, on a writable
partition, and both are far less invasive than anything tried so far. Worth
keeping in mind as a fallback that needs no resource-format work at all.

### etc/app.txt is the authoritative resource manifest

The camera ships its own listing of `/usr/share/app` (6,818 bytes), naming
`color_cmn.uxc`, `global.xdb`, `style_cmn.uxc`, `style.uxb`, `lang.uxb`,
`fontlist.dat` and all ~290 screens. Useful for verifying the tree is complete
and for noticing a missing file. Note the manifest lists only the `_43`
(4:3) image variants, matching the on-device directory.

### The palette cross-reference, resolved

The earlier negative came from sampling five tiny boot screens. Against the full
291-screen set from the 2025 dump:

- **197 of 291 files reference the 0x4000-range palette ids, 2,245 clean hits**
- `master_camera.uxc` and `viewPanoramaStl.uxc` carry them inside a repeating
  widget record
- the `string_*_f.uxc` hits are coincidental (ascending u16 offset tables) and
  are excluded

So the palette is genuinely consumed. The negative was a sampling artefact, and
that correction is now on the record.

`uxc_widget_rec.py` could not pin the colour field's exact offset: the records
are TLV chains (`1f 02 80 55 02 08 00`, `1b 57 22 04 01 0e 08`), not a fixed
stride, and the dominant 60-byte period yields only a 1%-dense slot. That is
fine — the patch does not need the widget layout, only the palette file.

## Final patch target: blue (0x4009)

Sony's palette in `color_cmn.uxc` is entirely warm — white, five alphas of
black, three greys, orange (`0x4010`/`0x4011`), yellow (`0x4013`), and red
(`0x4007`) for record and warning states. **Nothing needs a saturated blue.**
That makes `0x4009` the best target on both counts: it appears wherever a blue
accent would, and a garish blue cannot be read as a factory state, a warning,
or a fault.

`0x4007` (red) was explicitly rejected: Sony uses red for record and warning
states, so recolouring it would read as an error condition rather than as our
work — the opposite of the intent.

```
blue    id 0x4009  00 00 dd ff -> 00 ff ff ff   @ 0x00a4..0x00a7
grey33  id 0x400c  33 33 33 80 -> 00 00 dd 80   @ 0x00bc..0x00bf

length unchanged: 312 bytes
5 byte(s) changed, all inside rgba quads -- no id or const touched
patched file re-parses: 28 records, all ids and consts intact

out:     sha256 ad5e093ba1b00f2ffba1bb07c61df4beb29efdd030ac59eba8575d0d92c4d46c
restore: sha256 0bcce3983df45ac38e888f556e4f359c06e51ff8550e5e69b239d7b486dc485b
```

`0x400c` is the translucent dark grey used in panel shading. Included because it
is the one entry that can shift a *large* screen area rather than a small
accent, so the effect shows even on a screen with no blue accent. It is a
subtle shift; if a strict single-quad patch is wanted, drop it and the file
still round-trips.

Five bytes total. That is the deliberate choice: the engine parses this file
normally, so the less that changes, the more clearly any visible change is
attributable to us rather than to collateral damage.

## CORRECTION: `/usr` is mounted read-only

The live mount table settles the open question, and it goes against the palette
route:

```
/dev/nflasha7  /    ext2 ro,relatime,errors=continue 0 0
/dev/nflasha15 /usr ext2 ro,relatime,errors=continue 0 0
```

`/usr/share/app` is on a **read-only mount**, so `color_cmn.uxc` cannot be
written at runtime.

### Why the offline analysis missed it

`nflasha15_super.py` read the ext superblock and found
`EXT4_FEATURE_INCOMPAT_RO_COMPAT` clear, concluding "the filesystem supports
write... the necessary condition is met." That was accurate about what it
measured and misleading about what it implied.

The superblock feature flags describe **what the filesystem format can do**.
The mount option describes **what the kernel did**. Only the second decides
whether a write lands. The script did flag the mount as an outstanding unknown,
but the framing ("necessary condition is met", "one `mount` command away") made
it read as closer to working than it was.

The kernel reports the filesystem as **ext2, not ext4** — no journal, which is
the old-style ext2 that gets mounted read-only. That detail was available in
the superblock output and should have been read as the warning it was.

The decoded format, the verified 5-byte patch, and inode 4299 all remain correct
and useful for a reflash. What does not survive is the idea of writing the file
on a running camera.

### Staging on the card would not have helped either

`global.xdb` stores image resources as absolute `/usr/share/app` paths, so the
engine opens them by full path rather than searching a directory list. A
patched `color_cmn.uxc` on the SD card would simply never be read.

## The writable space that does exist

```
/dev/nflasha10 /tmp      vfat rw    12 MB
/dev/nflasha10 /etc      vfat rw    12 MB
/dev/nflasha3  /system   vfat rw    48 MB
/dev/nflasha2  /setting  vfat rw    20 MB
/dev/nflasha18 /lens     vfat rw    20 MB
/dev/nflasha12 /cert     vfat rw    40 MB
/dev/nflasha11 /log      vfat rw   500 MB
```

The camera plainly has a partition-write path: `up.sh` mounts nflasha1 vfat
read-write and writes to it, and `change_mode.sh` writes `/setting/mode/dmode`
to change the boot mode.

## Options, assessed

| | option | assessment |
|---|--------|------------|
| A | remount `/usr` rw | **Not advised.** ext2 with no journal, entire UI on it, and a write fault leaves the camera unbootable. The one option that can brick the device. |
| B | reflash nflasha15 | Viable. Full 300 MB image on the card, 5-byte patch, exact restore. Single-partition file edit. Needs a working partition-write path. |
| C | bind/overlay mount | Needs privileges the service shell may not have, and would not survive a reboot. |
| D | LD_PRELOAD / gdbserver | Lowest device risk, off writable `/setting`, but means writing and debugging our own `.so` — back to the hard problem rather than a clean resource edit. |
| E | `logo.bin` swap | Same read-only problem: it is on `/usr` too. |

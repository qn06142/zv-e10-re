# 07 — Modifying the camera: writable space, applied changes, the updater door

What can be written, what has been written, and the one operation that can cost
the shell. Consolidates `_merge-rootfs`, `_merge-updater`, `_merge-iconfont`,
`FLASHED_DEVICEINFO_VERSION`, `FLASHED_STRING_TABLE`.

## The mount table

```
/dev/nflasha7  /    ext2 ro,relatime,errors=continue 0 0
/dev/nflasha15 /usr ext2 ro,relatime,errors=continue 0 0
/dev/nflasha10 /tmp      vfat rw    12 MB
/dev/nflasha10 /etc      vfat rw    12 MB
/dev/nflasha3  /system   vfat rw    48 MB
/dev/nflasha2  /setting  vfat rw    20 MB
/dev/nflasha18 /lens     vfat rw    20 MB
/dev/nflasha12 /cert     vfat rw    40 MB
/dev/nflasha11 /log      vfat rw   500 MB
```

**`/usr` is ext2, not squashfs**, and `mount -o remount,rw /usr` **succeeds**.
This was verified by writing `/usr/bin/_wtest2` and reading it back.

A prior note recorded `/usr/bin` as "READ-ONLY squashfs in service mode"
(`touch /usr/bin/_wtest: Read-only file system`). **That is stale.** It was
presumably observed when the service environment mounted `/usr` differently. It
should be re-verified rather than inherited.

> **Correction of record.** An offline superblock read found
> `EXT4_FEATURE_INCOMPAT_RO_COMPAT` clear and concluded "the filesystem supports
> write, the necessary condition is met." Superblock feature flags describe what
> the format **can** do; the mount option describes what the kernel **did**. Only
> the second decides whether a write lands. The kernel also reports the
> filesystem as **ext2, not ext4** — no journal — which was in the superblock
> output and should have been read as the warning it was.

### What is and is not wiped at boot

| path | survives power cycle |
|---|---|
| `/usr/bin` | **yes** — `/usr/bin/_marker3` persisted |
| `/usr/share` | **yes** — `/usr/share/_marker4`, `/usr/share/pmbp/_marker2` persisted |
| `/usr/share/app` | **no** — wiped |

The wipe is specific to `/usr/share/app`, which is where the main firmware
rewrites its UI resources. It is **not** a property of `/usr` as a whole.

### Filesystem facts, for a reflash

`nflasha15.img` (300 MB), ext superblock at the canonical `0x400 + 0x38`:

```
magic 0xef53 OK      state 0x0001 clean
block size           1024 bytes
blocks               242416 (236.7 MB)
free blocks          10957
free inodes          59700
inode size           128
feature_incompat     0x00000002   RECOVER
feature_ro_compat    0x00000003   DIRTY, COMPAT_HAS_JOURNAL
```

Only two partitions have a superblock at the genuine `0x438` offset:
`nflasha15` and `nflasha7`. `nflasha7` is 8 MB and cannot hold `/usr/share`
(41 MB gzipped). `nflasha15` contains **251 uxc-container signatures and 2
literal `color_cmn.uxc` strings** — it is the root. The many other magic hits in
a deep scan are false positives on compressed data; only the `0x438` placement is
diagnostic.

`color_cmn.uxc` located precisely:

```
@0x0e47e618  inode 4299  rec_len 24  name_len 13  type 1  'color_cmn.uxc'
```

## The updater is a code-execution door

`crypter.elf`'s `.rodata` literals, in order, give the whole flow:

```
le.cpp
/tmp_updater/updater
/tmp_updater/updater/bodyimg
/usr/bin/udtrbody.bin
/root/IAMUPDATER
/tmp_updater/updater/bodyfs
/tmp_updater/updater/bodyfs/bodylib/libupdaterbody.so
```

Read `/usr/bin/udtrbody.bin`, extract to `/tmp_updater/updater/bodyfs/`,
`dlopen` the `bodylib/libupdaterbody.so` inside it, `dlsym` one symbol, call it.
Body header magic is `0100UDTRFIRM`; the body itself is Compressed ROMFS
(magic `453dcd28`).

`/usr/bin/udtrbody.bin` is present and writable:

```
-rw-r--r-- 1 57285 1000 143360 Mar 14  2025 /usr/bin/udtrbody.bin
-r-xr-xr-x 1 57285 1000  39084 Mar 14  2025 /usr/bin/crypter.elf
```

**The symbol name does not have to be reverse-engineered.** There are exactly
two plain, unmangled C identifiers in `crypter.elf` — `Dec_ScrambleInit`
(`0x1d7f`) and `Fsys_Init` (`0x1e12`, `0x67eb`) — which is what a `GetSymbol()`
argument looks like. A replacement library can export **both** names and
whichever is looked up resolves. `Updater::DllHandler::Open(char const*, int)`
and `Updater::DllHandler::GetSymbol(char const*)` are present as mangled symbols,
confirming the mechanism.

### Why this is the one-way door

The `dlopen` happens inside `crypter.elf`, **before any script runs**. So the
code execution does not depend on the update proceeding.

```
startupdate.sh exits immediately unless /root/IAMUPDATER exists
/root is read-only, so that flag is created by the real update flow
=> the update cannot be driven from the service shell
```

**But if the replacement `libupdaterbody.so` is malformed, `im.elf` will not
start, the service shell never returns, and the only recovery is the SD card.**
That is the standing reason this is not attempted unilaterally.

The `libIMDB.so` → `im.elf` route has the same shape and the same risk.

Mitigations that do exist: the stock `udtrbody.bin` is in three local copies
plus the SD card; the updater runs on the service CPU, isolated from the main
firmware; `crypter.elf` can be invoked by hand so no reboot is needed to try it,
and a wedged process can be killed.

Not mitigated: if the write succeeds and crypter then wedges the service side in
a way that prevents a normal remount, recovery is "restore the stock body",
which itself needs the shell.

### Body tooling

No `arm-linux-gnueabi-gcc`, but the venv can hand-build the library:

| package | version | use |
|---|---|---|
| `keystone-engine` | 0.9.2 | ARM assembler |
| `capstone` | 5.0.9 | disassembler, for verification |
| `pyelftools` | 0.33 | emit the `.so` |
| `unicorn` | 2.1.4 | test the emitted ARM code before it runs |

`udtrbody_extract/` already holds an extracted copy including the stock
`bodylib/libupdaterbody.so` (106,156 B) and the whole updater toolkit, so a
packer can be written against a known-good round trip. The integrity check is
`CrcChecker` / `uc_crc32sum.elf` — **CRC, which is forgeable, not a signature.**

## Changes that have been applied and verified on the device

Three, each verified by whole-file md5 on the camera, not inferred. In every
case `/usr` was remounted rw, the file written, and `/usr` remounted ro again.

### 1. `DeviceInfo.xml` — version strings

`/usr/share/pmbp/DeviceInfo.xml`, a 517-byte Apple-plist XML with CRLF endings,
delivered in a single command.

```xml
<key>Version</key>   <string>1.3.00.19200</string>  ->  9.9.99.99999
<key>version</key>   <string>1.0.00</string>         ->  9.9.99
```

| | |
|---|---|
| original | `325881bdde84eb36d006ba13efb54eb5` · 517 B |
| patched | `9b2d8cc0f59d9b82c69e1f8e2478e545` · 517 B |
| changed | 12 bytes, length identical |

**Never seen on screen.** If the Version screen still shows the old values, the
file is read by something that was not reloaded, or not by the path that draws
the screen.

### 2. `string_english_f.uxc` — `Playback` → `OPENCODE`

`/usr/share/app/string_english_f.uxc`, 349,020 bytes. Same-length in-place
substitution, because replacing N bytes with N bytes cannot move an offset,
change an entry count, or touch the container index.

```
@0x041bac rec / 0x041bb0 text  id 0xb547
@0x0476d8 rec / 0x0476dc text  id 0xb740
@0x04cbbc rec / 0x04cbc0 text  id 0xb976
```

| | |
|---|---|
| before | `349711603d2e16c1fc620e4e8bf30be0`, 349,020 B |
| after | `9853d47ad4197d3387f10babdc8728b9`, 349,020 B |
| changed | 24 bytes |

Three independent methods produced that target hash before anything was
written: a direct byte patch, `sed` with a backreference, and line-addressed
`sed`. An 8-byte slice at `0x041bb0` md5s to `04fbbbde1afb0c4bafde6ba5ce069ac6`,
which is md5 of `OPENCODE` and not of `Playback` (`8dc55bfc…`).

**Unquantified side effects, stated not hidden:**

- Only takes effect if the camera is set to **English**.
- `Playback` occurs 3 times, so all three labels change, not one.
- The other 67 language files are untouched, so switching language shows the
  original.
- **Unknown whether the engine measures text width before drawing.** Equal
  length in a proportional font can still occupy a different pixel width, which
  could shift a right-aligned or centred label. The palette edit had no such
  question because it changed colour, not content.

**Never seen on screen.**

### 3. `Sony_DI_Icons.ttf` — 138 glyph outlines replaced

`/usr/share/app/Sony_DI_Icons.ttf`, registered by `fontlist.dat` as
`FONT_ICONS`. Every character of a label cycles through **OPX**; Sony's
horizontal rules are kept byte-for-byte.

```
STD          -> OPX          1080/60p     -> OPXO/PXO
60           -> OP           16:9         -> OP:X
100          -> OPX          XAVC S       -> OPXO P
STEADYSHOT   -> OPXOPXOPXO   1/128ND      -> O/PXOPX
```

Digits are replaced too, deliberately: preserving them would have left seven of
the twenty-seven barred labels — 60, 50, 35, 25, 100, 16, 30 — completely
unchanged, since those labels are nothing but figures.

Families: 27 barred image-size labels, 17 recording formats, 3 codec, 1
SteadyShot, 28 ND-filter, 4 sensitivity, 14 megapixel, 14 image format, 13
colour (including the picture profile names `CLASSIC`…`FOREST`), 6 focus, 8
shooting assists.

| | |
|---|---|
| original | 619,664 B, md5 `1dffdb46352f91c7b484a4b75cf1905f` |
| patched | 614,336 B, md5 `b1e5d23e9d69b269b785b9155688f351` |
| glyphs | 1732 → 1732 |
| cmap | 1,684 entries, identical |
| advance widths moved | 0 |
| glyphs outside int16 | 0 |
| non-target glyphs byte-identical | 1594 of 1594 |

The font has no checksum table, no key table and no unknown addressing scheme —
the first target in this project where that is true, and the reason a 619 KB
file was a reasonable thing to attempt.

**Never seen on screen.** This is the highest-information negative available: if
the OPX labels appear, `/usr/share/app` is live and readable and the path was
never the problem (the `.uxc` loader would be). If they do not appear, the whole
directory is being served from elsewhere — which is the more interesting result.

Restore: copy the stock file back to `/tmp/sd/Sony_DI_Icons.STOCK.ttf`, remount
`/usr` rw, `cp` it into place, verify md5 `1dffdb46…`.

### 4. The palette — worked, then was reverted

`color_cmn.uxc` palette id `0x400c`, `333333`@80a → `0000dd`@80a, changed the
live-view framing guides from grey to blue. Then `ff00ff`@80a made the guides
**magenta**, which is the control that settles the mechanism (see
[05-formats.md](05-formats.md)): magenta appears nowhere in Sony's palette, so
nothing but entry `0x400c` can explain it.

The staging pipeline, every stage hash-verified on the camera:

| stage | md5 | size |
|---|---|---:|
| baseline (matched the card copy exactly) | `f468bd3e72ca4e5b948a1c9f1f35c0a1` | 312 B |
| staged on the card, verified before writing | `9474c2846a1a952179a2408018ff0295` | 312 B |
| after `remount,rw /usr` and write, read back | `9474c2846a1a952179a2408018ff0295` | 312 B |
| after `rm`, still intact | `9474c2846a1a952179a2408018ff0295` | 312 B |

```
remount  /dev/nflasha15 /usr ext2 rw,relatime,errors=continue
```

What this proves end to end: the `.uxc` container is decoded, the engine re-reads
`color_cmn.uxc` at boot, the palette ids resolve against it, and a 5-byte edit to
a 312-byte file on a filesystem mounted `ro` changed what the camera draws on its
LCD. No patched firmware, no `av-cam.bin`, no ioctl struct, no message id, no
driver — the engine opened a file it already opens, and was supplied different
bytes in a format it already parses.

That the file was written at all contradicts the `ro` mount above — the palette
was staged on the card and `cp`'d in after a remount, and `/usr/share/app` is
listed as boot-wiped, so the edit does not survive a power cycle. **Treat the
palette as a proven mechanism, not a persistent change.**

The UI resources themselves came off the camera in one tar,
`/tmp_bt/ui.tar` (30,720 B, md5 `529b5ec9f4a210f37d0c7ac46c1cf253`), which
completed and verified before the session wedged.

### 5. `libtestcmd.so` — code execution, then reverted

A 66-byte Thumb-2 raw-`svc` payload injected into
`cmdline_show_revision` in `libtestcmd.so`. A `/tmp/ox` file containing `OPX`
appeared, which is arbitrary code running as root.

Restored to stock md5 `f370de888ae662e7f509f2274846eac6`, mode
`-r-xr-xr-x 1 57285 1000`. Payload builder: `research/firmware/opx_payload.py`.

`libtestcmd.so` was used rather than `libIMDB.so` **precisely to avoid the
one-way door** — `libtestcmd.so` is not linked by `im.elf`, so a malformed
library cannot stop the application from starting.

## The transport that carries large files

Commands on this link are bounded at about **1,022 characters**; a 4,000-char
command is accepted and **silently discarded**. The icon font base64-encodes to
819,120 characters, so as commands it would need some 800 of them, each a
chance for the link to drop.

The terminal is a pty, so it has a stdin, and **stdin is not length-limited**:

```
/tmp/sd/tools/busybox-armel stty -echo
/tmp/sd/tools/busybox-armel base64 -d > /tmp/sd/Sony_DI_Icons.OPX.ttf.xz
<355,344 characters of base64, wrapped at 76 columns>
Ctrl-D
/tmp/sd/tools/busybox-armel xz -d -k -f .../Sony_DI_Icons.OPX.ttf.xz
/tmp/sd/tools/busybox-armel md5sum .../Sony_DI_Icons.OPX.ttf
```

`xz` takes the font to 43.4%. Proven on a 512-byte payload and then a 3,000-byte
one, both md5-exact, before the font was attempted.

### Five things that have to be right

**The card must be mounted by hand.** `/tmp/sd` is absent; the camera does not
mount it on this path by itself.

```
mkdir -p /tmp/sd; mount /dev/mmca1 /tmp/sd
```

`/proc/partitions` calls the card `mmca10p1` and the device node is
`/dev/mmca1`. `/dev/mmcca1` is a different controller and does not work.

**The camera's own shell has almost nothing.** It is BusyBox 1.34.1 ash, built
without `base64`, `stty`, `md5sum`, `df`, `tr`, `head` or `which`. Everything
used for the transfer comes from the toolbelt on the card,
`/tmp/sd/tools/busybox-armel`, which has all of it. `/tmp/busybox` looks like a
busybox and is a **zero-byte file**.

> An early attempt ran `base64 -d > file`, got *not found*, and then typed 446
> base64 characters at a live prompt, where they were **executed as shell
> commands**.

**Echo has to be turned off first.** A pty echoes what it is sent, and 355 KB of
echoed base64 fills the device's *output* buffer and wedges the link in the
opposite direction to the one being avoided.

**Nothing can be checked while the decoder is running.** The shell is blocked
inside `base64 -d`, so any command typed in that window is consumed as payload.
An intermediate version ran `ls -l` to prove the decoder had started and
corrupted its own file with the reply. The probe and the md5 afterwards are the
checks; there is no check *during*.

**`drain()` returned `None`.** It read and discarded, then fell off the end. Every
reply was invisible, so the script reported "no md5" and concluded the transfer
had failed — when the identical payload verified exactly when the same loop was
written to accumulate. Three consecutive "failures" were this one bug. **A
function that silently drops the evidence is worse than the bug it hides.**

### Other transport facts

- `busybox <applet>` must be used explicitly for `md5sum` / `tail` / `dd`.
  `xxd` / `tr` / `head` / `wc` are listed but **not linked**.
- `busybox xxd -r -p` is unusable: 132 hex characters produced 30 bytes.
- To write arbitrary bytes, use `printf '\200\265...'` (octal) with
  `busybox tail -c +N` for the offset. **Base64 chunks must be generated
  programmatically**, never hand-typed — a single mistyped character once
  decoded to `0000` at offsets `0xa5`/`0xa6`, which are the *id field of the
  next record*, not a colour. The pre-write md5 comparison caught it; the file
  was never written in that state.
- `dd` on this busybox has **no `conv=notrunc`**, so any `dd of=<live file>`
  truncates the target to the write offset. **Use `cp`.**
- Hash the staged file **on the camera before** writing it, not after.

## Boot-mode debug hooks

`change_mode.sh` supports:

```
echo 3g > /setting/mode/dmode                 # target gdb
echo 3s > /setting/mode/dmode                 # gdbserver
mode 3p + PRELOAD_FILE=/setting/mode/preload  # LD_PRELOAD injection
```

Both gdbserver and `LD_PRELOAD` are Sony's **own** supported debug entry points,
on a writable partition, and both are far less invasive than anything else here.
`BOOTMODE=NORM` with no `/setting/sen/smode`, no `dmode` and no kernel flag is
the observed default — the application is not loaded in that state, and why is
unexplained.

## Other writable targets

| target | note |
|---|---|
| `/usr/share/startbinary/logo.bin` | 8,532 B, a **plain JFIF JPEG**. Sony's startup logo, drawn at boot. No container to reverse; a one-file swap, trivially reversible and unambiguously ours. It is on `/usr`, so it needs the same remount. |
| `/usr/bin/udtrbody.bin` | 143,360 B Compressed ROMFS. The updater door above. |
| `/etc/app.txt` | 6,818 B, the camera's own manifest of `/usr/share/app` (names `color_cmn.uxc`, `global.xdb`, `style_cmn.uxc`, `style.uxb`, `lang.uxb`, `fontlist.dat` and all ~290 screens). Lists only the `_43` (4:3) image variants. Useful for verifying the tree is complete. |
| `/lens/VX<id>_lensfile.bin` | per-lens ISP calibration table. `LF` magic, version, `lens_id` @+14, `ED` block of int16 coefficient sections. |
| `/setting` (nflasha2) | definitively writable — it is how the camera changes its own boot mode. Holds boot state, so prefer the SD card for staging. |

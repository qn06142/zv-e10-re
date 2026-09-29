# Flashing the icon font, and the transport that finally worked

## What is being changed

`/usr/share/app/Sony_DI_Icons.ttf`, the camera's icon font, registered by
`fontlist.dat` as `FONT_ICONS`. 138 of its 1,732 glyphs have their outlines
replaced. Everything else in the file is untouched.

| | |
|---|---|
| original | 619,664 bytes, md5 `1dffdb46352f91c7b484a4b75cf1905f` |
| patched | 614,336 bytes, md5 `b1e5d23e9d69b269b785b9155688f351` |
| glyphs | 1732 → 1732 |
| cmap | 1,684 entries, identical |
| advance widths moved | 0 |
| glyphs outside int16 | 0 |
| non-target glyphs byte-identical | 1594 of 1594 |

Only outlines change. The font has no checksum table, no key table and no
unknown addressing scheme, which is the first target in this project where that
is true — and the reason a 619 KB file was a reasonable thing to attempt.

## The labels

Every character of a label cycles through **OPX**; Sony's horizontal rules are
kept byte-for-byte, and separators are drawn rather than preserved.

    STD          -> OPX          1080/60p     -> OPXO/PXO
    60           -> OP           16:9         -> OP:X
    100          -> OPX          XAVC S       -> OPXO P
    STEADYSHOT   -> OPXOPXOPXO   1/128ND      -> O/PXOPX

Digits are replaced too, deliberately: preserving them would have left seven of
the twenty-seven barred labels — 60, 50, 35, 25, 100, 16 and 30 — completely
unchanged, since those labels are nothing but figures.

Families: 27 barred image-size labels, 17 recording formats, 3 codec, 1
SteadyShot, 28 ND-filter, 4 sensitivity, 14 megapixel, 14 image format, 13
colour (including the picture profile names `CLASSIC`…`FOREST`), 6 focus, 8
shooting assists.

## Transport: streaming base64 into the terminal's stdin

Commands on this link are bounded at about 1,022 characters, and a 4,000-char
command is accepted and silently discarded. The font base64-encodes to 819,120
characters, so as commands it would need some 800 of them, each a chance for the
link to drop. The string table avoided this only because a copy was already on
the card; the bytes still had to cross the wire once.

The terminal is a pty, so it has a stdin, and **stdin is not length-limited**:

    /tmp/sd/tools/busybox-armel stty -echo
    /tmp/sd/tools/busybox-armel base64 -d > /tmp/sd/Sony_DI_Icons.OPX.ttf.xz
    <355,344 characters of base64, wrapped at 76 columns>
    Ctrl-D
    /tmp/sd/tools/busybox-armel xz -d -k -f .../Sony_DI_Icons.OPX.ttf.xz
    /tmp/sd/tools/busybox-armel md5sum .../Sony_DI_Icons.OPX.ttf

`xz` takes the font to 43.4%, so the stream is 355,344 characters rather than
819,120. Proven on a 512-byte payload and then a 3,000-byte one, both md5-exact,
before the font was attempted.

### Five things that had to be got right

**The card has to be mounted by hand.** `/tmp/sd` was absent; the camera does not
mount it on this path by itself. `mkdir -p /tmp/sd; mount /dev/mmca1 /tmp/sd`
works. `/proc/partitions` calls the card `mmca10p1` and the device node is
`/dev/mmca1`; `/dev/mmcca1` is a different controller and does not work.

**The camera's own shell has almost nothing.** It is BusyBox 1.34.1 ash, built
without `base64`, `stty`, `md5sum`, `df`, `tr`, `head` or `which`. The first
attempt ran `base64 -d > file`, got *not found*, and then typed 446 base64
characters at a live prompt — where they were **executed as shell commands**.
Everything used for the transfer comes from the toolbelt on the card,
`/tmp/sd/tools/busybox-armel`, which does have all of it. `/tmp/busybox` looks
like a busybox and is a zero-byte file.

**Echo has to be turned off first.** A pty echoes what it is sent, and 355 KB of
echoed base64 fills the device's *output* buffer and wedges the link in the
opposite direction to the one being avoided.

**Nothing can be checked while the decoder is running.** The shell is blocked
inside `base64 -d`, so any command typed in that window is consumed as payload.
An intermediate version ran `ls -l` to prove the decoder had started and
corrupted its own file with the reply. The probe and the md5 afterwards are the
checks; there is no check *during*.

**`drain()` returned `None`.** It read and discarded, then fell off the end.
Every reply was therefore invisible, and the script reported "no md5" and
concluded the transfer had failed — when the identical payload verified exactly
when the same loop was written to accumulate, in `diag_stream.py`. Three
consecutive "failures" were this one bug. A function that silently drops the
evidence is worse than the bug it hides.

## Restoring

    /tmp/sd/tools/busybox-armel cp /usr/share/app/Sony_DI_Icons.ttf \
        /tmp/sd/Sony_DI_Icons.STOCK.ttf
    # remount /usr rw, then restore, then verify md5 1dffdb46...

Note `dd` on this busybox has no `conv=notrunc`, so any `dd of=<live file>`
truncates the target to the write offset. Use `cp`.

## What this also tests

`OPENCODE` in the string table and `9.9.99.99999` in `DeviceInfo.xml` are both
hash-verified on the camera but **have never been seen on screen**. If the OPX
labels appear, then `/usr/share/app` is live and readable, which would mean the
path was never the problem and the `.uxc` loader is. If they do not appear, that
is the more interesting result and says the whole directory is being served from
elsewhere.

# Result: the camera's UI palette is ours

**2026-09-28. The live-view framing guide lines changed from grey/white to blue.**

This is the first visible, unmistakably-ours effect produced on the ZV-E10
without patching firmware and without touching the display driver.

## What was done

Five bytes, in a 312-byte file:

```
id 0x4009  0000dd ff  ->  00ffff ff    blue      -> full cyan
id 0x400c  333333 80  ->  0000dd 80    grey 50%  -> translucent blue
```

Written to `/usr/share/app/color_cmn.uxc`, which required remounting the root:

```
baseline   f468bd3e72ca4e5b948a1c9f1f35c0a1   matched the card copy exactly
remount    /dev/nflasha15 /usr ext2 rw,relatime,errors=continue
staged     9474c2846a1a952179a2408018ff0295   312 B, verified before writing
write      9474c2846a1a952179a2408018ff0295   read back = matches
cleanup    9474c2846a1a952179a2408018ff0295   still intact after rm
```

## Why this is the right approach

The UI is resource-driven. The camera's own boot process opens
`/usr/share/app/color_cmn.uxc` and parses it into a colour table, and screen
files reference entries from that table by id. Recolouring an entry changes what
the camera draws, using the engine's own code path, with:

- no patched firmware (`/system/av-cam.bin` never written)
- no ioctl struct to recover
- no display-driver poking — the descriptor-driven display stack was never
  touched
- no message id, no VDF vtable, no uipc traffic
- no crash, and an exact byte-for-byte rollback

Five bytes in a file the firmware already reads.

## The route that got here

Worth recording, because most of it was wrong turns that narrowed the problem:

1. **Framebuffer hunt** — closed. No CPU-visible framebuffer; the display is
   descriptor-driven (APL/AIC + XDMAC + HME) and DMA-fed. 4 positive-controlled
   negatives.
2. **`/dev/ldec` ioctl** — abandoned. The driver dispatches on small ints
   (cmd 1 → `-EIO`, cmd 2 → `-EFAULT`) but the struct was unrecoverable: no
   `/dev/mem` at page granularity, no `/proc/ldec`, `pagemap` all zeros, and
   `ldec` turned out to be built into the kernel with no `.ko` on disk.
3. **VDF panel commands** — resolved by name (`SetPanelBrightness::Execute` =
   `0x00150BA8`) but uncallable; needs live interface objects and subsystem
   vtable slots `0x44c`–`0x858`.
4. **uipc / `testcmd.elf`** — the message interface fully decoded offline, but
   display command ids were never found, so the bus route went no further.
5. **The filesystem** — where the answer was. `/usr/share/app` is ~290 `.uxc`
   resources; `color_cmn.uxc` is 312 bytes of named colours and is loaded by the
   engine itself.

Step 5 is the lesson: the display was never the thing to attack. The thing that
draws *to* the display was, and it reads a file.

## Decoding notes worth keeping

### The container

```
0x00  3 bytes  magic 'uxc'
0x03  u8       format version (7)
0x08  u16      stream version (8 for .uxc, 9 for .uxb/.uxa)
0x0A  u16      file-specific, not a checksum
0x0C  u16      high-water id (0x4023 = one past the last)
0x0E  u16[]    sparse id->slot index, 0xffff = absent
0x58          28 records of exactly 8 bytes
```

Record: `u16 id` (0x4000..0x4022) | `u16 const 0x3a09` | `u8 r,g,b,a`.

### Two decoding errors worth not repeating

**A round-trip test that cannot fail.** `uxc_color.py` printed "BYTE-EXACT
MATCH -- container decoded". That test parses into records, re-packs the same
fields, and re-concatenates the untouched prefix — the exact inverse of the
parse. It returns the input for *any* stride that divides the body evenly. It
proves the codec loses nothing; it does not prove the field boundaries are right.
The real evidence is circumstantial but mutually reinforcing: the u16 at +0
steps 0x4000…0x4022 at exactly stride 8, `0x4023` sits one past the last, and
the bytes at +4..+7 are the only plausible UI colours in the file.

**A negative from a sample too small to be informative.** Scanning five tiny
boot screens found no palette ids, and I nearly called the approach dead. The
full 291-screen set shows **197 files referencing the ids, 2,245 clean hits**.
The earlier negative was a sampling artefact, not a result.

Also: the `string_*_f.uxc` hits are coincidental — those files are ascending u16
offset tables, and any `40 xx` byte pair in a run of offsets decodes as a
"palette id". They are excluded from the count.

### The filesystem

`/usr` is **ext2, mounted `ro`**. The superblock's `RO_COMPAT` flag being clear
says the *format* permits writes; the mount option says what the *kernel* did.
Only the second decides. I initially over-read the superblock analysis as
nearer to working than it was — the kernel reporting plain `ext2` with no
journal was in my own output and should have been read as the warning it was.

An in-place fixed-size write turned out to be the safe case, not the risky one:
no allocation, no metadata walk, single-sector overwrite. The real risk was
never the filesystem — it was that we had no proven recovery path.

## Rollback

```
/usr/share/app/color_cmn.restore.uxc
  md5    0bcce3983df45ac38e888f556e4f359c06e51ff8550e5e69b239d7b486dc485b
  sha256 0bcce3983df45ac38e888f556e4f359c06e51ff8550e5e69b239d7b486dc485b
```

Byte-identical to the camera's original, recovered from the card's
`RE_DUMP` copy. Same procedure: remount, write, verify. Takes under a minute.

## What this opens up

The palette is one file among ~290. The same remount-and-write applies to any
`.uxc` resource, and the container format is now known:

- `color_cmn.uxc` (312 B) — palette, **done**
- `style_cmn.uxc` (1,888 B) — style/attribute set
- `global.xdb` (12,252 B) — resource directory, holds absolute `/usr/share/app`
  paths and the `_43`/`_169` model pairings
- `logo.bin` (8,532 B) — the startup logo, a **plain JFIF JPEG**; swapping it
  needs no format knowledge at all
- `view*.uxc` — ~290 screens, TLV records, layout not yet decoded

The `_43` / `_169` split in `global.xdb` suggests model-gated resources, and
`image_cmn_169.uxc` is referenced but absent from the on-device directory —
worth checking whether the 16:9 set is elsewhere or model-gated.

## The staging lesson

The user directed us off `/setting` and onto the SD card early on, to avoid
risking the boot-state partition. That was the right instinct and it held: the
palette work needed neither. The card supplied the full 300 MB `nflasha15`
image, the `usr_share.tgz` with all 299 screens, `etc/app.txt`, and
`change_mode.sh` — and the answer came from reading the filesystem rather than
from poking the device.
